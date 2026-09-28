"""The reference and comparison ensemble are loaded once for all members.

``climatebench2.shared_sources.run_members`` runs a per-member cube suite one
diagnostic at a time and memoises the member-invariant stages (the
reference, the ``other_data`` ensemble) across the members. These tests
prove the two things that make that worth having and safe to have:

- **once** — a counting DataSource sees one ``get_cube`` per diagnostic for
  N members where it saw N before;
- **same rows** — every table of every diagnostic schema is identical with
  and without the cache (``--no-cache`` is the old member-by-member loop).

The suite YAML names the fake sources by dotted path, as a real suite names
``climatebench2.data.IMERG``: pytest puts this directory on ``sys.path``, so
``test_shared_sources.CountingReference`` resolves through ClimateEval's own
``str_to_object``.
"""

from __future__ import annotations

from collections import Counter
from typing import ClassVar

import numpy as np
import pytest

climateeval = pytest.importorskip("climateeval")

import ibis  # noqa: E402
import pandas as pd  # noqa: E402
import yaml  # noqa: E402
from cf_units import Unit  # noqa: E402
from iris.coords import DimCoord  # noqa: E402
from iris.cube import Cube, CubeList  # noqa: E402

from climateeval.data import DataSourceInformation  # noqa: E402
from climateeval.diags.simple import MeanTimeSeries  # noqa: E402
from climateeval.suites import Suite  # noqa: E402

from climatebench2.shared_sources import (  # noqa: E402
    EntrySuite,
    run_members,
    share_member_invariant_stages,
)

N_LAT, N_LON = 9, 18
N_COMPARISON = 4
N_MEMBERS = 3
TEST_WINDOW = "20150101/20241231"

#: ``get_cube`` calls per source id, across every fake source.
LOADS: Counter[str] = Counter()


def _monthly_cube(first_year: int, last_year: int, *, seed: int) -> Cube:
    """A (time, lat, lon) monthly ``tas`` cube with a pattern and noise."""
    rng = np.random.default_rng(seed)
    n_time = (last_year - first_year + 1) * 12
    time = DimCoord(
        np.arange(n_time, dtype=float) * 30.0 + 15.0,
        standard_name="time",
        units=Unit(f"days since {first_year}-01-01", calendar="360_day"),
    )
    lat = DimCoord(
        np.linspace(-80.0, 80.0, N_LAT),
        standard_name="latitude",
        units="degrees",
    )
    lon = DimCoord(
        np.linspace(10.0, 350.0, N_LON),
        standard_name="longitude",
        units="degrees",
        circular=True,
    )
    for coord in (time, lat, lon):
        coord.guess_bounds()
    months = np.arange(n_time) % 12
    pattern = rng.normal(0.0, 1.0, (N_LAT, N_LON))
    data = (
        280.0
        + 5.0 * np.sin(2 * np.pi * months / 12.0)[:, None, None]
        + pattern[None, :, :]
        + rng.normal(0.0, 0.2, (n_time, N_LAT, N_LON))
    )
    return Cube(
        data.astype(np.float32),
        var_name="tas",
        standard_name="air_temperature",
        units="K",
        dim_coords_and_dims=[(time, 0), (lat, 1), (lon, 2)],
    )


def _clipped(variable, *, seed: int) -> Cube:  # noqa: ANN001
    """The source's 1980-2025 record, clipped to the variable's window."""
    first, last = 1980, 2025
    if variable.timerange != "*":
        start, end = variable.timerange.split("/")
        first, last = max(first, int(start[:4])), min(last, int(end[:4]))
    return _monthly_cube(first, last, seed=seed)


class _CountingSource:
    """A DataSource-shaped fake that counts its ``get_cube`` calls."""

    _information: ClassVar[DataSourceInformation]
    seed: ClassVar[int] = 0

    @property
    def id(self) -> str:
        return self.information.id

    @property
    def information(self) -> DataSourceInformation:
        return self._information

    def download(self, variable, data_root_dir):  # noqa: ANN001, ANN201, ARG002
        return []

    def get_cube(self, data_root_dir, variable, *, download_missing_data=True):  # noqa: ANN001, ANN201, ARG002
        LOADS[self.id] += 1
        return _clipped(variable, seed=self.seed)


class CountingReference(_CountingSource):
    """The suite's ``reference_data``."""

    _information = DataSourceInformation(name="FAKEOBS", category="observation")
    seed = 1


