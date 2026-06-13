"""Motor Monte Carlo: simula N partidos muestreando de la matriz Dixon-Coles.

El usuario controla N. Más simulaciones => estimaciones más estables; convergen a
las probabilidades analíticas de la matriz Dixon-Coles cuando N -> infinito.

Antes el muestreo usaba dos Poisson INDEPENDIENTES (sin la corrección Dixon-Coles
del modelo analítico): sobre-estimaba ligeramente los marcadores bajos y los
empates. Ahora se muestrea de la misma matriz que produce las probabilidades
analíticas, así Monte Carlo y modelo quedan consistentes.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from app.model.poisson import DEFAULT_RHO, sample_from_matrix, score_matrix


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
    rho: float = DEFAULT_RHO,
    seed: int | None = None,
) -> SimulationResult:
    rng = np.random.default_rng(seed)
    matrix = score_matrix(lam_home, lam_away, rho=rho)
    home, away = sample_from_matrix(matrix, n, rng)

    prob_home = float(np.mean(home > away))
    prob_draw = float(np.mean(home == away))
    prob_away = float(np.mean(home < away))

    # Marcadores más probables (etiquetas exactas; los altos casi nunca entran al top).
    cap = matrix.shape[1]
    keys, counts = np.unique(home * cap + away, return_counts=True)
    order = np.argsort(counts)[::-1][:5]
    top_scorelines = [
        {"score": f"{int(k) // cap}-{int(k) % cap}", "prob": float(counts[i] / n)}
        for i, k in zip(order, keys[order])
    ]

    total = home + away
    over_2_5 = float(np.mean(total > 2.5))
    btts = float(np.mean((home > 0) & (away > 0)))

    dist = [{"goals": g, "prob": float(np.mean(total == g))} for g in range(7)]
    dist.append({"goals": 7, "prob": float(np.mean(total >= 7))})  # 7 o más

    return SimulationResult(
        n=n,
        prob_home=prob_home,
        prob_draw=prob_draw,
        prob_away=prob_away,
        # Goles esperados: la expectativa exacta del modelo (sin ruido de muestreo).
        exp_goals_home=lam_home,
        exp_goals_away=lam_away,
        top_scorelines=top_scorelines,
        over_2_5=over_2_5,
        btts=btts,
        total_goals_dist=dist,
    )
