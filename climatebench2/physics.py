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

import warnings

import numpy as np
from scipy import stats

EARTH_RADIUS_M = 6.371e6
LATENT_HEAT_VAPORIZATION = 2.5008e6  # J/kg  (L_v)
SECONDS_PER_DAY = 86400.0

# Thermodynamic constants of the column moist static energy (I.3c)
SPECIFIC_HEAT_DRY_AIR = 1004.6  # J/kg/K  (c_p)
GAS_CONSTANT_DRY_AIR = 287.04  # J/kg/K  (R_d)
VIRTUAL_TEMPERATURE_FACTOR = 0.608  # T_v = T (1 + 0.608 q)


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
    """λ-corrected aerosol ERF (Forster et al. 2021): ERF = ΔN − λ·ΔT.

    ``lambda_4x`` is the Gregory slope, which is *negative*; the paper's
    App. B.8 writes ``F = ΔN + λΔT``, correct only for λ as a positive
    feedback magnitude (see metrics_reference.md I.7).
    """
    return float(delta_n_end - lambda_4x * delta_t_end)


def clip_window_to_record(
    window: tuple[int, int],
    first_year: int,
    last_year: int,
) -> tuple[int, int]:
    """Fit the protocol's fixed year window into the record actually supplied.

    I.7 asks for the decadal mean **centred on 2015** (``[2010, 2019]``), but
    many DAMIP ``hist-aer`` runs stop in 2014. The window keeps its length
    and slides back so that it ends at the last year available; a record
    shorter than the window is used whole. Returns ``(first, last)``
    inclusive — the window actually used, which the diagnostic reports.
    """
    first_req, last_req = int(window[0]), int(window[1])
    length = last_req - first_req + 1
    if length < 1:
        msg = f"empty window {window}"
        raise ValueError(msg)
    first_year, last_year = int(first_year), int(last_year)
    if last_year < first_year:
        msg = f"empty record {first_year}-{last_year}"
        raise ValueError(msg)
    if last_year - first_year + 1 <= length:
        return (first_year, last_year)
    last = min(last_req, last_year)
    first = last - length + 1
    if first < first_year:
        first = first_year
        last = first + length - 1
    return (first, last)


def parallel_control_window(
    window: tuple[int, int],
    *,
    branch_year_in_parent: int,
    child_first_year: int,
) -> tuple[int, int]:
    """Return the piControl years parallel to ``window`` of a child run.

    CMIP6 records the branch point as ``branch_time_in_parent`` on the child
    run's own calendar-year axis; year *Y* of the child is then year
    ``Y − child_first_year + branch_year_in_parent`` of the control. Used by
    I.7 to remove control drift with the *parallel* piControl segment rather
    than the control's long-term mean (paper App. B.8).
    """
    offset = int(branch_year_in_parent) - int(child_first_year)
    return (int(window[0]) + offset, int(window[1]) + offset)


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
    *,
    lag_months: int = 0,
) -> tuple[float, float]:
    """(slope °/PW, r) of ITCZ latitude on cross-equatorial AMET (I.8b).

    Inputs are the 12-month climatological cycles (paper: 12 monthly means,
    not all timesteps), ordered by calendar month.

    ``lag_months`` circularly shifts ``itcz_lats`` so that ``itcz_lats[m]`` is
    compared with ``cross_equatorial_transport_pw[m - lag_months]`` (wrapping
    around the 12-month cycle). Donohoe et al. (2013) find the ITCZ latitude
    *lags* the cross-equatorial energy transport by about two months in the
    observed/reanalysis seasonal cycle — the ocean/land mixed layer's thermal
    inertia delays the precipitation response to the energy-transport forcing
    — and CB2's own retired benchmark script encoded exactly this lag
    (``itcz_v[2:]`` vs ``fxeq_v[:-2]``, git history ``b552b1c``) before it was
    dropped as "ad-hoc" during the ClimateEval migration. Regressing the two
    series in phase (``lag_months=0``) mixes points from opposite sides of
    the physical lag and depresses both the slope and the correlation — see
    ``ITCZEFEGate``, which passes the protocol's ``itcz_lag_months``
    (``thresholds.yml``, default 2).
    """
    itcz = np.asarray(itcz_lats, dtype=float)
    f_xeq = np.asarray(cross_equatorial_transport_pw, dtype=float)
    if lag_months:
        itcz = np.roll(itcz, -int(lag_months))
    reg = stats.linregress(f_xeq, itcz)
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


