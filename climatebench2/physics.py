"""Pure physics functions for the Tier I diagnostics (numpy only).

Ported from the retired ``benchmark_scrips`` per delineation-plan Phase 3,
aligned with the paper spec in ``docs/metrics_reference.md`` (section numbers
below). The ClimateEval ``Diagnostic`` wrappers live in
``climatebench2.diags.tier1_physics``; everything here takes plain arrays so
it is unit-testable without any data or ClimateEval install.

Conventions (metrics_reference.md "Conventions"):
- TOA net downward flux  N = rsdt − rsut − rlut
- Surface net downward   F_sfc = (rsds − rsus) + (rlds − rlus) − hfss − hfls
- Latitudes in degrees; area weights ∝ cos(lat).
"""

from __future__ import annotations

import numpy as np
from scipy import stats

EARTH_RADIUS_M = 6.371e6
LATENT_HEAT_VAPORIZATION = 2.5008e6  # J/kg
SECONDS_PER_DAY = 86400.0


# ---------------------------------------------------------------------------
# I.1 Energy balance closure
# ---------------------------------------------------------------------------


def running_mean_drift(
    annual_series: np.ndarray,
    window: int = 10,
) -> float:
    """Drift (per decade) of the ``window``-yr running mean of an annual series.

    Paper I.1 criterion 2: OLS slope of the centred 10-yr running mean of
    global annual-mean TOA net flux, expressed per decade.
    """
    x = np.asarray(annual_series, dtype=float)
    if x.size < window + 2:
        msg = f"need more than {window + 2} annual values, got {x.size}"
        raise ValueError(msg)
    kernel = np.ones(window) / window
    smoothed = np.convolve(x, kernel, mode="valid")
    years = np.arange(smoothed.size, dtype=float)
    slope = stats.linregress(years, smoothed).slope  # per year
    return float(slope * 10.0)


# ---------------------------------------------------------------------------
# I.2 Closure constraints
# ---------------------------------------------------------------------------


def water_budget_residual(p_mean: float, hfls_mean: float) -> float:
    """|⟨P⟩ − ⟨E⟩| in mm/day (I.2a; E = hfls / L_v; P in kg m⁻² s⁻¹)."""
    e_mean = hfls_mean / LATENT_HEAT_VAPORIZATION
    return float(abs(p_mean - e_mean) * SECONDS_PER_DAY)


def atmospheric_energy_residual(
    p_mean: float,
    toa_net_mean: float,
    sfc_net_radiation_mean: float,
    hfss_mean: float,
) -> float:
    """|⟨L_v·P⟩ − (⟨Q_rad⟩ + ⟨SHF⟩)| in W/m² (I.2b).

    Q_rad = column radiative *convergence* = TOA net − surface net radiation
    (typically ≈ −100 W/m², i.e. cooling); the identity is
    L_v·P + Q_rad ≈ SHF, i.e. latent heating balances radiative cooling minus
    sensible input, so the residual is |L_v·P − (−Q_rad + SHF)| with
    Q_rad_cooling = −(TOA_net − sfc_net_radiation).
    """
    lp = LATENT_HEAT_VAPORIZATION * p_mean
    q_rad_cooling = -(toa_net_mean - sfc_net_radiation_mean)
    return float(abs(lp - (q_rad_cooling + hfss_mean)))


# ---------------------------------------------------------------------------
# I.3a Clear-sky longwave feedback (gridpoint regression)
# ---------------------------------------------------------------------------


def gridpoint_regression_slope(
    y: np.ndarray,
    x: np.ndarray,
) -> np.ndarray:
    """Per-gridpoint OLS slope of y on x over the leading (time) axis.

    ``y``/``x``: shape ``(n_time, ...)``. Returns slope field of shape
    ``(...)``. NaN where the x variance vanishes.
    """
    y = np.asarray(y, dtype=float)
    x = np.asarray(x, dtype=float)
    xa = x - x.mean(axis=0, keepdims=True)
    ya = y - y.mean(axis=0, keepdims=True)
    var = (xa**2).mean(axis=0)
    with np.errstate(divide="ignore", invalid="ignore"):
        slope = (xa * ya).mean(axis=0) / var
    return np.where(var > 0, slope, np.nan)


def area_weighted_mean(field: np.ndarray, lats: np.ndarray) -> float:
    """cos(lat)-weighted mean of a (lat, lon) or (lat,) field (NaN-aware)."""
    field = np.asarray(field, dtype=float)
    w = np.cos(np.deg2rad(np.asarray(lats, dtype=float)))
    if field.ndim == 2:
        w = np.broadcast_to(w[:, None], field.shape)
    valid = np.isfinite(field)
    if not valid.any():
        return float("nan")
    return float((field * w)[valid].sum() / w[valid].sum())


# ---------------------------------------------------------------------------
# I.6 Forced responses (abrupt-4xCO2)
# ---------------------------------------------------------------------------


def gregory_regression(
    delta_t: np.ndarray,
    delta_n: np.ndarray,
) -> tuple[float, float, float]:
    """Gregory regression N = F_4x + λ·ΔT → (λ, F_4x, r²)."""
    reg = stats.linregress(np.asarray(delta_t, float), np.asarray(delta_n, float))
    return float(reg.slope), float(reg.intercept), float(reg.rvalue**2)


# ---------------------------------------------------------------------------
# I.7 Aerosol effective radiative forcing (hist-aer)
# ---------------------------------------------------------------------------


def aerosol_erf(delta_n_end: float, delta_t_end: float, lambda_4x: float) -> float:
    """λ-corrected aerosol ERF (Forster et al. 2021): ERF = ΔN − λ·ΔT."""
    return float(delta_n_end - lambda_4x * delta_t_end)


