"""Simulación Monte Carlo del Mundial 2026 completo (formato 48 equipos).

Formato 2026:
- 12 grupos de 4 (A..L), todos contra todos.
- Clasifican: 1° y 2° de cada grupo (24) + los 8 mejores 3° = 32.
- Eliminatoria directa: 32avos -> 16avos -> 8vos(QF) -> SF -> Final.

Se reutiliza el modelo de goles Elo->Poisson de `poisson.py`. Los partidos del
torneo se juegan en sede neutral, así que no se aplica ventaja de localía.
"""
from __future__ import annotations

import json

import numpy as np

from app.config import DATA_DIR
from app.model import strengths
from app.model.poisson import score_matrix
from app.services.ratings import all_teams, elo_of, get_rating

BASE_LAMBDA = 1.35
# Proporción de un partido que dura el alargue (30' sobre 90') — escala los goles.
# El alargue suele jugarse algo más cauto que el tiempo regular; 30/90 es la
# aproximación proporcional (null razonable, sin datos finos para afinarlo).
EXTRA_TIME_FRACTION = 30.0 / 90.0
# Sensibilidad de la tanda de penales a la diferencia de Elo: muy baja a propósito.
# Los penales son casi una moneda al aire; el mejor equipo apenas se favorece
# (0.0005 ⇒ una ventaja de 200 Elo da ~58%), con tope en [0.30, 0.70].
SHOOTOUT_ELO_SCALE = 0.0005
SHOOTOUT_CLIP = (0.30, 0.70)
GROUP_LETTERS = [chr(ord("A") + i) for i in range(12)]
# Etiquetas de las rondas alcanzadas (de menor a mayor).
STAGES = ["r32", "r16", "qf", "sf", "final", "champion"]


OFFICIAL_GROUPS_PATH = DATA_DIR / "groups_2026.json"


def official_groups() -> dict[str, list[str]] | None:
    """Grupos oficiales del Mundial 2026 desde data/groups_2026.json.

    Devuelve None si el archivo no existe o no es válido (12 grupos de 4).
    """
    if not OFFICIAL_GROUPS_PATH.exists():
        return None
    try:
        data = json.loads(OFFICIAL_GROUPS_PATH.read_text(encoding="utf-8"))
        groups = data["groups"]
    except (json.JSONDecodeError, KeyError, OSError):
        return None
    if len(groups) != 12 or any(len(t) != 4 for t in groups.values()):
        return None
    return groups


def default_groups() -> dict[str, list[str]]:
    """48 mejores selecciones (por ranking FIFA) repartidas en 12 grupos por bombos.

    Reparto serpenteado (snake) por pote: equilibra la fuerza entre grupos.
    Aproximación: no aplica las restricciones de confederación del sorteo real.
    """
    teams = [r.team for r in all_teams()][:48]
    groups: dict[str, list[str]] = {g: [] for g in GROUP_LETTERS}
    idx = 0
    for pot in range(4):
        order = GROUP_LETTERS if pot % 2 == 0 else GROUP_LETTERS[::-1]
        for g in order:
            groups[g].append(teams[idx])
            idx += 1
    return groups


def resolve_groups() -> tuple[dict[str, list[str]], bool]:
    """Devuelve (grupos, son_oficiales). Usa los oficiales si están disponibles."""
    official = official_groups()
    if official is not None:
        return official, True
    return default_groups(), False


class _Engine:
    """Cachea fuerzas y la distribución de marcadores por par para acelerar las sims.

    Usa el modelo Dixon-Coles ataque/defensa (app/model/strengths.py): los anfitriones
    reciben ventaja automáticamente y los goles totales dependen del cruce. Los
    marcadores se muestrean de la matriz Dixon-Coles (no de Poisson independientes),
    consistente con la predicción de cada partido.
    """

    def __init__(self, teams: list[str]):
        self.elo = {t: elo_of(t) for t in teams}
        self.rho = strengths.current_rho()
        self._samplers: dict[tuple[str, str, bool], tuple[np.ndarray, int]] = {}

    def _sampler(self, a: str, b: str, extra_time: bool) -> tuple[np.ndarray, int]:
        """(cumsum aplanada, n_columnas) de la matriz de marcadores del par a-b."""
        key = (a, b, extra_time)
        cached = self._samplers.get(key)
        if cached is None:
            la, lb = strengths.goal_lambdas(a, b, neutral=True, base_lambda=BASE_LAMBDA)
            if extra_time:  # solo se juegan 30' → menos goles esperados
                la, lb = la * EXTRA_TIME_FRACTION, lb * EXTRA_TIME_FRACTION
            matrix = score_matrix(la, lb, rho=self.rho)
            cached = (np.cumsum(matrix.ravel()), matrix.shape[1])
            self._samplers[key] = cached
        return cached

    def _draw(self, rng, a: str, b: str, extra_time: bool = False) -> tuple[int, int]:
        cumsum, cols = self._sampler(a, b, extra_time)
        idx = int(np.searchsorted(cumsum, rng.random() * cumsum[-1], side="right"))
        idx = min(idx, cumsum.size - 1)
        return idx // cols, idx % cols

    def play(self, rng, a: str, b: str) -> tuple[int, int]:
        return self._draw(rng, a, b)

    def knockout_winner(self, rng, a: str, b: str) -> str:
        ga, gb = self._draw(rng, a, b)
        if ga != gb:
            return a if ga > gb else b
        # Empate en los 90': se juega alargue (30').
        ea, eb = self._draw(rng, a, b, extra_time=True)
        if ea != eb:
            return a if ea > eb else b
        # Sigue empatado -> penales: casi una moneda al aire, leve sesgo por Elo.
        pa = 0.5 + SHOOTOUT_ELO_SCALE * (self.elo[a] - self.elo[b])
        pa = min(SHOOTOUT_CLIP[1], max(SHOOTOUT_CLIP[0], pa))
        return a if rng.random() < pa else b


