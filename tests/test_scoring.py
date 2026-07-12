"""Tests for the ClimateBench v2 scoring engine (climatebench2.scoring)."""

from __future__ import annotations

import numpy as np
import pytest

from climatebench2 import scoring

# ---------------------------------------------------------------------------
# CRPS
# ---------------------------------------------------------------------------


def test_crps_single_member_is_absolute_error() -> None:
    members = np.array([[1.0, 2.0, 5.0]])
    obs = np.array([1.5, 2.0, 3.0])
    crps = scoring.crps_ensemble(members, obs)
    np.testing.assert_allclose(crps, [0.5, 0.0, 2.0])


def test_crps_two_member_analytic() -> None:
    # For members {a, b} and obs y outside [a, b]:
    # CRPS = mean(|a-y|, |b-y|) - |a-b|/4
    members = np.array([[0.0], [2.0]])
    obs = np.array([3.0])
    expected = (3.0 + 1.0) / 2 - 2.0 / 4
    np.testing.assert_allclose(scoring.crps_ensemble(members, obs), [expected])


def test_crps_rewards_calibrated_spread() -> None:
    """A calibrated ensemble beats both a collapsed and an over-dispersed one."""
    rng = np.random.default_rng(1)
    n_time, n_members = 2000, 50
    truth = rng.normal(0.0, 1.0, n_time)
    calibrated = truth[None, :] * 0 + rng.normal(0.0, 1.0, (n_members, n_time))
    collapsed = np.zeros((n_members, n_time))
    overdispersed = rng.normal(0.0, 4.0, (n_members, n_time))
    s_cal = scoring.crps_ensemble(calibrated, truth).mean()
    s_col = scoring.crps_ensemble(collapsed, truth).mean()
    s_over = scoring.crps_ensemble(overdispersed, truth).mean()
    assert s_cal < s_col
    assert s_cal < s_over


def test_crps_shape_mismatch_raises() -> None:
    with pytest.raises(ValueError, match="time steps"):
        scoring.crps_ensemble(np.zeros((3, 5)), np.zeros(4))


# ---------------------------------------------------------------------------
# ESS correction
# ---------------------------------------------------------------------------


def test_lag1_autocorrelation_of_ar1() -> None:
    rng = np.random.default_rng(2)
    phi = 0.7
    x = np.zeros(20000)
    for i in range(1, x.size):
        x[i] = phi * x[i - 1] + rng.normal()
    assert scoring.lag1_autocorrelation(x) == pytest.approx(phi, abs=0.03)


def test_effective_sample_size_white_noise_and_ar1() -> None:
    rng = np.random.default_rng(3)
    white = rng.normal(size=1000)
    assert scoring.effective_sample_size(white) == pytest.approx(1000, rel=0.15)

    phi = 0.6
    ar1 = np.zeros(1000)
    for i in range(1, ar1.size):
        ar1[i] = phi * ar1[i - 1] + rng.normal()
    expected = 1000 * (1 - phi) / (1 + phi)
    assert scoring.effective_sample_size(ar1) == pytest.approx(expected, rel=0.25)


def test_crps_ess_score_fields() -> None:
    rng = np.random.default_rng(4)
    members = rng.normal(0, 1, (10, 300))
    obs = rng.normal(0, 1, 300)
    result = scoring.crps_ess_score(members, obs)
    assert result.n_members == 10
    assert result.n_time == 300
    assert 1.0 <= result.t_eff <= 300.0
    assert result.score > 0
    assert result.standard_error > 0


# ---------------------------------------------------------------------------
# piControl chunking
# ---------------------------------------------------------------------------


def test_chunked_statistic_std_mean_and_trend() -> None:
    rng = np.random.default_rng(5)
    series = rng.normal(0.0, 2.0, 1000)
    sigma_mean = scoring.chunked_statistic_std(series, 50, "mean")
    # std of the mean of 50 iid N(0,2) values ~ 2/sqrt(50)
    assert sigma_mean == pytest.approx(2.0 / np.sqrt(50), rel=0.4)
    sigma_trend = scoring.chunked_statistic_std(series, 50, "trend")
    assert sigma_trend > 0

    with pytest.raises(ValueError, match="at least 2"):
        scoring.chunked_statistic_std(series, 600)
    with pytest.raises(ValueError, match="Unknown statistic"):
        scoring.chunked_statistic_std(series, 50, "median")


