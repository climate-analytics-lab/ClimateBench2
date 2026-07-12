"""Tests for the pure Tier I physics functions (climatebench2.physics)."""

from __future__ import annotations

import numpy as np
import pytest

from climatebench2 import physics

# ---------------------------------------------------------------------------
# I.1 energy balance
# ---------------------------------------------------------------------------


def test_running_mean_drift_recovers_linear_trend() -> None:
    years = np.arange(200)
    series = 0.005 * years  # 0.05 W/m2/decade
    assert physics.running_mean_drift(series) == pytest.approx(0.05, rel=1e-6)


def test_running_mean_drift_ignores_fast_noise() -> None:
    rng = np.random.default_rng(0)
    years = np.arange(500)
    series = 0.002 * years + 0.5 * np.sin(2 * np.pi * years / 3.5)
    drift = physics.running_mean_drift(series + rng.normal(0, 0.05, 500))
    assert drift == pytest.approx(0.02, abs=0.005)


def test_running_mean_drift_short_series_raises() -> None:
    with pytest.raises(ValueError, match="annual values"):
        physics.running_mean_drift(np.zeros(10))


# ---------------------------------------------------------------------------
# I.2 closures
# ---------------------------------------------------------------------------


def test_water_budget_residual_balanced() -> None:
    p = 3.0 / physics.SECONDS_PER_DAY  # 3 mm/day in kg m-2 s-1
    hfls = p * physics.LATENT_HEAT_VAPORIZATION  # perfectly balanced
    assert physics.water_budget_residual(p, hfls) == pytest.approx(0.0)
    # 0.1 mm/day imbalance
    assert physics.water_budget_residual(
        p,
        hfls * (1 - 0.1 / 3.0),
    ) == pytest.approx(0.1, rel=1e-6)


def test_atmospheric_energy_residual_balanced() -> None:
    p = 3.0 / physics.SECONDS_PER_DAY
    lp = physics.LATENT_HEAT_VAPORIZATION * p  # ~87 W/m2
    shf = 20.0
    # Balanced atmosphere: radiative cooling = LP - SHF
    q_rad_cooling = lp - shf
    toa_net = 0.5
    sfc_net_rad = toa_net + q_rad_cooling
    assert physics.atmospheric_energy_residual(
        p,
        toa_net,
        sfc_net_rad,
        shf,
    ) == pytest.approx(0.0, abs=1e-9)


# ---------------------------------------------------------------------------
# I.3a gridpoint regression
# ---------------------------------------------------------------------------


def test_gridpoint_regression_slope_known_field() -> None:
    rng = np.random.default_rng(1)
    n_time, n_lat, n_lon = 100, 5, 4
    x = rng.normal(0, 1, (n_time, n_lat, n_lon))
    true_slope = np.linspace(1.0, 3.0, n_lat * n_lon).reshape(n_lat, n_lon)
    y = true_slope[None] * x + rng.normal(0, 0.01, x.shape)
    slope = physics.gridpoint_regression_slope(y, x)
    np.testing.assert_allclose(slope, true_slope, atol=0.02)


def test_area_weighted_mean_cosine_weighting() -> None:
    lats = np.array([-60.0, 0.0, 60.0])
    field = np.array([0.0, 1.0, 0.0])
    expected = np.cos(0.0) / (2 * np.cos(np.pi / 3) + np.cos(0.0))
    assert physics.area_weighted_mean(field, lats) == pytest.approx(expected)


# ---------------------------------------------------------------------------
# I.6c / I.7 Gregory & aerosol ERF
# ---------------------------------------------------------------------------


def test_gregory_regression_and_aerosol_erf() -> None:
    rng = np.random.default_rng(2)
    lam_true, f4x_true = -1.2, 7.5
    dt = np.linspace(0.5, 5.0, 150)
    dn = f4x_true + lam_true * dt + rng.normal(0, 0.05, 150)
    lam, f4x, r2 = physics.gregory_regression(dt, dn)
    assert lam == pytest.approx(lam_true, abs=0.02)
    assert f4x == pytest.approx(f4x_true, abs=0.06)
    assert r2 > 0.99

    # ERF = dN - lambda*dT: cooling with negative dN and dT
    erf = physics.aerosol_erf(-0.8, -0.5, lam)
    assert erf == pytest.approx(-0.8 - lam * -0.5)


# ---------------------------------------------------------------------------
# I.8a meridional transport
# ---------------------------------------------------------------------------


