"""Simulación Monte Carlo del Mundial 2026 completo (formato 48 equipos).

Formato 2026:
- 12 grupos de 4 (A..L), todos contra todos.
- Clasifican: 1° y 2° de cada grupo (24) + los 8 mejores 3° = 32.
- Eliminatoria directa: 32avos -> 16avos -> 8vos(QF) -> SF -> Final.

Se reutiliza el modelo de goles Elo->Poisson de `poisson.py`. Los partidos del
torneo se juegan en sede neutral, así que no se aplica ventaja de localía.
"""
from __future__ import annotations

import json

import numpy as np

from app.config import DATA_DIR
from app.model.poisson import lambdas_from_elo
from app.services.ratings import all_teams, elo_of, get_rating

BASE_LAMBDA = 1.35
GROUP_LETTERS = [chr(ord("A") + i) for i in range(12)]
# Etiquetas de las rondas alcanzadas (de menor a mayor).
STAGES = ["r32", "r16", "qf", "sf", "final", "champion"]


OFFICIAL_GROUPS_PATH = DATA_DIR / "groups_2026.json"


def official_groups() -> dict[str, list[str]] | None:
    """Grupos oficiales del Mundial 2026 desde data/groups_2026.json.

    Devuelve None si el archivo no existe o no es válido (12 grupos de 4).
    """
    if not OFFICIAL_GROUPS_PATH.exists():
        return None
    try:
        data = json.loads(OFFICIAL_GROUPS_PATH.read_text(encoding="utf-8"))
        groups = data["groups"]
    except (json.JSONDecodeError, KeyError, OSError):
        return None
    if len(groups) != 12 or any(len(t) != 4 for t in groups.values()):
        return None
    return groups


def default_groups() -> dict[str, list[str]]:
    """48 mejores selecciones (por ranking FIFA) repartidas en 12 grupos por bombos.

    Reparto serpenteado (snake) por pote: equilibra la fuerza entre grupos.
    Aproximación: no aplica las restricciones de confederación del sorteo real.
    """
    teams = [r.team for r in all_teams()][:48]
    groups: dict[str, list[str]] = {g: [] for g in GROUP_LETTERS}
    idx = 0
    for pot in range(4):
        order = GROUP_LETTERS if pot % 2 == 0 else GROUP_LETTERS[::-1]
        for g in order:
            groups[g].append(teams[idx])
            idx += 1
    return groups


def resolve_groups() -> tuple[dict[str, list[str]], bool]:
    """Devuelve (grupos, son_oficiales). Usa los oficiales si están disponibles."""
    official = official_groups()
    if official is not None:
        return official, True
    return default_groups(), False


class _Engine:
    """Cachea Elo y lambdas por par para acelerar las N simulaciones."""

    def __init__(self, teams: list[str]):
        self.elo = {t: elo_of(t) for t in teams}
        self._lam: dict[tuple[str, str], tuple[float, float]] = {}

    def lambdas(self, a: str, b: str) -> tuple[float, float]:
        key = (a, b)
        cached = self._lam.get(key)
        if cached is None:
            cached = lambdas_from_elo(
                self.elo[a], self.elo[b], home_advantage_elo=0.0, base_lambda=BASE_LAMBDA
            )
            self._lam[key] = cached
        return cached

    def play(self, rng, a: str, b: str) -> tuple[int, int]:
        la, lb = self.lambdas(a, b)
        return int(rng.poisson(la)), int(rng.poisson(lb))

    def knockout_winner(self, rng, a: str, b: str) -> str:
        ga, gb = self.play(rng, a, b)
        if ga > gb:
            return a
        if gb > ga:
            return b
        # Empate -> "penales": probabilidad por expectativa Elo.
        pa = 1.0 / (1.0 + 10 ** (-(self.elo[a] - self.elo[b]) / 400))
        return a if rng.random() < pa else b


def _seed_order(n: int) -> list[int]:
    """Orden de siembra estándar de un cuadro de n (1 y 2 sólo se cruzan en la final)."""
    order = [1]
    while len(order) < n:
        m = len(order) * 2
        order = [x for s in order for x in (s, m + 1 - s)]
    return order


def _group_standings(rng, engine: _Engine, teams: list[str]) -> list[dict]:
    """Round-robin de un grupo -> equipos ordenados por pts, GD, GF, Elo."""
    stats = {t: {"pts": 0, "gd": 0, "gf": 0} for t in teams}
    for i in range(len(teams)):
        for j in range(i + 1, len(teams)):
            a, b = teams[i], teams[j]
            ga, gb = engine.play(rng, a, b)
            stats[a]["gf"] += ga
            stats[b]["gf"] += gb
            stats[a]["gd"] += ga - gb
            stats[b]["gd"] += gb - ga
            if ga > gb:
                stats[a]["pts"] += 3
            elif gb > ga:
                stats[b]["pts"] += 3
            else:
                stats[a]["pts"] += 1
                stats[b]["pts"] += 1
    ranked = sorted(
        teams,
        key=lambda t: (stats[t]["pts"], stats[t]["gd"], stats[t]["gf"], engine.elo[t]),
        reverse=True,
    )
    return [{"team": t, **stats[t]} for t in ranked]


def _qualifiers(rng, engine: _Engine, groups: dict[str, list[str]]) -> list[str]:
    """1° y 2° de cada grupo + los 8 mejores 3° (32 clasificados)."""
    winners, runners, thirds = [], [], []
    for letter in GROUP_LETTERS:
        standings = _group_standings(rng, engine, groups[letter])
        winners.append(standings[0])
        runners.append(standings[1])
        thirds.append(standings[2])
    best_thirds = sorted(
        thirds,
        key=lambda s: (s["pts"], s["gd"], s["gf"], engine.elo[s["team"]]),
        reverse=True,
    )[:8]
    return [s["team"] for s in winners + runners + best_thirds]


def _run_knockout(rng, engine: _Engine, qualifiers: list[str], reached: dict) -> str:
    """Cuadro de 32 sembrado por Elo. Devuelve el campeón y marca rondas alcanzadas."""
    seeds = sorted(qualifiers, key=lambda t: engine.elo[t], reverse=True)
    bracket = [seeds[o - 1] for o in _seed_order(32)]
    # 'r32' = haber clasificado (todos los del cuadro).
    for t in bracket:
        reached[t]["r32"] += 1
    round_stages = ["r16", "qf", "sf", "final", "champion"]
    for stage in round_stages:
        winners = []
        for k in range(0, len(bracket), 2):
            w = engine.knockout_winner(rng, bracket[k], bracket[k + 1])
            reached[w][stage] += 1
            winners.append(w)
        bracket = winners
    return bracket[0]


def simulate_tournament(
    groups: dict[str, list[str]], n: int, seed: int | None = None
) -> dict:
    teams = [t for g in groups.values() for t in g]
    engine = _Engine(teams)
    rng = np.random.default_rng(seed)
    reached = {t: {s: 0 for s in STAGES} for t in teams}

    for _ in range(n):
        qualifiers = _qualifiers(rng, engine, groups)
        _run_knockout(rng, engine, qualifiers, reached)

    table = []
    for t in teams:
        row = {"team": t, "elo": round(engine.elo[t])}
        for s in STAGES:
            row[s] = reached[t][s] / n
        table.append(row)
    table.sort(key=lambda r: r["champion"], reverse=True)
    return {
        "n_simulations": n,
        "groups": groups,
        "ranking": table,
    }
