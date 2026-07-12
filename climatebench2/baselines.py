"""The three ClimateBench v2 baselines (metrics_reference.md Tier II).

Every submission's Tier II score is reported relative to:

(i)   **Climatology persistence** — forecast = the 1990–2020 (monthly or
      annual) climatology of the observations, held fixed.
(ii)  **Pattern scaling** — ΔT_global(t) from a two-layer energy-balance
      model driven by an ERF series, times the CMIP6 multi-model-mean
      normalized warming pattern, plus the climatology.
(iii) **CMIP6 multi-model ensemble** — the pooled CMIP6 comparison members
      scored as one ensemble (implemented in
      ``climatebench2.diags.tier2_scores`` as the ``CMIP6-MME`` row).

All three run through the identical scoring pipeline (CRPS-ESS /
consistency), never a special-cased metric. Pure numpy here; wiring lives in
the scored diagnostics and the leaderboard.
"""

from __future__ import annotations

import numpy as np

MONTHS_PER_YEAR = 12


def climatology_forecast(
    reference_series: np.ndarray,
    *,
    monthly: bool,
    n_time: int,
    baseline_slice: slice | None = None,
) -> np.ndarray:
    """Baseline (i): persistence of the reference climatology.

    ``reference_series``: the observed series (monthly or annual) from which
    the climatology is taken — restricted to ``baseline_slice`` (e.g. the
    1990–2020 window) if given. Returns a forecast of length ``n_time``:
    the repeating 12-month climatology (``monthly=True``) or the constant
    mean (``monthly=False``).
    """
    x = np.asarray(reference_series, dtype=float)
    if baseline_slice is not None:
        x = x[baseline_slice]
    if monthly:
        clim = np.array(
            [np.nanmean(x[m::MONTHS_PER_YEAR]) for m in range(MONTHS_PER_YEAR)],
        )
        reps = int(np.ceil(n_time / MONTHS_PER_YEAR))
        return np.tile(clim, reps)[:n_time]
    return np.full(n_time, np.nanmean(x))


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
