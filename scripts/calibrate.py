"""Calibra el modelo de goles con datos abiertos de partidos internacionales.

Ajusta un modelo **Dixon-Coles** ataque/defensa por máxima verosimilitud (ver
app/model/fitting.py para la matemática) y escribe data/model_params.json, que la
app carga al arrancar. Cada selección obtiene un parámetro de **ataque** (cuánto
marca) y otro de **defensa** (cuánto evita que le marquen) independientes — esto
rompe el supuesto de "goles totales constantes" del modelo Elo.

Fuente (dominio público, CC0): https://github.com/martj42/international_results

Uso:
    python scripts/calibrate.py
    python scripts/calibrate.py --since 2014 --half-life 1095 --reg 5
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import httpx
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.config import DATA_DIR  # noqa: E402
from app.model import fitting  # noqa: E402
from app.services.ratings import _normalize, all_teams  # noqa: E402

RESULTS_URL = (
    "https://raw.githubusercontent.com/martj42/international_results/master/results.csv"
)
SOURCE_LABEL = "martj42/international_results (dominio público, CC0)"
MIN_MATCHES = 8  # menos partidos que esto ⇒ el equipo cae al Elo en runtime


def download_results() -> str:
    print(f"Descargando datos de {RESULTS_URL} …")
    resp = httpx.get(RESULTS_URL, timeout=60)
    resp.raise_for_status()
    print(f"  {len(resp.content):,} bytes")
    return resp.text


def main() -> None:
    ap = argparse.ArgumentParser(description="Calibra el modelo de goles (Dixon-Coles).")
    ap.add_argument("--since", type=int, default=2010, help="Año inicial (default 2010).")
    ap.add_argument("--half-life", type=float, default=1095.0,
                    help="Vida media del peso por recencia, en días (default ~3 años).")
    ap.add_argument("--reg", type=float, default=5.0,
                    help="Fuerza del ridge sobre ataque/defensa (default 5).")
    ap.add_argument("--out", type=Path, default=DATA_DIR / "model_params.json")
    args = ap.parse_args()

    try:  # la consola de Windows (cp1252) no encodea μ/ρ
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

    text = download_results()
    since = date(args.since, 1, 1)
    pm = fitting.parse_matches(text, since)
    print(f"Partidos con marcador desde {since}: {pm.n_matches:,} · selecciones: {pm.n_teams}")
    if pm.n_matches < 1000:
        raise SystemExit("Muy pocos partidos; ampliá la ventana con --since.")

    fr = fitting.fit(pm, args.half_life, args.reg, as_of=date.today())
    print(f"Ajuste GLM: μ={fr.mu:.3f} · ventaja_local={fr.home_adv:.3f} · ρ={fr.rho:.4f}")

    counts = np.bincount(pm.home_i, minlength=pm.n_teams) + np.bincount(pm.away_i, minlength=pm.n_teams)
    teams = {}
    for k, raw in enumerate(pm.names):
        if counts[k] < MIN_MATCHES:
            continue
        teams[_normalize(raw)] = {
            "name": raw,
            "attack": round(float(fr.attack[k]), 4),
            "defense": round(float(fr.defense[k]), 4),
            "matches": int(counts[k]),
        }

    payload = {
        "source": SOURCE_LABEL,
        "fitted_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "window_since": str(since),
        "half_life_days": args.half_life,
        "ridge": args.reg,
        "n_matches": int(pm.n_matches),
        "global": {
            "mu": round(fr.mu, 4),
            "home_adv": round(fr.home_adv, 4),
            "rho": round(fr.rho, 4),
        },
        "teams": teams,
    }
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nEscrito {args.out} · {len(teams)} selecciones con fuerza ajustada.")

    wc = {_normalize(r.team) for r in all_teams()}
    fitted = [(v["name"], v["attack"], v["defense"]) for k, v in teams.items() if k in wc]
    top_atk = sorted(fitted, key=lambda r: r[1], reverse=True)[:8]
    top_def = sorted(fitted, key=lambda r: r[2], reverse=True)[:8]  # más alto = mejor defensa
    print("\nTop ataque (Mundial):  " + ", ".join(f"{n} {a:+.2f}" for n, a, _ in top_atk))
    print("Top defensa (Mundial): " + ", ".join(f"{n} {d:+.2f}" for n, _, d in top_def))


if __name__ == "__main__":
    main()
