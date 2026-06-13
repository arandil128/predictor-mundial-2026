"""Goles esperados (λ) de cada selección en un cruce — núcleo del modelo de goles.

Jerarquía de modelos (usa el mejor disponible para cada par):

1. **Dixon-Coles ataque/defensa** (preferido): cuando ambas selecciones tienen
   fuerza calibrada en data/model_params.json. Ataque y defensa independientes
   ⇒ los goles totales dependen del cruce (un goleador vs. una defensa floja
   produce muchos goles; dos defensas sólidas, pocos). Esto es lo que el modelo
   Elo de razón-constante no puede capturar.

       log λ_local = μ + ventaja + ataque[local] − defensa[visitante]
       log λ_visit = μ +          ataque[visit]  − defensa[local]

2. **Elo** (fallback): para selecciones sin histórico suficiente.

Sede: el Mundial se juega en cancha neutral, así que por defecto NO se aplica
ventaja de localía. La excepción son los anfitriones (EE.UU./México/Canadá), que
juegan de local — reciben la ventaja calibrada cuando enfrentan a un no-anfitrión.
"""
from __future__ import annotations

import numpy as np

from app.model import params
from app.model.poisson import lambdas_from_elo
from app.services.ratings import _normalize, elo_of

# Anfitriones 2026: sede formalmente neutral, pero juegan de local. Reciben la
# ventaja calibrada en CUALQUIER partido propio. Es exacto para EE.UU. (la mayoría
# de las sedes y todas las rondas finales son en EE.UU.) y una leve sobre-estimación
# para México/Canadá si avanzan a rondas que se juegan fuera de su país.
HOSTS = {"united states", "mexico", "canada"}

LAMBDA_FLOOR, LAMBDA_CEIL = 0.05, 6.0


def is_host(team: str) -> bool:
    return _normalize(team) in HOSTS


def uses_strengths(home: str, away: str) -> bool:
    """True si ambos equipos tienen fuerza calibrada (se usa Dixon-Coles, no Elo)."""
    return (
        params.team_strength(_normalize(home)) is not None
        and params.team_strength(_normalize(away)) is not None
    )


def _advantage_split(home: str, away: str, neutral: bool) -> tuple[float, float]:
    """Ventaja en log-goles (local, visitante) según sede y anfitriones."""
    home_adv = params.global_params().get("home_adv", 0.0)
    if not neutral:
        return home_adv, 0.0  # partido de local explícito (uso fuera del Mundial)
    h_host, a_host = is_host(home), is_host(away)
    if h_host and not a_host:
        return home_adv, 0.0
    if a_host and not h_host:
        return 0.0, home_adv
    return 0.0, 0.0  # cancha neutral pura


def goal_lambdas(
    home: str,
    away: str,
    *,
    neutral: bool = True,
    base_lambda: float = 1.35,
    home_advantage_elo: float = 55.0,
) -> tuple[float, float]:
    """Goles esperados (λ_local, λ_visitante) con el mejor modelo disponible."""
    sh = params.team_strength(_normalize(home))
    sa = params.team_strength(_normalize(away))
    adv_h, adv_a = _advantage_split(home, away, neutral)

    if sh is not None and sa is not None:
        mu = params.global_params().get("mu", 0.0)
        log_h = mu + adv_h + sh["attack"] - sa["defense"]
        log_a = mu + adv_a + sa["attack"] - sh["defense"]
        lam_h, lam_a = float(np.exp(log_h)), float(np.exp(log_a))
        return (
            float(np.clip(lam_h, LAMBDA_FLOOR, LAMBDA_CEIL)),
            float(np.clip(lam_a, LAMBDA_FLOOR, LAMBDA_CEIL)),
        )

    # Fallback Elo: traslada la ventaja al lado anfitrión (negativa si es el visitante).
    eff_adv_elo = home_advantage_elo if adv_h > 0 else (-home_advantage_elo if adv_a > 0 else 0.0)
    return lambdas_from_elo(elo_of(home), elo_of(away), eff_adv_elo, base_lambda)


def current_rho() -> float:
    """ρ de Dixon-Coles calibrado (o el default histórico)."""
    return params.global_params().get("rho", -0.05)
