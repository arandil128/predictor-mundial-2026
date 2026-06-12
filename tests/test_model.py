"""Tests de sanidad del modelo y de la conversión de cuotas."""
import numpy as np

from app.model.montecarlo import simulate
from app.model.poisson import (
    calibrate_lambdas_to_market,
    lambdas_from_elo,
    outcome_probs,
    score_matrix,
)
import itertools

from app.model.tournament import (
    _allocate_thirds,
    _third_slots,
    default_groups,
    load_ko_bracket,
    official_groups,
    resolve_groups,
    simulate_tournament,
)
from app.services.odds import implied_no_vig
from app.services.ratings import get_rating


def test_implied_no_vig_sums_to_one():
    probs = implied_no_vig(2.0, 3.5, 4.0)
    total = probs.home + probs.draw + probs.away
    assert abs(total - 1.0) < 1e-9
    assert probs.home > probs.away  # cuota menor => más probable


def test_score_matrix_normalized():
    m = score_matrix(1.6, 1.1)
    assert abs(m.sum() - 1.0) < 1e-9
    home, draw, away = outcome_probs(m)
    assert abs(home + draw + away - 1.0) < 1e-9
    assert home > away  # local con más goles esperados


def test_montecarlo_converges_to_analytic():
    lam_h, lam_a = 1.7, 1.0
    analytic = outcome_probs(score_matrix(lam_h, lam_a, rho=0.0))
    sim = simulate(lam_h, lam_a, n=200_000, seed=42)
    # Monte Carlo (Poisson independiente) ~ analítico sin corrección DC.
    assert abs(sim.prob_home - analytic[0]) < 0.01
    assert abs(sim.prob_draw - analytic[1]) < 0.01
    assert abs(sim.prob_away - analytic[2]) < 0.01


def test_calibration_reproduces_market():
    target = (0.55, 0.25, 0.20)
    lam_h, lam_a = calibrate_lambdas_to_market(*target)
    home, draw, away = outcome_probs(score_matrix(lam_h, lam_a))
    assert abs(home - target[0]) < 0.02
    assert abs(away - target[2]) < 0.02


def test_elo_favours_stronger_team():
    lam_h, lam_a = lambdas_from_elo(2100, 1700, home_advantage_elo=55, base_lambda=1.35)
    assert lam_h > lam_a


def test_simulation_probs_are_valid():
    sim = simulate(1.4, 1.2, n=5000, seed=1)
    assert abs(sim.prob_home + sim.prob_draw + sim.prob_away - 1.0) < 1e-9
    assert 0 <= sim.over_2_5 <= 1
    assert len(sim.top_scorelines) == 5
    assert abs(sum(d["prob"] for d in sim.total_goals_dist) - 1.0) < 1e-9


def test_default_groups_structure():
    groups = default_groups()
    assert len(groups) == 12
    assert all(len(teams) == 4 for teams in groups.values())
    flat = [t for teams in groups.values() for t in teams]
    assert len(set(flat)) == 48  # 48 equipos únicos


def test_official_groups_valid_and_known():
    groups = official_groups()
    assert groups is not None, "Debe existir data/groups_2026.json válido"
    assert len(groups) == 12
    flat = [t for teams in groups.values() for t in teams]
    assert len(flat) == 48
    assert len(set(flat)) == 48  # sin equipos repetidos
    # Cada selección debe tener rating Elo conocido (no caer al default).
    missing = [t for t in flat if get_rating(t) is None]
    assert not missing, f"Equipos sin rating en el dataset: {missing}"


def test_resolve_groups_prefers_official():
    groups, official = resolve_groups()
    assert official is True
    assert len(groups) == 12


def test_fixture_has_104_matches():
    from app.services.schedule import build_fixture

    fx = build_fixture()
    matches = fx["matches"]
    assert len(matches) == 104
    # 72 de grupos con equipos definidos (simulables).
    playable = [m for m in matches if m.get("home") and m.get("away")]
    assert len(playable) == 72
    # Todos tienen nombre mostrable en español (equipo o etiqueta de cupo).
    assert all(m["home_es"] and m["away_es"] for m in matches)
    # Numeración 1..104 completa.
    assert sorted(m["n"] for m in matches) == list(range(1, 105))


def test_ko_bracket_loads():
    bracket = load_ko_bracket()
    assert bracket is not None
    assert len(bracket["round_of_32"]) == 16
    assert len(bracket["tree"]) == 15


def test_third_allocation_valid_for_all_combinations():
    """Para cada una de las 495 combinaciones de 8 terceros, la asignación es
    una bijección válida que respeta los grupos permitidos por cada partido."""
    bracket = load_ko_bracket()
    slots = _third_slots(bracket["round_of_32"])
    assert len(slots) == 8
    all_groups = list("ABCDEFGHIJKL")
    for combo in itertools.combinations(all_groups, 8):
        alloc = _allocate_thirds(sorted(combo), slots)
        assert len(alloc) == 8  # todos los cupos asignados
        assert set(alloc.keys()) == set(slots.keys())  # un cupo por partido
        assert set(alloc.values()) == set(combo)  # cada tercero usado una vez
        for match, group in alloc.items():
            assert group in slots[match]  # respeta los grupos permitidos


def test_tournament_probabilities_consistent():
    res = simulate_tournament(default_groups(), n=400, seed=7)
    ranking = res["ranking"]
    # P(campeón) suma ~1 y 32 equipos clasifican en promedio.
    assert abs(sum(r["champion"] for r in ranking) - 1.0) < 1e-9
    assert abs(sum(r["r32"] for r in ranking) - 32.0) < 1e-9
    # Rondas monótonas decrecientes para cada equipo.
    for r in ranking:
        assert r["r32"] >= r["r16"] >= r["qf"] >= r["sf"] >= r["final"] >= r["champion"]
    # El ranking viene ordenado por probabilidad de campeón.
    champs = [r["champion"] for r in ranking]
    assert champs == sorted(champs, reverse=True)
