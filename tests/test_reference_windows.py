"""Tests for the per-variable scored window (`climatebench2.reference_windows`).

The protocol's Tier II window runs to the last complete year, but the
observational references lag by months to years, and ClimateEval **drops** a
reference whose record stops short of the requested range rather than clipping
it — which deletes the variable's whole scorecard row. These tests cover the
clipping that keeps the row: coverage from the NetCDF header, partial calendar
years excluded, and the suite rewrite the CLI applies.
"""

from __future__ import annotations

import pytest

from climatebench2 import reference_windows

netCDF4 = pytest.importorskip("netCDF4")  # noqa: N816


def _write(path, first_year, first_month, last_year, last_month) -> None:  # noqa: ANN001
    """A NetCDF file whose monthly time axis spans the given months."""
    path.parent.mkdir(parents=True, exist_ok=True)
    months = [
        (year, month)
        for year in range(first_year, last_year + 1)
        for month in range(1, 13)
        if (year, month) >= (first_year, first_month)
        and (year, month) <= (last_year, last_month)
    ]
    with netCDF4.Dataset(path, "w") as dataset:
        dataset.createDimension("time", len(months))
        time = dataset.createVariable("time", "f8", ("time",))
        time.units = "days since 1850-01-01"
        time.calendar = "standard"
        time[:] = [
            (year - 1850) * 365.0 + (month - 1) * 30.0 + 15.0 for year, month in months
        ]


NOMINAL = "20150101/20251231"


def test_coverage_excludes_partial_years(tmp_path) -> None:  # noqa: ANN001
    """HadCRUT5-shaped record: 1850-01 .. 2023-09 -> complete years 1850-2022."""
    _write(
        tmp_path / "observation_HadCRUT5" / "mon" / "tas" / "a.nc",
        1850,
        1,
        2023,
        9,
    )
    assert reference_windows.source_coverage(
        tmp_path,
        "observation_HadCRUT5",
        "mon",
        "tas",
    ) == (1850, 2022)


def test_coverage_spans_several_files_and_a_late_start(tmp_path) -> None:  # noqa: ANN001
    root = tmp_path / "observation_CERES-EBAF" / "mon" / "rlut"
    _write(root / "a.nc", 2000, 3, 2009, 12)
    _write(root / "b.nc", 2010, 1, 2025, 9)
    assert reference_windows.source_coverage(
        tmp_path,
        "observation_CERES-EBAF",
        "mon",
        "rlut",
    ) == (2001, 2024)


def test_coverage_is_none_when_nothing_is_staged(tmp_path) -> None:  # noqa: ANN001
    assert (
        reference_windows.source_coverage(tmp_path, "observation_X", "mon", "tas")
        is None
    )


def test_window_is_clipped_to_the_reference(tmp_path) -> None:  # noqa: ANN001
    _write(tmp_path / "observation_HadCRUT5" / "mon" / "tas" / "a.nc", 1850, 1, 2023, 9)
    variable = {
        "id": "tas",
        "var_name": "tas",
        "frequency": "mon",
        "reference_data": "climateeval.data.HadCRUT5",
    }
    assert (
        reference_windows.resolve_variable_timerange(variable, NOMINAL, tmp_path)
        == "20150101/20221231"
    )


def test_window_is_untouched_without_a_data_root_or_a_reference(tmp_path) -> None:  # noqa: ANN001
    variable = {
        "id": "tas",
        "var_name": "tas",
        "frequency": "mon",
        "reference_data": "climateeval.data.HadCRUT5",
    }
    assert (
        reference_windows.resolve_variable_timerange(variable, NOMINAL, None) == NOMINAL
    )
    # Nothing staged for it: clipping could only invent a window.
    assert (
        reference_windows.resolve_variable_timerange(variable, NOMINAL, tmp_path)
        == NOMINAL
    )
    no_reference = {"id": "x", "var_name": "tas", "frequency": "mon"}
    assert (
        reference_windows.resolve_variable_timerange(no_reference, NOMINAL, tmp_path)
        == NOMINAL
    )


def test_a_reference_that_never_reaches_the_window_keeps_it(tmp_path) -> None:  # noqa: ANN001
    """No overlap at all -> leave the nominal window and let the usual warning fire."""
    _write(
        tmp_path / "observation_HadCRUT5" / "mon" / "tas" / "a.nc", 1850, 1, 2000, 12
    )
    variable = {
        "id": "tas",
        "var_name": "tas",
        "frequency": "mon",
        "reference_data": "climateeval.data.HadCRUT5",
    }
    assert (
        reference_windows.resolve_variable_timerange(variable, NOMINAL, tmp_path)
        == NOMINAL
    )


