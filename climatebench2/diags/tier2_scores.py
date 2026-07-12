"""Tier II probabilistic scoring diagnostics (regimes a and b).

These wrap ClimateEval time-series diagnostics and post-process their raw
output through the ClimateBench2 scoring engine (``climatebench2.scoring``):

- :class:`ScoredAnnualMeanTimeSeries` / :class:`ScoredMonthlyMeanTimeSeries` —
  regime (a): per-data-source CRPS against the reference series with the
  effective-sample-size correction, appended to the metrics table. All
  ``other`` data sources (the CMIP6 comparison ensemble) are additionally
  pooled into one multi-model ensemble row (``data_id = "CMIP6-MME"``),
  which is the protocol's MME baseline scored through the identical pipeline.

- :class:`TrendConsistency` — regime (b) applied to the OLS trend of the
  series: is the observed trend consistent with the ensemble trend
  distribution? Ensemble = the benchmarked model + CMIP6 comparison members.
  The internal-variability term (piControl chunking) is wired in Phase 4 via
  a piControl data path; until then ``sigma_internal`` defaults to 0 and the
  test is spread+obs-error only (documented limitation).

Metrics rows use the numeric-column convention of ``pass_fail``:
``value``/``passes`` plus score-specific columns.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

import ibis
import numpy as np
import pandas as pd
from scipy import stats

from climateeval.diags._base import DiagnosticOutput
from climateeval.diags.simple import AnnualMeanTimeSeries, MeanTimeSeries

from climatebench2 import scoring
from climatebench2._thresholds import get_threshold

if TYPE_CHECKING:
    from collections.abc import Callable

MME_DATA_ID = "CMIP6-MME"
_META_COLUMNS = {"data_id", "data_type", "time"}


def _series_by_source(
    raw_df: pd.DataFrame,
) -> tuple[dict[tuple[str, str], pd.DataFrame], list[str]]:
    """Split a raw-output table into per-(data_id, data_type) time series."""
    var_columns = [c for c in raw_df.columns if c not in _META_COLUMNS]
    groups = {
        (str(data_id), str(data_type)): g.sort_values("time")
        for (data_id, data_type), g in raw_df.groupby(
            ["data_id", "data_type"],
            sort=False,
        )
    }
    return groups, var_columns


def _aligned(
    frame: pd.DataFrame,
    reference: pd.DataFrame,
    column: str,
) -> tuple[np.ndarray, np.ndarray]:
    """Align one series with the reference on the time column (inner join)."""
    merged = pd.merge(
        frame[["time", column]].rename(columns={column: "x"}),
        reference[["time", column]].rename(columns={column: "y"}),
        on="time",
        how="inner",
    ).dropna()
    return merged["x"].to_numpy(float), merged["y"].to_numpy(float)


def _stack_members(
    members: list[pd.DataFrame],
    reference: pd.DataFrame,
    column: str,
) -> tuple[np.ndarray, np.ndarray]:
    """Stack member series on the times every member shares with the obs."""
    obs = reference[["time", column]].rename(columns={column: "obs"}).dropna()
    merged = obs
    for i, member in enumerate(members):
        merged = pd.merge(
            merged,
            member[["time", column]].rename(columns={column: f"m{i}"}),
            on="time",
            how="inner",
        )
    merged = merged.dropna()
    member_matrix = merged[[f"m{i}" for i in range(len(members))]].to_numpy(float).T
    return member_matrix, merged["obs"].to_numpy(float)


class _ScoredTimeSeriesMixin:
    """Append regime-(a) CRPS-ESS rows to a time-series diagnostic's metrics."""

    _min_overlap: ClassVar[int] = 3

    def get_output(self, data: Any, data_information: Any) -> DiagnosticOutput:
        output = super().get_output(data, data_information)  # type: ignore[misc]
        if output.raw_output is None:
            return output
        raw_df = output.raw_output.to_pandas()
        if "time" not in raw_df.columns:
            return output
        groups, var_columns = _series_by_source(raw_df)

        rows: list[dict[str, Any]] = []
        for column in var_columns:
            references = [
                g for (_, data_type), g in groups.items() if data_type == "reference"
            ]
            if not references:
                continue
            reference = references[0]

            # Individual sources (the submission and each comparison model)
            for (data_id, data_type), frame in groups.items():
                if data_type == "reference":
                    continue
                x, y = _aligned(frame, reference, column)
                if x.size < self._min_overlap:
                    continue
                rows.append(
                    self._crps_row(column, data_id, data_type, x[None, :], y),
                )

            # Pooled CMIP6 comparison ensemble = the MME baseline
            member_frames = [
                g for (_, data_type), g in groups.items() if data_type == "other"
            ]
            if len(member_frames) > 1:
                members, y = _stack_members(member_frames, reference, column)
                if members.shape[1] >= self._min_overlap:
                    rows.append(
                        self._crps_row(column, MME_DATA_ID, "baseline", members, y),
                    )

        if not rows:
            return output
        scores_df = pd.DataFrame(rows)
        if output.metrics is not None:
            scores_df = pd.concat(
                [output.metrics.to_pandas(), scores_df],
                ignore_index=True,
                sort=False,
            )
        return DiagnosticOutput(
            raw_output=output.raw_output,
            metrics=ibis.memtable(scores_df),
            variables=output.variables,
            data_sources=output.data_sources,
        )

    @staticmethod
    def _crps_row(
        column: str,
        data_id: str,
        data_type: str,
        members: np.ndarray,
        obs: np.ndarray,
    ) -> dict[str, Any]:
        result = scoring.crps_ess_score(members, obs)
        return {
            "data_id": data_id,
            "data_type": data_type,
            "var_id": column,
            "crps": result.score,
            "crps_se": result.standard_error,
            "t_eff": result.t_eff,
            "n_members": result.n_members,
            "n_time": result.n_time,
        }


