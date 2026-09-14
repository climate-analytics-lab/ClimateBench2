"""Tier II scoring diagnostics.

- :class:`ScoredAnnualMeanTimeSeries` / :class:`ScoredMonthlyMeanTimeSeries` /
  :class:`ScoredAnnualMaxTimeSeries` — the time-series diagnostics the Tier II
  suites name. They are **thin subclasses of the ClimateEval diagnostics**
  (``ScoredAnnualMaxTimeSeries`` additionally takes a per-gridpoint annual
  maximum before the area mean): they emit the raw series and ClimateEval's
  deterministic metrics, and nothing else.

  The probabilistic score is *not* computed here. Since ensemble members
  arrive as separate data sources (``--member`` / DRS discovery, one run per
  member), the fair CRPS across a model's members can only be formed once
  every member has run — so it is a post-processing pass over the finished
  database, :mod:`climatebench2.scoring_pass`, which ``climatebench2 score``
  runs after the suites and ``climatebench2 leaderboard --rescore`` can
  re-run. Scoring each source separately, as this module used to, made every
  model an M = 1 "ensemble" whose fair CRPS is undefined.

- :class:`TrendConsistency` — regime (c) applied to the OLS trend of the
  series: is the observed trend consistent with the ensemble trend
  distribution? Ensemble = the benchmarked model + CMIP6 comparison members.
  The internal-variability term (piControl chunking) still needs a piControl
  data path; until then ``sigma_internal`` defaults to 0 and the test is
  spread+obs-error only (documented limitation).

Metrics rows use the numeric-column convention of ``pass_fail``:
``value``/``passes`` plus score-specific columns.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

import ibis
import numpy as np
import pandas as pd
from scipy import stats

from esmvalcore.preprocessor import (
    annual_statistics,
    area_statistics,
    regrid,
    regrid_time,
)

from climateeval._config import setup_esmvaltool_config_and_logging
from climateeval._variable import COORDINATES
from climateeval.diags._base import DiagnosticOutput
from climateeval.diags._utils import DEFAULT_GRID
from climateeval.diags.simple import AnnualMeanTimeSeries, MeanTimeSeries

from climatebench2 import scoring
from climatebench2._thresholds import get_threshold

if TYPE_CHECKING:
    from collections.abc import Callable

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


class ScoredAnnualMeanTimeSeries(AnnualMeanTimeSeries):
    """Annual-mean series scored by :mod:`climatebench2.scoring_pass`.

    A thin alias of ClimateEval's diagnostic so the Tier II suite YAMLs keep
    naming a CB2 class (and so the protocol's scored variables stay visible
    in the suite); the fair CRPS, its ESS standard error, the block-bootstrap
    interval and the skill against the CMIP6 median are appended to this
    diagnostic's ``metrics`` table by the post-processing pass, once every
    ensemble member has been ingested.
    """


class ScoredMonthlyMeanTimeSeries(MeanTimeSeries):
    """Monthly-mean series scored by :mod:`climatebench2.scoring_pass`."""


class ScoredAnnualMaxTimeSeries(AnnualMeanTimeSeries):
    """TXx-style annual block maxima, scored by the post-processing pass.

    Per-gridpoint annual maximum first, then the area mean — the global-mean
    TXx series of metrics_reference.md §II.1 "Daily tas extremes". Feed it
    daily ``tasmax`` (or ``tas``); on monthly input it degrades to the
    annual maximum of monthly means (documented, weaker).
    """

    def _preprocess(self, cube: Any, _variable: Any) -> Any:
        with setup_esmvaltool_config_and_logging():
            cube = regrid(cube, DEFAULT_GRID, "linear", cache_weights=True)
            cube = annual_statistics(cube, "max")  # per-gridpoint block max
            cube = area_statistics(cube, "mean")
            cube = regrid_time(
                cube,
                frequency="yr",
                calendar="standard",
                units=COORDINATES["time"]["units"],
            )
        return cube


class TrendConsistency(AnnualMeanTimeSeries):
    """Regime-(c) consistency of the observed trend with the ensemble.

    Post-processes the annual-mean series: OLS trend per data source; the
    ensemble distribution pools the benchmarked model and the CMIP6
    comparison members; the observed (reference) trend is tested with
    :func:`climatebench2.scoring.ensemble_consistency` at the protocol's
    ``tier2.consistency_p_value``.

    ``sigma_internal`` (piControl-chunk trend variability) still needs a
    piControl data path; ``sigma_obs`` may be passed as a diagnostic kwarg
    per variable until observational error fields are plumbed through.
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