def test_apply_reference_windows_rewrites_every_variable(tmp_path) -> None:  # noqa: ANN001
    _write(tmp_path / "observation_HadCRUT5" / "mon" / "tas" / "a.nc", 1850, 1, 2023, 9)
    definition = [
        {
            "name": "annual_mean_timeseries",
            "variables": [
                {
                    "id": "tas",
                    "var_name": "tas",
                    "frequency": "mon",
                    "reference_data": "climateeval.data.HadCRUT5",
                },
                {
                    "id": "pr",
                    "var_name": "pr",
                    "frequency": "mon",
                    "reference_data": "climateeval.data.GPCP",
                },
            ],
        },
    ]
    resolved: dict[str, str] = {}
    out = reference_windows.apply_reference_windows(
        definition,
        NOMINAL,
        tmp_path,
        resolved=resolved,
    )
    # `annual_mean_timeseries` is scored on anomalies, so its window reaches
    # back to the baseline window's first year; the end is still clipped to
    # what the reference actually covers (HadCRUT5 here stops 2023-09, so
    # 2022 is its last complete scored year).
    windows = {v["id"]: v["timerange"] for v in out[0]["variables"]}
    assert windows == {"tas": "19850101/20221231", "pr": "19850101/20251231"}
    assert resolved == {
        "annual_mean_timeseries/tas": ("19850101/20221231", "19850101/20251231"),
        "annual_mean_timeseries/pr": ("19850101/20251231", "19850101/20251231"),
    }
    # Only the clipped one is reported: `pr` got exactly what was asked for.
    assert list(reference_windows.summarise(resolved)) == [
        "  annual_mean_timeseries/tas: 19850101/20221231 "
        "(asked for 19850101/20251231)",
    ]


def test_only_the_anomaly_scored_entries_reach_back_to_the_baseline() -> None:
    """The EOF basis and the maps keep the test window; the series do not."""
    definition = [
        {
            "name": name,
            "variables": [{"id": "tas", "var_name": "tas", "frequency": "mon"}],
        }
        for name in ("annual_mean_timeseries", "map", "eof_projection", "sst")
    ]
    out = reference_windows.apply_reference_windows(definition, NOMINAL, None)
    used = {entry["name"]: entry["variables"][0]["timerange"] for entry in out}
    assert used == {
        "annual_mean_timeseries": "19850101/20251231",
        "sst": "19850101/20251231",
        "map": NOMINAL,
        "eof_projection": NOMINAL,
    }


def test_cli_materialises_a_windowed_suite(tmp_path) -> None:  # noqa: ANN001
    yaml = pytest.importorskip("yaml")

    from climatebench2._cli import materialise_windowed_suite

    _write(tmp_path / "observation_HadCRUT5" / "mon" / "tas" / "a.nc", 1850, 1, 2023, 9)
    source = tmp_path / "MySuite.yml"
    source.write_text(
        yaml.safe_dump(
            [
                {
                    "name": "annual_mean_timeseries",
                    "diagnostic": "climatebench2.diags.ScoredAnnualMeanTimeSeries",
                    "variables": [
                        {
                            "id": "tas",
                            "var_name": "tas",
                            "frequency": "mon",
                            "reference_data": "climateeval.data.HadCRUT5",
                        },
                    ],
                },
            ],
        ),
        encoding="utf-8",
    )
    out_dir = tmp_path / "windowed"
    out_dir.mkdir()
    target, used = materialise_windowed_suite(str(source), out_dir, NOMINAL, tmp_path)

    # Same stem, so the suite keeps its name and its database filename.
    assert target.endswith("MySuite.yml")
    assert used == {
        "annual_mean_timeseries/tas": ("19850101/20221231", "19850101/20251231"),
    }
    written = yaml.safe_load(open(target, encoding="utf-8"))  # noqa: PTH123, SIM115
    assert written[0]["variables"][0]["timerange"] == "19850101/20221231"


# ---------------------------------------------------------------------------
# The full-record suite: no nominal window, only a staged reference narrows it
# ---------------------------------------------------------------------------


