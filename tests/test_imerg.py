"""Tests for the staged IMERG daily-precipitation reference.

`climatebench2.data.IMERG` is what makes the precipitation half of
metrics_reference.md §II.1 *scorable*: before it, no daily observational
product existed anywhere in the stack, so the ETCCDI precipitation indices
and the wet-day intensity PDF were computed and thrown away.

Nothing is downloaded here. The tests write synthetic NetCDF files shaped
exactly like the staged contract — one file per calendar year,
``pr_day_IMERG-V07B_1deg_YYYY0101-YYYY1231.nc`` under
``<root>/observation_IMERG/day/pr/``, ``pr`` in kg m-2 s-1 with
``standard_name = precipitation_flux`` — and check that ClimateEval's
``DataSource`` machinery finds them, concatenates them, honours the
``timerange`` (both the filename pre-filter and the final clip) and converts
the units the same way it converts a model's ``pr``.
"""

from __future__ import annotations

import datetime as dt

import numpy as np
import pytest

netCDF4 = pytest.importorskip("netCDF4")  # noqa: N816
pytest.importorskip("climateeval")

from climateeval import Variable  # noqa: E402

from climatebench2 import reference_windows  # noqa: E402
from climatebench2.data import IMERG  # noqa: E402

#: IMERG's real grid is 1° global (lat −89.5…89.5, lon −179.5…179.5); the
#: tests use a handful of cells, because the DataSource's job is finding and
#: concatenating files, not resolution. The longitudes stay **negative**,
#: which is the part of the contract that matters: ClimateEval rotates a
#: −180…180 grid onto 0…360 itself (`_set_lon_to_0_360`), and it can only do
#: that if the staged grid is a proper periodic one.
LATS = np.array([-75.0, -45.0, -15.0, 15.0, 45.0, 75.0])
LONS = np.array([-150.0, -90.0, -30.0, 30.0, 90.0, 150.0])

#: kg m-2 s-1 that is exactly 1 mm day-1 once ESMValCore's precipitation_flux
#: conversion (divide by the 1000 kg m-3 density of water) has run.
ONE_MM_PER_DAY = 1.0 / 86400.0

TIME_UNITS = "days since 1970-01-01 00:00:00"


def _days(year: int, first_month: int = 1) -> list[float]:
    """Daily 12:00 offsets of one calendar year, from ``first_month`` on."""
    start = dt.date(year, first_month, 1)
    end = dt.date(year + 1, 1, 1)
    epoch = dt.date(1970, 1, 1)
    return [
        float((start - epoch).days + offset) + 0.5
        for offset in range((end - start).days)
    ]


def write_year(
    root,  # noqa: ANN001
    year: int,
    *,
    first_month: int = 1,
    value: float = ONE_MM_PER_DAY,
) -> None:
    """One staged IMERG year, following the file contract exactly."""
    var_dir = root / "observation_IMERG" / "day" / "pr"
    var_dir.mkdir(parents=True, exist_ok=True)
    days = _days(year, first_month)
    start = f"{year}{first_month:02d}01"
    path = var_dir / f"pr_day_IMERG-V07B_1deg_{start}-{year}1231.nc"
    with netCDF4.Dataset(path, "w") as ds:
        ds.createDimension("time", len(days))
        ds.createDimension("lat", LATS.size)
        ds.createDimension("lon", LONS.size)

        time = ds.createVariable("time", "f8", ("time",))
        time.units = TIME_UNITS
        time.calendar = "standard"
        time.standard_name = "time"
        time[:] = days

        lat = ds.createVariable("lat", "f8", ("lat",))
        lat.units = "degrees_north"
        lat.standard_name = "latitude"
        lat[:] = LATS

        lon = ds.createVariable("lon", "f8", ("lon",))
        lon.units = "degrees_east"
        lon.standard_name = "longitude"
        lon[:] = LONS

        pr = ds.createVariable("pr", "f4", ("time", "lat", "lon"))
        pr.units = "kg m-2 s-1"
        pr.standard_name = "precipitation_flux"
        pr.long_name = "Precipitation"
        pr[:] = np.full((len(days), LATS.size, LONS.size), value, dtype="f4")


