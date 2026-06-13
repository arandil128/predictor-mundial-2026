"""Servicio genérico de notificaciones por WhatsApp (reutilizable).

El núcleo de envío (`app/services/whatsapp.py`) y la lista de teléfonos son
genéricos: sirven para cualquier mensaje. Acá viven los **jobs**: cada uno arma el
TEXTO de un tipo de mensaje. Hoy hay uno (`matches`); para sumar otros más adelante
(p. ej. cumpleaños o agenda del día) alcanza con escribir una función que devuelva
el texto y registrarla en `JOBS`.

Correr un job (liviano, sin cargar el predictor):
    python scripts/notify.py matches [--dry-run]
"""
from __future__ import annotations

from collections.abc import Callable

from app.services import whatsapp


def _matches_message() -> str:
    """Resumen de los partidos de hoy (job `matches`).

    Devuelve "" en los días sin partidos: así el servicio NO manda nada en las
    jornadas de descanso (un texto vacío se interpreta como 'saltear').
    """
    from app.services import daily  # import local: mantiene el módulo liviano

    day = daily.today_local()
    matches = daily.todays_matches(day)
    if not matches:
        return ""
    return daily.format_daily_message(matches, day)


# Registro de jobs: nombre -> función que devuelve el texto a enviar.
# Para agregar uno nuevo: definí la función arriba y sumala a este diccionario.
#   def _birthdays_message() -> str: ...
#   JOBS["birthdays"] = _birthdays_message
JOBS: dict[str, Callable[[], str]] = {
    "matches": _matches_message,
}


def build_message(job: str) -> str:
    if job not in JOBS:
        raise KeyError(f"Job desconocido '{job}'. Disponibles: {', '.join(sorted(JOBS))}")
    return JOBS[job]()


async def run_job(job: str, dry_run: bool = False) -> dict:
    """Arma el mensaje del job y lo envía a todos los teléfonos (o lo previsualiza)."""
    try:
        text = build_message(job)
    except KeyError as exc:
        return {"status": "error", "error": str(exc)}
    if not text.strip():
        return {"status": "skipped", "job": job, "reason": "nada para enviar hoy"}
    if dry_run:
        return {"status": "dry_run", "job": job, "message": text}
    result = await whatsapp.send_to_all(text)
    status = "sent" if result.get("sent", 0) > 0 else "not_sent"
    return {"status": status, "job": job, "message": text, **result}
