"""Clip the Tier II test window to what each reference product actually covers.

The reserved test window is ``tier2.test_window_start`` → the last **complete**
calendar year (:mod:`climatebench2.windows`), which in 2026 is 2015–2025. No
observational product is that current: HadCRUT5 ends 2023-09, GPCP 2024-09,
HadISST's ``siconc`` 2021-12, ESACCI-CLOUD 2016-12. ClimateEval treats a
requested range the data does not cover as an error, not as something to clip::

    climateeval._utils._check_data
        if expected_max_year > actual_max_year:
            raise MissingDataError(...)

and ``climatebench2 score`` runs with ``fail_on_missing_data=False``, so that
error becomes a logged warning and **the reference is dropped**. A dropped
reference is not a smaller score, it is *no score at all*: the variable's whole
row vanishes from the scorecard, silently. On real data that removed ``tas`` —
the protocol's primary Tier II variable — from every Tier II table.

So the window is resolved **per variable** against the reference actually
staged, and the resolved window is what the suite carries. The protocol's
intent is preserved: every model is scored over the same window for a given
variable (the window is a property of the reference, not of the submission),
and the window used is reported rather than assumed. A variable whose reference
stops before the test window begins keeps the nominal window and is left to the
ordinary missing-data path.

Coverage is read from the NetCDF headers (first/last ``time`` value), not by
loading the cubes: a few milliseconds per file.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from climatebench2 import windows

if TYPE_CHECKING:
    from collections.abc import Iterable

#: ``path -> (first_year, first_month, last_year, last_month)`` — headers are
#: read at most once.
_FILE_SPAN_CACHE: dict[str, tuple[int, int, int, int] | None] = {}

#: The last month of a calendar year. A record ending before it has an
#: incomplete final year, which the protocol does not score: an annual mean
#: over Jan-Sep is a seasonal-cycle artefact, not a year.
_DECEMBER = 12


def _file_span(path: Path) -> tuple[int, int, int, int] | None:
    """``(first_year, first_month, last_year, last_month)`` of one file."""
    key = str(path)
    if key in _FILE_SPAN_CACHE:
        return _FILE_SPAN_CACHE[key]
    result: tuple[int, int, int, int] | None = None
    try:
        import cftime  # noqa: PLC0415
        import netCDF4  # noqa: PLC0415

        with netCDF4.Dataset(path) as dataset:
            time = dataset.variables.get("time")
            if time is not None and time.size:
                calendar = getattr(time, "calendar", "standard")
                first = cftime.num2date(time[0], time.units, calendar)
                last = cftime.num2date(time[-1], time.units, calendar)
                result = (
                    int(first.year),
                    int(first.month),
                    int(last.year),
                    int(last.month),
                )
    except Exception:  # noqa: BLE001 - a header we cannot read is "unknown"
        result = None
    _FILE_SPAN_CACHE[key] = result
    return result


def source_coverage(
    data_root: Path | str,
    source_id: str,
    frequency: str,
    var_name: str,
) -> tuple[int, int] | None:
    """``(first, last)`` **complete** calendar years of a staged variable.

    A record that starts in March or stops in September contributes no usable
    annual mean for that year, so the partial years at either end are dropped.
    ``None`` when nothing is staged for it, when no header could be read, or
    when no whole year is covered — all of which mean "do not clip", so an
    unreadable product behaves exactly as it does today.
    """
    var_dir = Path(data_root) / source_id / frequency / var_name
    if not var_dir.is_dir():
        return None
    spans = [span for span in map(_file_span, sorted(var_dir.glob("*.nc"))) if span]
    if not spans:
        return None
    first_year, first_month = min((s[0], s[1]) for s in spans)
    last_year, last_month = max((s[2], s[3]) for s in spans)
    if first_month > 1:
        first_year += 1
    if last_month < _DECEMBER:
        last_year -= 1
    if first_year > last_year:
        return None
    return (first_year, last_year)


def _derived_coverage(
    data_root: Path | str,
    source_id: str,
    frequency: str,
    var_name: str,
) -> tuple[int, int] | None:
    """Coverage of a derived variable: the intersection of its inputs'."""
    try:
        from climateeval import Variable  # noqa: PLC0415

        variable = Variable(var_name, var_name, frequency)
        if not variable.derived:
            return None
        required = [v.var_name for v in variable.get_required_variables()]
    except Exception:  # noqa: BLE001
        return None
    spans = [
        source_coverage(data_root, source_id, frequency, name) for name in required
    ]
    if not spans or any(span is None for span in spans):
        return None
    return (
        max(span[0] for span in spans if span),
        min(span[1] for span in spans if span),
    )


