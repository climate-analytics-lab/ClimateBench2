"""Tier I pass/fail gate machinery and the Phase-1 gate diagnostics.

A *gate* turns a quantity computed by an existing ClimateEval diagnostic into
a binary pass/fail against a bound from ``thresholds.yml``, emitted as extra
rows in the diagnostic's ``metrics`` table with the columns::

    data_id | data_type | var_id | value | bound_lower | bound_upper | passes

``passes`` is 1.0/0.0 (float, so the DuckDB schema stays numeric). Gates are
applied to *every* data source the diagnostic processed (the benchmarked
model, references, CMIP6 comparison models), so observations act as a sanity
check on the thresholds themselves.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar

import ibis
import numpy as np
import pandas as pd
from scipy import signal

from climateeval.diags._base import DiagnosticOutput
from climateeval.diags.complex import ECS
from climateeval.diags.simple import Nino34

from climatebench2._thresholds import get_threshold

if TYPE_CHECKING:
    from collections.abc import Callable

MONTHS_PER_YEAR = 12


# ---------------------------------------------------------------------------
# Gate machinery
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GateCheck:
    """One pass/fail check on a column of a diagnostic's raw output.

    ``statistic`` reduces the (time-ordered) series of ``column`` values for
    one data source to a scalar; ``None`` means the column already holds a
    scalar (one row per data source). Bounds are inclusive; ``None`` means
    unbounded on that side.
    """

    check_id: str
    column: str
    statistic: Callable[[pd.Series], float] | None = None
    lower: float | None = None
    upper: float | None = None


def gate_metrics(
    raw_df: pd.DataFrame,
    checks: tuple[GateCheck, ...],
    *,
    time_column: str = "time",
) -> pd.DataFrame:
    """Evaluate ``checks`` per data source of a raw-output DataFrame."""
    rows: list[dict[str, Any]] = []
    group_cols = [c for c in ("data_id", "data_type") if c in raw_df.columns]
    for keys, group in raw_df.groupby(group_cols, sort=False):
        key_dict = dict(zip(group_cols, keys if isinstance(keys, tuple) else (keys,)))
        if time_column in group.columns:
            group = group.sort_values(time_column)
        for check in checks:
            if check.column not in group.columns:
                continue
            series = group[check.column].dropna()
            if series.empty:
                continue
            value = (
                float(series.iloc[0])
                if check.statistic is None
                else float(check.statistic(series))
            )
            passes = (check.lower is None or value >= check.lower) and (
                check.upper is None or value <= check.upper
            )
            rows.append(
                {
                    **key_dict,
                    "var_id": check.check_id,
                    "value": value,
                    "bound_lower": np.nan if check.lower is None else check.lower,
                    "bound_upper": np.nan if check.upper is None else check.upper,
                    "passes": float(passes),
                },
            )
    return pd.DataFrame(rows)


def apply_gate(
    output: DiagnosticOutput,
    checks: tuple[GateCheck, ...],
) -> DiagnosticOutput:
    """Append gate metrics to a :class:`DiagnosticOutput`."""
    if output.raw_output is None or not checks:
        return output
    raw_df = output.raw_output.to_pandas()
    gates_df = gate_metrics(raw_df, checks)
    if gates_df.empty:
        return output
    if output.metrics is not None:
        existing = output.metrics.to_pandas()
        gates_df = pd.concat([existing, gates_df], ignore_index=True, sort=False)
    return DiagnosticOutput(
        raw_output=output.raw_output,
        metrics=ibis.memtable(gates_df),
        variables=output.variables,
        data_sources=output.data_sources,
    )


class GateMixin:
    """Mixin appending ``_gate_checks`` results to any diagnostic's output."""

    _gate_checks: ClassVar[tuple[GateCheck, ...]] = ()

    def get_output(self, data: Any, data_information: Any) -> DiagnosticOutput:
        output = super().get_output(data, data_information)  # type: ignore[misc]
        return apply_gate(output, self._gate_checks)


# ---------------------------------------------------------------------------
# Series statistics used by gates
# ---------------------------------------------------------------------------


def band_power_ratio(
    series: pd.Series,
    *,
    fs: float = float(MONTHS_PER_YEAR),
    numerator_period_years: tuple[float, float] = (2.0, 7.0),
    denominator_period_years: tuple[float, float] = (1.0, 2.0),
) -> float:
    """Ratio of mean spectral power between two period bands (Welch PSD).

    Defaults implement the ENSO spectral-shape check (metrics_reference I.5b):
    power in the 2–7 yr band over the 1–2 yr band of a monthly index.
    """
    x = np.asarray(series, dtype=float)
    x = x[np.isfinite(x)]
    nperseg = min(len(x), 20 * MONTHS_PER_YEAR)  # 20-yr segments resolve 7-yr power
    freqs, psd = signal.welch(x - x.mean(), fs=fs, nperseg=nperseg)

    def band_mean(period_band: tuple[float, float]) -> float:
        lo_p, hi_p = period_band  # years
        mask = (freqs >= 1.0 / hi_p) & (freqs <= 1.0 / lo_p)
        if not mask.any():
            return float("nan")
        return float(psd[mask].mean())

    return band_mean(numerator_period_years) / band_mean(denominator_period_years)


# ---------------------------------------------------------------------------
# Phase-1 gate diagnostics
# ---------------------------------------------------------------------------


def _ecs_checks() -> tuple[GateCheck, ...]:
    lo, hi = get_threshold("tier1.ecs.range")
    return (GateCheck(check_id="ecs_gate", column="ecs", lower=lo, upper=hi),)


def _enso_checks(column: str) -> tuple[GateCheck, ...]:
    amp_lo, amp_hi = get_threshold("tier1.enso.amplitude_range")
    ratio_min = get_threshold("tier1.enso.band_power_ratio_min")
    return (
        GateCheck(
            check_id="enso_amplitude",
            column=column,
            statistic=lambda s: float(s.std(ddof=1)),
            lower=amp_lo,
            upper=amp_hi,
        ),
        GateCheck(
            check_id="enso_spectral_ratio",
            column=column,
            statistic=band_power_ratio,
            lower=ratio_min,
        ),
    )


class ECSGate(GateMixin, ECS):
    """Tier I check I.6c: ECS from Gregory regression within [1, 7] K.

    Runs ClimateEval's ``ECS`` complex diagnostic (abrupt-4xCO2 + piControl,
    150-yr Gregory regression) unchanged and gates the resulting ECS against
    ``tier1.ecs.range``.
    """

    _gate_checks = _ecs_checks()


class ENSOGate(GateMixin, Nino34):
    """Tier I checks I.5a/b: ENSO amplitude and spectral shape.

    Runs ClimateEval's ``Nino34`` diagnostic (monthly Niño-3.4 SST anomaly,
    3-month running mean) unchanged, then gates:

    - amplitude: σ(Niño-3.4) within ``tier1.enso.amplitude_range``;
    - spectral shape: Welch band-power ratio (2–7 yr)/(1–2 yr) above
      ``tier1.enso.band_power_ratio_min``.

    Teleconnections (I.5c) need pr/ta fields regressed on the index and land
    in Phase 4 (see docs/climateeval_delineation_plan.md §5).
    """

    # The Nino34 suite entry uses variable id `tos_nino34` (kept for
    # compatibility with ClimateEval's Tier2_ocean_monthly stanza).
    _gate_checks = _enso_checks("tos_nino34")
