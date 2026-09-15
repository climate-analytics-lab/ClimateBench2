"""The ClimateBench v2 Tier II baselines (metrics_reference.md Tier II).

The headline skill of every scorecard entry is taken against the CMIP6
reference ensemble (``E_ref`` = median of the per-model fair CRPS, computed
in :mod:`climatebench2.scoring_pass`). Two further baselines are computed
and reported *alongside* it:

(i)   **Climatology** — the 1985–2014 pre-test climatology of the
      observations (`tier2.climatology_baseline_period`; it deliberately
      stops in 2014 so it cannot overlap the reserved post-2015 test period).

      ⚠ **CB2 interpretation.** The paper describes this baseline as the
      deterministic 1985–2014 monthly mean, which fair CRPS leaves
      *undefined* (M = 1). CB2 therefore scores the climatology as the
      **distribution** of the reference's baseline-window values for each
      calendar month — 30 pseudo-members for a monthly series, the 30 annual
      values for an annual one (:func:`climatology_pseudo_members`). This is
      the natural probabilistic reading of "predict the climatology" and it
      keeps the no-skill floor on the same fair-CRPS footing as every other
      row. Flagged for resolution in the manuscript.

(ii)  **Pattern scaling** — ΔT_global(t) from a two-layer energy-balance
      model driven by an ERF series, times the CMIP6 multi-model-mean
      normalized warming pattern, plus the climatology. Since work package 6b
      the GMST half is wired: :func:`load_erf_series` reads the packaged
      annual ERF table, :func:`calibrate_two_layer_ebm` fits **one**
      parameter (the feedback λ) by least squares to the observed GMST
      through 2014, and :func:`ebm_pseudo_members` turns the resulting
      deterministic trajectory into an ensemble fair CRPS can score.

      ⚠ **CB2 interpretation.** As with the Climatology baseline, a
      deterministic emulator is M = 1 and fair CRPS is undefined for it. CB2
      gives the trajectory pseudo-members by displacing it with the
      **detrended observed residuals of the 1985-2014 baseline window** — one
      member per baseline year — which is the same "the baseline's own
      historical scatter is its uncertainty" reading used for the
      climatology. Flagged for Duncan in docs/metrics_reference.md.

      The **spatial** half (a normalized CMIP6 MMM warming pattern) needs
      CMIP6 baseline-window maps that the databases only carry once
      ClimateEval PR #44 lands; :func:`pattern_scaling_forecast` is the maths
      and :func:`scoring_pass.pattern_scaling_rows` emits a ``reason`` row
      until the data are there.

Everything here is pure numpy/scipy plus one packaged CSV of protocol data;
the wiring lives in :mod:`climatebench2.scoring_pass` and the leaderboard.
"""

from __future__ import annotations

from dataclasses import dataclass
from importlib import resources

import numpy as np
from scipy import optimize

MONTHS_PER_YEAR = 12

#: Packaged annual effective-radiative-forcing table driving the pattern-
#: scaling baseline's two-layer EBM (``climatebench2/data/``). Its own header
#: carries the provenance and the ⚠ that it is a provisional interpolation of
#: published AR6 anchor values rather than the AR6 annual series itself.
ERF_DATA_PACKAGE = "climatebench2.data"


def climatology_pseudo_members(
    window_values: np.ndarray,
    *,
    window_months: np.ndarray | None = None,
    target_months: np.ndarray | None = None,
    n_time: int | None = None,
) -> np.ndarray:
    """Baseline (ii): the climatology as an ensemble of pseudo-members.

    Instead of a single deterministic climatological mean (undefined under
    fair CRPS), the forecast for a target step is the **set of
    baseline-window values** for that calendar month — one pseudo-member per
    baseline year.

    Parameters
    ----------
    window_values:
        The reference series restricted to the baseline window
        (1985–2014), shape ``(n_window,)``.
    window_months:
        Calendar month (1–12) of each ``window_values`` entry. Given for a
        **monthly** series; omit for an annual one.
    target_months:
        Calendar month of each target step (monthly series only).
    n_time:
        Number of target steps (annual series only).

    Returns
    -------
    :
        ``(n_members, n_time)``. For a monthly series the members are the
        baseline years — truncated to the smallest per-month count, so every
        month contributes the same number of members and the fair-CRPS
        spread term is not month-dependent. For an annual series every
        target step sees the same ``n_members`` baseline values.
    """
    values = np.asarray(window_values, dtype=float)
    if window_months is None:
        if n_time is None:
            msg = "annual climatology needs n_time"
            raise ValueError(msg)
        members = values[np.isfinite(values)]
        if members.size == 0:
            msg = "no finite values in the climatology baseline window"
            raise ValueError(msg)
        return np.tile(members[:, None], (1, int(n_time)))

    if target_months is None:
        msg = "monthly climatology needs target_months"
        raise ValueError(msg)
    months = np.asarray(window_months, dtype=int)
    targets = np.asarray(target_months, dtype=int)
    per_month = {
        m: values[(months == m) & np.isfinite(values)]
        for m in np.unique(targets)
    }
    counts = [v.size for v in per_month.values()]
    n_members = min(counts) if counts else 0
    if n_members == 0:
        msg = "no finite baseline-window values for some target month"
        raise ValueError(msg)
    stacked = {m: v[:n_members] for m, v in per_month.items()}
    return np.stack([stacked[int(m)] for m in targets], axis=1)