# ---------------------------------------------------------------------------
# Ensemble consistency
# ---------------------------------------------------------------------------


def test_ensemble_consistency_obvious_cases() -> None:
    ensemble = np.array([1.0, 1.1, 0.9, 1.05, 0.95])
    consistent = scoring.ensemble_consistency(ensemble, 1.0)
    assert consistent.passes
    assert abs(consistent.z) < 1.0

    inconsistent = scoring.ensemble_consistency(ensemble, 5.0)
    assert not inconsistent.passes
    assert inconsistent.p_value < 0.05


def test_ensemble_consistency_sigma_terms_widen_the_test() -> None:
    ensemble = np.array([1.0, 1.1, 0.9])
    obs = 2.0
    narrow = scoring.ensemble_consistency(ensemble, obs)
    wide = scoring.ensemble_consistency(ensemble, obs, sigma_internal=0.8)
    assert not narrow.passes
    assert wide.passes
    assert abs(wide.z) < abs(narrow.z)


def test_ensemble_consistency_calibration() -> None:
    """Under the null, the test should reject ~5% of the time."""
    rng = np.random.default_rng(6)
    rejections = 0
    n_trials = 2000
    for _ in range(n_trials):
        ensemble = rng.normal(0, 1, 20)
        obs = rng.normal(0, 1)
        if not scoring.ensemble_consistency(ensemble, obs).passes:
            rejections += 1
    rate = rejections / n_trials
    assert rate == pytest.approx(0.05, abs=0.025)


def test_ensemble_consistency_errors() -> None:
    with pytest.raises(ValueError, match="empty"):
        scoring.ensemble_consistency(np.array([np.nan]), 0.0)
    with pytest.raises(ValueError, match="zero"):
        scoring.ensemble_consistency(np.array([1.0]), 0.0)  # 1 member, no sigmas


# ---------------------------------------------------------------------------
# EOF projection
# ---------------------------------------------------------------------------


def _synthetic_fields(
    rng: np.random.Generator,
    n_samples: int,
    amp1: float = 3.0,
    amp2: float = 1.0,
) -> np.ndarray:
    """Fields = two orthogonal sinusoidal modes with random amplitudes."""
    x = np.linspace(0, 2 * np.pi, 60)
    mode1, mode2 = np.sin(x), np.cos(2 * x)
    a = rng.normal(0, amp1, n_samples)
    b = rng.normal(0, amp2, n_samples)
    return a[:, None] * mode1[None, :] + b[:, None] * mode2[None, :]


def test_eof_basis_recovers_leading_mode() -> None:
    rng = np.random.default_rng(7)
    fields = _synthetic_fields(rng, 200)
    basis = scoring.eof_basis(fields, n_modes=2)
    assert basis.eofs.shape == (2, 60)
    # Leading EOF should be the sin mode (up to sign/normalization)
    x = np.linspace(0, 2 * np.pi, 60)
    corr = np.corrcoef(basis.eofs[0], np.sin(x))[0, 1]
    assert abs(corr) > 0.99
    assert basis.explained_variance[0] > basis.explained_variance[1]


def test_project_onto_eofs_roundtrip_scale() -> None:
    rng = np.random.default_rng(8)
    fields = _synthetic_fields(rng, 100)
    basis = scoring.eof_basis(fields, n_modes=2)
    pcs = scoring.project_onto_eofs(basis, fields)
    assert pcs.shape == (100, 2)
    # PC variance should match the basis explained variance
    np.testing.assert_allclose(
        pcs.var(axis=0, ddof=1),
        basis.explained_variance,
        rtol=1e-8,
    )


def test_field_consistency_pass_and_fail() -> None:
    rng = np.random.default_rng(9)
    variability = _synthetic_fields(rng, 300)
    ensemble = _synthetic_fields(rng, 25)
    obs_ok = _synthetic_fields(rng, 1)[0]
    passes, results = scoring.field_consistency(
        ensemble,
        obs_ok,
        variability,
        n_modes=2,
    )
    assert passes
    assert len(results) == 2

    # An observation far outside the variability envelope must fail
    obs_bad = obs_ok + 100.0 * np.sin(np.linspace(0, 2 * np.pi, 60))
    fails, _ = scoring.field_consistency(ensemble, obs_bad, variability, n_modes=2)
    assert not fails


def test_eof_basis_validates_ndim() -> None:
    with pytest.raises(ValueError, match="2-D"):
        scoring.eof_basis(np.zeros(10), 2)
