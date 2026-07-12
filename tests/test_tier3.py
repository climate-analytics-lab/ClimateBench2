"""Tests for the Tier III scoring functions (proxy + perfect-model)."""

from __future__ import annotations

import numpy as np
import pytest

from climatebench2 import scoring


def test_proxy_site_consistency_perfect_and_poor_model() -> None:
    rng = np.random.default_rng(0)
    n_sites = 200
    truth = rng.normal(0, 2, n_sites)
    errors = np.full(n_sites, 1.0)
    proxies = truth + rng.normal(0, 1.0, n_sites)  # proxies = truth + error

    frac_good, z = scoring.proxy_site_consistency(truth, proxies, errors)
    assert frac_good > 0.9
    assert z.shape == (n_sites,)

    # A model off by 5 sigma everywhere fails nearly every site
    frac_bad, _ = scoring.proxy_site_consistency(truth + 5.0, proxies, errors)
    assert frac_bad < 0.1


def test_proxy_site_consistency_with_ensemble_and_nans() -> None:
    rng = np.random.default_rng(1)
    n_sites = 50
    truth = rng.normal(0, 1, n_sites)
    ensemble = truth[None, :] + rng.normal(0, 0.5, (8, n_sites))
    proxies = truth + rng.normal(0, 0.8, n_sites)
    errors = np.full(n_sites, 0.8)
    proxies[0] = np.nan  # excluded, not fatal
    frac, z = scoring.proxy_site_consistency(
        np.zeros(n_sites),
        proxies,
        errors,
        ensemble_values=ensemble,
    )
    assert 0.8 < frac <= 1.0
    assert np.isnan(z[0])

    with pytest.raises(ValueError, match="no valid proxy sites"):
        scoring.proxy_site_consistency(
            np.array([np.nan]),
            np.array([1.0]),
            np.array([1.0]),
        )


def test_sample_at_sites_nearest_and_wraparound() -> None:
    lats = np.array([-30.0, 0.0, 30.0])
    lons = np.array([0.0, 120.0, 240.0])
    field = np.arange(9, dtype=float).reshape(3, 3)
    # site at (2, 118): nearest (0, 120) -> row 1, col 1 -> 4
    # site at (-28, -20): lon -20 == 340 -> nearest col 0 (0) or 240? |340-0|=20 wraps, |340-240|=100 -> col 0
    sampled = scoring.sample_at_sites(
        field,
        lats,
        lons,
        np.array([2.0, -28.0]),
        np.array([118.0, -20.0]),
    )
    np.testing.assert_allclose(sampled, [4.0, 0.0])


def test_le_variance_ratio_and_pattern_correlation() -> None:
    rng = np.random.default_rng(2)
    n_members, n_space = 30, 500
    pattern = np.abs(np.sin(np.linspace(0, 3 * np.pi, n_space))) + 0.1
    truth = rng.normal(0, 1, (n_members, n_space)) * np.sqrt(pattern)

    # A perfect emulator of the spread
    pred_good = rng.normal(0, 1, (n_members, n_space)) * np.sqrt(pattern)
    ratio = scoring.le_variance_ratio(pred_good, truth)
    assert ratio == pytest.approx(1.0, abs=0.15)
    # 30-member variance estimates carry ~sqrt(2/29) sampling noise per
    # gridpoint, capping the recoverable pattern correlation well below 1
    corr = scoring.le_spread_pattern_correlation(pred_good, truth)
    assert corr > 0.5

    # A collapsed emulator: half the variance, flat pattern
    pred_flat = rng.normal(0, 0.7, (n_members, n_space))
    assert scoring.le_variance_ratio(pred_flat, truth) == pytest.approx(
        0.49 / pattern.mean(),
        rel=0.3,
    )
    assert scoring.le_spread_pattern_correlation(pred_flat, truth) < 0.3

    with pytest.raises(ValueError, match="zero variance"):
        scoring.le_variance_ratio(pred_good, np.zeros((3, 5)))


def test_tier3_diagnostics_importable_and_wired() -> None:
    climateeval = pytest.importorskip("climateeval")  # noqa: F841

    from climatebench2.diags import MidHoloceneMonsoonGate, PaleoProxyConsistencyGate
    from climatebench2.diags.tier1_physics import CB2ComplexDiagnostic

    assert issubclass(MidHoloceneMonsoonGate, CB2ComplexDiagnostic)
    assert issubclass(PaleoProxyConsistencyGate, CB2ComplexDiagnostic)
    (check,) = MidHoloceneMonsoonGate._gate_checks
    assert check.lower == 0.5  # mm/day, tier3.midholocene_monsoon
