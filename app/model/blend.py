"""Mezcla mercado <-> modelo Elo y produce los lambdas finales a simular.

- El modelo Elo siempre está disponible (CSV semilla).
- Si hay cuotas, se calibran lambdas de mercado y se mezclan con peso `w`.
- Devuelve los lambdas finales + las probabilidades de cada componente para que
  la UI muestre la comparación mercado vs modelo.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.model.poisson import (
    calibrate_lambdas_to_market,
    lambdas_from_elo,
    outcome_probs,
    score_matrix,
)
from app.services.odds import MarketProbs


@dataclass
class BlendResult:
    lam_home: float
    lam_away: float
    model_probs: dict  # probs del modelo Elo (home/draw/away)
    market_probs: dict | None  # probs del mercado (o None)
    market_weight: float  # peso efectivo del mercado en la mezcla


def _probs_dict(lam_home: float, lam_away: float) -> dict:
    home, draw, away = outcome_probs(score_matrix(lam_home, lam_away))
    return {"home": home, "draw": draw, "away": away}


def blend(
    elo_home: float,
    elo_away: float,
    home_advantage_elo: float,
    base_lambda: float,
    market: MarketProbs | None,
    market_weight: float,
) -> BlendResult:
    elo_lh, elo_la = lambdas_from_elo(
        elo_home, elo_away, home_advantage_elo, base_lambda
    )
    model_probs = _probs_dict(elo_lh, elo_la)

    if market is None:
        return BlendResult(
            lam_home=elo_lh,
            lam_away=elo_la,
            model_probs=model_probs,
            market_probs=None,
            market_weight=0.0,
        )

    mkt_lh, mkt_la = calibrate_lambdas_to_market(
        market.home, market.draw, market.away, seed_home=elo_lh, seed_away=elo_la
    )
    w = max(0.0, min(1.0, market_weight))
    lam_home = w * mkt_lh + (1 - w) * elo_lh
    lam_away = w * mkt_la + (1 - w) * elo_la
    return BlendResult(
        lam_home=lam_home,
        lam_away=lam_away,
        model_probs=model_probs,
        market_probs={"home": market.home, "draw": market.draw, "away": market.away},
        market_weight=w,
    )