def banded_pattern_correlation(
    a: np.ndarray,
    b: np.ndarray,
    lats: np.ndarray,
    *,
    band: tuple[float, float] = (-90.0, 90.0),
    absolute_latitude: bool = False,
) -> float:
    """Centred, cos(lat)-weighted correlation of two fields over a lat band.

    Fields ``(..., lat, lon)`` are pooled over every leading dimension (time,
    if any) and over the latitude band; NaNs are excluded **pairwise**, so a
    field that is masked somewhere (an SST reference over land, say) masks
    both sides of the comparison consistently. "Centred" means both fields
    have their own weighted band mean removed before the covariance — the
    statistic the protocol gates in I.5c.

    ``band`` is a ``(low, high)`` latitude interval; with
    ``absolute_latitude`` the interval is applied to ``|lat|``, i.e. to the
    same band in *both* hemispheres (I.3b's 30–60°).
    """
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    lats = np.asarray(lats, dtype=float)
    lat_key = np.abs(lats) if absolute_latitude else lats
    band_mask = (lat_key >= band[0]) & (lat_key <= band[1])
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


def midlatitude_pattern_correlation(
    a: np.ndarray,
    b: np.ndarray,
    lats: np.ndarray,
    *,
    band: tuple[float, float] = (30.0, 60.0),
) -> float:
    """cos(lat)-weighted correlation of two fields over both 30–60° bands (I.3b)."""
    return banded_pattern_correlation(a, b, lats, band=band, absolute_latitude=True)


# ---------------------------------------------------------------------------
# I.3c Tropical precipitation–buoyancy (column moist static energy)
# ---------------------------------------------------------------------------


def moist_static_energy(
    ta: np.ndarray,
    zg: np.ndarray,
    hus: np.ndarray,
) -> np.ndarray:
    """Moist static energy ``h = c_p·T + g·z + L_v·q`` (J/kg).

    ``zg`` is geopotential *height* in m (the CMIP6 ``zg`` variable), so the
    potential-energy term is ``g·zg``.
    """
    return (
        SPECIFIC_HEAT_DRY_AIR * np.asarray(ta, dtype=float)
        + GRAVITY * np.asarray(zg, dtype=float)
        + LATENT_HEAT_VAPORIZATION * np.asarray(hus, dtype=float)
    )


def mass_weighted_column_integral(
    field: np.ndarray,
    plev: np.ndarray,
    *,
    axis: int = 0,
) -> np.ndarray:
    """Mass-weighted vertical integral ``∫ field dp / g`` (I.3c).

    ``plev`` is the pressure of each level in Pa, in any order; the integral
    runs over the levels actually available (CMIP6 Amon data are on the
    truncated ``plev19``, so this is a *partial*-column integral — the same
    truncation must be applied to the observational reference for the slopes
    to be comparable). For ``field`` in J/kg the result is J/m².
    """
    field = np.asarray(field, dtype=float)
    plev = np.asarray(plev, dtype=float)
    if plev.size != field.shape[axis]:
        msg = (
            f"pressure coordinate has {plev.size} levels but the field has "
            f"{field.shape[axis]} along axis {axis}"
        )
        raise ValueError(msg)
    order = np.argsort(plev)  # ascending pressure: top of the column first
    integral = np.trapezoid(np.take(field, order, axis=axis), plev[order], axis=axis)
    return integral / GRAVITY


