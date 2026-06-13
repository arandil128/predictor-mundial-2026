"""API FastAPI: sirve el frontend y expone /api/matches y /api/simulate."""
from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.config import STATIC_DIR, get_settings
from app.model import blend as blend_mod
from app.model import params as params_mod
from app.model import tournament as tournament_mod
from app.model.montecarlo import simulate
from app.services import fixtures, ratings, schedule
from app.services.odds import get_market_probs
from app.services.ratings import elo_of, get_rating

app = FastAPI(title="Predicción Mundial 2026")


@app.on_event("startup")
async def _start_daily_whatsapp() -> None:
    """Arranca el envío diario por WhatsApp si está configurado y habilitado.

    Si usás el servicio separado (scripts/notify.py por cron) poné
    DAILY_SCHEDULER_ENABLED=false para no duplicar envíos.
    """
    import asyncio

    from app.services import daily

    settings = get_settings()
    if settings.has_whatsapp and settings.daily_scheduler_enabled:
        asyncio.create_task(daily.scheduler_loop())


class SimulateRequest(BaseModel):
    home_team: str = Field(..., min_length=1)
    away_team: str = Field(..., min_length=1)
    n_simulations: int = Field(10_000, ge=1_000, le=200_000)


class TournamentRequest(BaseModel):
    n_simulations: int = Field(2_000, ge=200, le=20_000)


@app.get("/api/matches")
async def api_matches() -> dict:
    """Equipos disponibles + próximos partidos del Mundial (si hay clave)."""
    settings = get_settings()
    return {
        "teams": fixtures.available_teams(),
        "matches": await fixtures.get_matches(),
        "sources": {
            "odds": settings.has_odds,
            "fixtures": settings.has_fixtures,
        },
        "elo_refreshed_at": ratings.last_refresh(),
        "model_fitted_at": params_mod.fitted_at(),
        "names_es": ratings.names_es_map(),
    }


@app.post("/api/refresh-ratings")
async def api_refresh_ratings() -> dict:
    """Actualiza los ratings Elo en vivo (a requerimiento, fuente abierta gratuita)."""
    try:
        return await ratings.refresh_from_source()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, f"No se pudieron actualizar los ratings: {exc}")


@app.post("/api/simulate")
async def api_simulate(req: SimulateRequest) -> dict:
    if req.home_team.strip().lower() == req.away_team.strip().lower():
        raise HTTPException(400, "Elegí dos selecciones distintas.")

    settings = get_settings()
    elo_home = elo_of(req.home_team)
    elo_away = elo_of(req.away_team)

    market = await get_market_probs(req.home_team, req.away_team)
    # El Mundial se juega en cancha neutral (los anfitriones reciben ventaja
    # automáticamente dentro del modelo de fuerzas, ver app/model/strengths.py).
    result = blend_mod.blend(
        req.home_team,
        req.away_team,
        neutral=True,
        base_lambda=settings.base_lambda,
        home_advantage_elo=settings.home_advantage_elo,
        market=market,
        market_weight=settings.market_blend_weight,
    )

    sim = simulate(result.lam_home, result.lam_away, req.n_simulations, rho=result.rho)

    home_rating = get_rating(req.home_team)
    away_rating = get_rating(req.away_team)
    return {
        "home_team": home_rating.team if home_rating else req.home_team,
        "away_team": away_rating.team if away_rating else req.away_team,
        "elo": {"home": elo_home, "away": elo_away},
        "n_simulations": sim.n,
        "lambdas": {"home": result.lam_home, "away": result.lam_away},
        "prediction": {
            "home": sim.prob_home,
            "draw": sim.prob_draw,
            "away": sim.prob_away,
        },
        "expected_goals": {
            "home": sim.exp_goals_home,
            "away": sim.exp_goals_away,
        },
        "top_scorelines": sim.top_scorelines,
        "markets": {"over_2_5": sim.over_2_5, "btts": sim.btts},
        "total_goals_dist": sim.total_goals_dist,
        "components": {
            "model": result.model_probs,
            "market": result.market_probs,
            "market_weight": result.market_weight,
            "model_basis": result.model_basis,
        },
        "has_market": market is not None,
    }


@app.get("/api/fixture")
async def api_fixture() -> dict:
    """Los 104 partidos del Mundial (con día/hora/TV si están cargados)."""
    return schedule.build_fixture()


@app.post("/api/simulate-tournament")
def api_simulate_tournament(req: TournamentRequest) -> dict:
    """Simula el Mundial completo N veces y devuelve probabilidades por equipo.

    Endpoint sync a propósito: es CPU-bound y FastAPI lo corre en un threadpool
    para no bloquear el event loop. Usa los Elo vigentes (incluye refrescos).
    """
    groups, official = tournament_mod.resolve_groups()
    result = tournament_mod.simulate_tournament(groups, req.n_simulations)
    result["official_groups"] = official
    return result


@app.post("/api/send-daily")
async def api_send_daily(dry_run: bool = False) -> dict:
    """Envía el resumen de partidos de hoy por WhatsApp (manual).

    Con `?dry_run=true` devuelve el mensaje SIN enviarlo (para previsualizar).
    """
    from app.services import daily

    if dry_run:
        day = daily.today_local()
        matches = daily.todays_matches(day)
        return {
            "status": "dry_run",
            "date": day.isoformat(),
            "matches": len(matches),
            "message": daily.format_daily_message(matches, day),
        }
    return await daily.send_daily_summary(force=True)


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
