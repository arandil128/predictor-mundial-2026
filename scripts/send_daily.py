"""Envía el resumen diario de partidos por WhatsApp (para cron o prueba manual).

La app ya programa el envío a las 07:30 sola (mientras esté corriendo). Este script
sirve para dispararlo a mano, probar el formato, o agendarlo con cron / Programador
de tareas si preferís no depender del proceso web.

Uso:
    python scripts/send_daily.py             # envía a todos los teléfonos del JSON
    python scripts/send_daily.py --dry-run   # muestra el mensaje, no envía nada

Cron de ejemplo (07:30 todos los días):
    30 7 * * *  cd /app && python scripts/send_daily.py
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.services import daily  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description="Resumen diario de partidos por WhatsApp.")
    ap.add_argument("--dry-run", action="store_true", help="Mostrar el mensaje sin enviarlo.")
    args = ap.parse_args()

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

    if args.dry_run:
        day = daily.today_local()
        print(daily.format_daily_message(daily.todays_matches(day), day))
        return

    result = asyncio.run(daily.send_daily_summary(force=True))
    print(f"[{result.get('status')}] {result}")


if __name__ == "__main__":
    main()