def hydrostatic_height(
    ta: np.ndarray,
    hus: np.ndarray,
    plev: np.ndarray,
    *,
    axis: int = 0,
) -> np.ndarray:
    """Geopotential height (m) from the hypsometric equation, bottom-up.

    ``z(p) = ∫ (R_d T_v / g) d ln p`` integrated upward from the lowest
    available level, whose height is taken as 0. Used only as a fallback for
    an observational product that provides ``ta``/``hus`` but no ``zg``
    (ERA5 through ClimateEval, see I.3c): the missing surface term is
    constant in time and therefore drops out of the monthly *anomalies* the
    precipitation–buoyancy regression is taken over.
    """
    ta = np.asarray(ta, dtype=float)
    hus = np.asarray(hus, dtype=float)
    plev = np.asarray(plev, dtype=float)
    if plev.size != ta.shape[axis]:
        msg = f"pressure coordinate has {plev.size} levels, field has {ta.shape[axis]}"
        raise ValueError(msg)
    order = np.argsort(plev)[::-1]  # descending pressure: bottom of the column first
    t_v = np.moveaxis(
        ta * (1.0 + VIRTUAL_TEMPERATURE_FACTOR * hus),
        axis,
        0,
    )[order]
    p = plev[order]
    z = np.zeros_like(t_v)
    scale = GAS_CONSTANT_DRY_AIR / GRAVITY
    for k in range(p.size - 1):
        d_z = scale * 0.5 * (t_v[k] + t_v[k + 1]) * np.log(p[k] / p[k + 1])
        z[k + 1] = z[k] + d_z
    out = np.empty_like(z)
    out[order] = z
    return np.moveaxis(out, 0, axis)


def pooled_regression_slope(y: np.ndarray, x: np.ndarray) -> float:
    """OLS slope of ``y`` on ``x`` with every (time, space) pair pooled (I.3c).

    Both inputs are anomaly fields of the same shape; they are flattened and
    regressed together, so one slope summarises the whole tropical band.
    Non-finite pairs are dropped.
    """
    y = np.asarray(y, dtype=float).ravel()
    x = np.asarray(x, dtype=float).ravel()
    if y.size != x.size:
        msg = f"pooled regression needs equal shapes, got {y.size} and {x.size}"
        raise ValueError(msg)
    valid = np.isfinite(x) & np.isfinite(y)
    if valid.sum() < 3:  # noqa: PLR2004
        return float("nan")
    return float(stats.linregress(x[valid], y[valid]).slope)


def deseasonalised_anomalies(
    field: np.ndarray,
    months: np.ndarray,
) -> np.ndarray:
    """Remove the per-calendar-month climatology along the leading axis.

    The numpy counterpart of ESMValCore's ``anomalies(period="month")``, for
    fields CB2 derives itself (the column MSE of I.3c) and therefore never
    holds as a cube. ``months`` is the calendar month of each time step.
    """
    field = np.asarray(field, dtype=float)
    months = np.asarray(months)
    if months.size != field.shape[0]:
        msg = f"got {months.size} months for {field.shape[0]} time steps"
        raise ValueError(msg)
    out = field.copy()
    for month in np.unique(months):
        idx = months == month
        out[idx] = field[idx] - np.nanmean(field[idx], axis=0)
    return out


# ---------------------------------------------------------------------------
# I.5c ENSO teleconnections
# ---------------------------------------------------------------------------


def standardised(series: np.ndarray) -> np.ndarray:
    """``(x − mean) / std`` of a 1-D series (I.5c's standardized Niño-3.4)."""
    x = np.asarray(series, dtype=float)
    sigma = np.nanstd(x, ddof=1)
    if not np.isfinite(sigma) or sigma == 0.0:
        return np.full_like(x, np.nan)
    return (x - np.nanmean(x)) / sigma


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


