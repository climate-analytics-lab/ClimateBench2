"""Tests for the Phase-4 physics additions and baselines."""

from __future__ import annotations

import numpy as np
import pytest

from climatebench2 import baselines, physics

# ---------------------------------------------------------------------------
# I.3b geostrophic balance
# ---------------------------------------------------------------------------


def test_geostrophic_wind_recovers_balanced_flow() -> None:
    """A zg field built from a known u_g must be recovered exactly."""
    lats = np.linspace(-80, 80, 81)
    lons = np.linspace(0, 355, 72)
    phi = np.deg2rad(lats)
    # Choose Z(φ) with dZ/dφ = -cos φ · sin φ · A  → u_g = (g A / (2Ω a)) · cos φ
    amp = 500.0
    z_profile = amp * 0.5 * np.cos(phi) ** 2
    zg = np.broadcast_to(z_profile[:, None], (81, 72))
    ug = physics.geostrophic_wind_u(zg, lats)
    # analytic: dZ/dy = -A cosφ sinφ / a ; u_g = g A cosφ sinφ / (f a) with
    # f = 2Ω sinφ → u_g = g A cosφ / (2Ω a)
    expected = (
        physics.GRAVITY * amp * np.cos(phi) / (2 * physics.OMEGA_EARTH * physics.EARTH_RADIUS_M)
    )
    band = (np.abs(lats) >= 30) & (np.abs(lats) <= 60)
    np.testing.assert_allclose(ug[band, 0], expected[band], rtol=0.01)
    # |lat| < 10 is masked
    assert np.isnan(ug[np.abs(lats) < 10]).all()


def test_midlatitude_pattern_correlation_perfect_and_anticorrelated() -> None:
    rng = np.random.default_rng(0)
    lats = np.linspace(-80, 80, 41)
    field = rng.normal(0, 1, (10, 41, 36))
    assert physics.midlatitude_pattern_correlation(
        field,
        field,
        lats,
    ) == pytest.approx(1.0)
    assert physics.midlatitude_pattern_correlation(
        field,
        -field,
        lats,
    ) == pytest.approx(-1.0)
    noisy = 0.9 * field + 0.1 * rng.normal(0, 1, field.shape)
    rho = physics.midlatitude_pattern_correlation(field, noisy, lats)
    assert 0.95 < rho < 1.0


# ---------------------------------------------------------------------------
# I.5c/d ENSO teleconnections & MJO
# ---------------------------------------------------------------------------


def test_regression_on_index() -> None:
    rng = np.random.default_rng(1)
    index = rng.normal(0, 1, 500)
    series = 0.7 * index + rng.normal(0, 0.1, 500)
    assert physics.regression_on_index(series, index) == pytest.approx(0.7, abs=0.02)


def test_mjo_ratio_eastward_wave_dominates() -> None:
    """A pure eastward k=2, 45-day wave gives a large east/west ratio."""
    n_time, n_lon = 720, 144
    t = np.arange(n_time)[:, None]
    x = np.arange(n_lon)[None, :] / n_lon  # planetary fraction
    eastward = np.cos(2 * np.pi * (2 * x - t / 45.0))
    ratio = physics.mjo_east_west_ratio(eastward)
    assert ratio > 10.0

    westward = np.cos(2 * np.pi * (2 * x + t / 45.0))
    assert physics.mjo_east_west_ratio(westward) < 0.1

    rng = np.random.default_rng(2)
    noise_ratio = physics.mjo_east_west_ratio(rng.normal(0, 1, (n_time, n_lon)))
    assert noise_ratio == pytest.approx(1.0, abs=0.35)


# ---------------------------------------------------------------------------
# Tier II scalars
# ---------------------------------------------------------------------------


def test_ols_trend_and_first_harmonic() -> None:
    assert physics.ols_trend(np.arange(50) * 0.3) == pytest.approx(0.3)
    assert np.isnan(physics.ols_trend(np.array([1.0, np.nan])))

    months = np.arange(12)
    cycle = 5.0 * np.cos(2 * np.pi * (months - 6) / 12.0) + 10.0
    amplitude, phase = physics.first_harmonic(cycle)
    assert amplitude == pytest.approx(5.0, rel=1e-6)
    assert phase == pytest.approx(6.0, abs=0.01)
    with pytest.raises(ValueError, match="12-month"):
        physics.first_harmonic(np.zeros(10))


# ---------------------------------------------------------------------------
# Baselines
# ---------------------------------------------------------------------------


def test_climatology_forecast_annual_and_monthly() -> None:
    annual = baselines.climatology_forecast(
        np.array([1.0, 2.0, 3.0]),
        monthly=False,
        n_time=5,
    )
    np.testing.assert_allclose(annual, np.full(5, 2.0))

    monthly_series = np.tile(np.arange(12, dtype=float), 3)  # 3 identical years
    monthly = baselines.climatology_forecast(
        monthly_series,
        monthly=True,
        n_time=18,
    )
    np.testing.assert_allclose(monthly, np.tile(np.arange(12.0), 2)[:18])


def test_two_layer_ebm_step_forcing_approaches_equilibrium() -> None:
    lam = -1.3
    forcing = np.full(3000, 3.9)  # ~2xCO2 step held for 3000 yr
    t = baselines.two_layer_ebm(forcing, lambda_feedback=lam)
    # Equilibrium T = -F/lambda = 3.0 K
    assert t[-1] == pytest.approx(-3.9 / lam, rel=0.02)
    # Monotonic warming, fast-then-slow
    assert np.all(np.diff(t) >= -1e-9)
    assert t[10] > 0.5  # fast initial response
    assert t[10] < t[500] < t[-1]


def test_pattern_scaling_forecast_shapes() -> None:
    gmst = np.array([0.0, 1.0, 2.0])
    pattern = np.array([0.5, 1.0, 1.5, 2.0])  # unit-global-mean pattern
    clim = np.full(4, 10.0)
    fields = baselines.pattern_scaling_forecast(gmst, pattern, clim)
    assert fields.shape == (3, 4)
    np.testing.assert_allclose(fields[0], clim)
    np.testing.assert_allclose(fields[2], 10.0 + 2.0 * pattern)