def test_meridional_transport_zero_flux_and_global_balance() -> None:
    lats = np.linspace(-89, 89, 90)
    np.testing.assert_allclose(
        physics.meridional_transport(np.zeros(90), lats),
        np.zeros(90),
    )
    # A flux pattern integrating to ~zero globally gives ~zero at the N pole
    flux = np.sin(np.deg2rad(lats) * 2)  # antisymmetric-ish, integrates to ~0
    transport = physics.meridional_transport(flux, lats)
    assert abs(transport[-1]) < 0.05 * np.abs(transport).max()


def test_meridional_transport_realistic_shape() -> None:
    """TOA-like forcing (surplus tropics, deficit poles) -> poleward peaks.

    F = A(cos φ − π/4) satisfies ∫F cos φ dφ = 0 over the sphere, so the
    implied transport closes at the N pole and is antisymmetric about the
    equator, peaking where F cos φ = 0, i.e. φ = arccos(π/4) ≈ 38°.
    """
    lats = np.linspace(-89.5, 89.5, 360)
    flux = 150 * (np.cos(np.deg2rad(lats)) - np.pi / 4)
    transport = physics.meridional_transport(flux, lats) / 1e15
    peak, peak_lat = physics.nh_peak(transport, lats, 20, 60)
    assert 1.0 < peak < 10.0  # PW, right order of magnitude
    assert 33 < peak_lat < 43
    # Antisymmetric: SH minimum mirrors NH maximum
    assert transport.min() == pytest.approx(-peak, rel=0.1)
    # Global closure: ~zero transport at the N pole
    assert abs(transport[-1]) < 0.05 * peak


def test_nh_peak_empty_band() -> None:
    value, lat = physics.nh_peak(np.ones(5), np.array([-80, -60, -40, -20, -10.0]), 10, 30)
    assert np.isnan(value)
    assert np.isnan(lat)


# ---------------------------------------------------------------------------
# I.8b ITCZ-EFE
# ---------------------------------------------------------------------------


def test_zero_crossing_nearest_equator() -> None:
    lats = np.linspace(-40, 40, 81)
    profile = lats - 5.0  # crosses zero at +5
    assert physics.zero_crossing_nearest_equator(profile, lats) == pytest.approx(5.0)

    # Multiple crossings: picks the one nearest the equator
    profile = (lats - 3.0) * (lats - 30.0) * (lats + 25.0)
    assert physics.zero_crossing_nearest_equator(profile, lats) == pytest.approx(
        3.0,
        abs=0.5,
    )

    assert np.isnan(physics.zero_crossing_nearest_equator(lats * 0 + 2.0, lats))


def test_zero_crossing_no_time_length_assumptions() -> None:
    """Regression test for the retired np.ones((1980,1)) bug: any profile
    length works."""
    for n in (7, 33, 181, 1980):
        lats = np.linspace(-40, 40, n)
        profile = lats + 2.0
        assert physics.zero_crossing_nearest_equator(
            profile,
            lats,
        ) == pytest.approx(-2.0, abs=80 / max(n - 1, 1))


def test_itcz_efe_regression_recovers_slope() -> None:
    rng = np.random.default_rng(3)
    f_xeq = np.sin(np.linspace(0, 2 * np.pi, 12, endpoint=False))  # PW
    itcz = -3.0 * f_xeq + rng.normal(0, 0.05, 12)
    slope, r = physics.itcz_efe_regression(itcz, f_xeq)
    assert slope == pytest.approx(-3.0, abs=0.15)
    assert abs(r) > 0.99


# ---------------------------------------------------------------------------
# Bjerknes & C-C
# ---------------------------------------------------------------------------


def test_monthly_anomalies_removes_seasonal_cycle() -> None:
    months = np.arange(240)
    seasonal = 5 * np.sin(2 * np.pi * months / 12)
    anom = physics.monthly_anomalies(seasonal + 2.0)
    assert np.abs(anom).max() < 1e-10


def test_bjerknes_correlation_anticorrelated_series() -> None:
    rng = np.random.default_rng(4)
    months = np.arange(2400)  # 200 yr
    decadal = np.sin(2 * np.pi * months / 240)  # 20-yr oscillation
    amet = decadal + 0.3 * rng.normal(size=months.size)
    omet = -decadal + 0.3 * rng.normal(size=months.size)
    r = physics.bjerknes_correlation(amet, omet)
    assert r < -0.8

    with pytest.raises(ValueError, match="too short"):
        physics.bjerknes_correlation(np.zeros(60), np.zeros(60))


def test_cc_scaling_slope() -> None:
    rng = np.random.default_rng(5)
    tas = 288.0 + rng.normal(0, 0.3, 200)
    prw = 25.0 * (1 + 0.07 * (tas - 288.0)) + rng.normal(0, 0.05, 200)
    slope = physics.cc_scaling_slope(prw, tas)
    assert slope == pytest.approx(7.0, abs=0.5)
