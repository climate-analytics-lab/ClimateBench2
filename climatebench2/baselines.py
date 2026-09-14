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
      normalized warming pattern, plus the climatology. The functions below
      are the pure-maths hook; wiring it (an ERF series, calibration through
      2014 and a CMIP6-MMM pattern) is a later work package.

Everything here is pure numpy; the wiring lives in
:mod:`climatebench2.scoring_pass` and the leaderboard.
"""

from __future__ import annotations

import numpy as np

MONTHS_PER_YEAR = 12


def climatology_pseudo_members(
    window_values: np.ndarray,
    *,
    window_months: np.ndarray | None = None,
    target_months: np.ndarray | None = None,
    n_time: int | None = None,
) -> np.ndarray:
    """Baseline (i): the climatology as an ensemble of pseudo-members.

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
    """Baseline (ii) core: two-layer EBM (Held et al. 2010; Geoffroy 2013).

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


def pattern_scaling_forecast(
    gmst_anomaly: np.ndarray,
    warming_pattern: np.ndarray,
    climatology: np.ndarray,
) -> np.ndarray:
    """Baseline (ii): ΔT_global(t) × normalized pattern + climatology.

    ``gmst_anomaly``: (n_time,); ``warming_pattern``: (n_space,) — the CMIP6
    MMM warming pattern normalized to unit global mean; ``climatology``:
    (n_space,) or (n_time, n_space). Returns (n_time, n_space).
    """
    gmst = np.asarray(gmst_anomaly, dtype=float)
    pattern = np.asarray(warming_pattern, dtype=float)
    clim = np.asarray(climatology, dtype=float)
    fields = gmst[:, None] * pattern[None, :]
    return fields + (clim[None, :] if clim.ndim == 1 else clim)
