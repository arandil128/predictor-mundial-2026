"""Cliente de fixtures del Mundial (football-data.org).

Si no hay clave, devuelve la lista de selecciones del dataset Elo para que los
selectores de la UI funcionen igual (sin partidos programados).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

import httpx

from app.config import get_settings
from app.services import cache
from app.services.ratings import all_teams

FD_MATCHES_URL = "https://api.football-data.org/v4/competitions/WC/matches"
_CACHE_KEY = "fixtures:world_cup"


@dataclass(frozen=True)
class Match:
    home_team: str
    away_team: str
    utc_date: str | None
    stage: str | None
    status: str | None


async def get_matches() -> list[dict]:
    """Próximos partidos del Mundial. Lista vacía si no hay clave o datos."""
    settings = get_settings()
    if not settings.football_data_api_key:
        return []
    cached = cache.get(_CACHE_KEY)
    if cached is not None:
        return cached
    headers = {"X-Auth-Token": settings.football_data_api_key}
    async with httpx.AsyncClient(timeout=15, headers=headers) as client:
        resp = await client.get(FD_MATCHES_URL)
        resp.raise_for_status()
        data = resp.json()
    matches: list[dict] = []
    for m in data.get("matches", []):
        home = (m.get("homeTeam") or {}).get("name")
        away = (m.get("awayTeam") or {}).get("name")
        if not home or not away:
            continue  # cruces aún sin definir (fase de grupos no sorteada)
        matches.append(
            asdict(
                Match(
                    home_team=home,
                    away_team=away,
                    utc_date=m.get("utcDate"),
                    stage=m.get("stage"),
                    status=m.get("status"),
                )
            )
        )
    cache.set(_CACHE_KEY, matches, settings.cache_ttl_seconds)
    return matches


def available_teams() -> list[dict]:
    """Lista de selecciones para poblar los selectores de la UI."""
    return [
        {"team": r.team, "code": r.code, "fifa_rank": r.fifa_rank}
        for r in all_teams()
    ]
