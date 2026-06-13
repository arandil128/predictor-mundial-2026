"""Ajuste del modelo de goles Dixon-Coles (ataque/defensa) por máxima verosimilitud.

Núcleo matemático compartido por `scripts/calibrate.py` (produce los parámetros de
producción) y `scripts/backtest.py` (validación out-of-sample). Mantenerlo en un
solo lugar garantiza que se valida exactamente el mismo modelo que se despliega.

Modelo:
    log λ_local = μ + ventaja·(1 si no es neutral) + ataque[L] − defensa[V]
    log λ_visit = μ +                                ataque[V] − defensa[L]

Ataque/defensa independientes ⇒ los goles totales dependen del cruce (a diferencia
de un rating único tipo Elo, que fija el producto λ_local·λ_visit).
"""
from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from datetime import date, datetime

import numpy as np
from scipy.optimize import minimize, minimize_scalar

from app.services.ratings import _normalize


def competition_weight(tournament: str) -> float:
    """Peso por importancia del torneo (los partidos 'de verdad' pesan más)."""
    t = tournament.lower()
    if "friendly" in t:
        return 0.5
    if "world cup" in t:
        return 1.0 if "qualification" not in t else 0.85
    if "confederations" in t:
        return 0.9
    if "nations league" in t:
        return 0.8
    continental = ("euro", "copa am", "african", "asian cup", "gold cup", "oceania")
    if any(k in t for k in continental):
        return 0.8 if "qualification" in t else 0.9
    return 0.7  # resto de competiciones oficiales


@dataclass
class ParsedMatches:
    home_i: np.ndarray
    away_i: np.ndarray
    home_goals: np.ndarray
    away_goals: np.ndarray
    neutral: np.ndarray
    dates: list[date]
    comp: np.ndarray  # peso de importancia por partido
    names: list[str]  # nombre crudo por índice de equipo
    name_to_idx: dict[str, int]

    @property
    def n_teams(self) -> int:
        return len(self.names)

    @property
    def n_matches(self) -> int:
        return len(self.home_goals)


def parse_matches(text: str, since: date, until: date | None = None) -> ParsedMatches:
    """Lee el CSV de resultados y arma arrays paralelos de partidos con marcador válido."""
    home_i, away_i, hs, as_, neutral, dates, comp = [], [], [], [], [], [], []
    name_to_idx: dict[str, int] = {}
    names: list[str] = []

    def idx(raw_name: str) -> int:
        key = _normalize(raw_name)
        if key not in name_to_idx:
            name_to_idx[key] = len(names)
            names.append(raw_name)
        return name_to_idx[key]

    for row in csv.DictReader(io.StringIO(text)):
        try:
            d = datetime.strptime(row["date"], "%Y-%m-%d").date()
        except (ValueError, KeyError):
            continue
        if d < since or (until is not None and d >= until):
            continue
        try:
            gh, ga = int(row["home_score"]), int(row["away_score"])
        except (ValueError, TypeError):
            continue  # "NA" (futuros) o vacíos
        home_i.append(idx(row["home_team"]))
        away_i.append(idx(row["away_team"]))
        hs.append(gh)
        as_.append(ga)
        neutral.append(1.0 if str(row.get("neutral", "")).upper() == "TRUE" else 0.0)
        dates.append(d)
        comp.append(competition_weight(row.get("tournament", "")))

    return ParsedMatches(
        home_i=np.array(home_i),
        away_i=np.array(away_i),
        home_goals=np.array(hs, dtype=float),
        away_goals=np.array(as_, dtype=float),
        neutral=np.array(neutral),
        dates=dates,
        comp=np.array(comp),
        names=names,
        name_to_idx=name_to_idx,
    )


def build_weights(
    dates: list[date], comp: np.ndarray, half_life_days: float, as_of: date
) -> np.ndarray:
    """Peso por partido = recencia (decaimiento exponencial hasta `as_of`) × importancia.

    `as_of` permite anclar la recencia a una fecha de corte (clave para que el
    backtest pese los datos como lo haría el modelo desplegado ese día).
    """
    decay = np.log(2.0) / half_life_days
    ages = np.array([(as_of - d).days for d in dates], dtype=float)
    w = np.exp(-decay * ages) * comp
    return w / w.mean()  # peso medio 1 → el ridge queda en escala interpretable


