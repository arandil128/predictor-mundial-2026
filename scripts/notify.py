"""Servicio de notificaciones por WhatsApp: corre un *job* y lo manda a los teléfonos.

LIVIANO: no carga el predictor (numpy/scipy/FastAPI). Pensado para correr por cron /
tarea programada, mandar, y terminar (cero consumo en reposo). Reutilizable para
varios tipos de mensaje (hoy `matches`; más adelante cumpleaños, agenda, etc.).

Uso:
    python scripts/notify.py matches             # manda el resumen de partidos de hoy
    python scripts/notify.py matches --dry-run   # muestra el mensaje, no envía
    python scripts/notify.py --list              # lista los jobs disponibles

Cron de ejemplo (07:30 todos los días):
    30 7 * * *  cd /app && python scripts/notify.py matches
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.services import notifier  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description="Notificaciones por WhatsApp (Evolution API).")
    ap.add_argument("job", nargs="?", help="Job a correr (ej. matches).")
    ap.add_argument("--dry-run", action="store_true", help="Mostrar el mensaje sin enviarlo.")
    ap.add_argument("--list", action="store_true", help="Listar los jobs disponibles.")
    args = ap.parse_args()

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

    if args.list or not args.job:
        print("Jobs disponibles:", ", ".join(sorted(notifier.JOBS)))
        return

    result = asyncio.run(notifier.run_job(args.job, dry_run=args.dry_run))
    if args.dry_run and "message" in result:
        print(result["message"])
    else:
        print(f"[{result.get('status')}] {result}")


if __name__ == "__main__":
    main()