def _imerg_files(root, last_year: int = 2025) -> None:  # noqa: ANN001
    """IMERG's shape: daily from 2000-06 to ``last_year``-12, one file a year.

    ``_write`` lays down a monthly axis, which is all `source_coverage` reads
    (first/last time value), so the months stand in for the days.
    """
    var_dir = root / "observation_IMERG" / "day" / "pr"
    _write(var_dir / "pr_day_IMERG-V07B_1deg_20000601-20001231.nc", 2000, 6, 2000, 12)
    for year in range(2001, last_year + 1):
        _write(
            var_dir / f"pr_day_IMERG-V07B_1deg_{year}0101-{year}1231.nc",
            year,
            1,
            year,
            12,
        )


#: The daily suite in miniature: the in-sample ETCCDI entry (pr referenced,
#: tasmax not), the Perkins entry whose tas reference is not staged, and the
#: held-out annual series that must keep the whole record.
DAILY_DEFINITION = [
    {
        "name": "extremes",
        "variables": [
            {"id": "tasmax", "var_name": "tasmax", "frequency": "day"},
            {
                "id": "pr",
                "var_name": "pr",
                "frequency": "day",
                "reference_data": "climatebench2.data.IMERG",
            },
        ],
    },
    {
        "name": "perkins",
        "variables": [
            {
                "id": "tas_anomaly_land",
                "var_name": "tas",
                "frequency": "day",
                "reference_data": "climateeval.data.ERA5Hourly",
            },
            {
                "id": "pr_intensity_land",
                "var_name": "pr",
                "frequency": "day",
                "reference_data": "climatebench2.data.IMERG",
            },
        ],
    },
    {
        "name": "pr_extremes_series",
        "variables": [
            {
                "id": "pr",
                "var_name": "pr",
                "frequency": "day",
                "reference_data": "climatebench2.data.IMERG",
            },
        ],
    },
]


def _daily_windows(tmp_path):  # noqa: ANN001, ANN202
    out = reference_windows.apply_reference_windows(
        DAILY_DEFINITION,
        None,
        tmp_path,
    )
    return {
        f"{entry['name']}/{variable['id']}": variable.get("timerange")
        for entry in out
        for variable in entry["variables"]
    }


def test_the_in_sample_pr_entries_run_over_the_imerg_overlap(tmp_path) -> None:  # noqa: ANN001
    """2001–2014: IMERG's complete years, clipped before the test window.

    IMERG starts 2000-06-01 (so 2000 is not a complete year) and runs to
    2025 (so the clip, not the record, fixes the end). Both the model and
    the reference are loaded through this one `timerange`, which is the
    point: the two Rx1day climatologies are then the same statistic.
    """
    _imerg_files(tmp_path)
    used = _daily_windows(tmp_path)
    assert used["extremes/pr"] == "20010101/20141231"
    assert used["perkins/pr_intensity_land"] == "20010101/20141231"


def test_an_unreferenced_variable_keeps_the_full_record(tmp_path) -> None:  # noqa: ANN001
    """`tasmax` has no daily observational product, so nothing may clip it."""
    _imerg_files(tmp_path)
    used = _daily_windows(tmp_path)
    assert used["extremes/tasmax"] is None


def test_a_reference_that_is_not_staged_does_not_clip(tmp_path) -> None:  # noqa: ANN001
    """The Perkins `tas` entries: ERA5Daily is merged upstream, not staged.

    Capping a model's record at 2014 for an entry that will not be scored
    anyway would only throw data away, so an unstaged reference leaves the
    full record alone — exactly as `clip_to_source` does for the monthly
    suite.
    """
    _imerg_files(tmp_path)
    used = _daily_windows(tmp_path)
    assert used["perkins/tas_anomaly_land"] is None


def test_the_held_out_series_is_clipped_to_the_baseline_and_the_reference(
    tmp_path,
) -> None:  # noqa: ANN001
    """`pr_extremes_series` is regime (a): it needs 1985–2014 AND post-2015.

    It is listed in `tier2.anomaly_baseline`, so the pre-test cap the
    in-sample entries get must not touch it — capping it at 2014 would
    delete every scored year. But it is not left on the model's whole
    1850–2100 record either: it is clipped to the LATER of the baseline
    start (1985) and IMERG's own first complete year, through IMERG's own
    LAST complete year (2024 for `_imerg_files`'s record, per
    `source_coverage`) — a world away from the full record, which is what
    reading it for every comparison-ensemble member timed out the 12 h daily
    job doing (2026-09-26).
    """
    _imerg_files(tmp_path)
    used = _daily_windows(tmp_path)
    assert used["pr_extremes_series/pr"] == "20010101/20241231"


