"""Tests for the diagnostics that reach back past the Tier II test window.

``ReferenceBaselineRecord`` (the Climatology baseline's 1985-2014 sample) and
``ReferenceEOFProjection`` (the regime-(b) basis) both load their reference
over a window *other* than the suite's, through a copy of the ``Variable``
carrying a different ``timerange``. The fake DataSource below records the
variable it is handed and clips its synthetic cube accordingly, so the tests
check exactly that hand-off without any real data.
"""

from __future__ import annotations

from typing import ClassVar

import numpy as np
import pytest

climateeval = pytest.importorskip("climateeval")

from cf_units import Unit  # noqa: E402
from iris.coords import DimCoord  # noqa: E402
from iris.cube import Cube, CubeList  # noqa: E402

from climateeval import Variable  # noqa: E402
from climateeval.data import DataSourceInformation  # noqa: E402
from climateeval.diags.simple._utils import SimpleDiagnosticInputData  # noqa: E402

from climatebench2.diags.tier2_reference import (  # noqa: E402
    ReferenceBaselineRecord,
    ReferenceEOFProjection,
    with_timerange,
)
from climatebench2.scoring_pass import (  # noqa: E402
    BASELINE_ANNUAL_DATA_TYPE,
    BASELINE_MONTHLY_DATA_TYPE,
    baseline_records,
)

N_LAT, N_LON = 9, 18


def _monthly_cube(
    first_year: int,
    last_year: int,
    *,
    var_name: str = "tas",
    pattern: np.ndarray | None = None,
    offset: float = 0.0,
    seed: int = 0,
) -> Cube:
    """A (time, lat, lon) monthly cube with a seasonal cycle and a pattern.

    ``pattern`` (lat, lon) is added as a *time-constant* field, which is what
    the EOF projection's climatological-anomaly target picks up.
    """
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
    seasonal = 5.0 * np.sin(2 * np.pi * months / 12.0)
    field = np.zeros((N_LAT, N_LON)) if pattern is None else np.asarray(pattern)
    data = (
        280.0
        + offset
        + seasonal[:, None, None]
        + field[None, :, :]
        + rng.normal(0.0, 0.2, (n_time, N_LAT, N_LON))
    )
    return Cube(
        data.astype(np.float32),
        var_name=var_name,
        units="K",
        dim_coords_and_dims=[(time, 0), (lat, 1), (lon, 2)],
    )


class _FakeReference:
    """A DataSource that serves a fixed record, clipped to the asked window."""

    _information = DataSourceInformation(name="FAKEOBS", category="observation")
    #: The whole record this "observation" has, as (first year, last year).
    record: ClassVar[tuple[int, int]] = (1980, 2025)
    #: Time-constant pattern of the served field, per window.
    patterns: ClassVar[dict[tuple[int, int], np.ndarray]] = {}
    #: Every variable the diagnostic asked for, in order.
    asked: ClassVar[list[Variable]] = []

    @property
    def id(self) -> str:
        return self._information.id

    @property
    def information(self) -> DataSourceInformation:
        return self._information

    def download(self, variable, data_root_dir):  # noqa: ANN001, ANN201, ARG002
        return []

    def get_cube(self, data_root_dir, variable, *, download_missing_data=True):  # noqa: ANN001, ANN201, ARG002
        type(self).asked.append(variable)
        first, last = self.record
        if variable.timerange != "*":
            start, end = variable.timerange.split("/")
            first = max(first, int(start[:4]))
            last = min(last, int(end[:4]))
        if last < first:
            msg = f"no data in {variable.timerange}"
            raise ValueError(msg)
        pattern = self.patterns.get((first, last))
        if pattern is None:
            pattern = self.patterns.get("any")  # type: ignore[call-overload]
        return _monthly_cube(first, last, pattern=pattern)


def _variable(timerange: str = "20150101/20251231") -> Variable:
    return Variable("tas", "tas", "mon", timerange=timerange)


def _diagnostic(cls, variable, *, other=()):  # noqa: ANN001, ANN201
    return cls(
        cls.__name__.lower(),
        {variable: SimpleDiagnosticInputData(reference=_FakeReference, other=other)},
        download_missing_data=False,
        fail_on_missing_data=False,
    )


def _information() -> DataSourceInformation:
    return DataSourceInformation(
        name="MyModel",
        category="model",
        exp="historical",
        variant="r1i1p1f1",
    )


@pytest.fixture(autouse=True)
def _reset_fake():  # noqa: ANN202
    _FakeReference.asked = []
    _FakeReference.patterns = {}
    _FakeReference.record = (1980, 2025)
    yield
    _FakeReference.asked = []


# ---------------------------------------------------------------------------
# with_timerange
# ---------------------------------------------------------------------------


def test_with_timerange_keeps_every_other_preprocessing_setting() -> None:
    variable = Variable(
        "tos",
        "tos",
        "mon",
        timerange="20150101/20251231",
        min_lat=-30.0,
        max_lat=30.0,
        units="K",
    )
    moved = with_timerange(variable, "19850101/20141231")
    assert moved.timerange == "19850101/20141231"
    assert (moved.id, moved.var_name, moved.frequency) == ("tos", "tos", "mon")
    assert (moved.min_lat, moved.max_lat, moved.units) == (-30.0, 30.0, "K")
    assert variable.timerange == "20150101/20251231"  # the original is untouched


# ---------------------------------------------------------------------------
# ReferenceBaselineRecord
# ---------------------------------------------------------------------------


