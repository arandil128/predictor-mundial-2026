"""Validación out-of-sample del modelo de goles sobre datos abiertos.

Responde con NÚMEROS la pregunta: ¿el modelo nuevo (Dixon-Coles ataque/defensa)
predice mejor que el viejo (Elo de razón-constante) y que un baseline trivial?

Diseño (sin filtraciones de información):
- TRAIN  (< --train-end): ajusta ataque/defensa y calcula el Elo histórico.
- VALID  ([train-end, valid-end)): ajusta la "temperatura" de calibración.
- TEST   (>= valid-end): evaluación final; ningún modelo vio estos partidos.

Modelos comparados (todos predicen los MISMOS partidos de test):
1. ataque/defensa  — Dixon-Coles calibrado (el nuevo).
2. Elo razón-cte   — Elo propio + lambdas_from_elo (reproduce el modelo viejo).
3. baseline        — frecuencias 1X2 y goles medios del train (constantes).

Métricas (menor = mejor, salvo score-LL): log-loss y Brier del 1X2, RPS (ordinal),
log-verosimilitud del marcador EXACTO (mide la predicción de goles) y MAE del total
de goles.

Uso:
    python scripts/backtest.py
    python scripts/backtest.py --train-end 2023-01-01 --valid-end 2024-01-01
"""
from __future__ import annotations

import argparse
import sys
from datetime import date, datetime
from pathlib import Path

import httpx
import numpy as np
from scipy.optimize import minimize_scalar

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.model import fitting  # noqa: E402
from app.model.fitting import ParsedMatches  # noqa: E402
from app.model.poisson import lambdas_from_elo, score_matrix  # noqa: E402

RESULTS_URL = (
    "https://raw.githubusercontent.com/martj42/international_results/master/results.csv"
)
CAP = 10           # goles máximos de la matriz de marcadores
HOME_ADV_ELO = 55  # ventaja de localía (en puntos Elo) para convertir a goles
MIN_TRAIN_MATCHES = 5  # equipos con menos partidos de train no se evalúan


def download() -> str:
    print(f"Descargando {RESULTS_URL} …")
    r = httpx.get(RESULTS_URL, timeout=60)
    r.raise_for_status()
    return r.text