# ---------------------------------------------------------------------------
# I.8 Meridional heat transport & ITCZ–EFE
# ---------------------------------------------------------------------------


def meridional_transport(
    zonal_mean_flux: np.ndarray,
    lats: np.ndarray,
) -> np.ndarray:
    """Implied northward transport from a zonal-mean flux profile (W).

    MET(φ) = 2π a² ∫_{−π/2}^{φ} F̄(φ′) cos φ′ dφ′, cumulative from the
    southernmost latitude. ``lats`` in degrees, ascending or descending.
    """
    flux = np.asarray(zonal_mean_flux, dtype=float)
    lats = np.asarray(lats, dtype=float)
    order = np.argsort(lats)
    lats_sorted, flux_sorted = lats[order], flux[order]
    phi = np.deg2rad(lats_sorted)
    dphi = np.gradient(phi)
    integrand = flux_sorted * np.cos(phi) * dphi
    transport_sorted = 2.0 * np.pi * EARTH_RADIUS_M**2 * np.cumsum(integrand)
    # return in the caller's latitude order
    out = np.empty_like(transport_sorted)
    out[order] = transport_sorted
    return out


def nh_peak(
    profile: np.ndarray,
    lats: np.ndarray,
    lat_min: float,
    lat_max: float,
) -> tuple[float, float]:
    """(peak value, peak latitude) of a profile within a NH latitude band."""
    profile = np.asarray(profile, dtype=float)
    lats = np.asarray(lats, dtype=float)
    mask = (lats >= lat_min) & (lats <= lat_max) & np.isfinite(profile)
    if not mask.any():
        return float("nan"), float("nan")
    idx = np.nanargmax(np.where(mask, profile, -np.inf))
    return float(profile[idx]), float(lats[idx])


def zero_crossing_nearest_equator(
    profile: np.ndarray,
    lats: np.ndarray,
    band: float = 40.0,
) -> float:
    """Latitude of the profile's zero crossing nearest the equator.

    Linear interpolation between the bracketing points; NaN if no crossing
    within ±``band``°. (Replaces the retired ``compute_efe`` and its
    hard-coded ``np.ones((1980, 1))`` time-length bug — this is a pure
    1-D profile operation with no time-dimension assumptions.)
    """
    profile = np.asarray(profile, dtype=float)
    lats = np.asarray(lats, dtype=float)
    order = np.argsort(lats)
    lats_s, prof_s = lats[order], profile[order]
    in_band = (lats_s >= -band) & (lats_s <= band)
    lats_s, prof_s = lats_s[in_band], prof_s[in_band]
    sign_change = np.where(np.diff(np.sign(prof_s)) != 0)[0]
    if sign_change.size == 0:
        return float("nan")
    crossings = []
    for i in sign_change:
        y0, y1 = prof_s[i], prof_s[i + 1]
        x0, x1 = lats_s[i], lats_s[i + 1]
        crossings.append(x0 - y0 * (x1 - x0) / (y1 - y0))
    crossings_arr = np.array(crossings)
    return float(crossings_arr[np.argmin(np.abs(crossings_arr))])


def itcz_efe_regression(
    itcz_lats: np.ndarray,
    cross_equatorial_transport_pw: np.ndarray,
) -> tuple[float, float]:
    """(slope °/PW, r) of ITCZ latitude on cross-equatorial AMET (I.8b).

    Inputs are the 12-month climatological cycles (paper: 12 monthly means,
    not all timesteps).
    """
    reg = stats.linregress(
        np.asarray(cross_equatorial_transport_pw, float),
        np.asarray(itcz_lats, float),
    )
    return float(reg.slope), float(reg.rvalue)


# ---------------------------------------------------------------------------
# Bjerknes compensation (extra, code-only)
# ---------------------------------------------------------------------------


def monthly_anomalies(series: np.ndarray) -> np.ndarray:
    """Remove the monthly climatology from a monthly series (length % 12 free)."""
    x = np.asarray(series, dtype=float)
    out = x.copy()
    for month in range(12):
        idx = np.arange(month, x.size, 12)
        out[idx] = x[idx] - np.nanmean(x[idx])
    return out


def bjerknes_correlation(
    amet_series: np.ndarray,
    omet_series: np.ndarray,
    window: int = 121,
) -> float:
    """Decadal AMET–OMET anti-correlation (Bjerknes 1964; Outten 2018).

    Monthly anomalies of the 40–70N band-mean transports, centred
    ``window``-month running means, Pearson r. Pass criterion (extra check):
    r < −0.3.
    """
    a = monthly_anomalies(amet_series)
    o = monthly_anomalies(omet_series)
    if a.size < window + 2:
        msg = f"series too short for window {window}"
        raise ValueError(msg)
    kernel = np.ones(window) / window
    a_smooth = np.convolve(a, kernel, mode="valid")
    o_smooth = np.convolve(o, kernel, mode="valid")
    return float(stats.pearsonr(a_smooth, o_smooth)[0])


# ---------------------------------------------------------------------------
# (extra) Clausius–Clapeyron scaling
# ---------------------------------------------------------------------------


def cc_scaling_slope(
    prw_annual: np.ndarray,
    tas_annual: np.ndarray,
) -> float:
    """Slope of fractional column-water-vapour anomaly (%) on ΔT (K)."""
    prw = np.asarray(prw_annual, dtype=float)
    tas = np.asarray(tas_annual, dtype=float)
    prw_pct = (prw / prw.mean() - 1.0) * 100.0
    return float(stats.linregress(tas - tas.mean(), prw_pct).slope)
