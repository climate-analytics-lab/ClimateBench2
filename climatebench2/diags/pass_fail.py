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
from esmvalcore.preprocessor import (
    anomalies,
    area_statistics,
    extract_region,
    regrid,
    regrid_time,
)
from loguru import logger
from scipy import signal

from climateeval._config import setup_esmvaltool_config_and_logging
from climateeval._variable import COORDINATES
from climateeval.diags._base import DiagnosticOutput
from climateeval.diags._utils import DEFAULT_GRID
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


class SupersetExperimentMixin:
    """Mixin: superset experiment keys + graceful skip when they are absent.

    ClimateEval's ``ComplexDiagnostic`` requires the data dict to match
    ``_required_data_keys`` *exactly*. CB2 runs a whole Tier I suite from one
    experiment dict (``Suite.get_database`` hands the same object to every
    diagnostic), so CB2 complex diagnostics — and the CB2 gate wrappers around
    upstream ClimateEval ones — accept a *superset* of their required keys.
    With ``fail_on_missing_data=False`` (the CLI default) a gate whose
    experiments were not supplied at all is skipped with a warning instead of
    aborting the suite.

    Mix in *before* :class:`GateMixin` so the skip short-circuits gating too.
    """

    def _check_required_dict_keys(self, dict_: dict[str, Any], dict_name: str) -> None:
        """Require a *subset* match so one suite dict feeds every gate."""
        required: tuple[str, ...] = self._required_data_keys  # type: ignore[attr-defined]
        missing = set(required) - set(dict_)
        if missing:
            name = getattr(self, "name", type(self).__name__)
            msg = (
                f"Missing keys {sorted(missing)} for {dict_name} dictionary of "
                f"diagnostic '{name}' (required: {required})"
            )
            raise ValueError(msg)

    def get_output(self, data: Any, data_information: Any) -> DiagnosticOutput:
        """Run the diagnostic; degrade to an empty output on missing keys."""
        try:
            self._check_required_dict_keys(data, "data")
        except ValueError as exc:
            if self._fail_on_missing_data:  # type: ignore[attr-defined]
                raise
            logger.warning(f"Skipping gate '{self.name}': {exc}")  # type: ignore[attr-defined]
            return DiagnosticOutput(
                raw_output=None,
                metrics=None,
                variables=None,  # type: ignore[arg-type] - Suite skips None tables
                data_sources=None,  # type: ignore[arg-type]
            )
        return super().get_output(data, data_information)  # type: ignore[misc]


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
    """Ratio of *integrated* spectral power between two period bands.

    Welch PSD, then ``∫S df`` over each band (paper I.5b: integrated power,
    not the mean PSD — the 1–2 yr band spans 0.5 cycles/yr against the 2–7 yr
    band's 0.357, so a mean-PSD ratio runs ≈ 1.4× high).

    Defaults implement the ENSO spectral-shape check (metrics_reference I.5b):
    power in the 2–7 yr band over the 1–2 yr band of a monthly index.
    """
    x = np.asarray(series, dtype=float)
    x = x[np.isfinite(x)]
    nperseg = min(len(x), 20 * MONTHS_PER_YEAR)  # 20-yr segments resolve 7-yr power
    freqs, psd = signal.welch(x - x.mean(), fs=fs, nperseg=nperseg)

    def band_power(period_band: tuple[float, float]) -> float:
        lo_p, hi_p = period_band  # years
        mask = (freqs >= 1.0 / hi_p) & (freqs <= 1.0 / lo_p)
        if mask.sum() < 2:  # cannot integrate over fewer than two frequencies
            return float("nan")
        return float(np.trapezoid(psd[mask], freqs[mask]))

    return band_power(numerator_period_years) / band_power(denominator_period_years)


# ---------------------------------------------------------------------------
# Phase-1 gate diagnostics
# ---------------------------------------------------------------------------


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


class ENSOGate(GateMixin, Nino34):
    """Tier I checks I.5a/b: ENSO amplitude and spectral shape.

    Runs ClimateEval's ``Nino34`` diagnostic (deseasonalised monthly Niño-3.4
    SST anomalies) with ``_rolling_window_length = 1``: the paper's σ and
    spectrum are of the *unsmoothed* monthly anomalies, whereas ClimateEval's
    default 3-month running mean (the operational ONI definition) lowers σ by
    roughly 5–10% and reddens the spectrum. Then gates:

    - amplitude: σ(Niño-3.4) within ``tier1.enso.amplitude_range``;
    - spectral shape: Welch band-power ratio (2–7 yr)/(1–2 yr) above
      ``tier1.enso.band_power_ratio_min``.

    Teleconnections (I.5c) need pr/ta fields regressed on the index and land
    in Phase 4 (see docs/climateeval_delineation_plan.md §5).
    """

    # No 3-month running mean: gate the raw monthly anomalies (paper I.5a/b).
    _rolling_window_length: ClassVar[int] = 1

    # The Nino34 suite entry uses variable id `tos_nino34` (kept for
    # compatibility with ClimateEval's Tier2_ocean_monthly stanza).
    _gate_checks = _enso_checks("tos_nino34")

    def _preprocess(self, cube: Any, variable: Any) -> Any:
        """Niño-3.4 index, running mean applied only if it has ≥ 2 points.

        Mirrors ``Nino34._preprocess`` (same region, same deseasonalisation,
        same output calendar) minus the smoothing step: iris refuses a
        rolling window shorter than two points, so the upstream chain cannot
        express the paper's *unsmoothed* monthly index. Upstream-PR
        candidate: accept ``window_length = 1`` as a no-op, after which this
        override can go and only the ClassVar remains.
        """
        if self._rolling_window_length >= 2:
            return super()._preprocess(cube, variable)  # type: ignore[misc]
        with setup_esmvaltool_config_and_logging():
            cube = regrid(cube, DEFAULT_GRID, "linear", cache_weights=True)
            cube = extract_region(
                cube,
                start_longitude=self._start_longitude,
                end_longitude=self._end_longitude,
                start_latitude=self._start_latitude,
                end_latitude=self._end_latitude,
            )
            cube = anomalies(cube, period="month")
            cube = area_statistics(cube, "mean")
            cube = regrid_time(
                cube,
                frequency="mon",
                calendar="standard",
                units=COORDINATES["time"]["units"],
            )
        return cube