def _source_id(class_path: str) -> str | None:
    """Data source id of a ``module.Class`` path, or ``None`` if unloadable."""
    try:
        from climateeval._utils import str_to_object  # noqa: PLC0415

        source_cls = str_to_object(class_path)
        return str(source_cls._information.id)  # noqa: SLF001
    except Exception:  # noqa: BLE001
        return None


def resolve_variable_timerange(
    variable: dict[str, Any],
    nominal: str,
    data_root: Path | str | None,
) -> str:
    """The window a variable is really scored over.

    ``nominal`` is clipped to the reference's coverage. The clip is dropped
    (``nominal`` is returned unchanged) when there is no data root, no
    ``reference_data``, nothing staged for it, or no overlap at all — in every
    one of those cases clipping could only invent a window.
    """
    if data_root is None:
        return nominal
    reference = variable.get("reference_data")
    var_name = variable.get("var_name")
    frequency = variable.get("frequency")
    if not reference or not var_name or not frequency:
        return nominal
    source_id = _source_id(str(reference))
    if source_id is None:
        return nominal
    coverage = source_coverage(data_root, source_id, str(frequency), str(var_name))
    if coverage is None:
        # A derived variable (rtnt, phcint) is never staged under its own name;
        # `DataSource.get_cube` builds it from the variables ESMValCore says it
        # requires, so its coverage is their intersection.
        coverage = _derived_coverage(
            data_root,
            source_id,
            str(frequency),
            str(var_name),
        )
    if coverage is None:
        return nominal

    first_nominal = int(nominal.split("/")[0][:4])
    last_nominal = int(nominal.split("/")[1][:4])
    first = max(first_nominal, coverage[0])
    last = min(last_nominal, coverage[1])
    if first > last:
        # The reference does not reach the window at all; leave the nominal
        # window so the ordinary missing-data warning names the real problem.
        return nominal
    return windows.timerange(first, last)


def apply_reference_windows(
    node: Any,  # noqa: ANN401
    nominal: str,
    data_root: Path | str | None,
    *,
    resolved: dict[str, str] | None = None,
) -> Any:  # noqa: ANN401
    """Walk a parsed suite definition, giving each variable its own window.

    Returns the rewritten definition. ``resolved``, when given, collects
    ``variable id -> timerange`` for reporting.
    """
    if isinstance(node, list):
        return [
            apply_reference_windows(item, nominal, data_root, resolved=resolved)
            for item in node
        ]
    if not isinstance(node, dict):
        return node
    if "var_name" in node and "frequency" in node:
        timerange = resolve_variable_timerange(node, nominal, data_root)
        if resolved is not None:
            resolved[str(node.get("id", node["var_name"]))] = timerange
        return {**node, "timerange": timerange}
    return {
        key: apply_reference_windows(value, nominal, data_root, resolved=resolved)
        for key, value in node.items()
    }


def summarise(resolved: dict[str, str], nominal: str) -> Iterable[str]:
    """Human-readable lines describing every window that had to be clipped."""
    for var_id, timerange in sorted(resolved.items()):
        if timerange != nominal:
            yield f"  {var_id}: {timerange} (nominal {nominal})"
