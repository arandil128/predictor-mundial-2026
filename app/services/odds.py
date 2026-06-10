"""Cliente de The Odds API: cuotas 1X2 -> probabilidades implícitas sin vig.

Si no hay clave configurada o el partido no tiene cuotas todavía (habitual hasta
cerca del torneo), devuelve None y el modelo trabaja solo con Elo/FIFA.
"""
from __future__ import annotations

from dataclasses import dataclass

import httpx

from app.config import get_settings
from app.services import cache
from app.services.ratings import _normalize

ODDS_URL = "https://api.the-odds-api.com/v4/sports/soccer_fifa_world_cup/odds"
_CACHE_KEY = "odds:world_cup:h2h"


@dataclass(frozen=True)
class MarketProbs:
    """Probabilidades 1X2 implícitas del mercado, ya normalizadas (sin vig)."""

    home: float
    draw: float
    away: float
    bookmakers: int


def implied_no_vig(home_odds: float, draw_odds: float, away_odds: float) -> MarketProbs:
    """Convierte cuotas decimales a probabilidades y elimina el margen de la casa."""
    raw = [1.0 / home_odds, 1.0 / draw_odds, 1.0 / away_odds]
    overround = sum(raw)
    home, draw, away = (p / overround for p in raw)
    return MarketProbs(home=home, draw=draw, away=away, bookmakers=1)


async def _fetch_all_events() -> list[dict]:
    settings = get_settings()
    if not settings.odds_api_key:
        return []
    cached = cache.get(_CACHE_KEY)
    if cached is not None:
        return cached
    params = {
        "apiKey": settings.odds_api_key,
        "regions": "eu,uk",
        "markets": "h2h",
        "oddsFormat": "decimal",
    }
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(ODDS_URL, params=params)
        resp.raise_for_status()
        events = resp.json()
    cache.set(_CACHE_KEY, events, settings.cache_ttl_seconds)
    return events


def _average_h2h(event: dict) -> MarketProbs | None:
    """Promedia las cuotas h2h de todas las casas de un evento y quita el vig."""
    home_name = event.get("home_team", "")
    away_name = event.get("away_team", "")
    homes, draws, aways = [], [], []
    for book in event.get("bookmakers", []):
        for market in book.get("markets", []):
            if market.get("key") != "h2h":
                continue
            prices: dict[str, float] = {}
            for outcome in market.get("outcomes", []):
                prices[_normalize(outcome["name"])] = float(outcome["price"])
            h = prices.get(_normalize(home_name))
            a = prices.get(_normalize(away_name))
            d = prices.get("draw")
            if h and a and d:
                homes.append(h)
                draws.append(d)
                aways.append(a)
    if not homes:
        return None
    avg = lambda xs: sum(xs) / len(xs)
    probs = implied_no_vig(avg(homes), avg(draws), avg(aways))
    return MarketProbs(probs.home, probs.draw, probs.away, bookmakers=len(homes))


async def get_market_probs(home_team: str, away_team: str) -> MarketProbs | None:
    """Devuelve las probabilidades de mercado para el cruce, o None si no hay datos."""
    events = await _fetch_all_events()
    h, a = _normalize(home_team), _normalize(away_team)
    for event in events:
        eh = _normalize(event.get("home_team", ""))
        ea = _normalize(event.get("away_team", ""))
        if {eh, ea} == {h, a}:
            probs = _average_h2h(event)
            if probs is None:
                return None
            # Reorientar al sentido local/visitante solicitado.
            if eh == h:
                return probs
            return MarketProbs(probs.away, probs.draw, probs.home, probs.bookmakers)
    return None