class ScoredAnnualMeanTimeSeries(_ScoredTimeSeriesMixin, AnnualMeanTimeSeries):
    """Annual-mean time series with regime-(a) CRPS-ESS scoring."""


class ScoredMonthlyMeanTimeSeries(_ScoredTimeSeriesMixin, MeanTimeSeries):
    """Monthly-mean time series with regime-(a) CRPS-ESS scoring."""


class TrendConsistency(AnnualMeanTimeSeries):
    """Regime-(b) consistency of the observed trend with the ensemble.

    Post-processes the annual-mean series: OLS trend per data source; the
    ensemble distribution pools the benchmarked model and the CMIP6
    comparison members; the observed (reference) trend is tested with
    :func:`climatebench2.scoring.ensemble_consistency` at the protocol's
    ``tier2.consistency_p_value``.

    ``sigma_internal`` (piControl-chunk trend variability) is wired in
    Phase 4; ``sigma_obs`` may be passed as a diagnostic kwarg per variable
    until observational error fields are plumbed through.
    """

    _trend_statistic: ClassVar[Callable[[np.ndarray], float]] = staticmethod(  # type: ignore[assignment]
        lambda y: float(stats.linregress(np.arange(y.size, dtype=float), y).slope),
    )

    def __init__(self, *args: Any, sigma_obs: float = 0.0, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._sigma_obs = sigma_obs

    def get_output(self, data: Any, data_information: Any) -> DiagnosticOutput:
        output = super().get_output(data, data_information)
        if output.raw_output is None:
            return output
        raw_df = output.raw_output.to_pandas()
        if "time" not in raw_df.columns:
            return output
        groups, var_columns = _series_by_source(raw_df)
        p_threshold = get_threshold("tier2.consistency_p_value")

        rows: list[dict[str, Any]] = []
        for column in var_columns:
            references = [
                g for (_, dt), g in groups.items() if dt == "reference"
            ]
            if not references:
                continue
            reference = references[0]

            def trend_of(frame: pd.DataFrame, col: str = column) -> float | None:
                y = frame.sort_values("time")[col].dropna().to_numpy(float)
                if y.size < 3:  # noqa: PLR2004 - trend needs >= 3 points
                    return None
                return self._trend_statistic(y)

            obs_trend = trend_of(reference)
            if obs_trend is None:
                continue
            member_trends = {
                (data_id, dt): t
                for (data_id, dt), g in groups.items()
                if dt in ("to_benchmark", "other") and (t := trend_of(g)) is not None
            }
            if len(member_trends) < 2:  # noqa: PLR2004 - need ensemble spread
                continue
            result = scoring.ensemble_consistency(
                np.array(list(member_trends.values())),
                obs_trend,
                sigma_obs=self._sigma_obs,
                p_threshold=p_threshold,
            )
            submission_ids = [i for (i, dt) in member_trends if dt == "to_benchmark"]
            rows.append(
                {
                    "data_id": submission_ids[0] if submission_ids else "ensemble",
                    "data_type": "to_benchmark",
                    "var_id": f"{column}_trend_consistency",
                    "value": obs_trend,
                    "z": result.z,
                    "p_value": result.p_value,
                    "ensemble_mean": result.ensemble_mean,
                    "total_sigma": result.total_sigma,
                    "n_members": len(member_trends),
                    "passes": float(result.passes),
                },
            )

        if not rows:
            return output
        scores_df = pd.DataFrame(rows)
        if output.metrics is not None:
            scores_df = pd.concat(
                [output.metrics.to_pandas(), scores_df],
                ignore_index=True,
                sort=False,
            )
        return DiagnosticOutput(
            raw_output=output.raw_output,
            metrics=ibis.memtable(scores_df),
            variables=output.variables,
            data_sources=output.data_sources,
        )