def first_harmonic(cycle: np.ndarray) -> tuple[float, float]:
    """(amplitude, phase) of the first harmonic of a closed cycle.

    ``cycle`` is one period sampled at ``n`` equally spaced points — the
    12-month seasonal cycle of §II.1 or the ``n``-point diurnal cycle of the
    same section (24 hourly, 8 three-hourly, …). The fit is
    ``A·cos(2π t / n − φ)``; the phase is returned **in units of the input's
    own step**, i.e. months for a 12-point seasonal cycle and hours for a
    24-point hourly one, in ``[0, n)``.

    Generalised from the 12-point-only form (work package 6b) so the diurnal
    diagnostic can use it at any sub-daily sampling; ``n = 12`` is unchanged.
    """
    x = np.asarray(cycle, dtype=float)
    n = x.size
    if n < 3:  # noqa: PLR2004 - two points cannot separate amplitude and phase
        msg = f"a first harmonic needs at least 3 points, got {n}"
        raise ValueError(msg)
    if not np.isfinite(x).all():
        return (float("nan"), float("nan"))
    coeff = np.fft.rfft(x)[1]
    amplitude = 2.0 * np.abs(coeff) / n
    phase = float((-np.angle(coeff)) % (2 * np.pi) / (2 * np.pi) * n)
    return float(amplitude), phase


def phase_components(phase: float, n_points: int) -> tuple[float, float]:
    """``(cos, sin)`` of a phase expressed in cycle steps (§II.1, diurnal).

    Fair CRPS is defined on the real line, so it cannot score a phase
    directly: the distance between 23 h and 1 h is 2 h, not 22 h, and a
    circular mean of an ensemble is not the mean of its values. The protocol
    layer therefore scores the **two components of the unit vector**
    ``(cos φ, sin φ)`` — each an ordinary real number — and leaves the
    reconstruction of the angle to the reader (⚠ CB2 interpretation, recorded
    in docs/metrics_reference.md §II.1 "Diurnal cycle").
    """
    if not np.isfinite(phase):
        return (float("nan"), float("nan"))
    angle = 2.0 * np.pi * float(phase) / float(n_points)
    return (float(np.cos(angle)), float(np.sin(angle)))


# ---------------------------------------------------------------------------
# Tier II — ETCCDI daily extremes (§II.1 "Daily tas extremes / pr intensity")
#
# Every function here takes a daily field of shape ``(n_time, ...)`` (the
# trailing axes are grid points, already conservatively regridded and
# land-masked by the diagnostic) plus the calendar year of each step, and
# returns one value per year: ``(years, index)``. Keeping them pure means the
# indices are unit-testable on hand-built arrays whose answer is known by
# construction, which is how tests/test_physics.py checks them.
# ---------------------------------------------------------------------------


