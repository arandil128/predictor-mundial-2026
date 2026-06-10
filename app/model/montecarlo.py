"""Motor Monte Carlo: simula N partidos muestreando goles de sendas Poisson.

El usuario controla N. Más simulaciones => estimaciones más estables. Las
probabilidades convergen a las analíticas de Poisson cuando N -> infinito.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class SimulationResult:
    n: int
    prob_home: float
    prob_draw: float
    prob_away: float
    exp_goals_home: float
    exp_goals_away: float
    top_scorelines: list[dict]  # [{"score": "2-1", "prob": 0.08}, ...]
    over_2_5: float
    btts: float  # ambos equipos marcan
    total_goals_dist: list[dict]  # [{"goals": 0, "prob": ...}, ...] hasta 7+


def simulate(
    lam_home: float,
    lam_away: float,
    n: int,
    seed: int | None = None,
) -> SimulationResult:
    rng = np.random.default_rng(seed)
    home = rng.poisson(lam_home, size=n)
    away = rng.poisson(lam_away, size=n)

    prob_home = float(np.mean(home > away))
    prob_draw = float(np.mean(home == away))
    prob_away = float(np.mean(home < away))

    # Top marcadores (capados a 6 para el conteo de etiquetas).
    cap = 6
    hc = np.minimum(home, cap)
    ac = np.minimum(away, cap)
    keys, counts = np.unique(hc * (cap + 1) + ac, return_counts=True)
    order = np.argsort(counts)[::-1][:5]
    top_scorelines = [
        {
            "score": f"{int(k) // (cap + 1)}-{int(k) % (cap + 1)}",
            "prob": float(counts[i] / n),
        }
        for i, k in zip(order, keys[order])
    ]

    total = home + away
    over_2_5 = float(np.mean(total > 2.5))
    btts = float(np.mean((home > 0) & (away > 0)))

    dist = []
    for g in range(7):
        dist.append({"goals": g, "prob": float(np.mean(total == g))})
    dist.append({"goals": 7, "prob": float(np.mean(total >= 7))})  # 7 o más

    return SimulationResult(
        n=n,
        prob_home=prob_home,
        prob_draw=prob_draw,
        prob_away=prob_away,
        exp_goals_home=float(home.mean()),
        exp_goals_away=float(away.mean()),
        top_scorelines=top_scorelines,
        over_2_5=over_2_5,
        btts=btts,
        total_goals_dist=dist,
    )
