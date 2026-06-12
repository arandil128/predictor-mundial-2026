"""Genera data/fixture_2026.json a partir del calendario provisto (hora de Argentina).

- Fase de grupos: 72 partidos con equipos, día/hora/sede/TV (datos del usuario).
  Los 6 cupos de repechaje se resuelven al equipo confirmado (coinciden por
  posición con data/groups_2026.json).
- Eliminatoria: se generan las 32 llaves desde data/ko_bracket_2026.json (etiquetas
  'Ganador X'), con las fechas/sedes conocidas del 3er puesto y la final.

Re-ejecutá este script si actualizás el calendario:  python scripts/build_fixture.py
"""
import json
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"

# Canales (hora/fecha de Argentina). Los de Argentina suman TV abierta.
BASE_TV = ["Disney+", "DSports", "DGO", "Flow", "Paramount+", "Prime Video"]
ARG_TV = ["TV Pública", "Telefe", "TyC Sports"]


def tv_for(home: str, away: str) -> list[str]:
    return (ARG_TV + BASE_TV) if "Argentina" in (home, away) else list(BASE_TV)


# (n, grupo, local, visitante, fecha, hora, sede, ciudad) — equipos en inglés.
GROUP_MATCHES = [
    (1, "A", "Mexico", "South Africa", "2026-06-11", "16:00", "Estadio Azteca", "Ciudad de México"),
    (2, "A", "South Korea", "Czechia", "2026-06-11", "23:00", "Estadio Akron", "Guadalajara"),
    (3, "A", "Czechia", "South Africa", "2026-06-18", "13:00", "Mercedes-Benz Stadium", "Atlanta"),
    (4, "A", "Mexico", "South Korea", "2026-06-18", "22:00", "Estadio Akron", "Guadalajara"),
    (5, "A", "Czechia", "Mexico", "2026-06-24", "22:00", "Estadio Azteca", "Ciudad de México"),
    (6, "A", "South Africa", "South Korea", "2026-06-24", "22:00", "Estadio BBVA", "Monterrey"),
    (7, "B", "Canada", "Bosnia and Herzegovina", "2026-06-12", "16:00", "BMO Field", "Toronto"),
    (8, "B", "Qatar", "Switzerland", "2026-06-13", "16:00", "Levi's Stadium", "San Francisco Bay Area"),
    (9, "B", "Switzerland", "Bosnia and Herzegovina", "2026-06-18", "16:00", "SoFi Stadium", "Los Ángeles"),
    (10, "B", "Canada", "Qatar", "2026-06-18", "19:00", "BC Place", "Vancouver"),
    (11, "B", "Switzerland", "Canada", "2026-06-24", "16:00", "BC Place", "Vancouver"),
    (12, "B", "Bosnia and Herzegovina", "Qatar", "2026-06-24", "16:00", "Lumen Field", "Seattle"),
    (13, "C", "Brazil", "Morocco", "2026-06-13", "19:00", "MetLife Stadium", "Nueva York/Nueva Jersey"),
    (14, "C", "Haiti", "Scotland", "2026-06-13", "22:00", "Gillette Stadium", "Boston"),
    (15, "C", "Scotland", "Morocco", "2026-06-19", "19:00", "Gillette Stadium", "Boston"),
    (16, "C", "Brazil", "Haiti", "2026-06-19", "22:00", "Lincoln Financial Field", "Filadelfia"),
    (17, "C", "Scotland", "Brazil", "2026-06-24", "19:00", "Hard Rock Stadium", "Miami"),
    (18, "C", "Morocco", "Haiti", "2026-06-24", "19:00", "Mercedes-Benz Stadium", "Atlanta"),
    (19, "D", "United States", "Paraguay", "2026-06-12", "22:00", "SoFi Stadium", "Los Ángeles"),
    (20, "D", "Australia", "Turkey", "2026-06-14", "01:00", "BC Place", "Vancouver"),
    (21, "D", "Turkey", "Paraguay", "2026-06-20", "01:00", "Levi's Stadium", "San Francisco Bay Area"),
    (22, "D", "United States", "Australia", "2026-06-19", "16:00", "Lumen Field", "Seattle"),
    (23, "D", "Turkey", "United States", "2026-06-25", "23:00", "SoFi Stadium", "Los Ángeles"),
    (24, "D", "Paraguay", "Australia", "2026-06-25", "23:00", "Levi's Stadium", "San Francisco Bay Area"),
    (25, "E", "Germany", "Curacao", "2026-06-14", "14:00", "NRG Stadium", "Houston"),
    (26, "E", "Ivory Coast", "Ecuador", "2026-06-14", "20:00", "Lincoln Financial Field", "Filadelfia"),
    (27, "E", "Germany", "Ivory Coast", "2026-06-20", "17:00", "BMO Field", "Toronto"),
    (28, "E", "Ecuador", "Curacao", "2026-06-20", "21:00", "Arrowhead Stadium", "Kansas City"),
    (29, "E", "Ecuador", "Germany", "2026-06-25", "17:00", "MetLife Stadium", "Nueva York/Nueva Jersey"),
    (30, "E", "Curacao", "Ivory Coast", "2026-06-25", "17:00", "Lincoln Financial Field", "Filadelfia"),
    (31, "F", "Netherlands", "Japan", "2026-06-14", "17:00", "AT&T Stadium", "Dallas"),
    (32, "F", "Sweden", "Tunisia", "2026-06-14", "23:00", "Estadio BBVA", "Monterrey"),
    (33, "F", "Netherlands", "Sweden", "2026-06-20", "14:00", "NRG Stadium", "Houston"),
    (34, "F", "Tunisia", "Japan", "2026-06-21", "01:00", "Levi's Stadium", "San Francisco Bay Area"),
    (35, "F", "Japan", "Sweden", "2026-06-25", "20:00", "AT&T Stadium", "Dallas"),
    (36, "F", "Tunisia", "Netherlands", "2026-06-25", "20:00", "Arrowhead Stadium", "Kansas City"),
    (37, "G", "Iran", "New Zealand", "2026-06-15", "22:00", "SoFi Stadium", "Los Ángeles"),
    (38, "G", "Belgium", "Egypt", "2026-06-15", "16:00", "Lumen Field", "Seattle"),
    (39, "G", "Belgium", "Iran", "2026-06-21", "16:00", "SoFi Stadium", "Los Ángeles"),
    (40, "G", "New Zealand", "Egypt", "2026-06-21", "22:00", "BC Place", "Vancouver"),
    (41, "G", "Egypt", "Iran", "2026-06-27", "00:00", "Lumen Field", "Seattle"),
    (42, "G", "New Zealand", "Belgium", "2026-06-27", "00:00", "BC Place", "Vancouver"),
    (43, "H", "Spain", "Cape Verde", "2026-06-15", "13:00", "Mercedes-Benz Stadium", "Atlanta"),
    (44, "H", "Saudi Arabia", "Uruguay", "2026-06-15", "19:00", "Hard Rock Stadium", "Miami"),
    (45, "H", "Spain", "Saudi Arabia", "2026-06-21", "13:00", "Mercedes-Benz Stadium", "Atlanta"),
    (46, "H", "Uruguay", "Cape Verde", "2026-06-21", "19:00", "Hard Rock Stadium", "Miami"),
    (47, "H", "Cape Verde", "Saudi Arabia", "2026-06-26", "21:00", "NRG Stadium", "Houston"),
    (48, "H", "Uruguay", "Spain", "2026-06-26", "21:00", "Estadio Akron", "Guadalajara"),
    (49, "I", "France", "Senegal", "2026-06-16", "16:00", "MetLife Stadium", "Nueva York/Nueva Jersey"),
    (50, "I", "Iraq", "Norway", "2026-06-16", "19:00", "Gillette Stadium", "Boston"),
    (51, "I", "France", "Iraq", "2026-06-22", "18:00", "Lincoln Financial Field", "Filadelfia"),
    (52, "I", "Norway", "Senegal", "2026-06-22", "21:00", "MetLife Stadium", "Nueva York/Nueva Jersey"),
    (53, "I", "Norway", "France", "2026-06-26", "16:00", "Gillette Stadium", "Boston"),
    (54, "I", "Senegal", "Iraq", "2026-06-26", "16:00", "BMO Field", "Toronto"),
    (55, "J", "Argentina", "Algeria", "2026-06-16", "22:00", "Arrowhead Stadium", "Kansas City"),
    (56, "J", "Austria", "Jordan", "2026-06-17", "01:00", "Levi's Stadium", "San Francisco Bay Area"),
    (57, "J", "Argentina", "Austria", "2026-06-22", "14:00", "AT&T Stadium", "Dallas"),
    (58, "J", "Jordan", "Algeria", "2026-06-23", "00:00", "Levi's Stadium", "San Francisco Bay Area"),
    (59, "J", "Algeria", "Austria", "2026-06-27", "23:00", "Arrowhead Stadium", "Kansas City"),
    (60, "J", "Jordan", "Argentina", "2026-06-27", "23:00", "AT&T Stadium", "Dallas"),
    (61, "K", "Portugal", "DR Congo", "2026-06-17", "14:00", "NRG Stadium", "Houston"),
    (62, "K", "Uzbekistan", "Colombia", "2026-06-17", "23:00", "Estadio Azteca", "Ciudad de México"),
    (63, "K", "Portugal", "Uzbekistan", "2026-06-23", "14:00", "NRG Stadium", "Houston"),
    (64, "K", "Colombia", "DR Congo", "2026-06-23", "23:00", "Estadio Akron", "Guadalajara"),
    (65, "K", "Colombia", "Portugal", "2026-06-27", "20:30", "Hard Rock Stadium", "Miami"),
    (66, "K", "DR Congo", "Uzbekistan", "2026-06-27", "20:30", "Mercedes-Benz Stadium", "Atlanta"),
    (67, "L", "England", "Croatia", "2026-06-17", "17:00", "AT&T Stadium", "Dallas"),
    (68, "L", "Ghana", "Panama", "2026-06-17", "20:00", "BMO Field", "Toronto"),
    (69, "L", "England", "Ghana", "2026-06-23", "17:00", "Gillette Stadium", "Boston"),
    (70, "L", "Panama", "Croatia", "2026-06-23", "20:00", "BMO Field", "Toronto"),
    (71, "L", "Panama", "England", "2026-06-27", "18:00", "MetLife Stadium", "Nueva York/Nueva Jersey"),
    (72, "L", "Croatia", "Ghana", "2026-06-27", "18:00", "Lincoln Financial Field", "Filadelfia"),
]

