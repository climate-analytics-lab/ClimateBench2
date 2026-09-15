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
    # Since work package 6b the harmonic is defined for any sampling (the
    # diurnal cycle needs 24 or 8 points), so a 10-point cycle is legal and
    # only fewer than three points is not.
    assert physics.first_harmonic(np.zeros(10)) == (0.0, 0.0)
    with pytest.raises(ValueError, match="at least 3 points"):
        physics.first_harmonic(np.zeros(2))


# ---------------------------------------------------------------------------
# Baselines
# ---------------------------------------------------------------------------


def test_climatology_pseudo_members_annual() -> None:
    """Annual series: every target step sees all baseline-window values."""
    members = baselines.climatology_pseudo_members(
        np.array([1.0, 2.0, 3.0]),
        n_time=5,
    )
    assert members.shape == (3, 5)
    np.testing.assert_allclose(members[:, 0], [1.0, 2.0, 3.0])
    np.testing.assert_allclose(members[:, 4], [1.0, 2.0, 3.0])


def test_climatology_pseudo_members_monthly() -> None:
    """Monthly series: the members of a step are that calendar month's years."""
    window_months = np.tile(np.arange(1, 13), 3)  # 3 baseline years
    window_values = np.arange(36, dtype=float)
    target_months = np.array([1, 2, 12])
    members = baselines.climatology_pseudo_members(
        window_values,
        window_months=window_months,
        target_months=target_months,
    )
    assert members.shape == (3, 3)  # 3 baseline years x 3 target steps
    np.testing.assert_allclose(members[:, 0], [0.0, 12.0, 24.0])  # Januarys
    np.testing.assert_allclose(members[:, 2], [11.0, 23.0, 35.0])  # Decembers


def test_climatology_pseudo_members_truncates_to_equal_member_counts() -> None:
    """A ragged final year must not make one month's spread term different."""
    window_months = np.array([1, 2, 1, 2, 1])  # 3 Januarys, 2 Februaries
    window_values = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    members = baselines.climatology_pseudo_members(
        window_values,
        window_months=window_months,
        target_months=np.array([1, 2]),
    )
    assert members.shape == (2, 2)


def test_climatology_pseudo_members_errors() -> None:
    with pytest.raises(ValueError, match="n_time"):
        baselines.climatology_pseudo_members(np.array([1.0]))
    with pytest.raises(ValueError, match="target_months"):
        baselines.climatology_pseudo_members(
            np.array([1.0]),
            window_months=np.array([1]),
        )
    with pytest.raises(ValueError, match="no finite"):
        baselines.climatology_pseudo_members(np.array([np.nan]), n_time=3)


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


# ---------------------------------------------------------------------------
# Pattern-scaling baseline (work package 6b)
# ---------------------------------------------------------------------------


def test_load_erf_series_is_annual_monotone_and_anchored() -> None:
    years, erf = baselines.load_erf_series()
    assert years[0] == 1750
    assert years[-1] >= 2030  # extended with SSP2-4.5
    np.testing.assert_array_equal(np.diff(years), 1)
    assert erf[0] == pytest.approx(0.0)
    # the AR6 headline anchor the table is built around
    assert erf[years == 2019][0] == pytest.approx(2.72, abs=0.01)
    assert np.all(np.diff(erf) >= -1e-9)  # no natural forcing: monotone


def test_detrended_residuals_remove_the_line_not_the_scatter() -> None:
    index = np.arange(30, dtype=float)
    wobble = 0.3 * np.sin(index)
    residuals = baselines.detrended_residuals(5.0 + 0.1 * index + wobble)
    assert residuals.mean() == pytest.approx(0.0, abs=1e-12)
    np.testing.assert_allclose(residuals, wobble - np.polyval(
        np.polyfit(index, wobble, 1), index), atol=1e-12)
    with pytest.raises(ValueError, match="at least 3"):
        baselines.detrended_residuals(np.array([1.0, np.nan]))


def _synthetic_ebm_target(lam: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """An ERF series and the EBM's own answer for a known lambda."""
    years, erf = baselines.load_erf_series()
    truth = baselines.two_layer_ebm(erf, lambda_feedback=lam)
    return years, erf, truth


def test_calibrate_two_layer_ebm_recovers_a_synthetic_lambda() -> None:
    """Fit the EBM to its own output: the parameter must come back."""
    years, erf, truth = _synthetic_ebm_target(-1.05)
    calibration = baselines.calibrate_two_layer_ebm(
        erf,
        years,
        truth,
        years,
        baseline=(1985, 2014),
        calibration_end=2014,
    )
    assert calibration.parameter == "lambda_feedback"
    assert calibration.value == pytest.approx(-1.05, abs=0.02)
    assert calibration.rmse < 1e-3
    assert calibration.n_years == int((years <= 2014).sum())
    # the trajectory is returned as an anomaly about the baseline window
    window = (calibration.years >= 1985) & (calibration.years <= 2014)
    assert calibration.trajectory[window].mean() == pytest.approx(0.0, abs=1e-9)


def test_calibrate_two_layer_ebm_never_sees_the_test_window() -> None:
    """Post-2014 observations must not move the fit."""
    years, erf, truth = _synthetic_ebm_target(-1.2)
    spoiled = truth.copy()
    spoiled[years > 2014] += 5.0  # nonsense in the reserved window
    fitted = baselines.calibrate_two_layer_ebm(
        erf, years, spoiled, years, baseline=(1985, 2014), calibration_end=2014,
    )
    clean = baselines.calibrate_two_layer_ebm(
        erf, years, truth, years, baseline=(1985, 2014), calibration_end=2014,
    )
    assert fitted.value == pytest.approx(clean.value, abs=1e-6)


def test_calibrate_two_layer_ebm_can_scale_the_forcing_instead() -> None:
    years, erf = baselines.load_erf_series()
    truth = baselines.two_layer_ebm(erf * 1.4)
    calibration = baselines.calibrate_two_layer_ebm(
        erf,
        years,
        truth,
        years,
        baseline=(1985, 2014),
        calibration_end=2014,
        parameter="forcing_scale",
        bracket=(0.5, 2.0),
    )
    assert calibration.value == pytest.approx(1.4, abs=0.02)
    with pytest.raises(ValueError, match="unknown parameter"):
        baselines.calibrate_two_layer_ebm(
            erf, years, truth, years, baseline=(1985, 2014),
            calibration_end=2014, parameter="c_deep",
        )


def test_calibrate_two_layer_ebm_needs_an_overlapping_baseline() -> None:
    years, erf = baselines.load_erf_series()
    with pytest.raises(ValueError, match="too few overlapping years"):
        baselines.calibrate_two_layer_ebm(
            erf, years, np.zeros(2), np.array([2100, 2101]),
            baseline=(1985, 2014), calibration_end=2014,
        )


def test_ebm_pseudo_members_displace_the_trajectory() -> None:
    trajectory = np.array([0.0, 0.5, 1.0])
    members = baselines.ebm_pseudo_members(trajectory, np.array([-0.1, 0.0, 0.1]))
    assert members.shape == (3, 3)
    np.testing.assert_allclose(members[:, 1], [0.4, 0.5, 0.6])
    # the ensemble mean is the trajectory when the residuals are centred
    np.testing.assert_allclose(members.mean(axis=0), trajectory)
    with pytest.raises(ValueError, match="at least 2 residuals"):
        baselines.ebm_pseudo_members(trajectory, np.array([0.1]))