KO_BRACKET_PATH = DATA_DIR / "ko_bracket_2026.json"

# Etiqueta de ronda alcanzada por el GANADOR de cada partido del árbol.
_TREE_STAGE = {
    **{m: "qf" for m in ("89", "90", "91", "92", "93", "94", "95", "96")},
    **{m: "sf" for m in ("97", "98", "99", "100")},
    **{m: "final" for m in ("101", "102")},
    "104": "champion",
}


def load_ko_bracket() -> dict | None:
    """Cuadro oficial de eliminatorias desde data/ko_bracket_2026.json, o None."""
    if not KO_BRACKET_PATH.exists():
        return None
    try:
        data = json.loads(KO_BRACKET_PATH.read_text(encoding="utf-8"))
        r32, tree = data["round_of_32"], data["tree"]
    except (json.JSONDecodeError, KeyError, OSError):
        return None
    if len(r32) != 16 or len(tree) != 15:
        return None
    return {"round_of_32": r32, "tree": tree}


# ---------------------- Fase de grupos con desempate FIFA ----------------------

def _result_between(results: dict, x: str, y: str) -> tuple[int, int]:
    """Goles (de x, de y) en el partido directo, sin importar el orden guardado."""
    if (x, y) in results:
        return results[(x, y)]
    gy, gx = results[(y, x)]
    return gx, gy


def _h2h_order(subset: list[str], results: dict, engine: _Engine) -> list[str]:
    """Ordena un subconjunto empatado por enfrentamiento directo (criterio FIFA)."""
    p = {t: 0 for t in subset}
    gd = {t: 0 for t in subset}
    gf = {t: 0 for t in subset}
    for i in range(len(subset)):
        for j in range(i + 1, len(subset)):
            x, y = subset[i], subset[j]
            gx, gy = _result_between(results, x, y)
            gf[x] += gx
            gf[y] += gy
            gd[x] += gx - gy
            gd[y] += gy - gx
            if gx > gy:
                p[x] += 3
            elif gy > gx:
                p[y] += 3
            else:
                p[x] += 1
                p[y] += 1
    return sorted(
        subset, key=lambda t: (p[t], gd[t], gf[t], engine.elo[t]), reverse=True
    )


def _group_standings(rng, engine: _Engine, teams: list[str]) -> list[dict]:
    """Round-robin de un grupo. Orden FIFA: Pts, DG, GF, enfrentamiento directo, Elo."""
    stats = {t: {"pts": 0, "gd": 0, "gf": 0} for t in teams}
    results: dict[tuple[str, str], tuple[int, int]] = {}
    for i in range(len(teams)):
        for j in range(i + 1, len(teams)):
            a, b = teams[i], teams[j]
            ga, gb = engine.play(rng, a, b)
            results[(a, b)] = (ga, gb)
            stats[a]["gf"] += ga
            stats[b]["gf"] += gb
            stats[a]["gd"] += ga - gb
            stats[b]["gd"] += gb - ga
            if ga > gb:
                stats[a]["pts"] += 3
            elif gb > ga:
                stats[b]["pts"] += 3
            else:
                stats[a]["pts"] += 1
                stats[b]["pts"] += 1

    # Orden primario por Pts, DG, GF; los empatados se resuelven por h2h.
    base = sorted(
        teams, key=lambda t: (stats[t]["pts"], stats[t]["gd"], stats[t]["gf"]), reverse=True
    )
    ordered: list[str] = []
    i = 0
    while i < len(base):
        j = i
        key = (stats[base[i]]["pts"], stats[base[i]]["gd"], stats[base[i]]["gf"])
        while j < len(base) and (
            stats[base[j]]["pts"], stats[base[j]]["gd"], stats[base[j]]["gf"]
        ) == key:
            j += 1
        tie = base[i:j]
        ordered.extend(_h2h_order(tie, results, engine) if len(tie) > 1 else tie)
        i = j
    return [{"team": t, **stats[t]} for t in ordered]


