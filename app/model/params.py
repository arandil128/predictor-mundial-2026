"""Carga los parámetros calibrados del modelo de goles (data/model_params.json).

Los produce `scripts/calibrate.py`, ajustando un Dixon-Coles ataque/defensa sobre
datos abiertos de partidos internacionales. Si el archivo no existe, el modelo cae
al Elo y todo sigue funcionando (los getters devuelven defaults neutros).
"""
from __future__ import annotations

import json
from functools import lru_cache

from app.config import DATA_DIR

PARAMS_PATH = DATA_DIR / "model_params.json"

# Defaults si no hay archivo calibrado: μ=0 y sin ventaja → equivalen a "sin modelo
# de fuerzas" (se usa el Elo). El ρ replica el DEFAULT_RHO histórico de poisson.py.
_DEFAULT_GLOBAL = {"mu": 0.0, "home_adv": 0.0, "rho": -0.05}


@lru_cache
def _load() -> dict | None:
    """Lee y valida el JSON una sola vez. None si falta o es inválido."""
    if not PARAMS_PATH.exists():
        return None
    try:
        data = json.loads(PARAMS_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if isinstance(data, dict) and "global" in data and "teams" in data:
        return data
    return None


def reload() -> None:
    """Olvida la caché (útil tras recalibrar sin reiniciar el proceso)."""
    _load.cache_clear()


def has_params() -> bool:
    return _load() is not None


def global_params() -> dict:
    data = _load()
    return dict(data["global"]) if data else dict(_DEFAULT_GLOBAL)


def team_strength(norm_key: str) -> dict | None:
    """{'attack', 'defense', 'matches', 'name'} de una selección, o None.

    `norm_key` debe venir normalizado (app.services.ratings._normalize).
    """
    data = _load()
    if not data:
        return None
    return data["teams"].get(norm_key)


def fitted_at() -> str | None:
    data = _load()
    return data.get("fitted_at") if data else None