def test_baseline_record_writes_the_pre_test_window() -> None:
    diag = _diagnostic(ReferenceBaselineRecord, _variable())
    output = diag.get_output(CubeList([]), _information())
    raw = output.raw_output.to_pandas()

    # The reference was asked for the BASELINE window, not the suite's
    assert [v.timerange for v in _FakeReference.asked] == ["19850101/20141231"]

    assert set(raw["data_type"]) == {
        BASELINE_MONTHLY_DATA_TYPE,
        BASELINE_ANNUAL_DATA_TYPE,
    }
    monthly = raw[raw["data_type"] == BASELINE_MONTHLY_DATA_TYPE]
    annual = raw[raw["data_type"] == BASELINE_ANNUAL_DATA_TYPE]
    assert len(monthly) == 30 * 12
    assert len(annual) == 30
    assert (raw["data_id"] == "observation_FAKEOBS").all()
    # The monthly series keeps the seasonal cycle the annual mean removes
    assert monthly["tas"].std() > 3.0
    assert annual["tas"].std() < 1.0
    # No metrics: this diagnostic reports a window, it scores nothing
    assert output.metrics is None


def test_baseline_record_rows_feed_the_scoring_pass() -> None:
    """The pass must find both frequencies keyed by variable."""
    diag = _diagnostic(ReferenceBaselineRecord, _variable())
    raw = diag.get_output(CubeList([]), _information()).raw_output.to_pandas()
    found = baseline_records(raw)
    assert set(found) == {("tas", "monthly"), ("tas", "annual")}
    assert len(found["tas", "annual"]) == 30


def test_baseline_record_skips_a_reference_that_stops_too_early() -> None:
    """A short reference is skipped with a reason, not half-sampled."""
    _FakeReference.record = (2010, 2025)  # only 5 yr inside 1985-2014
    diag = _diagnostic(ReferenceBaselineRecord, _variable())
    output = diag.get_output(CubeList([]), _information())
    assert output.raw_output is None


def test_baseline_record_skips_a_reference_that_misses_the_window() -> None:
    _FakeReference.record = (2016, 2025)  # nothing before the test window
    diag = _diagnostic(ReferenceBaselineRecord, _variable())
    output = diag.get_output(CubeList([]), _information())
    assert output.raw_output is None


# ---------------------------------------------------------------------------
# ReferenceEOFProjection
# ---------------------------------------------------------------------------


def _hemispheric_pattern(amplitude: float) -> np.ndarray:
    """A north-south dipole: the field the projection should pick up."""
    lats = np.linspace(-80.0, 80.0, N_LAT)
    return amplitude * np.sign(lats)[:, None] * np.ones((1, N_LON))


def test_eof_projection_emits_one_row_per_source_and_mode() -> None:
    _FakeReference.patterns = {"any": None}
    variable = _variable()
    diag = _diagnostic(ReferenceEOFProjection, variable)
    model = CubeList([_monthly_cube(2015, 2025, seed=7)])
    raw = diag.get_output(model, _information()).raw_output.to_pandas()

    assert set(raw.columns) == {
        "data_id",
        "data_type",
        "var_id",
        "mode",
        "coefficient",
        "explained_variance",
        "sigma_pre2015",
    }
    assert set(raw["data_type"]) == {"reference", "to_benchmark"}
    assert set(raw["var_id"]) == {"tas"}
    # Same number of modes for every source, numbered from 1
    per_source = raw.groupby("data_id")["mode"].agg(["count", "min", "max"])
    assert per_source["count"].nunique() == 1
    assert (per_source["min"] == 1.0).all()
    n_modes = int(per_source["count"].iloc[0])
    assert 1 <= n_modes <= int(
        __import__("climatebench2._thresholds", fromlist=["x"]).get_threshold(
            "tier2.eof.max_modes",
        ),
    )
    # The basis is the reference's own, so its modes explain what they claim
    assert raw["explained_variance"].between(0.0, 1.0).all()
    assert (raw["sigma_pre2015"] > 0).all()

    # The reference was loaded over the pre-2015 window AND the test window
    windows_asked = {v.timerange for v in _FakeReference.asked}
    assert windows_asked == {"19850101/20141231", variable.timerange}


def test_eof_projection_separates_a_biased_model_from_the_reference() -> None:
    """A model with a large climatological anomaly scores far from the obs."""
    _FakeReference.patterns = {"any": None}
    diag = _diagnostic(ReferenceEOFProjection, _variable())

    unbiased = CubeList([_monthly_cube(2015, 2025, seed=3)])
    biased = CubeList([_monthly_cube(2015, 2025, pattern=_hemispheric_pattern(4.0), seed=3)])

    def coefficients(model: CubeList) -> tuple[np.ndarray, np.ndarray]:
        raw = diag.get_output(model, _information()).raw_output.to_pandas()
        ordered = raw.sort_values("mode")
        return (
            ordered[ordered["data_type"] == "to_benchmark"]["coefficient"].to_numpy(),
            ordered[ordered["data_type"] == "reference"]["coefficient"].to_numpy(),
        )

    near, obs = coefficients(unbiased)
    far, obs_again = coefficients(biased)
    np.testing.assert_allclose(obs, obs_again)
    assert np.abs(far - obs).sum() > np.abs(near - obs).sum()


def test_eof_projection_skips_a_variable_without_a_pre2015_reference() -> None:
    _FakeReference.record = (2016, 2025)
    diag = _diagnostic(ReferenceEOFProjection, _variable())
    output = diag.get_output(CubeList([_monthly_cube(2016, 2025)]), _information())
    assert output.raw_output is None


def test_eof_projection_survives_a_model_missing_the_variable() -> None:
    """A missing model variable leaves the reference row, not an exception."""
    _FakeReference.patterns = {"any": None}
    diag = _diagnostic(ReferenceEOFProjection, _variable())
    empty = CubeList([_monthly_cube(2015, 2025, var_name="pr")])
    raw = diag.get_output(empty, _information()).raw_output.to_pandas()
    assert set(raw["data_type"]) == {"reference"}
