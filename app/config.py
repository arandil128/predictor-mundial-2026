"""Configuración central de la app, leída desde variables de entorno / .env."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
STATIC_DIR = BASE_DIR / "static"


class Settings(BaseSettings):
    """Parámetros de la aplicación. Todas las claves son opcionales."""

    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    odds_api_key: str = ""
    football_data_api_key: str = ""
    api_football_key: str = ""

    # Peso del mercado en la mezcla mercado<->modelo (0..1).
    market_blend_weight: float = 0.65
    # TTL de caché para respuestas de APIs externas, en segundos.
    cache_ttl_seconds: int = 300

    # Ventaja de localía expresada en puntos Elo equivalentes.
    home_advantage_elo: float = 55.0
    # Goles esperados base por equipo en un partido equilibrado.
    base_lambda: float = 1.35

    # --- WhatsApp: resumen diario de partidos vía Evolution API ---
    evolution_api_url: str = ""      # URL del servidor de Evolution API
    evolution_instance: str = ""     # nombre de la instancia
    evolution_api_key: str = ""      # API key de la instancia
    whatsapp_phones_file: str = ""   # ruta al JSON {nombre: telefono} (default data/phones.json)
    whatsapp_phones: str = ""        # alternativa: el JSON {nombre: telefono} inline (útil en deploy)
    daily_send_time: str = "07:30"   # hora del envío diario (HH:MM)
    daily_timezone: str = "America/Argentina/Buenos_Aires"
    # Scheduler dentro de la app web. Apagalo (false) si usás el servicio separado
    # (scripts/notify.py por cron), para no enviar dos veces.
    daily_scheduler_enabled: bool = True

    @property
    def has_odds(self) -> bool:
        return bool(self.odds_api_key)

    @property
    def has_fixtures(self) -> bool:
        return bool(self.football_data_api_key or self.api_football_key)

    @property
    def has_whatsapp(self) -> bool:
        return bool(self.evolution_api_url and self.evolution_instance and self.evolution_api_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()