def two_layer_ebm(
    forcing: np.ndarray,
    *,
    lambda_feedback: float = -1.3,  # W m-2 K-1
    c_upper: float = 8.0,  # W yr m-2 K-1 (mixed layer)
    c_deep: float = 100.0,  # W yr m-2 K-1 (deep ocean)
    gamma: float = 0.7,  # W m-2 K-1 (exchange coefficient)
    efficacy: float = 1.3,
    dt_years: float = 1.0,
) -> np.ndarray:
    """Baseline (iii) core: two-layer EBM (Held et al. 2010; Geoffroy 2013).

    C  dT/dt  = F + λT − εγ(T − T_d)
    C_d dT_d/dt = γ(T − T_d)

    ``forcing``: annual ERF series (W/m²). Returns the upper-layer (surface)
    temperature anomaly series (K). Default parameters are AR6-ish midrange;
    the protocol fixes them in ``thresholds.yml`` when calibrated.
    """
    f = np.asarray(forcing, dtype=float)
    t_upper = np.zeros(f.size)
    t_deep = np.zeros(f.size)
    for i in range(1, f.size):
        heat_exchange = efficacy * gamma * (t_upper[i - 1] - t_deep[i - 1])
        dt_upper = (
            f[i - 1] + lambda_feedback * t_upper[i - 1] - heat_exchange
        ) / c_upper
        dt_deep = gamma * (t_upper[i - 1] - t_deep[i - 1]) / c_deep
        t_upper[i] = t_upper[i - 1] + dt_upper * dt_years
        t_deep[i] = t_deep[i - 1] + dt_deep * dt_years
    return t_upper


