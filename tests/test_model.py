"""Tests de sanidad del modelo y de la conversión de cuotas."""
import numpy as np

from app.model.montecarlo import simulate
from app.model.poisson import (
    calibrate_lambdas_to_market,
    lambdas_from_elo,
    outcome_probs,
    score_matrix,
)
from app.services.odds import implied_no_vig


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
