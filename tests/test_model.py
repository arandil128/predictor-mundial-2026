"""Tests de sanidad del modelo y de la conversión de cuotas."""
import numpy as np
import pytest

from app.model import params, strengths
from app.model.montecarlo import simulate
from app.model.poisson import (
    calibrate_lambdas_to_market,
    lambdas_from_elo,
    outcome_probs,
    sample_from_matrix,
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
    sim = simulate(lam_h, lam_a, n=200_000, rho=0.0, seed=42)
    assert abs(sim.prob_home - analytic[0]) < 0.01
    assert abs(sim.prob_draw - analytic[1]) < 0.01
    assert abs(sim.prob_away - analytic[2]) < 0.01


def test_montecarlo_consistent_with_dixon_coles():
    """Muestrear de la matriz DC ⇒ Monte Carlo coincide con el modelo analítico
    también con la corrección de marcadores bajos (rho != 0)."""
    lam_h, lam_a, rho = 1.5, 1.2, -0.06
    analytic = outcome_probs(score_matrix(lam_h, lam_a, rho=rho))
    sim = simulate(lam_h, lam_a, n=200_000, rho=rho, seed=7)
    assert abs(sim.prob_home - analytic[0]) < 0.01
    assert abs(sim.prob_draw - analytic[1]) < 0.01
    assert abs(sim.prob_away - analytic[2]) < 0.01


def test_sample_from_matrix_reproduces_marginals():
    m = score_matrix(1.6, 1.1, rho=-0.05)
    rng = np.random.default_rng(0)
    home, away = sample_from_matrix(m, 100_000, rng)
    # La media muestral de goles ~ media analítica de la matriz.
    goals = np.arange(m.shape[0])
    exp_home = float((m.sum(axis=1) * goals).sum())
    assert abs(home.mean() - exp_home) < 0.03


def test_calibration_reproduces_market():
    target = (0.55, 0.25, 0.20)
    lam_h, lam_a = calibrate_lambdas_to_market(*target)
    home, draw, away = outcome_probs(score_matrix(lam_h, lam_a))
    assert abs(home - target[0]) < 0.02
    assert abs(away - target[2]) < 0.02


def test_elo_favours_stronger_team():
    lam_h, lam_a = lambdas_from_elo(2100, 1700, home_advantage_elo=55, base_lambda=1.35)
    assert lam_h > lam_a


def test_attack_defense_gradient_is_correct():
    """El gradiente analítico del ajuste coincide con diferencias finitas.

    Garantiza que scripts/calibrate.py y scripts/backtest.py optimizan la
    verosimilitud correcta (un gradiente mal calculado converge a parámetros malos).
    """
    from scipy.optimize import check_grad

    from app.model.fitting import ParsedMatches, attack_defense_objective

    rng = np.random.default_rng(0)
    n_teams, n = 5, 40
    pm = ParsedMatches(
        home_i=rng.integers(0, n_teams, n),
        away_i=rng.integers(0, n_teams, n),
        home_goals=rng.integers(0, 4, n).astype(float),
        away_goals=rng.integers(0, 4, n).astype(float),
        neutral=rng.integers(0, 2, n).astype(float),
        dates=[],
        comp=np.ones(n),
        names=[str(i) for i in range(n_teams)],
        name_to_idx={},
    )
    w = rng.uniform(0.5, 1.5, n)
    reg = 1.5
    x0 = rng.normal(0, 0.3, 2 + 2 * n_teams)
    f = lambda x: attack_defense_objective(x, pm, w, reg)[0]
    g = lambda x: attack_defense_objective(x, pm, w, reg)[1]
    assert check_grad(f, g, x0) < 1e-4


# ----------------------- Modelo de fuerzas (ataque/defensa) --------------------

def test_strengths_favours_stronger_team():
    lam_h, lam_a = strengths.goal_lambdas("Brazil", "Haiti", neutral=True)
    assert lam_h > lam_a  # el favorito marca más


def test_attack_defense_breaks_constant_total_goals():
    """El gran aporte sobre el Elo: los goles totales dependen del cruce.

    Un cruce desparejo (gran ataque vs. defensa floja) produce MÁS goles totales
    que el choque de dos defensas sólidas — algo imposible con razón-constante.
    """
    if not params.has_params():
        pytest.skip("Sin data/model_params.json calibrado (corré scripts/calibrate.py).")
    mismatch = sum(strengths.goal_lambdas("Spain", "Haiti", neutral=True))
    tight = sum(strengths.goal_lambdas("Argentina", "Brazil", neutral=True))
    assert mismatch > tight


def test_host_advantage_split():
    home_adv = params.global_params()["home_adv"]
    # Un anfitrión que enfrenta a un no-anfitrión recibe la ventaja, esté de local o no.
    assert strengths._advantage_split("Mexico", "Japan", neutral=True) == (home_adv, 0.0)
    assert strengths._advantage_split("Japan", "Mexico", neutral=True) == (0.0, home_adv)
    # Cancha neutral pura: ni anfitriones, o ambos anfitriones => sin ventaja.
    assert strengths._advantage_split("Japan", "Brazil", neutral=True) == (0.0, 0.0)
    assert strengths._advantage_split("Mexico", "United States", neutral=True) == (0.0, 0.0)


def test_host_boost_equals_exp_home_adv():
    if not params.has_params():
        pytest.skip("Sin data/model_params.json calibrado.")
    g = params.global_params()
    mx = params.team_strength(strengths._normalize("Mexico"))
    jp = params.team_strength(strengths._normalize("Japan"))
    no_host = float(np.exp(g["mu"] + mx["attack"] - jp["defense"]))
    host_lh, _ = strengths.goal_lambdas("Mexico", "Japan", neutral=True)
    assert host_lh > no_host
    assert abs(host_lh / no_host - np.exp(g["home_adv"])) < 1e-6


def test_host_advantage_is_slot_independent():
    if not params.has_params():
        pytest.skip("Sin data/model_params.json calibrado.")
    lh, _ = strengths.goal_lambdas("Mexico", "Japan", neutral=True)  # México de local
    _, la = strengths.goal_lambdas("Japan", "Mexico", neutral=True)  # México de visitante
    assert abs(lh - la) < 1e-9  # la ventaja sigue al anfitrión, no al casillero


# --------------------------- Mezcla mercado ↔ modelo ---------------------------

def _market(home, draw, away, books):
    from app.services.odds import MarketProbs

    return MarketProbs(home=home, draw=draw, away=away, bookmakers=books)


def _blend(market, weight=1.0):
    from app.model.blend import blend

    return blend("Brazil", "Haiti", neutral=True, base_lambda=1.35,
                 home_advantage_elo=55.0, market=market, market_weight=weight)


def test_blend_market_weight_scales_with_bookmakers():
    r_many = _blend(_market(0.5, 0.3, 0.2, books=10))
    r_few = _blend(_market(0.5, 0.3, 0.2, books=1))
    assert abs(r_many.market_weight - 1.0) < 1e-9   # ≥5 casas ⇒ peso pleno
    assert abs(r_few.market_weight - 0.2) < 1e-9    # 1/5 casas ⇒ peso atenuado


def test_blend_full_market_reproduces_market_probs():
    r = _blend(_market(0.55, 0.25, 0.20, books=8), weight=1.0)
    home, draw, away = outcome_probs(score_matrix(r.lam_home, r.lam_away, rho=r.rho))
    # Con peso pleno la mezcla (en log) reproduce las probabilidades del mercado.
    assert abs(home - 0.55) < 0.03
    assert abs(away - 0.20) < 0.03


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
