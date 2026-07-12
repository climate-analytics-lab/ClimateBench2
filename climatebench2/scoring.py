"""The ClimateBench v2 probabilistic scoring engine (pure functions).

Implements the two Tier II scoring regimes of the protocol
(docs/metrics_reference.md, Tier II preamble):

(a) **Time-resolved quantities** — CRPS of an ensemble against an observed
    series, time-averaged with an effective-sample-size (lag-1
    autocorrelation) correction on the average's uncertainty.

(b) **Aggregated scalar diagnostics** — ensemble-consistency test: is the
    observed value consistent with the model-ensemble distribution, whose
    spread combines ensemble spread, internal variability (piControl chunks)
    and observational uncertainty in quadrature; two-sided test at p < 0.05.
    Spatial fields are first projected onto a small number of EOFs and each
    PC tested (Bonferroni-corrected).

Everything here is numpy/scipy only — no ClimateEval imports — so the engine
is unit-testable anywhere. The ClimateEval ``Diagnostic`` wrappers live in
``climatebench2.diags.tier2_scores``.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import stats

# ---------------------------------------------------------------------------
# Regime (a): CRPS with effective-sample-size correction
# ---------------------------------------------------------------------------


def crps_ensemble(members: np.ndarray, obs: np.ndarray) -> np.ndarray:
    """Empirical CRPS of an ensemble forecast, per time step.

    CRPS(F, y) = E|X − y| − ½ E|X − X′| (Gneiting & Raftery 2007, eq. 21).

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
        CRPS per time step, shape ``(n_time,)``. For ``n_members == 1`` this
        reduces to the absolute error |x − y|.
    """
    members = np.atleast_2d(np.asarray(members, dtype=float))  # (m, t)
    obs = np.atleast_1d(np.asarray(obs, dtype=float))  # (t,)
    if members.shape[1] != obs.shape[0]:
        msg = (
            f"members has {members.shape[1]} time steps but obs has "
            f"{obs.shape[0]}"
        )
        raise ValueError(msg)
    mae_term = np.abs(members - obs[None, :]).mean(axis=0)
    # pairwise |X - X'| over members, per time step
    pairwise = np.abs(members[:, None, :] - members[None, :, :]).mean(axis=(0, 1))
    return mae_term - 0.5 * pairwise


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


def crps_ess_score(members: np.ndarray, obs: np.ndarray) -> CRPSScore:
    """Regime-(a) score: mean CRPS over time, SE from the effective T.

    ``score = (1/T) Σ_t CRPS_t``; ``SE = std(CRPS_t) / sqrt(T_eff)`` where
    T_eff uses the lag-1 autocorrelation of the CRPS series.
    """
    members = np.atleast_2d(np.asarray(members, dtype=float))
    crps_t = crps_ensemble(members, obs)
    valid = crps_t[np.isfinite(crps_t)]
    t_eff = effective_sample_size(valid)
    se = float(valid.std(ddof=1) / np.sqrt(t_eff)) if valid.size > 1 else np.nan
    return CRPSScore(
        score=float(valid.mean()),
        standard_error=se,
        t_eff=t_eff,
        r1=lag1_autocorrelation(valid),
        n_members=members.shape[0],
        n_time=int(valid.size),
    )


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
