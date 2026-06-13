"""Resumen diario de partidos por WhatsApp (Evolution API).

- `todays_matches`: los partidos del día (según el calendario del fixture).
- `format_daily_message`: arma el texto con hora y banderas.
- `send_daily_summary`: lo manda a todos los teléfonos (idempotente por día).
- `scheduler_loop`: tarea de fondo que dispara el envío a la hora configurada.

Formato de cada línea:  `19:00 hs   🇲🇽 México vs Sudáfrica 🇿🇦`
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from app.config import DATA_DIR, get_settings
from app.services import whatsapp
from app.services.flags import emoji_flag
from app.services.schedule import build_fixture

log = logging.getLogger("uvicorn.error")

# Marcador de "ya enviado hoy": evita duplicados ante reinicios o varios workers.
SENT_MARKER = DATA_DIR / ".daily_sent"

_DAYS_ES = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
_MONTHS_ES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
              "agosto", "septiembre", "octubre", "noviembre", "diciembre"]


def _tz() -> ZoneInfo:
    return ZoneInfo(get_settings().daily_timezone)


def today_local() -> date:
    """Fecha de hoy en la zona horaria configurada (el fixture está en hora argentina)."""
    return datetime.now(_tz()).date()


def _format_date_es(day: date) -> str:
    return f"{_DAYS_ES[day.weekday()]} {day.day} de {_MONTHS_ES[day.month - 1]}"


def todays_matches(day: date | None = None) -> list[dict]:
    """Partidos cuyo `date` coincide con el día dado, ordenados por hora."""
    day = day or today_local()
    iso = day.isoformat()
    matches = [m for m in build_fixture()["matches"] if m.get("date") == iso]
    matches.sort(key=lambda m: (m.get("time") or "99:99"))
    return matches


def format_daily_message(matches: list[dict], day: date | None = None) -> str:
    day = day or today_local()
    header = f"⚽ *Partidos de hoy* — {_format_date_es(day)}"
    if not matches:
        return f"{header}\n\nHoy no hay partidos del Mundial."
    lines = [header, ""]
    for m in matches:
        t = m.get("time") or "--:--"
        hf = emoji_flag(m.get("home_code"))
        af = emoji_flag(m.get("away_code"))
        hf = f"{hf} " if hf else ""
        af = f" {af}" if af else ""
        lines.append(f"{t} hs   {hf}{m.get('home_es', '')} vs {m.get('away_es', '')}{af}")
    return "\n".join(lines)


def _already_sent(iso: str) -> bool:
    try:
        return SENT_MARKER.read_text(encoding="utf-8").strip() == iso
    except OSError:
        return False


def _mark_sent(iso: str) -> None:
    try:
        SENT_MARKER.write_text(iso, encoding="utf-8")
    except OSError:
        pass


async def send_daily_summary(force: bool = False) -> dict:
    """Envía el resumen del día por WhatsApp. `force` ignora el marcador anti-duplicado."""
    day = today_local()
    iso = day.isoformat()
    if not force and _already_sent(iso):
        return {"status": "skipped", "reason": "ya enviado hoy", "date": iso}

    matches = todays_matches(day)
    if not matches:
        _mark_sent(iso)  # marcamos el día para no recalcular; no se envía nada
        return {"status": "no_matches", "date": iso}

    message = format_daily_message(matches, day)
    result = await whatsapp.send_to_all(message)
    sent_ok = result.get("sent", 0) > 0
    if sent_ok:
        _mark_sent(iso)
    return {
        "status": "sent" if sent_ok else "not_sent",
        "date": iso,
        "matches": len(matches),
        "message": message,
        **result,
    }


def _parse_hhmm(value: str) -> tuple[int, int]:
    try:
        hh, mm = value.split(":")
        return int(hh), int(mm)
    except (ValueError, AttributeError):
        return 7, 30


async def scheduler_loop() -> None:
    """Duerme hasta la hora configurada cada día y dispara el envío."""
    settings = get_settings()
    hh, mm = _parse_hhmm(settings.daily_send_time)
    log.info("Resumen diario por WhatsApp activo: %02d:%02d hs (%s)", hh, mm, settings.daily_timezone)
    while True:
        now = datetime.now(_tz())
        target = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
        if target <= now:
            target += timedelta(days=1)
        await asyncio.sleep((target - now).total_seconds())
        try:
            result = await send_daily_summary()
            log.info("Resumen diario: %s (%s)", result.get("status"), result.get("date"))
        except Exception:  # noqa: BLE001 — un fallo no debe matar el loop
            log.exception("Error enviando el resumen diario por WhatsApp")
