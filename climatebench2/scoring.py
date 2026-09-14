"""The ClimateBench v2 probabilistic scoring engine (pure functions).

Implements the Tier II scoring machinery of the protocol
(docs/metrics_reference.md, Tier II preamble):

(a) **Time-resolved quantities** — **fair** (Ferro) CRPS of an ensemble
    against an observed series, time-averaged, with an effective-sample-size
    (lag-1 autocorrelation) correction on the *uncertainty* of that average
    and a moving-block bootstrap confidence interval.

(b) **Aggregated diagnostics and spatial fields** — fair CRPS in a projected
    basis (EOFs of the reference, fixed pre-2015) — the reference-EOF basis
    is a later work package; the primitives here are ``eof_basis`` /
    ``project_onto_eofs``.

(c) **Ensemble-consistency test** (complementary diagnostic) — is the
    observed value consistent with the model-ensemble distribution, whose
    spread combines ensemble spread, internal variability (piControl chunks)
    and observational uncertainty in quadrature; two-sided test at p < 0.05.
    Spatial fields are first projected onto a small number of EOFs and each
    PC tested (Bonferroni-corrected).

Everything here is numpy/scipy only — no ClimateEval imports, no protocol
constants (those live in ``thresholds.yml`` and are passed in by the caller)
— so the engine is unit-testable anywhere. The pass that applies it to a
results database is ``climatebench2.scoring_pass``.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import stats

_MIN_FAIR_MEMBERS = 2

# ---------------------------------------------------------------------------
# Regime (a): fair CRPS with effective-sample-size correction
# ---------------------------------------------------------------------------


def crps_fair(members: np.ndarray, obs: np.ndarray) -> np.ndarray:
    """Fair (Ferro) CRPS of an ensemble forecast, per time step.

    The protocol's primary probabilistic score throughout Tiers II and III
    (metrics_reference.md, Tier II preamble)::

        CRPS_fair(x_1..M, y) = (1/M) Σ_i |x_i − y|
                             − (1/(2M(M−1))) Σ_i Σ_j |x_i − x_j|

    Note the ``M(M−1)`` normalisation of the spread term: the double sum runs
    over all ordered pairs, so pairs with ``i = j`` (which contribute zero)
    are excluded from the average. This makes the *expected* score of a
    calibrated ensemble independent of the ensemble size, so submissions with
    3 and with 50 members are directly comparable; the empirical estimator
    (``M²`` normalisation) penalises small ensembles.

    Parameters
    ----------
    members:
        Ensemble values, shape ``(n_members, n_time)`` (or ``(n_members,)``
        for a single time).
    obs:
        Observed values, shape ``(n_time,)`` (or scalar).

    Returns
    -------
    :
        Fair CRPS per time step, shape ``(n_time,)``.

    Raises
    ------
    ValueError
        If fewer than two members are given: **fair CRPS is undefined for a
        deterministic forecast** and must never fall through to |x − y|
        (paper §5.3). Deterministic references are handled explicitly by the
        caller (``climatebench2.scoring_pass``).
    """
    members = np.atleast_2d(np.asarray(members, dtype=float))  # (m, t)
    obs = np.atleast_1d(np.asarray(obs, dtype=float))  # (t,)
    n_members = members.shape[0]
    if n_members < _MIN_FAIR_MEMBERS:
        msg = (
            f"fair CRPS is undefined for {n_members} member(s): it needs at "
            f"least {_MIN_FAIR_MEMBERS} (a deterministic forecast has no "
            f"spread term). Handle M = 1 explicitly rather than falling "
            f"through to the absolute error."
        )
        raise ValueError(msg)
    if members.shape[1] != obs.shape[0]:
        msg = (
            f"members has {members.shape[1]} time steps but obs has "
            f"{obs.shape[0]}"
        )
        raise ValueError(msg)
    mae_term = np.abs(members - obs[None, :]).mean(axis=0)
    # Σ_i Σ_j |x_i − x_j| over all ordered pairs, per time step; the fair
    # normalisation 1/(2M(M−1)) is the average over the i ≠ j pairs only.
    pairwise = np.abs(members[:, None, :] - members[None, :, :]).sum(axis=(0, 1))
    spread_term = pairwise / (2.0 * n_members * (n_members - 1))
    return mae_term - spread_term


def crps_fair_with_obs_draws(
    members: np.ndarray,
    obs: np.ndarray,
    *,
    obs_sigma: float | np.ndarray = 0.0,
    n_draws: int = 100,
    seed: int = 0,
) -> np.ndarray:
    """Fair CRPS averaged over draws of the observational uncertainty.

    The protocol's treatment of observational error (metrics_reference.md
    Tier II, "observational variance term"): instead of widening the
    forecast, the score is averaged over pseudo-observations
    ``y_k ~ N(obs, σ_obs)``::

        CRPS_obs = (1/K) Σ_k CRPS_fair(x_1..M, y_k)

    The draws are generated from ``seed`` alone, so a submission and its
    baselines — scored with the same seed, the same ``n_draws`` and the same
    aligned time axis — see the **identical** pseudo-observations and remain
    directly comparable.

    ``obs_sigma`` may be a scalar or a per-time-step array. With
    ``obs_sigma = 0`` (or ``n_draws < 1``) this reproduces :func:`crps_fair`
    exactly, with no random numbers drawn at all.
    """
    obs = np.atleast_1d(np.asarray(obs, dtype=float))
    sigma = np.broadcast_to(np.asarray(obs_sigma, dtype=float), obs.shape)
    if n_draws < 1 or not np.any(sigma > 0.0):
        return crps_fair(members, obs)
    rng = np.random.default_rng(seed)
    draws = rng.standard_normal((int(n_draws), obs.size))
    total = np.zeros(obs.size)
    for draw in draws:
        total += crps_fair(members, obs + sigma * draw)
    return total / float(n_draws)


def lag1_autocorrelation(x: np.ndarray) -> float:
    """Lag-1 autocorrelation of a series (NaNs dropped, mean removed)."""
    x = np.asarray(x, dtype=float)
    x = x[np.isfinite(x)]
    if x.size < 3:  # noqa: PLR2004 - need at least 3 points for a meaningful r1
        return 0.0
    x = x - x.mean()
    denom = float(np.sum(x * x))
    if denom == 0.0:
        return 0.0
    return float(np.sum(x[:-1] * x[1:]) / denom)


def effective_sample_size(x: np.ndarray) -> float:
    """T_eff = T (1 − r₁) / (1 + r₁), clipped to [1, T]."""
    x = np.asarray(x, dtype=float)
    n = int(np.isfinite(x).sum())
    if n == 0:
        return 0.0
    r1 = np.clip(lag1_autocorrelation(x), -0.999, 0.999)
    return float(np.clip(n * (1.0 - r1) / (1.0 + r1), 1.0, n))


@dataclass(frozen=True)
class CRPSScore:
    """Time-averaged CRPS with ESS-corrected uncertainty."""

    score: float
    standard_error: float
    t_eff: float
    r1: float
    n_members: int
    n_time: int


def crps_ess_from_series(crps_t: np.ndarray, n_members: int) -> CRPSScore:
    """Regime-(a) summary of an already-computed per-time-step CRPS series.

    ``score = (1/T) Σ_t CRPS_t``; ``SE = std(CRPS_t) / sqrt(T_eff)`` where
    T_eff uses the lag-1 autocorrelation of the CRPS series (the ESS
    correction applies to the *uncertainty*, never to the point score).
    """
    valid = np.asarray(crps_t, dtype=float)
    valid = valid[np.isfinite(valid)]
    if valid.size == 0:
        msg = "CRPS series has no finite values"
        raise ValueError(msg)
    t_eff = effective_sample_size(valid)
    se = float(valid.std(ddof=1) / np.sqrt(t_eff)) if valid.size > 1 else np.nan
    return CRPSScore(
        score=float(valid.mean()),
        standard_error=se,
        t_eff=t_eff,
        r1=lag1_autocorrelation(valid),
        n_members=int(n_members),
        n_time=int(valid.size),
    )


def crps_ess_score(members: np.ndarray, obs: np.ndarray) -> CRPSScore:
    """Regime-(a) score of an ensemble: mean **fair** CRPS with its ESS SE.

    Raises ``ValueError`` for a single member (see :func:`crps_fair`).
    """
    members = np.atleast_2d(np.asarray(members, dtype=float))
    return crps_ess_from_series(crps_fair(members, obs), members.shape[0])


# ---------------------------------------------------------------------------
# Regime (a): moving-block bootstrap confidence interval
# ---------------------------------------------------------------------------


def moving_block_bootstrap_ci(
    crps_t: np.ndarray,
    *,
    block_length: int,
    n_boot: int = 1000,
    alpha: float = 0.05,
    seed: int = 0,
    members: np.ndarray | None = None,
    obs: np.ndarray | None = None,
) -> tuple[float, float]:
    """Percentile CI of the time-mean CRPS from a moving-block bootstrap.

    The per-time-step CRPS series is serially correlated, so the interval is
    built from **moving blocks** of ``block_length`` consecutive steps
    (protocol defaults in ``thresholds.yml`` ``tier2.bootstrap``: 12 steps —
    one year — for a monthly series, 3 for an annual one). ``ceil(T/L)``
    blocks are drawn with replacement and concatenated to length ``T``, and
    the mean of each resample forms the bootstrap distribution.

    When ``members`` and ``obs`` are given, each replicate **also resamples
    the ensemble members** with replacement and recomputes the fair CRPS
    from the resampled ensemble, so the interval covers ensemble-sampling as
    well as time-sampling uncertainty. Member resampling costs
    ``O(n_boot · M² · T)``; pass only ``crps_t`` to skip it.

    Returns
    -------
    :
        ``(lo, hi)``, the ``alpha/2`` and ``1 − alpha/2`` percentiles of the
        resampled means. ``(nan, nan)`` for a series shorter than two steps.
    """
    series = np.asarray(crps_t, dtype=float)
    series = series[np.isfinite(series)]
    n_time = series.size
    if n_time < 2:  # noqa: PLR2004 - a CI needs at least two points
        return (float("nan"), float("nan"))
    length = int(np.clip(block_length, 1, n_time))
    n_blocks = int(np.ceil(n_time / length))
    rng = np.random.default_rng(seed)
    offsets = np.arange(length)

    def block_index(size: int) -> np.ndarray:
        starts = rng.integers(0, n_time - length + 1, size=(size, n_blocks))
        idx = starts[:, :, None] + offsets[None, None, :]
        return idx.reshape(size, n_blocks * length)[:, :n_time]

    resample_members = (
        members is not None
        and obs is not None
        # Member resampling recomputes the series, so it needs the raw series
        # to be gap-free (otherwise the block indices no longer line up).
        and np.asarray(crps_t, dtype=float).size == n_time
    )
    if not resample_members:
        means = series[block_index(int(n_boot))].mean(axis=1)
    else:
        ensemble = np.atleast_2d(np.asarray(members, dtype=float))
        n_members = ensemble.shape[0]
        means = np.empty(int(n_boot))
        for i in range(int(n_boot)):
            picked = rng.integers(0, n_members, size=n_members)
            replicate = crps_fair(ensemble[picked], obs)
            means[i] = replicate[block_index(1)[0]].mean()
    lo, hi = np.percentile(means, [100 * alpha / 2.0, 100 * (1.0 - alpha / 2.0)])
    return (float(lo), float(hi))


# ---------------------------------------------------------------------------
# Regime (b): ensemble-consistency test
# ---------------------------------------------------------------------------


def chunked_statistic_std(
    series: np.ndarray,
    chunk_length: int,
    statistic: str = "mean",
) -> float:
    """Internal-variability σ of a statistic from non-overlapping chunks.

    Chops a (piControl) series into ``chunk_length`` segments, evaluates the
    statistic on each, and returns the inter-chunk standard deviation — the
    protocol's estimate of internal variability for an observation-length
    diagnostic.

    ``statistic``: ``"mean"`` or ``"trend"`` (OLS slope per step).
    """
    x = np.asarray(series, dtype=float)
    n_chunks = x.size // chunk_length
    if n_chunks < 2:  # noqa: PLR2004 - need >= 2 chunks for a std
        msg = (
            f"series of length {x.size} gives {n_chunks} chunk(s) of "
            f"{chunk_length}; need at least 2"
        )
        raise ValueError(msg)
    values = []
    t = np.arange(chunk_length, dtype=float)
    for i in range(n_chunks):
        chunk = x[i * chunk_length : (i + 1) * chunk_length]
        if statistic == "mean":
            values.append(np.nanmean(chunk))
        elif statistic == "trend":
            mask = np.isfinite(chunk)
            values.append(stats.linregress(t[mask], chunk[mask]).slope)
        else:
            msg = f"Unknown statistic '{statistic}'"
            raise ValueError(msg)
    return float(np.std(values, ddof=1))


@dataclass(frozen=True)
class ConsistencyResult:
    """Result of the regime-(b) ensemble-consistency test."""

    z: float
    p_value: float
    passes: bool
    ensemble_mean: float
    total_sigma: float


def ensemble_consistency(
    ensemble_values: np.ndarray,
    observed_value: float,
    *,
    sigma_internal: float = 0.0,
    sigma_obs: float = 0.0,
    p_threshold: float = 0.05,
) -> ConsistencyResult:
    """Two-sided consistency of an observation with an ensemble distribution.

    σ_total² = var(ensemble) + σ_internal² + σ_obs²;
    z = (obs − mean(ensemble)) / σ_total; pass iff two-sided p ≥ p_threshold.

    A single-member "ensemble" is allowed when σ_internal/σ_obs carry the
    spread (var(ensemble) is then 0).
    """
    values = np.asarray(ensemble_values, dtype=float)
    values = values[np.isfinite(values)]
    if values.size == 0:
        msg = "ensemble_values is empty"
        raise ValueError(msg)
    var_ens = float(values.var(ddof=1)) if values.size > 1 else 0.0
    total_var = var_ens + sigma_internal**2 + sigma_obs**2
    if total_var <= 0.0:
        msg = "total variance is zero: no ensemble spread and no sigma terms"
        raise ValueError(msg)
    mu = float(values.mean())
    z = (float(observed_value) - mu) / float(np.sqrt(total_var))
    p_value = float(2.0 * stats.norm.sf(abs(z)))
    return ConsistencyResult(
        z=z,
        p_value=p_value,
        passes=p_value >= p_threshold,
        ensemble_mean=mu,
        total_sigma=float(np.sqrt(total_var)),
    )


# ---------------------------------------------------------------------------
# EOF projection for spatial fields (regime b)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EOFBasis:
    """Leading EOFs of a variability sample."""

    eofs: np.ndarray  # (n_modes, n_space)
    explained_variance: np.ndarray  # (n_modes,)
    mean: np.ndarray  # (n_space,)
    weights: np.ndarray  # (n_space,)


def eof_basis(
    variability_fields: np.ndarray,
    n_modes: int,
    *,
    weights: np.ndarray | None = None,
) -> EOFBasis:
    """Leading EOFs (area-weighted SVD) of a sample of fields.

    ``variability_fields``: shape ``(n_samples, n_space)`` — e.g. piControl
    chunks or CMIP6-member anomalies, flattened over space with any masked
    points removed beforehand.
    """
    fields = np.asarray(variability_fields, dtype=float)
    if fields.ndim != 2:  # noqa: PLR2004
        msg = f"variability_fields must be 2-D (samples, space), got {fields.ndim}-D"
        raise ValueError(msg)
    w = np.ones(fields.shape[1]) if weights is None else np.asarray(weights, float)
    sqrt_w = np.sqrt(w / w.sum())
    mean = fields.mean(axis=0)
    anom = (fields - mean) * sqrt_w[None, :]
    _u, s, vt = np.linalg.svd(anom, full_matrices=False)
    n_modes = min(n_modes, s.size)
    var = s**2 / max(fields.shape[0] - 1, 1)
    return EOFBasis(
        eofs=vt[:n_modes],  # weighted-space orthonormal
        explained_variance=var[:n_modes],
        mean=mean,
        weights=sqrt_w,
    )


def project_onto_eofs(basis: EOFBasis, field: np.ndarray) -> np.ndarray:
    """Project a field (``(n_space,)`` or ``(n, n_space)``) onto the basis."""
    field = np.asarray(field, dtype=float)
    anom = (field - basis.mean) * basis.weights
    return anom @ basis.eofs.T


def field_consistency(
    ensemble_fields: np.ndarray,
    observed_field: np.ndarray,
    variability_fields: np.ndarray,
    *,
    n_modes: int = 5,
    weights: np.ndarray | None = None,
    sigma_obs_field: np.ndarray | None = None,
    p_threshold: float = 0.05,
) -> tuple[bool, list[ConsistencyResult]]:
    """Regime-(b) test for a spatial field via EOF projection.

    EOFs come from ``variability_fields`` (e.g. piControl chunks); the
    inter-sample PC spread is the internal-variability term. Ensemble fields
    and the observed field are projected onto each mode and tested with
    :func:`ensemble_consistency`, Bonferroni-corrected across modes
    (per-mode threshold = p_threshold / n_modes). Overall pass = all modes
    pass.

    ``sigma_obs_field``: optional per-gridpoint observational σ, projected in
    quadrature onto each mode.
    """
    basis = eof_basis(variability_fields, n_modes, weights=weights)
    n_modes = basis.eofs.shape[0]
    pcs_ens = np.atleast_2d(project_onto_eofs(basis, ensemble_fields))
    pcs_obs = project_onto_eofs(basis, observed_field)
    pcs_var = project_onto_eofs(basis, variability_fields)
    sigma_int = pcs_var.std(axis=0, ddof=1)

    if sigma_obs_field is not None:
        obs_var = np.asarray(sigma_obs_field, dtype=float) ** 2
        sigma_obs_pc = np.sqrt((obs_var * basis.weights**2) @ (basis.eofs.T**2))
    else:
        sigma_obs_pc = np.zeros(n_modes)

    per_mode_threshold = p_threshold / n_modes  # Bonferroni
    results = [
        ensemble_consistency(
            pcs_ens[:, k],
            float(pcs_obs[k]),
            sigma_internal=float(sigma_int[k]),
            sigma_obs=float(sigma_obs_pc[k]),
            p_threshold=per_mode_threshold,
        )
        for k in range(n_modes)
    ]
    return all(r.passes for r in results), results


# ---------------------------------------------------------------------------
# Tier III: proxy-aware site consistency & perfect-model spread tests
# ---------------------------------------------------------------------------


def proxy_site_consistency(
    model_values: np.ndarray,
    proxy_values: np.ndarray,
    proxy_errors: np.ndarray,
    *,
    ensemble_values: np.ndarray | None = None,
    p_threshold: float = 0.05,
) -> tuple[float, np.ndarray]:
    """Regime-(b) consistency at proxy sites (metrics_reference.md III.1).

    Per site: z = (proxy − model) / sqrt(var_ens + σ_proxy²); the score is
    the fraction of sites with two-sided p ≥ ``p_threshold`` (proxy error
    dominates σ, per the paper).

    ``model_values``: model anomaly sampled at the sites — ``(n_sites,)``
    (single run) or via ``ensemble_values`` ``(n_members, n_sites)``.
    Returns (fraction consistent, per-site z). Sites with NaN model, proxy
    or error values are excluded from the fraction.
    """
    proxy = np.asarray(proxy_values, dtype=float)
    err = np.asarray(proxy_errors, dtype=float)
    if ensemble_values is not None:
        members = np.asarray(ensemble_values, dtype=float)
        mu = members.mean(axis=0)
        var_ens = members.var(axis=0, ddof=1) if members.shape[0] > 1 else 0.0
    else:
        mu = np.asarray(model_values, dtype=float)
        var_ens = 0.0
    total_sigma = np.sqrt(var_ens + err**2)
    with np.errstate(divide="ignore", invalid="ignore"):
        z = (proxy - mu) / total_sigma
    valid = np.isfinite(z)
    if not valid.any():
        msg = "no valid proxy sites"
        raise ValueError(msg)
    z_crit = stats.norm.isf(p_threshold / 2.0)
    fraction = float((np.abs(z[valid]) < z_crit).mean())
    return fraction, z


def sample_at_sites(
    field: np.ndarray,
    lats: np.ndarray,
    lons: np.ndarray,
    site_lats: np.ndarray,
    site_lons: np.ndarray,
) -> np.ndarray:
    """Nearest-gridpoint sampling of a (lat, lon) field at proxy sites.

    Longitudes are compared modulo 360 so −20 and 340 match.
    """
    field = np.asarray(field, dtype=float)
    lats = np.asarray(lats, dtype=float)
    lons = np.asarray(lons, dtype=float) % 360.0
    out = np.empty(len(site_lats))
    for i, (slat, slon) in enumerate(zip(site_lats, site_lons)):
        j = int(np.argmin(np.abs(lats - slat)))
        k = int(np.argmin(np.abs((lons - float(slon) % 360.0 + 180.0) % 360.0 - 180.0)))
        out[i] = field[j, k]
    return out


def le_variance_ratio(
    predicted_members: np.ndarray,
    truth_members: np.ndarray,
) -> float:
    """Large-ensemble spread test (III.2): predicted/true inter-member
    variance, aggregated over all remaining dimensions."""
    pred = np.asarray(predicted_members, dtype=float)
    truth = np.asarray(truth_members, dtype=float)
    var_pred = np.nanmean(pred.var(axis=0, ddof=1))
    var_truth = np.nanmean(truth.var(axis=0, ddof=1))
    if var_truth == 0:
        msg = "truth ensemble has zero variance"
        raise ValueError(msg)
    return float(var_pred / var_truth)


def le_spread_pattern_correlation(
    predicted_members: np.ndarray,
    truth_members: np.ndarray,
    *,
    weights: np.ndarray | None = None,
) -> float:
    """Spatial correlation of the inter-member variability patterns (III.2).

    Members of shape ``(n_members, n_space)``; optional area weights.
    """
    pred_var = np.asarray(predicted_members, dtype=float).var(axis=0, ddof=1)
    truth_var = np.asarray(truth_members, dtype=float).var(axis=0, ddof=1)
    w = np.ones(pred_var.size) if weights is None else np.asarray(weights, float)
    valid = np.isfinite(pred_var) & np.isfinite(truth_var)
    x, y, w = pred_var[valid], truth_var[valid], w[valid]
    mx, my = np.average(x, weights=w), np.average(y, weights=w)
    cov = np.average((x - mx) * (y - my), weights=w)
    vx = np.average((x - mx) ** 2, weights=w)
    vy = np.average((y - my) ** 2, weights=w)
    return float(cov / np.sqrt(vx * vy))