class _ComparisonMember(_CountingSource):
    """One member of the comparison ensemble."""

    def __init__(self, index: int) -> None:
        self._information = DataSourceInformation(  # type: ignore[misc]
            name="FAKECMIP",
            category="model",
            exp="historical-ssp245",
            variant=f"r{index}i1p1f1",
        )
        self.seed = 100 + index  # type: ignore[misc]


class CountingEnsemble:
    """The suite's ``other_data``: a generator, like StagedCMIP6HistoricalSSP245."""

    def generate(self, _variable):  # noqa: ANN001, ANN201
        yield from (_ComparisonMember(i) for i in range(1, N_COMPARISON + 1))


class SelfLoadingTimeSeries(MeanTimeSeries):
    """A simple diagnostic with its OWN ``get_output``: must not be shared."""

    def get_output(self, data, data_information):  # noqa: ANN001, ANN201
        return super().get_output(data, data_information)


def _variable(timerange: str = TEST_WINDOW) -> dict:
    return {
        "id": "tas",
        "var_name": "tas",
        "frequency": "mon",
        "timerange": timerange,
        "reference_data": f"{__name__}.CountingReference",
        "other_data": [f"{__name__}.CountingEnsemble"],
    }


#: The generic stage memo (upstream MeanTimeSeries, which also computes
#: metrics against the reference), both CB2 opt-in diagnostics, and one that
#: can share nothing.
SUITE = [
    {
        "name": "tas_series",
        "diagnostic": "climateeval.diags.simple.MeanTimeSeries",
        "variables": [_variable("19850101/20241231")],
    },
    {
        "name": "tas_baseline_record",
        "diagnostic": "climatebench2.diags.ReferenceBaselineRecord",
        "variables": [_variable()],
    },
    {
        "name": "tas_eof_projection",
        "diagnostic": "climatebench2.diags.ReferenceEOFProjection",
        "variables": [_variable()],
    },
    {
        "name": "tas_self_loading",
        "diagnostic": f"{__name__}.SelfLoadingTimeSeries",
        "variables": [_variable()],
    },
]


@pytest.fixture(autouse=True)
def _reset_loads():  # noqa: ANN202
    LOADS.clear()
    yield
    LOADS.clear()


def _suite(directory):  # noqa: ANN001, ANN202
    path = directory / "SharedSourcesSuite.yml"
    path.write_text(yaml.safe_dump(SUITE, sort_keys=False), encoding="utf-8")
    return Suite(
        path,
        diagnostic_kwargs={
            "data_root_dir": directory / "data_root",
            "download_missing_data": False,
            "fail_on_missing_data": False,
            "fail_on_metric_error": False,
        },
    )


@pytest.fixture
def suite(tmp_path):  # noqa: ANN001, ANN201
    return _suite(tmp_path)


def _runs() -> list[tuple[CubeList, DataSourceInformation]]:
    return [
        (
            CubeList([_monthly_cube(1985, 2024, seed=10 + m)]),
            DataSourceInformation(
                name="MyModel",
                category="model",
                exp="historical",
                variant=f"r{m}i1p1f1",
            ),
        )
        for m in range(1, N_MEMBERS + 1)
    ]


def _run(suite, tmp_path, label: str, *, share: bool):  # noqa: ANN001, ANN202
    LOADS.clear()
    db = tmp_path / f"{label}.ddb"
    report = run_members(
        suite,
        _runs(),
        database_resource=f"duckdb://{db}",
        share=share,
    )
    return db, Counter(LOADS), report


def _tables(db) -> dict[tuple[str, str], pd.DataFrame]:  # noqa: ANN001
    """Every (schema, table) of a results database, rows in a canonical order."""
    connection = ibis.duckdb.connect(str(db), read_only=True)
    try:
        out = {}
        for schema in connection.list_databases():
            if schema in {"main", "information_schema", "pg_catalog"}:
                continue
            for table in connection.list_tables(database=schema):
                frame = connection.table(table, database=schema).to_pandas()
                frame = frame[sorted(frame.columns)]
                out[schema, table] = frame.sort_values(
                    list(frame.columns),
                ).reset_index(drop=True)
        return out
    finally:
        connection.disconnect()


@pytest.fixture(scope="module")
def both_runs(tmp_path_factory):  # noqa: ANN001, ANN201
    """The same suite and members, without and with the cache (run once)."""
    directory = tmp_path_factory.mktemp("shared_sources")
    suite = _suite(directory)
    old_db, unshared, _ = _run(suite, directory, "old", share=False)
    new_db, shared, report = _run(suite, directory, "new", share=True)
    return unshared, shared, report, _tables(old_db), _tables(new_db)