def test_the_held_out_series_keeps_its_last_partial_year_out(tmp_path) -> None:  # noqa: ANN001
    """The real IMERG record (2000-06 .. 2025-09) drops its partial last year.

    Same shape as the real staged root today: a September cutoff means 2025
    is not a complete year, so the held-out series' upper bound is 2024, not
    2025 — same rule the in-sample entries already followed.
    """
    _write(
        tmp_path / "observation_IMERG" / "day" / "pr" / "a.nc",
        2000,
        6,
        2025,
        9,
    )
    used = _daily_windows(tmp_path)
    assert used["pr_extremes_series/pr"] == "20010101/20241231"
    # A monthly, nominal-window entry's own resolution is untouched by this
    # change to the full-record path.
    variable = {
        "id": "tas",
        "var_name": "tas",
        "frequency": "mon",
        "reference_data": "climateeval.data.HadCRUT5",
    }
    _write(tmp_path / "observation_HadCRUT5" / "mon" / "tas" / "a.nc", 1850, 1, 2023, 9)
    assert (
        reference_windows.resolve_variable_timerange(variable, NOMINAL, tmp_path)
        == "20150101/20221231"
    )


def test_a_full_record_suite_without_a_data_root_is_untouched() -> None:
    """No data root, no coverage, no clip — the suite runs as written."""
    out = reference_windows.apply_reference_windows(DAILY_DEFINITION, None, None)
    assert all(
        "timerange" not in variable
        for entry in out
        for variable in entry["variables"]
    )


def test_the_pre_test_cap_is_the_year_before_the_test_window() -> None:
    from climatebench2 import windows

    assert windows.pre_test_last_year() == 2014


def test_cli_materialises_the_real_daily_suite_against_a_staged_imerg(tmp_path) -> None:  # noqa: ANN001
    """The CLI branch, on the shipped YAML: only the IMERG entries move.

    `materialise_windowed_suite(..., nominal=None)` is what
    `SuiteSpec.reference_overlap` triggers for `ClimateBench2_TierII_daily`.
    """
    yaml = pytest.importorskip("yaml")
    pytest.importorskip("climateeval")

    from climatebench2._cli import _resolve_suite, materialise_windowed_suite

    _imerg_files(tmp_path)
    out_dir = tmp_path / "windowed"
    out_dir.mkdir()
    target, used = materialise_windowed_suite(
        _resolve_suite("ClimateBench2_TierII_daily"),
        out_dir,
        None,
        tmp_path,
    )

    # Every moved window is IMERG's overlap: 2001-2014 for the in-sample
    # entries, 2001-2024 for the held-out series (`source_coverage` reads
    # `_imerg_files`'s last file as ending 2024, not 2014, since nothing
    # caps its upper end at the pre-test year).
    assert used == {
        "extremes/pr": ("20010101/20141231", reference_windows.FULL_RECORD),
        "perkins/pr_intensity_land": (
            "20010101/20141231",
            reference_windows.FULL_RECORD,
        ),
        "perkins/pr_intensity_tropics": (
            "20010101/20141231",
            reference_windows.FULL_RECORD,
        ),
        "pr_extremes_series/pr": (
            "20010101/20241231",
            reference_windows.FULL_RECORD,
        ),
    }

    written = yaml.safe_load(open(target, encoding="utf-8"))  # noqa: PTH123, SIM115
    by_entry = {entry["name"]: entry["variables"] for entry in written}
    # The held-out series is clipped to the baseline and IMERG's own record,
    # not left on the model's whole 1850-2100 record.
    assert by_entry["pr_extremes_series"][0]["timerange"] == "20010101/20241231"
    # ... but the temperature extremes, which have no reference at all, do
    # keep the full record.
    assert all(
        "timerange" not in variable
        for variable in by_entry["extremes"]
        if variable["var_name"] != "pr"
    )


# ---------------------------------------------------------------------------
# The Tier II suite's cloud and CRE columns (2026-09-24): MODIS and CERES
# ---------------------------------------------------------------------------


def _modis_files(root, last_year: int) -> None:  # noqa: ANN001
    """MODIS's shape: monthly from 2002-07 to ``last_year + 1``-06, yearly files.

    Named ``YYYY01-YYYY12`` even for the partial first and last years, as
    ``fetch_modis.py`` writes them. The partial year after ``last_year``
    stands for "the record runs into the current year".
    """
    for var_name in ("clt", "clwvi", "clivi", "lwp"):
        var_dir = root / "observation_MODIS" / "mon" / var_name
        for year in range(2002, last_year + 2):
            _write(
                var_dir / f"{var_name}_Amon_MODIS_MYD08-M3_{year}01-{year}12.nc",
                year,
                7 if year == 2002 else 1,
                year,
                6 if year == last_year + 1 else 12,
            )


