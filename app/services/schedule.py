"""Construye el fixture de los 104 partidos del Mundial 2026 para la UI.

- Si existe data/fixture_2026.json (los datos que cargás vos: día/hora/sede/TV),
  se usa tal cual.
- Si no, se genera automáticamente a partir de los grupos oficiales y el cuadro
  de eliminatorias, con los campos de día/hora/TV vacíos (listos para completar).

Cada partido se enriquece con los nombres en español.
"""
from __future__ import annotations

import json

from app.config import DATA_DIR
from app.model.tournament import load_ko_bracket, resolve_groups
from app.services.ratings import get_rating, name_es, names_es_map

FIXTURE_PATH = DATA_DIR / "fixture_2026.json"

STAGE_ES = {
    "group": "Fase de grupos",
    "r32": "Dieciseisavos",
    "r16": "Octavos",
    "qf": "Cuartos",
    "sf": "Semifinal",
    "third": "Tercer puesto",
    "final": "Final",
}


def _match_stage(num: int) -> str:
    if 1 <= num <= 72:
        return "group"
    if 73 <= num <= 88:
        return "r32"
    if 89 <= num <= 96:
        return "r16"
    if 97 <= num <= 100:
        return "qf"
    if 101 <= num <= 102:
        return "sf"
    if num == 103:
        return "third"
    return "final"


def _slot_label(slot: str) -> str:
    """'1A'->'1° A', '2B'->'2° B', '3:A/B/C'->'3° (A/B/C)'."""
    if slot.startswith("3:"):
        return "3° (" + slot[2:] + ")"
    return f"{slot[0]}° {slot[1]}"


def _empty_meta() -> dict:
    return {"date": None, "time": None, "venue": None, "tv": []}


def _canonical_team(name: str | None) -> str | None:
    """Resuelve un equipo a su nombre canónico (inglés) desde inglés, código o español.

    Permite que el JSON del fixture use cualquiera de las tres formas.
    """
    if not name:
        return None
    rating = get_rating(name)  # maneja nombre en inglés o código (ej. 'MEX')
    if rating:
        return rating.team
    es_to_en = {v: k for k, v in names_es_map().items()}
    return es_to_en.get(name, name)


def _generate() -> list[dict]:
    """Genera los 104 partidos a partir de grupos + cuadro (sin día/hora/TV)."""
    groups, _ = resolve_groups()
    matches: list[dict] = []

    n = 0
    for letter in sorted(groups):
        teams = groups[letter]
        for i in range(len(teams)):
            for j in range(i + 1, len(teams)):
                n += 1
                matches.append(
                    {
                        "n": n,
                        "stage": "group",
                        "group": letter,
                        "home": teams[i],
                        "away": teams[j],
                        **_empty_meta(),
                    }
                )

    bracket = load_ko_bracket()
    if bracket:
        for m in sorted(bracket["round_of_32"], key=int):
            pair = bracket["round_of_32"][m]
            matches.append(
                {
                    "n": int(m),
                    "stage": "r32",
                    "group": None,
                    "home": None,
                    "away": None,
                    "home_label": _slot_label(pair["home"]),
                    "away_label": _slot_label(pair["away"]),
                    **_empty_meta(),
                }
            )
        for m in sorted(bracket["tree"], key=int):
            f1, f2 = bracket["tree"][m]
            matches.append(
                {
                    "n": int(m),
                    "stage": _match_stage(int(m)),
                    "group": None,
                    "home": None,
                    "away": None,
                    "home_label": f"Ganador {f1}",
                    "away_label": f"Ganador {f2}",
                    **_empty_meta(),
                }
            )

        # Partido por el tercer puesto (#103): perdedores de las semifinales.
        matches.append(
            {
                "n": 103,
                "stage": "third",
                "group": None,
                "home": None,
                "away": None,
                "home_label": "Perdedor 101",
                "away_label": "Perdedor 102",
                **_empty_meta(),
            }
        )

    matches.sort(key=lambda m: m["n"])
    return matches


def build_fixture() -> dict:
    """Devuelve {matches, source}. 'file' si vino del JSON cargado, 'auto' si no."""
    source = "auto"
    matches: list[dict] | None = None
    if FIXTURE_PATH.exists():
        try:
            data = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
            matches = data["matches"]
            source = "file"
        except (json.JSONDecodeError, KeyError, OSError):
            matches = None
    if matches is None:
        matches = _generate()

    for m in matches:
        if source == "file":
            # Normaliza los equipos a su nombre canónico para que /api/simulate funcione.
            m["home"] = _canonical_team(m.get("home"))
            m["away"] = _canonical_team(m.get("away"))
        home, away = m.get("home"), m.get("away")
        m["home_es"] = name_es(home) if home else m.get("home_label", "")
        m["away_es"] = name_es(away) if away else m.get("away_label", "")
        # Código FIFA (ARG, BRA…) para que el frontend muestre la bandera.
        rh = get_rating(home) if home else None
        ra = get_rating(away) if away else None
        m["home_code"] = rh.code if rh else None
        m["away_code"] = ra.code if ra else None
        m["stage_es"] = STAGE_ES.get(m.get("stage"), "")
        m.setdefault("tv", [])
    return {"matches": matches, "source": source}
