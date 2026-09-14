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
    """Paper identity (2026-09): Q_rad = L_v·P + SHF, Q_rad = sfc_rad − TOA."""
    p = 3.0 / physics.SECONDS_PER_DAY
    lp = physics.LATENT_HEAT_VAPORIZATION * p  # ~87 W/m2
    shf = 20.0
    q_rad_cooling = lp + shf  # balanced atmosphere
    toa_net = 0.5
    sfc_net_rad = toa_net + q_rad_cooling
    assert physics.atmospheric_energy_residual(
        p,
        toa_net,
        sfc_net_rad,
        shf,
    ) == pytest.approx(0.0, abs=1e-9)


def test_atmospheric_energy_residual_earth_like_magnitudes() -> None:
    """LP ≈ 80, SHF ≈ 20, Q_rad ≈ 100 W/m² closes; the old form gave ≈ 40."""
    lp = 80.0
    p = lp / physics.LATENT_HEAT_VAPORIZATION
    shf = 20.0
    q_rad_cooling = 100.0
    toa_net = 0.0
    sfc_net_rad = toa_net + q_rad_cooling
    residual = physics.atmospheric_energy_residual(p, toa_net, sfc_net_rad, shf)
    assert residual == pytest.approx(0.0, abs=1e-9)
    # And a real imbalance is reported at its true size
    assert physics.atmospheric_energy_residual(
        p,
        toa_net,
        sfc_net_rad + 3.0,
        shf,
    ) == pytest.approx(3.0, abs=1e-9)


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
    band = (lats >= 20.0) & (lats <= 60.0)
    peak = float(transport[band].max())
    peak_lat = float(lats[band][np.argmax(transport[band])])
    assert 1.0 < peak < 10.0  # PW, right order of magnitude
    assert 33 < peak_lat < 43
    # Antisymmetric: SH minimum mirrors NH maximum
    assert transport.min() == pytest.approx(-peak, rel=0.1)
    # Global closure: ~zero transport at the N pole
    assert abs(transport[-1]) < 0.05 * peak


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


# ---------------------------------------------------------------------------
# I.3c tropical precipitation-buoyancy (column MSE, pooled regression)
# ---------------------------------------------------------------------------


def test_moist_static_energy_sums_its_three_terms() -> None:
    h = physics.moist_static_energy(np.array([300.0]), np.array([1000.0]), np.array([0.01]))
    expected = (
        physics.SPECIFIC_HEAT_DRY_AIR * 300.0
        + physics.GRAVITY * 1000.0
        + physics.LATENT_HEAT_VAPORIZATION * 0.01
    )
    assert h[0] == pytest.approx(expected)


def test_mass_weighted_column_integral_of_a_uniform_column() -> None:
    """A constant h integrates to h·Δp/g whatever the level ordering."""
    plev = np.array([100000.0, 85000.0, 50000.0, 25000.0, 10000.0])
    field = np.full((plev.size, 3, 4), 3.2e5)
    integral = physics.mass_weighted_column_integral(field, plev, axis=0)
    expected = 3.2e5 * (100000.0 - 10000.0) / physics.GRAVITY
    assert integral.shape == (3, 4)
    np.testing.assert_allclose(integral, expected, rtol=1e-12)
    # descending levels (the CMOR order) give the same answer
    np.testing.assert_allclose(
        physics.mass_weighted_column_integral(field[::-1], plev[::-1], axis=0),
        expected,
    )
    with pytest.raises(ValueError, match="pressure coordinate"):
        physics.mass_weighted_column_integral(field, plev[:-1], axis=0)


def test_mass_weighted_column_integral_over_a_middle_axis() -> None:
    plev = np.array([100000.0, 50000.0])
    field = np.ones((7, 2, 5, 6))
    integral = physics.mass_weighted_column_integral(field, plev, axis=1)
    assert integral.shape == (7, 5, 6)
    np.testing.assert_allclose(integral, 50000.0 / physics.GRAVITY)


def test_hydrostatic_height_matches_the_isothermal_atmosphere() -> None:
    """Dry isothermal column: z = (R_d T / g) ln(p0/p) above the base level."""
    plev = np.array([100000.0, 85000.0, 70000.0, 50000.0, 25000.0])
    temperature = 250.0
    ta = np.full((plev.size, 2, 3), temperature)
    hus = np.zeros_like(ta)
    z = physics.hydrostatic_height(ta, hus, plev, axis=0)
    expected = (
        physics.GAS_CONSTANT_DRY_AIR * temperature / physics.GRAVITY
    ) * np.log(plev[0] / plev)
    np.testing.assert_allclose(z[:, 0, 0], expected, rtol=1e-6)
    # moisture makes the column thicker (virtual temperature)
    z_moist = physics.hydrostatic_height(ta, np.full_like(ta, 0.01), plev, axis=0)
    assert (z_moist[1:] > z[1:]).all()