# Fechas/sedes conocidas de la eliminatoria (el resto se confirma con los cruces).
KO_META = {
    103: ("2026-07-18", "Hard Rock Stadium, Miami"),
    104: ("2026-07-19", "MetLife Stadium, Nueva York/Nueva Jersey"),
}


def _match_stage(num: int) -> str:
    if 73 <= num <= 88:
        return "r32"
    if 89 <= num <= 96:
        return "r16"
    if 97 <= num <= 100:
        return "qf"
    if 101 <= num <= 102:
        return "sf"
    return "final"


def _slot_label(slot: str) -> str:
    if slot.startswith("3:"):
        return "3° (" + slot[2:] + ")"
    return f"{slot[0]}° {slot[1]}"


def build() -> list[dict]:
    matches: list[dict] = []
    for n, g, home, away, date, time, sede, ciudad in GROUP_MATCHES:
        matches.append(
            {
                "n": n, "stage": "group", "group": g,
                "home": home, "away": away,
                "date": date, "time": time,
                "venue": f"{sede}, {ciudad}", "tv": tv_for(home, away),
            }
        )

    bracket = json.loads((DATA / "ko_bracket_2026.json").read_text(encoding="utf-8"))
    for m, pair in bracket["round_of_32"].items():
        matches.append(
            {
                "n": int(m), "stage": "r32", "group": None,
                "home": None, "away": None,
                "home_label": _slot_label(pair["home"]),
                "away_label": _slot_label(pair["away"]),
                "date": None, "time": None, "venue": None, "tv": list(BASE_TV),
            }
        )
    for m, (f1, f2) in bracket["tree"].items():
        num = int(m)
        matches.append(
            {
                "n": num, "stage": _match_stage(num), "group": None,
                "home": None, "away": None,
                "home_label": f"Ganador {f1}", "away_label": f"Ganador {f2}",
                "date": None, "time": None, "venue": None, "tv": list(BASE_TV),
            }
        )
    matches.append(
        {
            "n": 103, "stage": "third", "group": None,
            "home": None, "away": None,
            "home_label": "Perdedor 101", "away_label": "Perdedor 102",
            "date": None, "time": None, "venue": None, "tv": list(BASE_TV),
        }
    )

    for mt in matches:
        if mt["n"] in KO_META and mt.get("home") is None:
            mt["date"], mt["venue"] = KO_META[mt["n"]]

    matches.sort(key=lambda x: x["n"])
    return matches


if __name__ == "__main__":
    out = {
        "_comment": "Generado por scripts/build_fixture.py desde el calendario provisto (hora de Argentina).",
        "timezone": "America/Argentina/Buenos_Aires",
        "matches": build(),
    }
    path = DATA / "fixture_2026.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Escrito {path} con {len(out['matches'])} partidos.")
