"""Modelo de goles: Elo -> lambdas, matriz Dixon-Coles y calibración al mercado.

- `lambdas_from_elo`: traduce la diferencia de fuerza (Elo + localía) a goles esperados.
- `score_matrix`: matriz de probabilidad de marcadores con corrección Dixon-Coles
  para los marcadores bajos (el Poisson puro subestima 0-0, 1-1, etc.).
- `calibrate_lambdas_to_market`: encuentra los lambdas cuyo modelo reproduce las
  probabilidades 1X2 implícitas del mercado de apuestas.
"""
from __future__ import annotations

import numpy as np
from scipy.optimize import least_squares
from scipy.stats import poisson

# Sensibilidad de la razón de goles a la diferencia de Elo (log-lineal). Calibrado:
# regresión de la supremacía de goles ajustada (ataque+defensa) contra el Elo de las
# selecciones da ~0.0029 (correlación 0.93). Solo se usa en el fallback Elo, cuando
# una selección no tiene fuerza ajustada (ver app/model/strengths.py).
ELO_TO_LOG_GOALS = 0.0029

# Parámetro de dependencia de Dixon-Coles para marcadores bajos.
DEFAULT_RHO = -0.05

MAX_GOALS = 10


def lambdas_from_elo(
    elo_home: float,
    elo_away: float,
    home_advantage_elo: float,
    base_lambda: float,
) -> tuple[float, float]:
    """Goles esperados (local, visitante) a partir de la diferencia de Elo."""
    eff_diff = (elo_home + home_advantage_elo) - elo_away
    factor = np.exp(ELO_TO_LOG_GOALS * eff_diff / 2.0)
    lam_home = base_lambda * factor
    lam_away = base_lambda / factor
    return float(np.clip(lam_home, 0.15, 6.0)), float(np.clip(lam_away, 0.15, 6.0))


def score_matrix(
    lam_home: float, lam_away: float, rho: float = DEFAULT_RHO, max_goals: int = MAX_GOALS
) -> np.ndarray:
    """Matriz (max_goals+1 x max_goals+1) de P(local=i, visitante=j)."""
    goals = np.arange(max_goals + 1)
    ph = poisson.pmf(goals, lam_home)
    pa = poisson.pmf(goals, lam_away)
    matrix = np.outer(ph, pa)

    # Corrección Dixon-Coles sobre los cuatro marcadores bajos.
    tau = np.ones_like(matrix)
    tau[0, 0] = 1 - lam_home * lam_away * rho
    tau[0, 1] = 1 + lam_home * rho
    tau[1, 0] = 1 + lam_away * rho
    tau[1, 1] = 1 - rho
    matrix = matrix * tau
    return matrix / matrix.sum()


def outcome_probs(matrix: np.ndarray) -> tuple[float, float, float]:
    """(P_local, P_empate, P_visitante) a partir de la matriz de marcadores."""
    home = float(np.tril(matrix, -1).sum())  # i > j
    draw = float(np.trace(matrix))
    away = float(np.triu(matrix, 1).sum())  # j > i
    return home, draw, away


def sample_from_matrix(
    matrix: np.ndarray, n: int, rng: np.random.Generator
) -> tuple[np.ndarray, np.ndarray]:
    """Muestrea n marcadores (goles_local, goles_visitante) de la matriz Dixon-Coles.

    Muestrear de la matriz —en lugar de dos Poisson independientes— mantiene el
    Monte Carlo CONSISTENTE con el modelo analítico (incluida la corrección DC).
    """
    flat = matrix.ravel()
    flat = flat / flat.sum()  # robustez ante errores de redondeo
    cols = matrix.shape[1]
    idx = rng.choice(flat.size, size=n, p=flat)
    return idx // cols, idx % cols


def _residuals(log_lams, target_home, target_away, rho):
    lam_home, lam_away = np.exp(log_lams)
    home, _, away = outcome_probs(score_matrix(lam_home, lam_away, rho))
    return [home - target_home, away - target_away]


def calibrate_lambdas_to_market(
    market_home: float,
    market_draw: float,
    market_away: float,
    seed_home: float = 1.35,
    seed_away: float = 1.35,
    rho: float = DEFAULT_RHO,
) -> tuple[float, float]:
    """Lambdas cuyo modelo Dixon-Coles reproduce las probs 1X2 del mercado."""
    result = least_squares(
        _residuals,
        x0=np.log([seed_home, seed_away]),
        args=(market_home, market_away, rho),
        bounds=(np.log(0.1), np.log(6.0)),
    )
    lam_home, lam_away = np.exp(result.x)
    return float(lam_home), float(lam_away)