@pytest.fixture
def staged(tmp_path):  # noqa: ANN001, ANN201
    """The real record's shape in miniature: 2000-06 onwards, yearly files."""
    write_year(tmp_path, 2000, first_month=6)
    for year in (2001, 2002, 2003):
        write_year(tmp_path, year)
    return tmp_path


def test_the_data_source_id_is_the_staged_directory_name() -> None:
    """`observation_IMERG` is what `_get_data_dir` globs, and what the suite
    header, the staging script and `reference_windows` all have to agree on.
    """
    assert IMERG().id == "observation_IMERG"
    assert IMERG().information.category == "observation"


def test_the_yearly_files_are_found_and_concatenated(staged) -> None:  # noqa: ANN001
    cube = IMERG().get_cube(
        staged,
        Variable("pr", "pr", "day"),
        download_missing_data=False,
    )
    # 2000-06-01..2003-12-31 = 214 + 365 + 365 + 365 days
    assert cube.shape == (214 + 365 * 3, LATS.size, LONS.size)
    times = cube.coord("time")
    assert times.units.num2date(times.points[0]).year == 2000
    assert times.units.num2date(times.points[-1]).year == 2003


def test_the_timerange_is_honoured(staged) -> None:  # noqa: ANN001
    """Both halves: the filename pre-filter and the final time extraction.

    Note the **last day is dropped**: ESMValCore reads the ``/20021231`` end
    of a timerange as the instant 2002-12-31T00:00, so a daily record
    stamped at 12:00 stops on 30 December. That is upstream behaviour and it
    applies identically to the submission, the reference and every
    comparison member — one day in ~5100 of the 2001–2014 window — so it
    cannot bias a comparison; it is asserted here so a change upstream is
    noticed rather than absorbed.
    """
    cube = IMERG().get_cube(
        staged,
        Variable("pr", "pr", "day", timerange="20010101/20021231"),
        download_missing_data=False,
    )
    times = cube.coord("time")
    assert str(times.units.num2date(times.points[0])) == "2001-01-01 12:00:00"
    assert str(times.units.num2date(times.points[-1])) == "2002-12-30 12:00:00"
    assert cube.shape[0] == 365 * 2 - 1
    years = {times.units.num2date(p).year for p in times.points}
    assert years == {2001, 2002}


def test_units_convert_to_mm_per_day_like_a_model(staged) -> None:  # noqa: ANN001
    """The suite asks for `mm day-1`; the ETCCDI code assumes it.

    The conversion is ESMValCore's `precipitation_flux` special case in
    `get_prepared_cube`, i.e. exactly the line that converts a submission's
    `pr` — not anything this DataSource does.
    """
    cube = IMERG().get_cube(
        staged,
        Variable("pr", "pr", "day", units="mm day-1"),
        download_missing_data=False,
    )
    assert str(cube.units) == "mm day-1"
    assert float(np.asarray(cube.data).max()) == pytest.approx(1.0, rel=1e-5)


def test_the_first_complete_year_is_2001(staged) -> None:  # noqa: ANN001
    """The record starts 2000-06-01, so the protocol's first usable year is 2001.

    This is the fact the in-sample precipitation window rests on: the
    reference's complete years, clipped to the pre-test period, are
    2001–2014.
    """
    assert reference_windows.source_coverage(
        staged,
        "observation_IMERG",
        "day",
        "pr",
    ) == (2001, 2003)


def test_a_variable_imerg_does_not_have_is_refused(staged) -> None:  # noqa: ANN001
    with pytest.raises(NotImplementedError, match="does not provide variable"):
        IMERG().get_cube(staged, Variable("tasmax", "tasmax", "day"))


def test_a_frequency_imerg_does_not_have_is_refused(staged) -> None:  # noqa: ANN001
    with pytest.raises(NotImplementedError, match="frequency"):
        IMERG().get_cube(staged, Variable("pr", "pr", "mon"))


def test_there_is_no_download_path(tmp_path) -> None:  # noqa: ANN001
    """IMERG has no ESMValTool CMORizer: missing data must say "stage it"."""
    from climateeval.exceptions import DownloadError

    with pytest.raises(DownloadError, match="cannot be downloaded|Stage one file"):
        IMERG().download(Variable("pr", "pr", "day"), tmp_path)