def test_pooled_regression_slope_recovers_a_known_slope() -> None:
    rng = np.random.default_rng(11)
    x = rng.normal(0.0, 1.0, (60, 10, 20))  # (time, lat, lon) anomalies
    y = 0.35 * x + rng.normal(0.0, 0.02, x.shape)
    assert physics.pooled_regression_slope(y, x) == pytest.approx(0.35, abs=0.01)
    # NaNs are dropped pairwise, not propagated
    y_masked = y.copy()
    y_masked[:, 0, :] = np.nan
    assert physics.pooled_regression_slope(y_masked, x) == pytest.approx(0.35, abs=0.01)
    assert np.isnan(physics.pooled_regression_slope(np.array([1.0]), np.array([1.0])))
    with pytest.raises(ValueError, match="equal shapes"):
        physics.pooled_regression_slope(np.zeros(4), np.zeros(5))


def test_deseasonalised_anomalies_removes_the_monthly_climatology() -> None:
    months = np.tile(np.arange(1, 13), 5)
    seasonal = 5.0 * np.sin(2 * np.pi * months / 12.0)
    field = (seasonal[:, None, None] + 2.0) * np.ones((months.size, 3, 4))
    anom = physics.deseasonalised_anomalies(field, months)
    assert np.abs(anom).max() < 1e-10
    with pytest.raises(ValueError, match="time steps"):
        physics.deseasonalised_anomalies(np.zeros((5, 2)), np.arange(4))


# ---------------------------------------------------------------------------
# I.5c pattern correlation over an arbitrary latitude band
# ---------------------------------------------------------------------------


def test_banded_pattern_correlation_over_the_tropics() -> None:
    rng = np.random.default_rng(12)
    lats = np.linspace(-88.0, 88.0, 45)
    pattern = rng.normal(0.0, 1.0, (45, 36))
    band = (-30.0, 30.0)
    assert physics.banded_pattern_correlation(
        pattern, pattern, lats, band=band,
    ) == pytest.approx(1.0)
    assert physics.banded_pattern_correlation(
        pattern, -pattern, lats, band=band,
    ) == pytest.approx(-1.0)
    # only the band matters: scrambling the extratropics changes nothing
    other = pattern.copy()
    other[np.abs(lats) > 30.0] = rng.normal(0.0, 5.0, other[np.abs(lats) > 30.0].shape)
    assert physics.banded_pattern_correlation(
        pattern, other, lats, band=band,
    ) == pytest.approx(1.0)


def test_banded_pattern_correlation_is_centred_and_nan_aware() -> None:
    lats = np.linspace(-30.0, 30.0, 31)
    rng = np.random.default_rng(13)
    a = rng.normal(0.0, 1.0, (31, 20))
    # a constant offset is removed by the centring
    assert physics.banded_pattern_correlation(a, a + 7.0, lats) == pytest.approx(1.0)
    # points missing in one field (an SST reference over land) drop from both
    b = a.copy()
    b[:, :5] = np.nan
    a_land = a.copy()
    a_land[:, :5] = 99.0  # would ruin the correlation if it were not masked
    assert physics.banded_pattern_correlation(a_land, b, lats) == pytest.approx(1.0)


def test_midlatitude_pattern_correlation_still_spans_both_hemispheres() -> None:
    lats = np.linspace(-80.0, 80.0, 41)
    rng = np.random.default_rng(14)
    field = rng.normal(0.0, 1.0, (41, 36))
    other = field.copy()
    other[np.abs(lats) < 30.0] = rng.normal(0.0, 9.0, other[np.abs(lats) < 30.0].shape)
    assert physics.midlatitude_pattern_correlation(
        field, other, lats,
    ) == pytest.approx(1.0)


def test_standardised_series() -> None:
    x = np.array([1.0, 2.0, 3.0, 4.0])
    z = physics.standardised(x)
    assert z.mean() == pytest.approx(0.0)
    assert z.std(ddof=1) == pytest.approx(1.0)
    assert np.isnan(physics.standardised(np.ones(5))).all()


# ---------------------------------------------------------------------------
# I.7 the decadal window and the parallel piControl segment
# ---------------------------------------------------------------------------


def test_clip_window_to_record() -> None:
    window = (2010, 2019)
    # a record covering the window keeps it
    assert physics.clip_window_to_record(window, 1850, 2020) == (2010, 2019)
    assert physics.clip_window_to_record(window, 1850, 2019) == (2010, 2019)
    # a hist-aer run ending in 2014 gets the last 10 yr it has
    assert physics.clip_window_to_record(window, 1850, 2014) == (2005, 2014)
    # the window never slides before the start of the record
    assert physics.clip_window_to_record(window, 2001, 2014) == (2005, 2014)
    # a record shorter than the window is used whole
    assert physics.clip_window_to_record(window, 2012, 2014) == (2012, 2014)
    assert physics.clip_window_to_record(window, 2008, 2014) == (2008, 2014)
    with pytest.raises(ValueError, match="empty window"):
        physics.clip_window_to_record((2019, 2010), 1850, 2020)
    with pytest.raises(ValueError, match="empty record"):
        physics.clip_window_to_record(window, 2020, 1850)


def test_parallel_control_window() -> None:
    # a child starting in 1850 that branched from control year 3200
    assert physics.parallel_control_window(
        (2010, 2019),
        branch_year_in_parent=3200,
        child_first_year=1850,
    ) == (3360, 3369)
    # a control whose calendar matches the child's is the identity
    assert physics.parallel_control_window(
        (1990, 1999),
        branch_year_in_parent=1850,
        child_first_year=1850,
    ) == (1990, 1999)
