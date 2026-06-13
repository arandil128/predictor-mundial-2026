"""Cliente de Evolution API para enviar mensajes de WhatsApp.

Configuración por variables de entorno (ver .env.example):
- EVOLUTION_API_URL   URL del servidor de Evolution API (ej. https://evo.midominio.com)
- EVOLUTION_INSTANCE  nombre de la instancia
- EVOLUTION_API_KEY   API key de la instancia

Teléfonos destino en un JSON {nombre: telefono} (WHATSAPP_PHONES_FILE, por defecto
data/phones.json). El número va en formato internacional sin signos (ej. 5491123456789).
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import httpx

from app.config import DATA_DIR, get_settings


def phones_path() -> Path:
    settings = get_settings()
    return Path(settings.whatsapp_phones_file) if settings.whatsapp_phones_file else DATA_DIR / "phones.json"


def _only_digits(value) -> str:
    return re.sub(r"\D", "", str(value))


def load_phones() -> dict[str, str]:
    """Carga {nombre: telefono} desde la env var inline o el archivo JSON.

    Prioridad: WHATSAPP_PHONES (JSON inline, cómodo para deploy) > WHATSAPP_PHONES_FILE
    / data/phones.json. Devuelve {} si no hay nada válido.
    """
    settings = get_settings()
    data = None
    if settings.whatsapp_phones.strip():
        try:
            data = json.loads(settings.whatsapp_phones)
        except json.JSONDecodeError:
            data = None
    if data is None:
        path = phones_path()
        if not path.exists():
            return {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
    if not isinstance(data, dict):
        return {}
    # Ignora claves de metadatos como "_comment" (convención de los JSON del repo).
    return {
        str(name): _only_digits(num)
        for name, num in data.items()
        if not str(name).startswith("_") and _only_digits(num)
    }


async def send_text(client: httpx.AsyncClient, number: str, text: str) -> dict:
    """Envía un texto a un número vía Evolution API (formato v2: number + text)."""
    settings = get_settings()
    url = f"{settings.evolution_api_url.rstrip('/')}/message/sendText/{settings.evolution_instance}"
    headers = {"apikey": settings.evolution_api_key, "Content-Type": "application/json"}
    resp = await client.post(url, json={"number": number, "text": text}, headers=headers)
    resp.raise_for_status()
    return resp.json()


async def send_to_all(text: str) -> dict:
    """Envía el mismo texto a todos los teléfonos del JSON. Devuelve un resumen."""
    settings = get_settings()
    if not settings.has_whatsapp:
        return {"sent": 0, "failed": 0, "error": "WhatsApp no configurado (faltan EVOLUTION_*)."}
    phones = load_phones()
    if not phones:
        return {"sent": 0, "failed": 0, "error": f"Sin teléfonos en {phones_path()}."}

    detail: dict[str, str] = {}
    sent = failed = 0
    async with httpx.AsyncClient(timeout=20) as client:
        for name, number in phones.items():
            try:
                await send_text(client, number, text)
                detail[name] = "ok"
                sent += 1
            except Exception as exc:  # noqa: BLE001 — reportamos por destinatario, no abortamos
                detail[name] = f"error: {exc}"
                failed += 1
    return {"sent": sent, "failed": failed, "detail": detail}