def _iso(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


def subset(pm: ParsedMatches, mask: np.ndarray) -> ParsedMatches:
    """Sub-conjunto de partidos compartiendo el espacio de índices/nombres."""
    return ParsedMatches(
        home_i=pm.home_i[mask],
        away_i=pm.away_i[mask],
        home_goals=pm.home_goals[mask],
        away_goals=pm.away_goals[mask],
        neutral=pm.neutral[mask],
        dates=[d for d, m in zip(pm.dates, mask) if m],
        comp=pm.comp[mask],
        names=pm.names,
        name_to_idx=pm.name_to_idx,
    )


def compute_elo(pm: ParsedMatches, train_mask, k=40.0, home_adv=65.0, init=1500.0):
    """Elo histórico procesando el train en orden cronológico (margen de gol incluido)."""
    R = np.full(pm.n_teams, init)
    order = sorted(np.where(train_mask)[0], key=lambda m: pm.dates[m])
    for m in order:
        i, j = pm.home_i[m], pm.away_i[m]
        gh, ga = pm.home_goals[m], pm.away_goals[m]
        ha = 0.0 if pm.neutral[m] else home_adv
        exp_h = 1.0 / (1.0 + 10 ** (-((R[i] + ha) - R[j]) / 400))
        score = 1.0 if gh > ga else (0.5 if gh == ga else 0.0)
        margin = abs(gh - ga)
        g_mult = 1.0 if margin <= 1 else (1.5 if margin == 2 else (11 + margin) / 8)
        delta = k * g_mult * (score - exp_h)
        R[i] += delta
        R[j] -= delta
    return R


# ------------------------------ métricas ------------------------------------

def _outcome(gh, ga) -> int:
    return 0 if gh > ga else (1 if gh == ga else 2)


def _probs_from_matrix(m):
    home = float(np.tril(m, -1).sum())
    draw = float(np.trace(m))
    away = float(np.triu(m, 1).sum())
    return np.array([home, draw, away])


def _rps(p, o) -> float:
    y = np.zeros(3)
    y[o] = 1.0
    cp = cy = c = 0.0
    for k in range(2):  # r-1 pasos acumulados
        cp += p[k]
        cy += y[k]
        c += (cp - cy) ** 2
    return c / 2.0


class Metrics:
    def __init__(self):
        self.n = 0
        self.logloss = self.brier = self.rps = self.score_ll = self.tot_mae = 0.0
        self.p_home = []  # para la curva de calibración
        self.y_home = []

    def add(self, p, matrix, gh, ga):
        o = _outcome(gh, ga)
        self.n += 1
        self.logloss += -np.log(max(p[o], 1e-12))
        y = np.zeros(3)
        y[o] = 1.0
        self.brier += float(np.sum((p - y) ** 2))
        self.rps += _rps(p, o)
        gi, gj = min(int(gh), CAP), min(int(ga), CAP)
        self.score_ll += np.log(max(matrix[gi, gj], 1e-12))
        exp_total = float((matrix.sum(0) * np.arange(CAP + 1)).sum()
                          + (matrix.sum(1) * np.arange(CAP + 1)).sum())
        self.tot_mae += abs(exp_total - (gh + ga))
        self.p_home.append(p[0])
        self.y_home.append(1.0 if o == 0 else 0.0)

    def row(self, name):
        n = max(self.n, 1)
        return (f"{name:<16} {self.logloss/n:8.4f} {self.brier/n:8.4f} "
                f"{self.rps/n:8.4f} {self.score_ll/n:9.4f} {self.tot_mae/n:8.3f}")


def predict_attack_defense(fr, i, j, neutral):
    not_n = 0.0 if neutral else 1.0
    log_h = fr.mu + fr.home_adv * not_n + fr.attack[i] - fr.defense[j]
    log_a = fr.mu + fr.attack[j] - fr.defense[i]
    lh = float(np.clip(np.exp(log_h), 0.05, 6.0))
    la = float(np.clip(np.exp(log_a), 0.05, 6.0))
    m = score_matrix(lh, la, rho=fr.rho, max_goals=CAP)
    return _probs_from_matrix(m), m


def predict_elo(R, i, j, neutral):
    ha = 0.0 if neutral else HOME_ADV_ELO
    lh, la = lambdas_from_elo(R[i], R[j], ha, base_lambda=1.35)
    m = score_matrix(lh, la, rho=-0.05, max_goals=CAP)  # ρ del modelo viejo
    return _probs_from_matrix(m), m


def fit_temperature(fr, pm_valid) -> float:
    """Temperatura T que minimiza el log-loss del 1X2 en VALID (p^(1/T) renormalizado)."""
    rows = []
    for k in range(pm_valid.n_matches):
        i, j = pm_valid.home_i[k], pm_valid.away_i[k]
        p, _ = predict_attack_defense(fr, i, j, pm_valid.neutral[k])
        rows.append((p, _outcome(pm_valid.home_goals[k], pm_valid.away_goals[k])))

    def nll(T):
        s = 0.0
        for p, o in rows:
            q = p ** (1.0 / T)
            q = q / q.sum()
            s += -np.log(max(q[o], 1e-12))
        return s

    return float(minimize_scalar(nll, bounds=(0.5, 3.0), method="bounded").x)


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

    ap = argparse.ArgumentParser(description="Backtest del modelo de goles.")
    ap.add_argument("--since", type=int, default=1994, help="Año inicial del train.")
    ap.add_argument("--train-end", type=_iso, default=_iso("2023-01-01"))
    ap.add_argument("--valid-end", type=_iso, default=_iso("2024-01-01"))
    ap.add_argument("--half-life", type=float, default=1095.0)
    ap.add_argument("--reg", type=float, default=5.0)
    args = ap.parse_args()

    pm = fitting.parse_matches(download(), date(args.since, 1, 1))
    dts = np.array([d.toordinal() for d in pm.dates])
    train_mask = dts < args.train_end.toordinal()
    valid_mask = (dts >= args.train_end.toordinal()) & (dts < args.valid_end.toordinal())
    test_mask = dts >= args.valid_end.toordinal()
    print(f"Partidos: {pm.n_matches:,} | train {train_mask.sum():,} · "
          f"valid {valid_mask.sum():,} · test {test_mask.sum():,}")

    pm_train = subset(pm, train_mask)
    fr = fitting.fit(pm_train, args.half_life, args.reg, as_of=args.train_end)
    R = compute_elo(pm, train_mask)
    print(f"Ajuste train: μ={fr.mu:.3f} · ventaja={fr.home_adv:.3f} · ρ={fr.rho:.4f}")

    # Baseline: frecuencias 1X2 y goles medios del train.
    tr_gh, tr_ga = pm_train.home_goals, pm_train.away_goals
    base_p = np.array([
        float(np.mean(tr_gh > tr_ga)),
        float(np.mean(tr_gh == tr_ga)),
        float(np.mean(tr_gh < tr_ga)),
    ])
    base_m = score_matrix(float(tr_gh.mean()), float(tr_ga.mean()), rho=0.0, max_goals=CAP)

    # Equipos con suficiente historia de train (para que todos predigan lo mismo).
    train_counts = (np.bincount(pm_train.home_i, minlength=pm.n_teams)
                    + np.bincount(pm_train.away_i, minlength=pm.n_teams))
    eligible = train_counts >= MIN_TRAIN_MATCHES

    T = fit_temperature(fr, subset(pm, valid_mask))
    print(f"Temperatura de calibración (de VALID): T={T:.3f}")

    m_ad, m_elo, m_base, m_temp = Metrics(), Metrics(), Metrics(), Metrics()
    test_idx = np.where(test_mask)[0]
    for k in test_idx:
        i, j = pm.home_i[k], pm.away_i[k]
        if not (eligible[i] and eligible[j]):
            continue
        gh, ga, neu = pm.home_goals[k], pm.away_goals[k], pm.neutral[k]
        p_ad, mat_ad = predict_attack_defense(fr, i, j, neu)
        p_elo, mat_elo = predict_elo(R, i, j, neu)
        m_ad.add(p_ad, mat_ad, gh, ga)
        m_elo.add(p_elo, mat_elo, gh, ga)
        m_base.add(base_p, base_m, gh, ga)
        q = p_ad ** (1.0 / T)
        m_temp.add(q / q.sum(), mat_ad, gh, ga)

    print(f"\nPartidos de test evaluados: {m_ad.n:,}\n")
    print(f"{'modelo':<16} {'logloss':>8} {'brier':>8} {'rps':>8} {'score-LL':>9} {'totMAE':>8}")
    print("-" * 62)
    print(m_base.row("baseline"))
    print(m_elo.row("Elo razón-cte"))
    print(m_ad.row("ataque/defensa"))
    print(m_temp.row("at/def+temp"))

    # Mejora relativa del modelo nuevo sobre el viejo.
    imp = lambda new, old: (old - new) / old * 100
    print(f"\nMejora ataque/defensa vs Elo razón-cte: "
          f"log-loss {imp(m_ad.logloss, m_elo.logloss):+.1f}% · "
          f"RPS {imp(m_ad.rps, m_elo.rps):+.1f}% · "
          f"score-LL {(m_ad.score_ll - m_elo.score_ll)/m_ad.n:+.4f}/partido")

    # Curva de calibración del modelo nuevo (deciles de P(gana local)).
    print("\nCalibración P(gana local) — modelo ataque/defensa:")
    p_home = np.array(m_ad.p_home)
    y_home = np.array(m_ad.y_home)
    print(f"  {'rango pred.':<14}{'pred.medio':>11}{'observado':>11}{'n':>7}")
    for lo in np.arange(0.0, 1.0, 0.1):
        sel = (p_home >= lo) & (p_home < lo + 0.1)
        if sel.sum() == 0:
            continue
        print(f"  {f'{lo:.1f}-{lo+0.1:.1f}':<14}{p_home[sel].mean():>11.3f}"
              f"{y_home[sel].mean():>11.3f}{sel.sum():>7d}")


if __name__ == "__main__":
    main()
