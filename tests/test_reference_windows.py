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
    windows = {v["id"]: v["timerange"] for v in out[0]["variables"]}
    assert windows == {"tas": "20150101/20221231", "pr": NOMINAL}
    assert resolved == windows
    # Only the clipped one is reported.
    assert list(reference_windows.summarise(resolved, NOMINAL)) == [
        "  tas: 20150101/20221231 (nominal 20150101/20251231)",
    ]


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
    assert used == {"tas": "20150101/20221231"}
    written = yaml.safe_load(open(target, encoding="utf-8"))  # noqa: PTH123, SIM115
    assert written[0]["variables"][0]["timerange"] == "20150101/20221231"
