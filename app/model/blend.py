"""Mezcla mercado <-> modelo de fuerzas y produce los lambdas finales a simular.

- El modelo de fuerzas (Dixon-Coles ataque/defensa, o Elo de fallback) siempre está
  disponible (ver app/model/strengths.py).
- Si hay cuotas, se calibran lambdas de mercado y se mezclan con peso `w`.
- Devuelve los lambdas finales + las probabilidades de cada componente para que
  la UI muestre la comparación mercado vs modelo.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from app.model import strengths
from app.model.poisson import (
    calibrate_lambdas_to_market,
    outcome_probs,
    score_matrix,
)
from app.services.odds import MarketProbs

# Cuántas casas de apuestas hacen falta para confiar plenamente en el mercado.
# Con menos, se reduce su peso proporcionalmente (menos liquidez ⇒ menos señal).
BOOKS_FOR_FULL_WEIGHT = 5


@dataclass
class BlendResult:
    lam_home: float
    lam_away: float
    model_probs: dict  # probs del modelo de fuerzas (home/draw/away)
    market_probs: dict | None  # probs del mercado (o None)
    market_weight: float  # peso efectivo del mercado en la mezcla
    model_basis: str  # "strengths" (ataque/defensa) o "elo" (fallback)
    rho: float  # ρ Dixon-Coles usado (para muestrear consistente en Monte Carlo)


def _probs_dict(lam_home: float, lam_away: float, rho: float) -> dict:
    home, draw, away = outcome_probs(score_matrix(lam_home, lam_away, rho=rho))
    return {"home": home, "draw": draw, "away": away}


def blend(
    home_team: str,
    away_team: str,
    *,
    neutral: bool,
    base_lambda: float,
    home_advantage_elo: float,
    market: MarketProbs | None,
    market_weight: float,
) -> BlendResult:
    rho = strengths.current_rho()
    basis = "strengths" if strengths.uses_strengths(home_team, away_team) else "elo"
    model_lh, model_la = strengths.goal_lambdas(
        home_team,
        away_team,
        neutral=neutral,
        base_lambda=base_lambda,
        home_advantage_elo=home_advantage_elo,
    )
    model_probs = _probs_dict(model_lh, model_la, rho)

    if market is None:
        return BlendResult(
            lam_home=model_lh,
            lam_away=model_la,
            model_probs=model_probs,
            market_probs=None,
            market_weight=0.0,
            model_basis=basis,
            rho=rho,
        )

    mkt_lh, mkt_la = calibrate_lambdas_to_market(
        market.home, market.draw, market.away, seed_home=model_lh, seed_away=model_la, rho=rho
    )
    # Peso efectivo: el configurado, atenuado si hay pocas casas (menos confianza).
    confidence = min(1.0, market.bookmakers / BOOKS_FOR_FULL_WEIGHT)
    w = max(0.0, min(1.0, market_weight)) * confidence
    # Mezcla en espacio log (media geométrica de las tasas de gol): más natural para
    # un modelo multiplicativo de goles que el promedio lineal de λ.
    lam_home = math.exp(w * math.log(mkt_lh) + (1 - w) * math.log(model_lh))
    lam_away = math.exp(w * math.log(mkt_la) + (1 - w) * math.log(model_la))
    return BlendResult(
        lam_home=lam_home,
        lam_away=lam_away,
        model_probs=model_probs,
        market_probs={"home": market.home, "draw": market.draw, "away": market.away},
        market_weight=w,
        model_basis=basis,
        rho=rho,
    )