def _year_index(years: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """``(unique years, position of each step in them)``."""
    unique, inverse = np.unique(np.asarray(years, dtype=int), return_inverse=True)
    return unique, inverse


def _annual_reduce(
    values: np.ndarray,
    years: np.ndarray,
    reducer: str,
) -> tuple[np.ndarray, np.ndarray]:
    """Per-year NaN-aware reduction along the leading (time) axis."""
    x = np.asarray(values, dtype=float)
    unique, inverse = _year_index(years)
    if inverse.size != x.shape[0]:
        msg = f"got {inverse.size} years for {x.shape[0]} time steps"
        raise ValueError(msg)
    func = {
        "max": np.nanmax,
        "min": np.nanmin,
        "sum": np.nansum,
        "mean": np.nanmean,
    }[reducer]
    out = np.empty((unique.size, *x.shape[1:]), dtype=float)
    with warnings.catch_warnings():
        # A grid point that is masked all year (ocean under a land mask) is an
        # all-NaN slice: NaN is the right answer, not a warning.
        warnings.filterwarnings("ignore", r"(All-NaN|Mean of empty) slice")
        warnings.filterwarnings("ignore", "invalid value encountered")
        for i in range(unique.size):
            block = x[inverse == i]
            out[i] = np.nan if block.size == 0 else func(block, axis=0)
    return unique, out


def annual_extreme(
    values: np.ndarray,
    years: np.ndarray,
    statistic: str = "max",
) -> tuple[np.ndarray, np.ndarray]:
    """TXx / TNn: the annual block maximum (or minimum) per grid point."""
    if statistic not in ("max", "min"):
        msg = f"expected 'max' or 'min', got '{statistic}'"
        raise ValueError(msg)
    return _annual_reduce(values, years, statistic)


def calendar_percentile(
    values: np.ndarray,
    calendar_unit: np.ndarray,
    base_period: np.ndarray,
    percentile: float,
) -> np.ndarray:
    """Base-period percentile of each step, from its own calendar unit.

    ``calendar_unit`` is the calendar month (CB2's choice, see below) or day
    of year of each step and ``base_period`` a boolean mask selecting the
    fixed base-period days (1985-2014). The percentile is taken over the
    base-period days *of the same calendar unit*, then broadcast back to
    **every** step, so the caller can compare the whole record against it.

    ⚠ CB2 reads "percentile threshold from the base period, per calendar day
    or month" as **per calendar month**: the ETCCDI calendar-day definition
    needs a 5-day window and Zhang et al.'s bootstrap to avoid an
    inhomogeneity at the base-period edge, which a monthly threshold sidesteps
    at the cost of a slightly smoother annual cycle of the threshold.
    """
    x = np.asarray(values, dtype=float)
    unit = np.asarray(calendar_unit)
    base = np.asarray(base_period, dtype=bool)
    if unit.size != x.shape[0] or base.size != x.shape[0]:
        msg = "calendar_unit and base_period must have one entry per time step"
        raise ValueError(msg)
    if not base.any():
        msg = "the base period selects no time steps"
        raise ValueError(msg)
    out = np.full(x.shape, np.nan, dtype=float)
    for value in np.unique(unit):
        sample = x[base & (unit == value)]
        if sample.size == 0:
            continue
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", "All-NaN slice encountered")
            threshold = np.nanpercentile(sample, float(percentile), axis=0)
        out[unit == value] = threshold
    return out


def _forward_run_lengths(mask: np.ndarray, reset: np.ndarray | None = None) -> np.ndarray:
    """Length of the run of ``True`` ending at each step (0 where ``False``).

    ``reset`` (one bool per step) starts a fresh run *before* that step, which
    is how an annual index truncates a spell at the year boundary.
    """
    m = np.asarray(mask, dtype=bool)
    out = np.zeros(m.shape, dtype=np.int32)
    running = np.zeros(m.shape[1:], dtype=np.int32)
    for t in range(m.shape[0]):
        if reset is not None and bool(reset[t]):
            running = np.zeros_like(running)
        running = np.where(m[t], running + 1, 0).astype(np.int32)
        out[t] = running
    return out


def spell_duration_days(
    exceedance: np.ndarray,
    years: np.ndarray,
    min_length: int = 6,
) -> tuple[np.ndarray, np.ndarray]:
    """WSDI: days per year inside runs of ``>= min_length`` exceedance days.

    Spells are found over the **whole record** (so one that straddles New
    Year is not broken in two) and each day is then counted in the year it
    falls in, which is the ETCCDI attribution rule.
    """
    exceed = np.asarray(exceedance, dtype=bool)
    forward = _forward_run_lengths(exceed)
    backward = _forward_run_lengths(exceed[::-1])[::-1]
    total = forward + backward - 1
    in_spell = exceed & (total >= int(min_length))
    return _annual_reduce(in_spell.astype(float), years, "sum")


def exceedance_fraction(
    values: np.ndarray,
    years: np.ndarray,
    threshold: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """TX90p: percentage of days per year above a per-step threshold."""
    x = np.asarray(values, dtype=float)
    known = np.isfinite(x) & np.isfinite(threshold)
    exceed = np.where(known, (x > threshold).astype(float), np.nan)
    unique, fraction = _annual_reduce(exceed, years, "mean")
    return unique, fraction * 100.0


def annual_max_running_sum(
    values: np.ndarray,
    years: np.ndarray,
    window: int = 1,
) -> tuple[np.ndarray, np.ndarray]:
    """Rx1day / Rx5day: annual maximum of the ``window``-day running total.

    Each window is attributed to the year of its **last** day, so a window
    straddling New Year counts towards the new year (the ETCCDI convention).
    Daily precipitation is expected in mm day⁻¹, so a 1-day "total" is the
    day's own value.
    """
    x = np.asarray(values, dtype=float)
    n = int(window)
    if n < 1:
        msg = f"window must be >= 1 day, got {n}"
        raise ValueError(msg)
    if n == 1:
        totals = x
    else:
        filled = np.nan_to_num(x, nan=0.0)
        cumulative = np.cumsum(filled, axis=0)
        totals = np.full(x.shape, np.nan, dtype=float)
        totals[n - 1 :] = cumulative[n - 1 :] - np.concatenate(
            [np.zeros((1, *x.shape[1:])), cumulative[: -n]],
            axis=0,
        )
    return _annual_reduce(totals, years, "max")


def wet_day_percentile(
    values: np.ndarray,
    base_period: np.ndarray,
    percentile: float,
    wet_day_threshold: float = 1.0,
) -> np.ndarray:
    """Base-period percentile of **wet-day** precipitation, per grid point.

    Wet days are those with ``pr >= wet_day_threshold`` (1 mm/day). Grid
    points with no wet day in the base period get NaN, which propagates to a
    NaN index rather than a spurious zero.
    """
    x = np.asarray(values, dtype=float)
    base = np.asarray(base_period, dtype=bool).reshape((-1, *([1] * (x.ndim - 1))))
    wet = np.where(base & np.isfinite(x) & (x >= float(wet_day_threshold)), x, np.nan)
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", "All-NaN slice encountered")
        return np.nanpercentile(wet, float(percentile), axis=0)


def heavy_precipitation_fraction(
    values: np.ndarray,
    years: np.ndarray,
    threshold: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """R95pTOT: fraction of the annual total falling on days above ``threshold``.

    ``threshold`` is the base-period wet-day 95th percentile per grid point
    (:func:`wet_day_percentile`). The denominator is the **annual total**
    precipitation (not the wet-day total), which is the reading of "fraction
    of annual precipitation" in the paper's §5.2 list.
    """
    x = np.asarray(values, dtype=float)
    threshold = np.asarray(threshold, dtype=float)
    heavy = np.where(np.isfinite(x) & (x > threshold), x, 0.0)
    years_out, heavy_total = _annual_reduce(heavy, years, "sum")
    _years, total = _annual_reduce(np.nan_to_num(x, nan=0.0), years, "sum")
    with np.errstate(divide="ignore", invalid="ignore"):
        fraction = np.where(total > 0.0, heavy_total / total, np.nan)
    # A grid point with no base-period wet day has no threshold, so it has no
    # index either — never a spurious zero.
    return years_out, np.where(np.isfinite(threshold)[None, ...], fraction, np.nan)


def max_consecutive_dry_days(
    values: np.ndarray,
    years: np.ndarray,
    dry_day_threshold: float = 1.0,
) -> tuple[np.ndarray, np.ndarray]:
    """CDD: longest run of days with ``pr < dry_day_threshold``, per year.

    Runs are truncated at the year boundary (the annual ETCCDI index), so a
    dry spell spanning New Year contributes its within-year part to each of
    the two years.
    """
    x = np.asarray(values, dtype=float)
    dry = np.isfinite(x) & (x < float(dry_day_threshold))
    years_array = np.asarray(years, dtype=int)
    new_year = np.concatenate([[True], years_array[1:] != years_array[:-1]])
    runs = _forward_run_lengths(dry, reset=new_year)
    return _annual_reduce(runs.astype(float), years, "max")