def attack_defense_objective(x, pm: ParsedMatches, w, reg):
    """NLL ponderada + ridge, con gradiente analítico. x = [μ, ventaja, atk[n], def[n]]."""
    n = pm.n_teams
    A0, D0 = 2, 2 + n
    mu, hadv = x[0], x[1]
    atk, dfn = x[A0:A0 + n], x[D0:D0 + n]
    not_neutral = 1.0 - pm.neutral

    log_h = mu + hadv * not_neutral + atk[pm.home_i] - dfn[pm.away_i]
    log_a = mu + atk[pm.away_i] - dfn[pm.home_i]
    lh, la = np.exp(log_h), np.exp(log_a)

    nll = np.sum(w * ((lh - pm.home_goals * log_h) + (la - pm.away_goals * log_a)))
    nll += 0.5 * reg * (np.sum(atk**2) + np.sum(dfn**2))

    rh = w * (lh - pm.home_goals)
    ra = w * (la - pm.away_goals)
    g = np.zeros_like(x)
    g[0] = np.sum(rh + ra)
    g[1] = np.sum(rh * not_neutral)
    g[A0:A0 + n] = np.bincount(pm.home_i, rh, n) + np.bincount(pm.away_i, ra, n) + reg * atk
    g[D0:D0 + n] = -np.bincount(pm.away_i, rh, n) - np.bincount(pm.home_i, ra, n) + reg * dfn
    return nll, g


def fit_attack_defense(pm: ParsedMatches, w: np.ndarray, reg: float):
    """Ajusta el GLM Poisson ponderado con ridge. Devuelve (μ, ventaja, atk, def, res).

    Ataque/defensa se centran a media 0 (identificabilidad) absorbiendo el
    corrimiento en μ; el ridge encoge hacia 0 a los equipos con pocos partidos.
    """
    n = pm.n_teams
    x0 = np.zeros(2 + 2 * n)
    x0[0] = np.log(max(pm.home_goals.mean(), 0.1))
    res = minimize(
        attack_defense_objective, x0, args=(pm, w, reg), jac=True, method="L-BFGS-B",
        options={"maxiter": 500, "ftol": 1e-10, "gtol": 1e-7},
    )
    mu, hadv = res.x[0], res.x[1]
    atk, dfn = res.x[2:2 + n], res.x[2 + n:2 + 2 * n]
    mu = mu + atk.mean() - dfn.mean()
    atk = atk - atk.mean()
    dfn = dfn - dfn.mean()
    return float(mu), float(hadv), atk, dfn, res


def fit_rho(pm: ParsedMatches, w, mu, hadv, atk, dfn) -> float:
    """Ajusta ρ de Dixon-Coles maximizando la verosimilitud de los marcadores bajos."""
    log_h = mu + hadv * (1.0 - pm.neutral) + atk[pm.home_i] - dfn[pm.away_i]
    log_a = mu + atk[pm.away_i] - dfn[pm.home_i]
    lh, la = np.exp(log_h), np.exp(log_a)
    hs, as_ = pm.home_goals, pm.away_goals
    m00 = (hs == 0) & (as_ == 0)
    m01 = (hs == 0) & (as_ == 1)
    m10 = (hs == 1) & (as_ == 0)
    m11 = (hs == 1) & (as_ == 1)

    def neg_ll(rho):
        tau = np.ones_like(lh)
        tau[m00] = 1.0 - lh[m00] * la[m00] * rho
        tau[m01] = 1.0 + lh[m01] * rho
        tau[m10] = 1.0 + la[m10] * rho
        tau[m11] = 1.0 - rho
        if np.any(tau <= 0):
            return 1e12
        return -np.sum(w * np.log(tau))

    return float(minimize_scalar(neg_ll, bounds=(-0.2, 0.05), method="bounded").x)


@dataclass
class FitResult:
    mu: float
    home_adv: float
    rho: float
    attack: np.ndarray
    defense: np.ndarray
    pm: ParsedMatches

    def team_idx(self, name: str) -> int | None:
        return self.pm.name_to_idx.get(_normalize(name))


def fit(pm: ParsedMatches, half_life_days: float, reg: float, as_of: date) -> FitResult:
    """Ajuste completo (ataque/defensa + ρ) sobre los partidos ya parseados."""
    w = build_weights(pm.dates, pm.comp, half_life_days, as_of)
    mu, hadv, atk, dfn, _ = fit_attack_defense(pm, w, reg)
    rho = fit_rho(pm, w, mu, hadv, atk, dfn)
    return FitResult(mu=mu, home_adv=hadv, rho=rho, attack=atk, defense=dfn, pm=pm)