# ----------------------- Asignación oficial de los terceros ---------------------

def _third_slots(r32: dict) -> dict[str, set[str]]:
    """Para cada partido con un tercero, el conjunto de grupos permitidos."""
    slots = {}
    for match, pair in r32.items():
        if pair["away"].startswith("3:"):
            slots[match] = set(pair["away"][2:].split("/"))
    return slots


def _allocate_thirds(
    qualified_groups: list[str], slots: dict[str, set[str]]
) -> dict[str, str]:
    """Empareja los 8 grupos de terceros clasificados con los 8 cupos (criterio FIFA).

    Emparejamiento bipartito por caminos aumentantes: respeta el conjunto de grupos
    permitido por cada partido. (La tabla del Anexo C desempata cuál asignación
    concreta cuando hay varias válidas; acá se toma una válida determinista.)
    """
    slot_ids = sorted(slots.keys())
    group_to_slot: dict[str, str] = {}

    def augment(slot: str, visited: set[str]) -> bool:
        for g in qualified_groups:
            if g in slots[slot] and g not in visited:
                visited.add(g)
                cur = group_to_slot.get(g)
                if cur is None or augment(cur, visited):
                    group_to_slot[g] = slot
                    return True
        return False

    for slot in slot_ids:
        augment(slot, set())

    slot_to_group = {s: g for g, s in group_to_slot.items()}
    # Salvaguarda (no debería ocurrir con el cuadro oficial): cupos sin asignar.
    if len(slot_to_group) < len(slot_ids):
        leftover = [g for g in qualified_groups if g not in group_to_slot]
        for slot in slot_ids:
            if slot not in slot_to_group and leftover:
                slot_to_group[slot] = leftover.pop()
    return slot_to_group


# ----------------------------- Eliminatoria -----------------------------------

def _run_official_knockout(rng, engine, standings: dict, bracket: dict, reached: dict) -> str:
    """Juega el cuadro oficial (32avos -> final) y marca rondas alcanzadas."""
    winners = {L: standings[L][0]["team"] for L in standings}
    runners = {L: standings[L][1]["team"] for L in standings}
    thirds = {L: standings[L][2] for L in standings}

    ranked_third_groups = sorted(
        standings.keys(),
        key=lambda L: (
            thirds[L]["pts"], thirds[L]["gd"], thirds[L]["gf"], engine.elo[thirds[L]["team"]]
        ),
        reverse=True,
    )
    qualified = sorted(ranked_third_groups[:8])
    slot_to_group = _allocate_thirds(qualified, _third_slots(bracket["round_of_32"]))

    def resolve(slot: str) -> str:
        pos, letter = slot[0], slot[1]
        return winners[letter] if pos == "1" else runners[letter]

    result: dict[str, str] = {}
    for match, pair in bracket["round_of_32"].items():
        home = resolve(pair["home"])
        if pair["away"].startswith("3:"):
            away = thirds[slot_to_group[match]]["team"]
        else:
            away = resolve(pair["away"])
        reached[home]["r32"] += 1
        reached[away]["r32"] += 1
        w = engine.knockout_winner(rng, home, away)
        reached[w]["r16"] += 1
        result[match] = w

    for match in sorted(bracket["tree"], key=int):
        f1, f2 = bracket["tree"][match]
        w = engine.knockout_winner(rng, result[f1], result[f2])
        reached[w][_TREE_STAGE[match]] += 1
        result[match] = w

    return result["104"]


def simulate_tournament(
    groups: dict[str, list[str]], n: int, seed: int | None = None
) -> dict:
    teams = [t for g in groups.values() for t in g]
    engine = _Engine(teams)
    rng = np.random.default_rng(seed)
    reached = {t: {s: 0 for s in STAGES} for t in teams}
    bracket = load_ko_bracket()

    for _ in range(n):
        standings = {L: _group_standings(rng, engine, groups[L]) for L in groups}
        _run_official_knockout(rng, engine, standings, bracket, reached)

    table = []
    for t in teams:
        row = {"team": t, "elo": round(engine.elo[t])}
        for s in STAGES:
            row[s] = reached[t][s] / n
        table.append(row)
    table.sort(key=lambda r: r["champion"], reverse=True)
    return {
        "n_simulations": n,
        "groups": groups,
        "ranking": table,
        "official_bracket": bracket is not None,
    }