def test_the_ensemble_is_loaded_once_across_members(both_runs) -> None:  # noqa: ANN001
    unshared, shared, report, _old, _new = both_runs

    comparison = [f"model_FAKECMIP_historical-ssp245_r{i}i1p1f1" for i in (1, 2, 3, 4)]
    reference = "observation_FAKEOBS"

    # Before: every member re-read every comparison source, once per
    # diagnostic that uses it (tas_series, tas_eof_projection,
    # tas_self_loading) ...
    for source in comparison:
        assert unshared[source] == 3 * N_MEMBERS
    # ... and the reference once per diagnostic stage that loads it
    # (series 1, baseline record 1, EOF basis + test window 2, self-loading 1).
    assert unshared[reference] == 5 * N_MEMBERS

    # After: the shared diagnostics load them ONCE; only the one with its
    # own get_output still loads them per member.
    for source in comparison:
        assert shared[source] == 2 + N_MEMBERS
    assert shared[reference] == 4 + N_MEMBERS

    assert report.members == N_MEMBERS
    assert report.shared == ["tas_series", "tas_baseline_record", "tas_eof_projection"]
    assert report.unshared == ["tas_self_loading"]
    assert "rebuilt per member: tas_self_loading" in report.summary()


def test_every_table_is_identical_with_and_without_the_cache(both_runs) -> None:  # noqa: ANN001
    _unshared, _shared, _report, old, new = both_runs

    assert set(old) == set(new)
    schemas = {schema for schema, _table in old}
    assert schemas == {entry["name"] for entry in SUITE}
    for key in old:
        pd.testing.assert_frame_equal(old[key], new[key], obj=str(key))

    # The rows are really there: every member, the reference and the
    # comparison ensemble in the time series, with metrics against the
    # reference for the members and the comparison sources ...
    series = new["tas_series", "raw_output"]
    assert set(series["data_type"]) == {"to_benchmark", "reference", "other"}
    members = series.loc[series["data_type"] == "to_benchmark", "data_id"]
    assert members.nunique() == N_MEMBERS
    metrics = new["tas_series", "metrics"]
    assert metrics["data_id"].nunique() == N_MEMBERS + N_COMPARISON
    # ... and the EOF coefficients of every member and comparison source.
    eof = new["tas_eof_projection", "raw_output"]
    assert eof["data_id"].nunique() == N_MEMBERS + N_COMPARISON + 1


def test_a_single_member_takes_the_old_loop(suite, tmp_path) -> None:  # noqa: ANN001
    db = tmp_path / "single.ddb"
    report = run_members(
        suite,
        _runs()[:1],
        database_resource=f"duckdb://{db}",
        share=True,
    )
    assert report.shared == []
    assert report.unshared == []
    assert _tables(db)


def test_release_drops_what_the_entry_memoised(suite) -> None:  # noqa: ANN001
    entry = EntrySuite(suite, SUITE[0])
    (diag,) = entry._get_diagnostics().values()  # noqa: SLF001
    assert entry.shared is True
    assert entry._get_diagnostics()["tas_series"] is diag  # noqa: SLF001 - built once

    reference_cubes = diag._get_reference_cubes()  # noqa: SLF001
    assert diag._get_reference_cubes() is reference_cubes  # noqa: SLF001
    assert LOADS["observation_FAKEOBS"] == 1

    entry.release()
    memo = diag._cb2_member_invariant_memo  # noqa: SLF001
    assert memo._reference_cubes is None  # noqa: SLF001
    # A fresh build afterwards (nothing is carried between suites).
    (rebuilt,) = entry._get_diagnostics().values()  # noqa: SLF001
    assert rebuilt is not diag


def test_only_diagnostics_whose_stages_are_member_invariant_share(suite) -> None:  # noqa: ANN001
    diagnostics = suite._get_diagnostics()  # noqa: SLF001
    assert share_member_invariant_stages(diagnostics["tas_series"])
    assert share_member_invariant_stages(diagnostics["tas_eof_projection"])
    assert not share_member_invariant_stages(diagnostics["tas_self_loading"])

    # A Tier I gate (complex diagnostic) never shares.
    from climatebench2._cli import _resolve_suite

    tier1 = Suite(_resolve_suite("ClimateBench2_TierI"))._get_diagnostics()  # noqa: SLF001
    assert not any(share_member_invariant_stages(d) for d in tier1.values())
