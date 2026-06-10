"""Carga de ratings Elo / ranking FIFA de selecciones desde el CSV semilla.

Sirve como fuente de fuerza de equipos y como fallback cuando no hay cuotas.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from functools import lru_cache

from app.config import DATA_DIR


@dataclass(frozen=True)
class TeamRating:
    team: str
    code: str
    confederation: str
    elo: float
    fifa_rank: int


def _normalize(name: str) -> str:
    """Normaliza nombres para matchear variantes (mayúsculas, espacios, alias)."""
    key = name.strip().lower()
    aliases = {
        "usa": "united states",
        "estados unidos": "united states",
        "korea republic": "south korea",
        "south korea": "south korea",
        "ir iran": "iran",
        "türkiye": "turkey",
        "turkiye": "turkey",
        "czech republic": "czechia",
        "ivory coast": "ivory coast",
        "côte d'ivoire": "ivory coast",
        "cote d'ivoire": "ivory coast",
        "republic of ireland": "republic of ireland",
        "ireland": "republic of ireland",
        "dr congo": "dr congo",
        "congo dr": "dr congo",
        "curaçao": "curacao",
    }
    return aliases.get(key, key)


@lru_cache
def _load() -> dict[str, TeamRating]:
    path = DATA_DIR / "elo_ratings.csv"
    table: dict[str, TeamRating] = {}
    with path.open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            rating = TeamRating(
                team=row["team"],
                code=row["code"],
                confederation=row["confederation"],
                elo=float(row["elo"]),
                fifa_rank=int(row["fifa_rank"]),
            )
            table[_normalize(rating.team)] = rating
            table[_normalize(rating.code)] = rating
    return table


def all_teams() -> list[TeamRating]:
    """Lista de selecciones únicas ordenadas por ranking FIFA."""
    seen: dict[str, TeamRating] = {}
    for rating in _load().values():
        seen[rating.code] = rating
    return sorted(seen.values(), key=lambda r: r.fifa_rank)


def get_rating(name: str) -> TeamRating | None:
    return _load().get(_normalize(name))


# Elo medio aproximado de una selección de nivel mundialista, usado como
# referencia cuando un equipo no está en el dataset.
DEFAULT_ELO = 1700.0


def elo_of(name: str) -> float:
    rating = get_rating(name)
    return rating.elo if rating else DEFAULT_ELO