def _ceres_files(root) -> None:  # noqa: ANN001
    """CERES-EBAF's staged record, 2000-03 .. 2025-09, for the four TOA fluxes."""
    for var_name in ("rsut", "rsutcs", "rlut", "rlutcs", "rsdt"):
        _write(
            root / "observation_CERES-EBAF" / "mon" / var_name / "a.nc",
            2000,
            3,
            2025,
            9,
        )


def test_the_tier2_cloud_and_cre_windows_on_the_shipped_suite(tmp_path) -> None:  # noqa: ANN001
    """What `climatebench2 score` resolves for clt/clwvi/clivi and swcre/lwcre.

    * MODIS starts 2002-07, so its first complete year is 2003: the
      regime-(a) entry loads the clouds from **2003** (the 1985 baseline
      start, clipped), i.e. the anomaly baseline is **2003–2014**, 12 years,
      above `tier2.anomaly_baseline.min_years`; the scored steps still run
      to the last complete year.
    * The CREs are derived from CERES-EBAF, whose coverage is the
      intersection of the all-sky and clear-sky fluxes' — 2001–2024.
    * The entries that are not anomaly-scored keep the test window.
    """
    yaml = pytest.importorskip("yaml")
    pytest.importorskip("climateeval")

    from climatebench2 import windows
    from climatebench2._cli import (
        _resolve_suite,
        default_tier2_timerange,
        materialise_windowed_suite,
    )

    last = windows.last_complete_year()
    _modis_files(tmp_path, last)
    _ceres_files(tmp_path)
    out_dir = tmp_path / "windowed"
    out_dir.mkdir()
    nominal = default_tier2_timerange()
    target, used = materialise_windowed_suite(
        _resolve_suite("ClimateBench2_TierII"),
        out_dir,
        nominal,
        tmp_path,
    )

    ceres_last = min(2024, last)
    for var_id in ("clt", "clwvi", "clivi"):
        assert used[f"annual_mean_timeseries/{var_id}"][0] == f"20030101/{last}1231"
        for entry in ("eof_projection", "map", "reference_baseline", "annual_cycle"):
            assert used[f"{entry}/{var_id}"][0] == f"20150101/{last}1231", entry
    for var_id in ("swcre", "lwcre"):
        assert used[f"annual_mean_timeseries/{var_id}"][0] == (
            f"20010101/{ceres_last}1231"
        )
        assert used[f"eof_projection/{var_id}"][0] == f"20150101/{ceres_last}1231"

    # The anomaly baseline those windows imply is long enough to score.
    _, last_baseline = windows.baseline_window_years()
    assert last_baseline - 2003 + 1 == 12
    assert last_baseline - 2003 + 1 >= windows.anomaly_min_baseline_years()

    written = yaml.safe_load(open(target, encoding="utf-8"))  # noqa: PTH123, SIM115
    by_entry = {entry["name"]: entry["variables"] for entry in written}
    clt = next(v for v in by_entry["annual_mean_timeseries"] if v["id"] == "clt")
    assert clt["timerange"] == f"20030101/{last}1231"
    assert clt["reference_data"] == "climatebench2.data.MODIS"


def test_the_reference_diagnostics_reach_back_to_2003_for_modis(tmp_path) -> None:  # noqa: ANN001
    """`reference_baseline` and the EOF basis ask for 1985–2014 themselves.

    `clip_to_source` narrows that to the part MODIS has (2003–2014), and for
    a derived CERES variable to the intersection of its inputs (2001–2014).
    """
    pytest.importorskip("climateeval")

    _modis_files(tmp_path, 2025)
    _ceres_files(tmp_path)
    baseline = "19850101/20141231"
    for var_name in ("clt", "clwvi", "clivi"):
        assert reference_windows.clip_to_source(
            baseline,
            tmp_path,
            "observation_MODIS",
            "mon",
            var_name,
        ) == "20030101/20141231"
    for var_name in ("swcre", "lwcre"):
        assert reference_windows.clip_to_source(
            baseline,
            tmp_path,
            "observation_CERES-EBAF",
            "mon",
            var_name,
        ) == "20010101/20141231"
