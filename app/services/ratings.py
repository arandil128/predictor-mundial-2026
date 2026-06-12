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


@lru_cache
def _names_es() -> dict[str, str]:
    """Mapa nombre-en-inglés -> nombre-en-español desde data/teams_es.json."""
    path = DATA_DIR / "teams_es.json"
    if not path.exists():
        return {}
    import json

    try:
        return json.loads(path.read_text(encoding="utf-8")).get("names", {})
    except (json.JSONDecodeError, OSError):
        return {}


def name_es(name: str) -> str:
    """Nombre en español de una selección (cae al nombre original si no está)."""
    return _names_es().get(name, name)


def names_es_map() -> dict[str, str]:
    """Mapa completo inglés->español para que el frontend traduzca."""
    return dict(_names_es())


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
    key = _normalize(name)
    if key in _overrides:
        return _overrides[key]
    rating = get_rating(name)
    return rating.elo if rating else DEFAULT_ELO


# --- Refresco a requerimiento de los ratings Elo (fuente abierta, sin clave) ---
#
# eloratings.net publica dos archivos gratuitos: World.tsv (código->Elo actual)
# y en.teams.tsv (código->nombre). Cruzamos por NOMBRE (robusto) y guardamos los
# valores como "overrides" en memoria. NO hay polling automático: solo se dispara
# cuando el usuario lo pide (botón/endpoint), para no gastar nada y ser predecible.
import httpx  # noqa: E402  (import local para mantener el módulo liviano arriba)
from datetime import datetime, timezone  # noqa: E402

ELO_NAMES_URL = "https://www.eloratings.net/en.teams.tsv"
ELO_WORLD_URL = "https://www.eloratings.net/World.tsv"

_overrides: dict[str, float] = {}
_last_refresh: str | None = None


def last_refresh() -> str | None:
    """ISO timestamp del último refresco en vivo, o None si nunca se hizo."""
    return _last_refresh


async def refresh_from_source() -> dict:
    """Descarga los Elo actuales y actualiza los overrides en memoria."""
    global _last_refresh
    async with httpx.AsyncClient(timeout=20) as client:
        names_resp = await client.get(ELO_NAMES_URL)
        names_resp.raise_for_status()
        world_resp = await client.get(ELO_WORLD_URL)
        world_resp.raise_for_status()

    code2name: dict[str, str] = {}
    for line in names_resp.text.splitlines():
        parts = line.split("\t")
        if len(parts) >= 2 and parts[0]:
            code2name[parts[0]] = parts[1]

    name2elo: dict[str, float] = {}
    for line in world_resp.text.splitlines():
        cols = line.split("\t")
        if len(cols) > 3 and cols[2] in code2name:
            try:
                name2elo[_normalize(code2name[cols[2]])] = float(cols[3])
            except ValueError:
                continue

    new_overrides: dict[str, float] = {}
    updated = 0
    for rating in all_teams():
        key = _normalize(rating.team)
        if key in name2elo:
            elo = name2elo[key]
            new_overrides[key] = elo
            new_overrides[_normalize(rating.code)] = elo
            updated += 1

    _overrides.clear()
    _overrides.update(new_overrides)
    _last_refresh = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return {
        "updated": updated,
        "total": len(all_teams()),
        "refreshed_at": _last_refresh,
    }