def load_erf_series(filename: str = "erf_ar6_ssp245.csv") -> tuple[np.ndarray, np.ndarray]:
    """``(years, ERF)`` of the packaged annual effective-radiative-forcing table.

    The forcing that drives the pattern-scaling baseline's EBM: total
    anthropogenic (plus natural, where the source provides it) ERF relative
    to 1750, in W m⁻², one value per year, extended beyond the historical
    period with SSP2-4.5. Provenance and the ⚠ on the current table are in
    the file's own header; it is *protocol data*, not model or observational
    data, which is why it is packaged here rather than fetched through a
    ClimateEval DataSource.
    """
    text = resources.files(ERF_DATA_PACKAGE).joinpath(filename).read_text()
    rows = [
        line.split(",")
        for line in text.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    if rows and not rows[0][0].strip().lstrip("-").isdigit():
        rows = rows[1:]  # a header line
    years = np.array([int(r[0]) for r in rows], dtype=int)
    forcing = np.array([float(r[1]) for r in rows], dtype=float)
    order = np.argsort(years)
    return years[order], forcing[order]


def detrended_residuals(values: np.ndarray) -> np.ndarray:
    """Residuals of a series about its own OLS straight line (NaNs dropped).

    The spread the pattern-scaling baseline is given as pseudo-members: what
    the observations do around their trend over the baseline window, which is
    the closest thing to "the internal variability the emulator does not
    simulate" that the observations alone can supply.
    """
    y = np.asarray(values, dtype=float)
    finite = y[np.isfinite(y)]
    if finite.size < 3:  # noqa: PLR2004 - a trend needs three points
        msg = f"need at least 3 finite values to detrend, got {finite.size}"
        raise ValueError(msg)
    index = np.arange(finite.size, dtype=float)
    slope, intercept = np.polyfit(index, finite, 1)
    return finite - (slope * index + intercept)


@dataclass(frozen=True)
class EBMCalibration:
    """One-parameter calibration of the two-layer EBM to observed GMST."""

    parameter: str
    value: float
    years: np.ndarray
    trajectory: np.ndarray
    rmse: float
    n_years: int


def calibrate_two_layer_ebm(  # noqa: PLR0913
    forcing: np.ndarray,
    forcing_years: np.ndarray,
    observed: np.ndarray,
    observed_years: np.ndarray,
    *,
    baseline: tuple[int, int],
    calibration_end: int,
    parameter: str = "lambda_feedback",
    bracket: tuple[float, float] = (-3.0, -0.3),
    **ebm_kwargs: float,
) -> EBMCalibration:
    """Fit **one** EBM parameter by least squares to observed GMST.

    The protocol's pattern-scaling baseline is "a two-layer EBM calibrated to
    observations **through 2014**" — deliberately a single degree of freedom
    (the feedback λ by default, or a scaling of the forcing), with the other
    Geoffroy parameters held at their ``tier2.ebm`` values, so the emulator
    stays the "simplest defensible" reference rather than a tuned competitor.

    Both series are reduced to anomalies about the same ``baseline`` window
    before they are compared, so the EBM's arbitrary absolute level (it starts
    from 0 K in 1750) cancels. Only years up to ``calibration_end`` enter the
    fit — the reserved test window must never be seen by a baseline.

    Returns the fitted value together with the **full** trajectory (as a
    baseline-window anomaly) over ``forcing_years``, which is what the scoring
    pass turns into a forecast.
    """
    if parameter not in ("lambda_feedback", "forcing_scale"):
        msg = f"cannot calibrate unknown parameter '{parameter}'"
        raise ValueError(msg)
    f_years = np.asarray(forcing_years, dtype=int)
    f_values = np.asarray(forcing, dtype=float)
    o_years = np.asarray(observed_years, dtype=int)
    o_values = np.asarray(observed, dtype=float)

    first, last = int(baseline[0]), int(baseline[1])
    fit_mask = (
        np.isin(o_years, f_years) & (o_years <= int(calibration_end)) & np.isfinite(o_values)
    )
    if fit_mask.sum() < 3:  # noqa: PLR2004
        msg = "too few overlapping years to calibrate the EBM"
        raise ValueError(msg)
    observed_baseline = o_values[(o_years >= first) & (o_years <= last)]
    if observed_baseline.size == 0 or not np.isfinite(observed_baseline).any():
        msg = f"the observations do not cover the {first}-{last} baseline window"
        raise ValueError(msg)
    target = o_values[fit_mask] - float(np.nanmean(observed_baseline))
    target_years = o_years[fit_mask]
    positions = np.searchsorted(f_years, target_years)

    def trajectory_for(value: float) -> np.ndarray:
        kwargs = dict(ebm_kwargs)
        driver = f_values
        if parameter == "lambda_feedback":
            kwargs["lambda_feedback"] = float(value)
        else:
            driver = f_values * float(value)
        series = two_layer_ebm(driver, **kwargs)
        window = series[(f_years >= first) & (f_years <= last)]
        return series - (float(np.mean(window)) if window.size else 0.0)

    def cost(value: float) -> float:
        return float(np.sum((trajectory_for(value)[positions] - target) ** 2))

    result = optimize.minimize_scalar(
        cost,
        bounds=(float(bracket[0]), float(bracket[1])),
        method="bounded",
    )
    best = float(result.x)
    series = trajectory_for(best)
    residual = series[positions] - target
    return EBMCalibration(
        parameter=parameter,
        value=best,
        years=f_years,
        trajectory=series,
        rmse=float(np.sqrt(np.mean(residual**2))),
        n_years=int(fit_mask.sum()),
    )


def ebm_pseudo_members(
    trajectory: np.ndarray,
    residuals: np.ndarray,
) -> np.ndarray:
    """Baseline (iii) as an ensemble: the trajectory displaced by each residual.

    ⚠ **CB2 interpretation** (see the module docstring). Fair CRPS is
    undefined for the deterministic emulator, so each pseudo-member is the
    EBM trajectory shifted by one of the ``residuals`` — the detrended
    observed departures over the baseline window. The members therefore
    differ by a constant offset: the ensemble expresses "we do not know which
    phase of internal variability the real world is in", not a simulated
    year-by-year noise process.

    Returns ``(n_members, n_time)``.
    """
    mean_trajectory = np.asarray(trajectory, dtype=float)
    offsets = np.asarray(residuals, dtype=float)
    offsets = offsets[np.isfinite(offsets)]
    if offsets.size < 2:  # noqa: PLR2004 - fair CRPS needs two members
        msg = f"need at least 2 residuals for pseudo-members, got {offsets.size}"
        raise ValueError(msg)
    return mean_trajectory[None, :] + offsets[:, None]


def pattern_scaling_forecast(
    gmst_anomaly: np.ndarray,
    warming_pattern: np.ndarray,
    climatology: np.ndarray,
) -> np.ndarray:
    """Baseline (iii): ΔT_global(t) × normalized pattern + climatology.

    ``gmst_anomaly``: (n_time,); ``warming_pattern``: (n_space,) — the CMIP6
    MMM warming pattern normalized to unit global mean; ``climatology``:
    (n_space,) or (n_time, n_space). Returns (n_time, n_space).
    """
    gmst = np.asarray(gmst_anomaly, dtype=float)
    pattern = np.asarray(warming_pattern, dtype=float)
    clim = np.asarray(climatology, dtype=float)
    fields = gmst[:, None] * pattern[None, :]
    return fields + (clim[None, :] if clim.ndim == 1 else clim)
