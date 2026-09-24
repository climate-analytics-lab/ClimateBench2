"""Tests for the staged MODIS monthly cloud reference.

`climatebench2.data.MODIS` is what puts the cloud variables back in the
Tier II figure set: their previous reference, ESACCI-CLOUD, ends in 2016,
two years into the reserved test window.

Nothing is downloaded here. The tests write synthetic NetCDF files shaped
exactly like the staged contract that ``runs/modis/fetch_modis.py`` writes —
one file per calendar year, ``<var>_Amon_MODIS_MYD08-M3_YYYY01-YYYY12.nc``
(named 01-12 even for a partial year) under
``<root>/observation_MODIS/mon/<var>/``, stamped on the 15th of each month,
lat ascending, lon −180…180 — and check that ClimateEval's ``DataSource``
machinery finds them, concatenates them and honours the ``timerange``.
"""

from __future__ import annotations

import datetime as dt

import numpy as np
import pytest

netCDF4 = pytest.importorskip("netCDF4")  # noqa: N816
pytest.importorskip("climateeval")

from climateeval import Variable  # noqa: E402

from climatebench2 import reference_windows  # noqa: E402
from climatebench2.data import MODIS  # noqa: E402

#: The real grid is 1° global (lat −89.5…89.5, lon −179.5…179.5); the tests
#: use a coarse periodic grid with the same property that matters — the
#: longitudes are **negative** and the guessed cell bounds span exactly
#: −180…180, so ClimateEval's `_set_lon_to_0_360` can rotate it.
LATS = np.array([-75.0, -45.0, -15.0, 15.0, 45.0, 75.0])
LONS = np.array([-150.0, -90.0, -30.0, 30.0, 90.0, 150.0])

TIME_UNITS = "days since 2000-01-01"

#: What fetch_modis.py writes per variable (standard_name, units).
ATTRS = {
    "clt": ("cloud_area_fraction", "%", 65.0),
    "clwvi": ("atmosphere_mass_content_of_cloud_condensed_water", "kg m-2", 0.14),
    "clivi": ("atmosphere_mass_content_of_cloud_ice", "kg m-2", 0.06),
    "lwp": (None, "kg m-2", 0.08),
}


def write_year(
    root,  # noqa: ANN001
    var_name: str,
    year: int,
    *,
    first_month: int = 1,
    last_month: int = 12,
) -> None:
    """One staged MODIS year of one variable, following the file contract."""
    standard_name, units, value = ATTRS[var_name]
    var_dir = root / "observation_MODIS" / "mon" / var_name
    var_dir.mkdir(parents=True, exist_ok=True)
    # Always named 01-12, even for the partial first and last years.
    path = var_dir / f"{var_name}_Amon_MODIS_MYD08-M3_{year}01-{year}12.nc"
    epoch = dt.date(2000, 1, 1)
    days = [
        float((dt.date(year, month, 15) - epoch).days)
        for month in range(first_month, last_month + 1)
    ]
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
        lat.axis = "Y"
        lat[:] = LATS

        lon = ds.createVariable("lon", "f8", ("lon",))
        lon.units = "degrees_east"
        lon.standard_name = "longitude"
        lon.axis = "X"
        lon[:] = LONS

        var = ds.createVariable(var_name, "f4", ("time", "lat", "lon"))
        var.units = units
        if standard_name is not None:
            var.standard_name = standard_name
        var[:] = np.full((len(days), LATS.size, LONS.size), value, dtype="f4")


def stage(root, var_name: str) -> None:  # noqa: ANN001
    """The real record's shape in miniature: 2002-07 .. 2006-06, yearly files."""
    write_year(root, var_name, 2002, first_month=7)
    for year in (2003, 2004, 2005):
        write_year(root, var_name, year)
    write_year(root, var_name, 2006, last_month=6)


@pytest.fixture
def staged(tmp_path):  # noqa: ANN001, ANN201
    for var_name in ATTRS:
        stage(tmp_path, var_name)
    return tmp_path


def _years(cube) -> list[int]:  # noqa: ANN001
    times = cube.coord("time")
    return [times.units.num2date(p).year for p in times.points]


def test_the_data_source_id_is_the_staged_directory_name() -> None:
    assert MODIS().id == "observation_MODIS"
    assert MODIS().information.category == "observation"
    assert MODIS._supported_var_names == ("clt", "clwvi", "clivi", "lwp")


@pytest.mark.parametrize("var_name", sorted(ATTRS))
def test_the_yearly_files_are_found_and_concatenated(staged, var_name) -> None:  # noqa: ANN001
    cube = MODIS().get_cube(
        staged,
        Variable(var_name, var_name, "mon"),
        download_missing_data=False,
    )
    # 2002-07..2006-06 = 6 + 12 * 3 + 6 months
    assert cube.shape == (48, LATS.size, LONS.size)
    assert _years(cube)[0] == 2002
    assert _years(cube)[-1] == 2006
    assert str(cube.units) == ATTRS[var_name][1]
    assert float(np.asarray(cube.data).mean()) == pytest.approx(
        ATTRS[var_name][2],
        rel=1e-5,
    )


def test_the_timerange_is_honoured(staged) -> None:  # noqa: ANN001
    """Both halves: the filename pre-filter and the final time extraction."""
    cube = MODIS().get_cube(
        staged,
        Variable("clt", "clt", "mon", timerange="20030101/20041231"),
        download_missing_data=False,
    )
    assert cube.shape[0] == 24
    assert set(_years(cube)) == {2003, 2004}
    times = cube.coord("time")
    assert str(times.units.num2date(times.points[0])) == "2003-01-15 00:00:00"
    assert str(times.units.num2date(times.points[-1])) == "2004-12-15 00:00:00"


def test_the_partial_first_year_is_used_where_asked(staged) -> None:  # noqa: ANN001
    """A window starting inside 2002 gets the six months that exist.

    The 2002 file is named ``200201-200212`` although it starts in July: the
    filename token only pre-filters, the time axis decides.
    """
    cube = MODIS().get_cube(
        staged,
        Variable("clwvi", "clwvi", "mon", timerange="20020701/20031231"),
        download_missing_data=False,
    )
    assert cube.shape[0] == 6 + 12


def test_the_first_complete_year_is_2003(staged) -> None:  # noqa: ANN001
    """The record starts 2002-07, so the protocol's first usable year is 2003.

    This is what makes the cloud variables' regime-(a) anomaly baseline
    2003–2014 (12 years of 1985–2014), and the partial final year is dropped
    the same way.
    """
    for var_name in ("clt", "clwvi", "clivi"):
        assert reference_windows.source_coverage(
            staged,
            "observation_MODIS",
            "mon",
            var_name,
        ) == (2003, 2005)


def test_a_variable_modis_does_not_have_is_refused(staged) -> None:  # noqa: ANN001
    with pytest.raises(NotImplementedError, match="does not provide variable"):
        MODIS().get_cube(staged, Variable("rsut", "rsut", "mon"))


def test_a_frequency_modis_does_not_have_is_refused(staged) -> None:  # noqa: ANN001
    with pytest.raises(NotImplementedError, match="frequency"):
        MODIS().get_cube(staged, Variable("clt", "clt", "day"))


def test_there_is_no_download_path(tmp_path) -> None:  # noqa: ANN001
    """The MODIS CMORizer output is Tier-3: missing data must say "stage it"."""
    from climateeval.exceptions import DownloadError

    with pytest.raises(DownloadError, match="cannot be downloaded"):
        MODIS().download(Variable("clt", "clt", "mon"), tmp_path)
