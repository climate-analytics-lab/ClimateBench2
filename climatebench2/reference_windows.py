"""Clip the Tier II test window to what each reference product actually covers.

The reserved test window is ``tier2.test_window_start`` → the last **complete**
calendar year (:mod:`climatebench2.windows`), which in 2026 is 2015–2025.
Most observational products are not that current: HadCRUT5 ends 2023-09,
GPCP 2024-09, CERES-EBAF 2025-09, HadISST's ``siconc`` 2021-12 (MODIS, which
runs into the current year, is the exception). ClimateEval treats a
requested range the data does not cover as an error, not as something to clip::

    climateeval._utils._check_data
        if expected_max_year > actual_max_year:
            raise MissingDataError(...)

and ``climatebench2 score`` runs with ``fail_on_missing_data=False``, so that
error becomes a logged warning and **the reference is dropped**. A dropped
reference is not a smaller score, it is *no score at all*: the variable's whole
row vanishes from the scorecard, silently. On real data that removed ``tas`` —
the protocol's primary Tier II variable — from every Tier II table.

A second thing moves a window: regime (a) is scored on **anomalies about
each source's own 1985–2014 climatology**, so the suite entries whose series
are scored that way (``windows.scores_anomalies``) are loaded from the
baseline window's first year rather than from the start of the test window.
That extension happens *before* the clip, so a reference that starts inside
the baseline window (CERES-EBAF: 2000-03) keeps the part of it that exists
and the scoring pass decides whether it is enough.

A third case has no protocol window to clip at all. ``ClimateBench2_TierII_daily``
runs over the model's **whole record** (``_cli.SuiteSpec.window == "full"``),
because the paper defines its extremes, PDFs and diurnal climatologies over
the full historical record. That is right while an entry has no reference,
and wrong as soon as one appears: IMERG starts 2000-06, so an Rx1day
climatology over a model's 1850–2100 and one over IMERG's record are simply
different statistics, and an in-sample statistic must not reach into the
reserved post-2015 window either. For such a suite the window of a
**referenced** variable is the reference's own complete years clipped to end
at :func:`climatebench2.windows.pre_test_last_year`
(:func:`resolve_full_record_timerange`) — 2001–2014 for IMERG — and every
unreferenced variable keeps the full record untouched.

A fourth case is a referenced variable of such a suite whose entry is
listed in ``tier2.anomaly_baseline`` — ``pr_extremes_series``, the one
HELD-OUT entry of the daily suite. It is scored as an **anomaly** about the
reference's own baseline climatology and needs the post-2015 steps too, so
it must not be capped at ``pre_test_last_year`` the way the in-sample
entries are — but it does not need the model's whole 1850–2100 record
either: nothing before the baseline start or after the reference's own last
complete year is ever read by that score. So it is clipped to
``max(baseline_first_year, reference_first_complete_year)`` .. the
reference's own last complete year — 2001–2024 for IMERG, not the full
record — and that window is loaded for every source: the submission, IMERG
and every comparison-ensemble member alike. Leaving it on the full record,
as an earlier version of this module did, meant reading each of the
comparison ensemble's ~119 members' entire 1850–2100 daily ``pr`` record
just to compute the same statistic; the fix is this same per-reference
clip, just with a different upper bound (:func:`resolve_full_record_timerange`).

So the window is resolved **per variable and per suite entry** against the
reference actually staged, and the resolved window is what the suite
carries. The protocol's
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


def clip_to_coverage(nominal: str, coverage: tuple[int, int] | None) -> str:
    """``nominal`` narrowed to ``coverage``; unchanged if that is impossible."""
    if coverage is None:
        return nominal
    first = max(int(nominal.split("/")[0][:4]), coverage[0])
    last = min(int(nominal.split("/")[1][:4]), coverage[1])
    if first > last:
        # The reference does not reach the window at all; leave the nominal
        # window so the ordinary missing-data warning names the real problem.
        return nominal
    return windows.timerange(first, last)


def clip_to_source(
    nominal: str,
    data_root: Path | str | None,
    source_id: str,
    frequency: str,
    var_name: str,
) -> str:
    """``nominal`` narrowed to what one staged data source actually holds.

    The diagnostics that fetch an observational record themselves (the Tier II
    aggregated scalars, the reference-window diagnostics) ask for a window that
    ends at the last complete year, which no product reaches; without this they
    get a ``MissingDataError`` and fall back to "the model's own scalars, which
    the scoring pass then cannot score".
    """
    if data_root is None:
        return nominal
    coverage = source_coverage(data_root, source_id, frequency, var_name)
    if coverage is None:
        coverage = _derived_coverage(data_root, source_id, frequency, var_name)
    return clip_to_coverage(nominal, coverage)


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
    return clip_to_coverage(nominal, coverage)


#: What :func:`summarise` prints as the "asked for" window of a suite that
#: has none — the daily suite runs over the model's whole record
#: (``_cli.SuiteSpec.window == "full"``).
FULL_RECORD = "full record"


def resolve_full_record_timerange(
    variable: dict[str, Any],
    entry: str,
    data_root: Path | str | None,
) -> str | None:
    """The window one variable of a **full-record** suite is computed over.

    ``ClimateBench2_TierII_daily`` has no protocol window: its extremes,
    PDFs and diurnal climatologies are defined over the whole historical
    record and labelled in-sample. That is right for an entry with no
    observational reference — the numbers are reported, not scored — but
    wrong the moment one appears, for two reasons:

    * **the statistics would not be comparable.** IMERG starts 2000-06; a
      submission's daily record may start in 1850. An Rx1day climatology
      over 1850–2100 and one over 2001–2025 are not the same statistic, and
      the difference between them would be read as model error.
    * **an in-sample statistic must not reach into the reserved window.**
      The whole record includes 2015-present, which is the held-out period
      (:func:`climatebench2.windows.pre_test_last_year`).

    So a referenced variable of such a suite is computed over the
    reference's own complete years, and both the model and the reference get
    that same window, because it is written into the ``Variable`` both are
    loaded through. Where that window ends depends on how the entry is
    scored:

    * an **in-sample** entry (``windows.scores_anomalies`` false — the
      ETCCDI climatologies, the Perkins PDFs, the diurnal harmonic) is
      clipped to end before the test window
      (:func:`climatebench2.windows.pre_test_last_year`) — 2001–2014 for
      IMERG;
    * an entry the protocol scores as **anomalies**
      (``tier2.anomaly_baseline``, i.e. regime (a) — ``pr_extremes_series``,
      the one HELD-OUT entry here) needs the 1985–2014 baseline *and* the
      post-2015 steps, so it is **not** capped at ``pre_test_last_year``;
      it runs from the later of the baseline start and the reference's own
      first complete year through the reference's own **last** complete
      year — 2001–2024 for IMERG today. That is still a fraction of the
      model's 1850–2100 record: leaving this entry on the full record (an
      earlier version of this function did, via an early ``return None``)
      meant every comparison-ensemble member's entire daily ``pr`` record
      was read to compute the same statistic, which is what timed out the
      12 h daily job at ~66 members in (2026-09-26).

    ``None`` means "leave the full record alone", which is every case where
    clipping could only invent a window:

    * no data root, no ``reference_data``, or a reference class that will
      not import;
    * **nothing staged** for the reference. An unstaged reference is going
      to be dropped by ClimateEval anyway, and capping the model's record at
      2014 (or 2024) for an entry that will not be scored would only throw
      data away. This is what keeps the ``perkins`` ``tas`` entries on the
      full record today: ``ERA5Daily`` is merged upstream but no daily ERA5
      is staged;
    * a reference whose record lies entirely after the test window starts,
      which cannot happen today and would be a staging error if it did.
    """
    if data_root is None:
        return None
    reference = variable.get("reference_data")
    var_name = variable.get("var_name")
    frequency = variable.get("frequency")
    if not reference or not var_name or not frequency:
        return None
    source_id = _source_id(str(reference))
    if source_id is None:
        return None
    coverage = source_coverage(data_root, source_id, str(frequency), str(var_name))
    if coverage is None:
        coverage = _derived_coverage(
            data_root,
            source_id,
            str(frequency),
            str(var_name),
        )
    if coverage is None:
        return None
    if windows.scores_anomalies(entry):
        first = max(coverage[0], windows.baseline_window_years()[0])
        last = coverage[1]
    else:
        first = coverage[0]
        last = min(coverage[1], windows.pre_test_last_year())
    if first > last:
        return None
    return windows.timerange(first, last)


def apply_reference_windows(
    node: Any,  # noqa: ANN401
    nominal: str | None,
    data_root: Path | str | None,
    *,
    resolved: dict[str, tuple[str, str]] | None = None,
    entry: str = "",
) -> Any:  # noqa: ANN401
    """Walk a parsed suite definition, giving each variable its own window.

    ``nominal`` is the suite's protocol window, or ``None`` for a suite that
    has none (``_cli.SuiteSpec.window == "full"``). With ``None`` the only
    thing that can move a window is a **staged reference**, and it moves it
    to the reference's own record — the pre-test years for an in-sample
    entry, or the baseline start through the reference's own last complete
    year for an entry scored as anomalies
    (:func:`resolve_full_record_timerange`); a variable with no reference
    keeps the full record and gets no ``timerange`` key at all.

    With a ``nominal``, two things decide a variable's window, in this order:

    1. **the suite entry it belongs to.** An entry whose series are scored as
       anomalies (``windows.scores_anomalies``, i.e. regime (a)) is loaded
       from the **baseline window's first year**, not from the start of the
       test window: the anomaly of the submission, of the reference and of
       every comparison member is taken about that source's own 1985–2014
       climatology, so the climatology has to be in the cube. Every other
       entry — the EOF basis, the maps, the annual cycles, the zonal lines —
       keeps the nominal test window, because their statistic *is* the
       test-window field and a longer cube would silently redefine it.
    2. **what the reference actually covers**, as before. Clipping narrows
       both ends, so a reference that starts after 1985 (CERES-EBAF: 2000-03)
       keeps whatever part of the baseline it has — and the scoring pass, not
       this module, decides whether that is enough to anomalise with.

    Returns the rewritten definition. ``resolved``, when given, collects
    ``"<entry>/<variable id>" -> (window used, window asked for)`` for
    reporting — keyed by entry because one variable now gets *different*
    windows in different entries (``tas`` is loaded from 1985 for
    ``annual_mean_timeseries`` and from 2015 for ``map``).
    """
    if isinstance(node, list):
        return [
            apply_reference_windows(
                item,
                nominal,
                data_root,
                resolved=resolved,
                entry=entry,
            )
            for item in node
        ]
    if not isinstance(node, dict):
        return node
    if "var_name" in node and "frequency" in node:
        if nominal is None:
            full_record = resolve_full_record_timerange(node, entry, data_root)
            if full_record is None:
                return node
            if resolved is not None:
                var_id = str(node.get("id", node["var_name"]))
                key = f"{entry}/{var_id}" if entry else var_id
                resolved[key] = (full_record, FULL_RECORD)
            return {**node, "timerange": full_record}
        timerange = resolve_variable_timerange(node, nominal, data_root)
        if resolved is not None:
            var_id = str(node.get("id", node["var_name"]))
            key = f"{entry}/{var_id}" if entry else var_id
            resolved[key] = (timerange, nominal)
        return {**node, "timerange": timerange}
    if "variables" in node:
        entry = str(node.get("name", entry))
        if nominal is not None and windows.scores_anomalies(entry):
            nominal = windows.extend_to_baseline(nominal)
    return {
        key: apply_reference_windows(
            value,
            nominal,
            data_root,
            resolved=resolved,
            entry=entry,
        )
        for key, value in node.items()
    }


def summarise(resolved: dict[str, tuple[str, str]]) -> Iterable[str]:
    """Human-readable lines for every window that is not the protocol nominal.

    Two things move a window off the nominal: the regime-(a) extension back
    to the baseline window, and the clip to the reference's record. Both are
    worth printing, and the ``(asked for …)`` half says which happened.
    """
    for key, (timerange, nominal) in sorted(resolved.items()):
        if timerange != nominal:
            yield f"  {key}: {timerange} (asked for {nominal})"
