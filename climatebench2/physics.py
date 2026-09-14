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
    """|⟨Q_rad⟩ − (⟨L_v·P⟩ + ⟨SHF⟩)| in W/m² (I.2b).

    The atmospheric column is heated by latent heat release and by the
    surface sensible heat flux and cooled radiatively, so in steady state
    ``Q_rad ≈ L_v·P + SHF`` with ``Q_rad`` the *magnitude of the net
    radiative cooling* of the column,

        Q_rad = [(rsds − rsus) + (rlds − rlus)] − (rsdt − rsut − rlut)
              = sfc_net_radiation − TOA_net        (positive, ≈ +100 W/m²).

    (Earlier revisions of the paper wrote the identity as
    ``|L_v·P − (Q_rad + SHF)|``, which implies the sensible heat flux cools
    the atmosphere; that arrangement is off by 2·SHF ≈ 40 W/m² against a
    2 W/m² bound and was abandoned in the 2026-09 draft.)
    """
    lp = LATENT_HEAT_VAPORIZATION * p_mean
    q_rad_cooling = sfc_net_radiation_mean - toa_net_mean
    return float(abs(q_rad_cooling - (lp + hfss_mean)))


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


# ---------------------------------------------------------------------------
# I.3b Midlatitude geostrophic balance (daily 850 hPa)
# ---------------------------------------------------------------------------

OMEGA_EARTH = 7.292e-5  # rad/s
GRAVITY = 9.80665  # m/s2


def geostrophic_wind_u(
    zg: np.ndarray,
    lats: np.ndarray,
) -> np.ndarray:
    """Zonal geostrophic wind u_g = −(g/f) ∂Z/∂y from geopotential height.

    ``zg``: shape ``(..., lat, lon)`` in m; ``lats`` in degrees. ∂/∂y uses
    the meridional gradient on the sphere (a·∂φ). Rows with |lat| < 10° are
    NaN (f too small).
    """
    zg = np.asarray(zg, dtype=float)
    lats = np.asarray(lats, dtype=float)
    f = 2.0 * OMEGA_EARTH * np.sin(np.deg2rad(lats))
    dzdy = np.gradient(zg, np.deg2rad(lats) * EARTH_RADIUS_M, axis=-2)
    with np.errstate(divide="ignore", invalid="ignore"):
        ug = -(GRAVITY / f)[..., :, None] * dzdy
    ug[..., np.abs(lats) < 10.0, :] = np.nan
    return ug


def midlatitude_pattern_correlation(
    a: np.ndarray,
    b: np.ndarray,
    lats: np.ndarray,
    *,
    band: tuple[float, float] = (30.0, 60.0),
) -> float:
    """cos(lat)-weighted correlation of two fields over both 30–60° bands.

    Fields ``(..., lat, lon)`` are pooled over every leading dimension (time)
    and both hemispheres' midlatitude bands; NaNs excluded pairwise.
    """
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    lats = np.asarray(lats, dtype=float)
    band_mask = (np.abs(lats) >= band[0]) & (np.abs(lats) <= band[1])
    a_band = a[..., band_mask, :]
    b_band = b[..., band_mask, :]
    w = np.broadcast_to(
        np.cos(np.deg2rad(lats[band_mask]))[:, None],
        a_band.shape[-2:],
    )
    w_full = np.broadcast_to(w, a_band.shape).ravel()
    x = a_band.ravel()
    y = b_band.ravel()
    valid = np.isfinite(x) & np.isfinite(y)
    x, y, w_full = x[valid], y[valid], w_full[valid]
    if x.size < 3:
        return float("nan")
    mx = np.average(x, weights=w_full)
    my = np.average(y, weights=w_full)
    cov = np.average((x - mx) * (y - my), weights=w_full)
    vx = np.average((x - mx) ** 2, weights=w_full)
    vy = np.average((y - my) ** 2, weights=w_full)
    return float(cov / np.sqrt(vx * vy))


# ---------------------------------------------------------------------------
# I.5c ENSO teleconnections
# ---------------------------------------------------------------------------


def regression_on_index(series: np.ndarray, index: np.ndarray) -> float:
    """OLS regression coefficient of a series on a (Niño-3.4) index."""
    series = np.asarray(series, dtype=float)
    index = np.asarray(index, dtype=float)
    n = min(series.size, index.size)
    valid = np.isfinite(series[:n]) & np.isfinite(index[:n])
    return float(stats.linregress(index[:n][valid], series[:n][valid]).slope)


# ---------------------------------------------------------------------------
# I.5d MJO (Wheeler–Kiladis east/west power ratio)
# ---------------------------------------------------------------------------


def mjo_east_west_ratio(
    pr_equatorial: np.ndarray,
    *,
    wavenumbers: tuple[int, int] = (1, 3),
    period_days: tuple[float, float] = (30.0, 90.0),
) -> float:
    """Eastward/westward power ratio for k = 1–3, 30–90 d (I.5d).

    ``pr_equatorial``: daily, meridionally averaged (±15°) precipitation of
    shape ``(n_time, n_lon)``. Detrended and Hann-tapered in time before the
    2-D FFT. With time factor e^{−iωt} and zonal factor e^{ikx}, eastward
    propagation has ω·k > 0.
    """
    x = np.asarray(pr_equatorial, dtype=float)
    n_time, _n_lon = x.shape
    x = x - x.mean(axis=0, keepdims=True)
    x = x * np.hanning(n_time)[:, None]
    spec = np.fft.fft2(x)  # (freq, wavenumber), FFT sign conventions below
    power = np.abs(spec) ** 2
    freqs = np.fft.fftfreq(n_time, d=1.0)  # cycles/day
    ks = np.fft.fftfreq(x.shape[1], d=1.0 / x.shape[1])  # integer wavenumbers

    f_lo, f_hi = 1.0 / period_days[1], 1.0 / period_days[0]
    k_lo, k_hi = wavenumbers

    def band_power(eastward: bool) -> float:
        total = 0.0
        for i, f in enumerate(freqs):
            for j, k in enumerate(ks):
                if not (f_lo <= abs(f) <= f_hi and k_lo <= abs(k) <= k_hi):
                    continue
                # numpy fft2 uses e^{-i(ωt + kx)}: propagation speed = -ω/k,
                # so eastward (+x) waves have ω·k < 0
                is_east = f * k < 0
                if is_east == eastward:
                    total += power[i, j]
        return total

    east = band_power(eastward=True)
    west = band_power(eastward=False)
    return float(east / west) if west > 0 else float("inf")


# ---------------------------------------------------------------------------
# Tier II scalar diagnostics
# ---------------------------------------------------------------------------


def ols_trend(series: np.ndarray) -> float:
    """OLS trend per step of a series (NaNs dropped)."""
    y = np.asarray(series, dtype=float)
    t = np.arange(y.size, dtype=float)
    valid = np.isfinite(y)
    if valid.sum() < 3:
        return float("nan")
    return float(stats.linregress(t[valid], y[valid]).slope)


def first_harmonic(seasonal_cycle: np.ndarray) -> tuple[float, float]:
    """(amplitude, phase in months) of the first harmonic of a 12-pt cycle."""
    x = np.asarray(seasonal_cycle, dtype=float)
    if x.size != 12:  # noqa: PLR2004
        msg = f"expected a 12-month climatology, got length {x.size}"
        raise ValueError(msg)
    coeff = np.fft.rfft(x)[1]
    amplitude = 2.0 * np.abs(coeff) / 12.0
    phase_months = float((-np.angle(coeff)) % (2 * np.pi) / (2 * np.pi) * 12.0)
    return float(amplitude), phase_months
