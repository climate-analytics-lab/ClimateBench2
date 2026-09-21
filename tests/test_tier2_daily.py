"""Tests for the Tier II daily/sub-daily diagnostics (work package 6b).

``ETCCDIExtremes``, ``DiurnalHarmonic`` and ``PerkinsSkillScore`` run on
synthetic daily/hourly cubes built so that every answer is known by
construction. Nothing is downloaded: the "reference" is a second synthetic
cube handed to the diagnostic through a stubbed reference DataSource, which
is also what proves the scalar diagnostics emit the ``reference`` rows the
scoring pass needs.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

climateeval = pytest.importorskip("climateeval")

from cf_units import Unit  # noqa: E402
from iris.coords import DimCoord  # noqa: E402
from iris.cube import Cube, CubeList  # noqa: E402

from climateeval import Variable  # noqa: E402
from climateeval.data import DataSourceInformation  # noqa: E402
from climateeval.diags.simple._utils import SimpleDiagnosticInputData  # noqa: E402

from climatebench2._thresholds import get_threshold  # noqa: E402
from climatebench2.diags import tier2_daily  # noqa: E402
from climatebench2.diags.tier2_daily import (  # noqa: E402
    DiurnalHarmonic,
    ETCCDIExtremes,
    PerkinsSkillScore,
)
from climatebench2.scoring_pass import is_scalar_output, score_scalar_output  # noqa: E402

#: The protocol grids (1x1 for the extremes, 2x2 for the diurnal cycle) mean
#: 65k/16k grid points, which is minutes of work and gigabytes of memory for a
#: synthetic record. Every test here runs on a coarse grid instead; that the
#: real ones come from thresholds.yml is asserted separately.
TEST_GRID = "10x10"


@pytest.fixture(autouse=True)
def _coarse_grid(monkeypatch: pytest.MonkeyPatch) -> None:
    """Swap the protocol's regridding targets for a cheap one."""
    real = tier2_daily.get_threshold

    def _patched(path: str):  # noqa: ANN202
        if path in ("tier2.extremes.grid", "tier2.diurnal.grid"):
            return TEST_GRID
        return real(path)

    monkeypatch.setattr(tier2_daily, "get_threshold", _patched)


def test_the_protocol_grids_come_from_thresholds() -> None:
    """What the fixture above replaces: the paper's ~1 degree, conservative."""
    assert get_threshold("tier2.extremes.grid") == "1x1"
    assert get_threshold("tier2.extremes.regrid_scheme") == "area_weighted"
    assert get_threshold("tier2.diurnal.grid") == "2x2"


BASE_FIRST, BASE_LAST = (int(y) for y in get_threshold("tier2.extremes.base_period"))
#: Ten years ending at the end of the base period — long enough for a trend,
#: short enough to keep the synthetic cubes small.
FIRST_YEAR = BASE_LAST - 9
N_YEARS = 10
DAYS_PER_YEAR = 360  # a 360-day calendar keeps every month 30 days


def _coords(
    n_time: int,
    *,
    hours: bool = False,
    n_lon: int = 6,
) -> tuple[DimCoord, DimCoord, DimCoord]:
    step = 1.0 / 24.0 if hours else 1.0
    time = DimCoord(
        np.arange(n_time, dtype=float) * step
        + 0.5 * step
        + (FIRST_YEAR - 1850) * 360.0,
        standard_name="time",
        units=Unit("days since 1850-01-01", calendar="360_day"),
    )
    lat = DimCoord(
        np.array([-75.0, -45.0, -15.0, 15.0, 45.0, 75.0]),
        standard_name="latitude",
        units="degrees",
    )
    lon = DimCoord(
        np.linspace(0.0, 360.0, n_lon, endpoint=False),
        standard_name="longitude",
        units="degrees",
        circular=True,
    )
    for coord in (time, lat, lon):
        coord.guess_bounds()
    return time, lat, lon


def _daily_cube(data: np.ndarray, var_name: str, units: str) -> Cube:
    time, lat, lon = _coords(data.shape[0])
    return Cube(
        data.astype(np.float32),
        var_name=var_name,
        units=units,
        dim_coords_and_dims=[(time, 0), (lat, 1), (lon, 2)],
    )


def _years_and_months() -> tuple[np.ndarray, np.ndarray]:
    years = np.repeat(np.arange(FIRST_YEAR, FIRST_YEAR + N_YEARS), DAYS_PER_YEAR)
    months = np.tile(np.repeat(np.arange(1, 13), 30), N_YEARS)
    return years, months


def _info(variant: str = "r1i1p1f1") -> DataSourceInformation:
    return DataSourceInformation(
        name="SynthModel",
        category="model",
        exp="historical",
        variant=variant,
    )


class _StubSource:
    """A DataSource-shaped stand-in returning a cube from memory."""

    information = DataSourceInformation(name="SynthObs", category="observation")

    #: Set per test before the diagnostic runs.
    cubes: dict[str, Cube] = {}  # noqa: RUF012

    @property
    def id(self) -> str:
        return self.information.id

    def get_cube(self, _root, variable, **_kwargs):  # noqa: ANN001, ANN003, ANN202
        return type(self).cubes[variable.id].copy()


def _run(diag_class, variables, cubes, *, reference=None, variant="r1i1p1f1"):  # noqa: ANN001, ANN202
    """Build the diagnostic from Variables and run it on synthetic cubes."""
    _StubSource.cubes = reference or {}
    variables_and_data = {
        variable: SimpleDiagnosticInputData(
            reference=_StubSource if reference else None,
            other=(),
        )
        for variable in variables
    }
    diag = diag_class(
        diag_class.__name__.lower(),
        variables_and_data,
        fail_on_missing_data=True,
        download_missing_data=False,
    )
    return diag.get_output(CubeList(cubes), _info(variant))


# ---------------------------------------------------------------------------
# ETCCDI extremes
# ---------------------------------------------------------------------------


def _tasmax_cube(spike_year: int = FIRST_YEAR, spike: float = 12.0) -> Cube:
    """A flat 290 K world with one hot day in ``spike_year``."""
    years, _months = _years_and_months()
    data = np.full((years.size, 6, 6), 290.0)
    data[np.flatnonzero(years == spike_year)[100]] = 290.0 + spike
    return _daily_cube(data, "tasmax", "K")


def _pr_cube() -> Cube:
    """2 mm/day everywhere, with ten 50 mm downpours in the first year."""
    years, _months = _years_and_months()
    data = np.full((years.size, 6, 6), 2.0)
    data[:10] = 50.0
    return _daily_cube(data, "pr", "mm day-1")


def test_extremes_emit_a_climatology_and_a_trend_per_index_and_region() -> None:
    variable = Variable("tasmax", "tasmax", "day")
    output = _run(ETCCDIExtremes, [variable], [_tasmax_cube()])
    frame = output.raw_output.to_pandas()

    # One row per data source, one column per (index, region, statistic)
    assert len(frame) == 1
    regions = get_threshold("tier2.extremes.regions")
    for index in ("txx", "tx90p", "wsdi"):
        for region in regions:
            assert f"{index}_{region}_clim" in frame.columns
            assert f"{index}_{region}_trend" in frame.columns
    # ... and none of the pr indices, which come from another variable
    assert not [c for c in frame.columns if c.startswith("rx1day")]

    # The hot day lifts exactly one year's TXx: mean over 10 years of
    # nine 290s and one 302 == 291.2
    assert frame["txx_global_land_clim"].iloc[0] == pytest.approx(291.2, abs=1e-3)


def test_extremes_have_no_time_axis_and_so_are_the_scalar_regime() -> None:
    """The pass must recognise the table as aggregated scalars, not a series."""
    variable = Variable("pr", "pr", "day", units="mm day-1")
    output = _run(ETCCDIExtremes, [variable], [_pr_cube()])
    frame = output.raw_output.to_pandas()
    assert "time" not in frame.columns
    # Without a reference there is nothing to score against: is_scalar_output
    # is False, which is exactly how "model-only, unscored" is expressed.
    assert not is_scalar_output(frame)
    # The precipitation indices are all there and finite
    for index in ("rx1day", "rx5day", "r95ptot", "cdd"):
        value = frame[f"{index}_global_land_clim"].iloc[0]
        assert np.isfinite(value), index
    # Rx1day is the 50 mm downpour in year 1, 2 mm in every other year
    assert frame["rx1day_global_land_clim"].iloc[0] == pytest.approx(
        (50.0 + 9 * 2.0) / 10.0,
        abs=1e-3,
    )
    # It never rains less than 2 mm/day, so there are no dry days at all
    assert frame["cdd_global_land_clim"].iloc[0] == pytest.approx(0.0)


def test_extremes_are_scored_once_a_reference_exists() -> None:
    """The day a daily obs DataSource lands, the pass scores these scalars."""
    variable = Variable("tasmax", "tasmax", "day")
    reference = {"tasmax": _tasmax_cube(spike=6.0)}
    members = []
    for i, variant in enumerate(("r1i1p1f1", "r2i1p1f1")):
        output = _run(
            ETCCDIExtremes,
            [variable],
            [_tasmax_cube(spike=10.0 + i)],
            reference=reference,
            variant=variant,
        )
        members.append(output.raw_output.to_pandas())
    frame = members[0].__class__.__mro__ and __import__("pandas").concat(
        members,
        ignore_index=True,
    )
    assert is_scalar_output(frame)
    sources = __import__("pandas").DataFrame(
        {
            "id": [_info("r1i1p1f1").id, _info("r2i1p1f1").id, _StubSource().id],
            "name": ["SynthModel", "SynthModel", "SynthObs"],
            "category": ["model", "model", "observation"],
        },
    )
    rows = score_scalar_output(frame, sources, diagnostic="extremes")
    scored = {r["var_id"]: r for r in rows if r["data_id"] == "SynthModel"}
    assert scored["txx_global_land_clim"]["n_members"] == 2.0
    assert np.isfinite(scored["txx_global_land_clim"]["crps"])
    assert scored["txx_global_land_clim"]["window"] == "in-sample"


def test_extremes_reject_a_variable_with_no_index() -> None:
    variable = Variable("clt", "clt", "day")
    years, _months = _years_and_months()
    cube = _daily_cube(np.zeros((years.size, 6, 6)), "clt", "%")
    with pytest.raises(ValueError, match="no ETCCDI index"):
        _run(ETCCDIExtremes, [variable], [cube])


def test_extremes_regional_bands_differ_when_the_field_does() -> None:
    """A warming confined to the tropics must not show in the NH band."""
    variable = Variable("tasmax", "tasmax", "day")
    years, _months = _years_and_months()
    data = np.full((years.size, 6, 6), 290.0)
    data[:, 2:4, :] += 5.0  # the two |lat| = 15 rows
    output = _run(ETCCDIExtremes, [variable], [_daily_cube(data, "tasmax", "K")])
    frame = output.raw_output.to_pandas()
    assert frame["txx_tropical_land_clim"].iloc[0] == pytest.approx(295.0, abs=1e-3)
    assert frame["txx_nh_extratropical_land_clim"].iloc[0] == pytest.approx(
        290.0,
        abs=1e-3,
    )


# ---------------------------------------------------------------------------
# Diurnal cycle
# ---------------------------------------------------------------------------


def _hourly_pr_cube(peak_hour: float = 15.0, amplitude: float = 2.0) -> Cube:
    """Hourly pr whose LOCAL-solar-time cycle peaks at ``peak_hour``.

    Built in UTC: a column at longitude ``lon`` peaks at local hour
    ``peak_hour``, i.e. at UTC hour ``peak_hour - lon/15``. A diagnostic that
    forgot the local-solar-time shift would average these columns to nearly
    nothing.
    """
    n_days = 60
    n_time = n_days * 24
    # 24 longitudes = one hour of local solar time per column, so the linear
    # regrid onto the analysis grid does not smear the wave's phase (with six
    # columns four hours apart it would, costing ~9% of the amplitude).
    time, lat, lon = _coords(n_time, hours=True, n_lon=24)
    utc_hour = (np.arange(n_time) % 24).astype(float)
    lon_hours = lon.points / 15.0
    local = utc_hour[:, None] + lon_hours[None, :]
    cycle = 5.0 + amplitude * np.cos(2 * np.pi * (local - peak_hour) / 24.0)
    data = np.broadcast_to(cycle[:, None, :], (n_time, 6, lon.points.size)).copy()
    return Cube(
        data.astype(np.float32),
        var_name="pr",
        units="mm day-1",
        dim_coords_and_dims=[(time, 0), (lat, 1), (lon, 2)],
    )


def test_diurnal_harmonic_recovers_amplitude_and_local_phase() -> None:
    variable = Variable("pr_land", "pr", "1hr", units="mm day-1")
    output = _run(DiurnalHarmonic, [variable], [_hourly_pr_cube()])
    frame = output.raw_output.to_pandas()
    assert "time" not in frame.columns
    prefix = "pr_land_tropics_djf"
    assert frame[f"{prefix}_amplitude"].iloc[0] == pytest.approx(2.0, abs=0.15)
    # 15:00 local solar time -> phase components of 15/24 of a turn
    angle = 2 * np.pi * 15.0 / 24.0
    assert frame[f"{prefix}_phase_cos"].iloc[0] == pytest.approx(
        np.cos(angle),
        abs=0.1,
    )
    assert frame[f"{prefix}_phase_sin"].iloc[0] == pytest.approx(
        np.sin(angle),
        abs=0.1,
    )
    # The phase is never emitted in hours: fair CRPS cannot score an angle.
    assert not [c for c in frame.columns if c.endswith("_phase_hours")]


def test_diurnal_harmonic_emits_one_block_per_season_and_region() -> None:
    variable = Variable("pr_land", "pr", "1hr", units="mm day-1")
    output = _run(DiurnalHarmonic, [variable], [_hourly_pr_cube()])
    columns = set(output.raw_output.to_pandas().columns)
    for region in get_threshold("tier2.diurnal.regions"):
        # Only DJF is present: the synthetic record is 60 days from 1 January
        prefix = f"pr_land_{region}_djf"
        assert {f"{prefix}_amplitude", f"{prefix}_phase_cos", f"{prefix}_phase_sin"} <= (
            columns
        )


# ---------------------------------------------------------------------------
# Perkins skill score
# ---------------------------------------------------------------------------


def _pr_intensity_cube(scale: float) -> Cube:
    """Wet-day intensities drawn from a fixed pseudo-random sample."""
    years, _months = _years_and_months()
    rng = np.random.default_rng(3)
    data = rng.gamma(2.0, scale, size=(years.size, 6, 6))
    return _daily_cube(data, "pr", "mm day-1")


def test_perkins_metrics_are_one_row_of_season_scores() -> None:
    variable = Variable(
        "pr_intensity_land",
        "pr",
        "day",
        units="mm day-1",
        diagnostic_kwargs={"quantity": "pr_intensity"},
    )
    output = _run(
        PerkinsSkillScore,
        [variable],
        [_pr_intensity_cube(3.0)],
        reference={"pr_intensity_land": _pr_intensity_cube(3.0)},
    )
    # No raw output at all: the preprocessed field is the whole daily record
    assert output.raw_output is None
    metrics = output.metrics.to_pandas()
    assert len(metrics) == 1
    for season in get_threshold("tier2.perkins.seasons"):
        assert f"perkins_{str(season).lower()}" in metrics.columns
    # Identical distributions overlap perfectly
    assert metrics["perkins_all"].iloc[0] == pytest.approx(1.0, abs=1e-5)
    assert metrics["perkins_djf"].iloc[0] == pytest.approx(1.0, abs=1e-5)


def test_perkins_score_falls_when_the_distributions_differ() -> None:
    variable = Variable(
        "pr_intensity_land",
        "pr",
        "day",
        units="mm day-1",
        diagnostic_kwargs={"quantity": "pr_intensity"},
    )
    output = _run(
        PerkinsSkillScore,
        [variable],
        [_pr_intensity_cube(3.0)],
        reference={"pr_intensity_land": _pr_intensity_cube(9.0)},
    )
    score = output.metrics.to_pandas()["perkins_all"].iloc[0]
    assert 0.0 <= score < 0.8  # far too wet a model


def test_perkins_tas_anomalies_are_taken_against_the_base_period() -> None:
    """A constant offset is an anomaly difference, and must cost skill."""
    variable = Variable(
        "tas_anomaly_land",
        "tas",
        "day",
        diagnostic_kwargs={"quantity": "tas_anomaly"},
    )
    years, months = _years_and_months()
    rng = np.random.default_rng(7)
    noise = rng.normal(0.0, 2.0, size=(years.size, 6, 6))
    seasonal = 10.0 * np.cos(2 * np.pi * (months - 1) / 12.0)[:, None, None]
    model = _daily_cube(280.0 + seasonal + noise, "tas", "K")
    # The reference has the same seasonal cycle but half the daily variance:
    # after the climatology is removed the PDFs differ in width, not in mean.
    reference = _daily_cube(280.0 + seasonal + 0.5 * noise, "tas", "K")
    output = _run(
        PerkinsSkillScore,
        [variable],
        [model],
        reference={"tas_anomaly_land": reference},
    )
    score = output.metrics.to_pandas()["perkins_all"].iloc[0]
    assert 0.3 < score < 0.95


def test_perkins_requires_a_pre_registered_quantity() -> None:
    variable = Variable("pr_odd", "pr", "day", diagnostic_kwargs={"quantity": "wat"})
    with pytest.raises(ValueError, match="'quantity'"):
        _run(PerkinsSkillScore, [variable], [_pr_intensity_cube(3.0)])


# ---------------------------------------------------------------------------
# The held-out annual index series
# ---------------------------------------------------------------------------

#: A record long enough to carry BOTH halves of a regime-(a) score: at least
#: `tier2.anomaly_baseline.min_years` (10) years inside the 1985-2014
#: baseline window, and some years after `tier2.test_window_start` to score.
SERIES_FIRST_YEAR = BASE_LAST - 9      # 2005
SERIES_LAST_YEAR = 2018
SERIES_YEARS = np.arange(SERIES_FIRST_YEAR, SERIES_LAST_YEAR + 1)


def _series_cube(annual_spikes: dict[int, float], background: float = 2.0) -> Cube:
    """Daily pr at ``background`` mm/day with one wet day in named years.

    The field is spatially uniform, so every `tier2.extremes.regions` band
    sees the same series and the expected Rx1day is simply the spike (or the
    background, in a year with none).
    """
    n_days = SERIES_YEARS.size * DAYS_PER_YEAR
    data = np.full((n_days, 6, 6), background)
    for offset, year in enumerate(SERIES_YEARS):
        if year in annual_spikes:
            data[offset * DAYS_PER_YEAR + 100] = annual_spikes[year]
    time = DimCoord(
        np.arange(n_days, dtype=float) + 0.5 + (SERIES_FIRST_YEAR - 1850) * 360.0,
        standard_name="time",
        units=Unit("days since 1850-01-01", calendar="360_day"),
    )
    lat = DimCoord(
        np.array([-75.0, -45.0, -15.0, 15.0, 45.0, 75.0]),
        standard_name="latitude",
        units="degrees",
    )
    lon = DimCoord(
        np.linspace(0.0, 360.0, 6, endpoint=False),
        standard_name="longitude",
        units="degrees",
        circular=True,
    )
    for coord in (time, lat, lon):
        coord.guess_bounds()
    return Cube(
        data.astype(np.float32),
        var_name="pr",
        units="mm day-1",
        dim_coords_and_dims=[(time, 0), (lat, 1), (lon, 2)],
    )


def _series_variable(index: str, region: str) -> Variable:
    return Variable(
        f"{index}_{region}",
        "pr",
        "day",
        units="mm day-1",
        diagnostic_kwargs={"index": index, "region": region},
    )


def test_the_index_series_is_annual_with_one_column_per_variable() -> None:
    """Regime (a)'s shape: a `time` axis and one column per suite variable id."""
    from climatebench2.diags import AnnualExtremeIndexSeries

    spikes = {year: 20.0 + year - SERIES_FIRST_YEAR for year in SERIES_YEARS}
    variables = [
        _series_variable("rx1day", "global_land"),
        _series_variable("rx1day", "tropical_land"),
    ]
    output = _run(
        AnnualExtremeIndexSeries,
        variables,
        [_series_cube(spikes)],
    )
    frame = output.raw_output.to_pandas().sort_values("time").reset_index(drop=True)

    assert "time" in frame.columns
    assert set(frame.columns) >= {"rx1day_global_land", "rx1day_tropical_land"}
    assert len(frame) == SERIES_YEARS.size
    assert list(pd.to_datetime(frame["time"]).dt.year) == list(SERIES_YEARS)

    # The field is uniform, so every band sees the year's own spike.
    expected = [float(spikes[year]) for year in SERIES_YEARS]
    assert frame["rx1day_global_land"].to_list() == pytest.approx(expected, abs=1e-3)
    assert frame["rx1day_tropical_land"].to_list() == pytest.approx(expected, abs=1e-3)


def test_rx5day_is_the_five_day_running_total() -> None:
    """One 50 mm day inside a 2 mm/day background: 50 + 4 x 2 = 58 mm."""
    from climatebench2.diags import AnnualExtremeIndexSeries

    output = _run(
        AnnualExtremeIndexSeries,
        [_series_variable("rx5day", "global_land")],
        [_series_cube({SERIES_FIRST_YEAR + 1: 50.0})],
    )
    frame = output.raw_output.to_pandas().sort_values("time").reset_index(drop=True)
    values = frame["rx5day_global_land"].to_numpy(float)
    # The spike year, and a plain 5 x 2 = 10 mm everywhere else
    assert values[1] == pytest.approx(58.0, abs=1e-3)
    assert values[0] == pytest.approx(10.0, abs=1e-3)
    assert values[-1] == pytest.approx(10.0, abs=1e-3)


def test_the_index_series_is_scored_held_out_over_the_test_window() -> None:
    """End to end through the pass: anomalies, post-2015 steps, `held-out`.

    Two members and a reference, all over 2005-2018 — 10 baseline years,
    which is exactly `tier2.anomaly_baseline.min_years`, the situation IMERG
    puts the real entry in (it has 14).
    """
    from climatebench2.diags import AnnualExtremeIndexSeries
    from climatebench2.scoring_pass import (
        deduplicate_raw_output,
        score_raw_output,
    )

    def spikes(amplitude: float) -> dict[int, float]:
        return {
            year: 20.0 + amplitude * (year - SERIES_FIRST_YEAR)
            for year in SERIES_YEARS
        }

    variable = _series_variable("rx1day", "global_land")
    reference = {variable.id: _series_cube(spikes(1.0))}
    frames = []
    for i, variant in enumerate(("r1i1p1f1", "r2i1p1f1")):
        output = _run(
            AnnualExtremeIndexSeries,
            [variable],
            [_series_cube(spikes(1.2 + 0.1 * i))],
            reference=reference,
            variant=variant,
        )
        frames.append(output.raw_output.to_pandas())
    # Each member's run emits its own copy of the reference row; the real
    # path (`score_database`) deduplicates before scoring, so do the same.
    frame = deduplicate_raw_output(pd.concat(frames, ignore_index=True))

    sources = pd.DataFrame(
        {
            "id": [_info("r1i1p1f1").id, _info("r2i1p1f1").id, _StubSource().id],
            "name": ["SynthModel", "SynthModel", "SynthObs"],
            "category": ["model", "model", "observation"],
        },
    )
    rows = score_raw_output(
        frame,
        sources,
        settings={
            "block_length_monthly": 12,
            "block_length_annual": 3,
            "n_boot": 40,
            "alpha": 0.05,
            "resample_members": True,
            "seed": 1,
        },
        diagnostic="pr_extremes_series",
    )
    scored = [
        r
        for r in rows
        if r["data_id"] == "SynthModel" and r["var_id"] == "rx1day_global_land"
    ]
    assert len(scored) == 1
    row = scored[0]
    assert row["n_members"] == 2.0
    assert np.isfinite(row["crps"])
    # The paper's SS 5.6 scorecard rule: this entry's observations postdate
    # the reserved period, so it is the one held-out row in the daily suite.
    assert row["window"] == "held-out"
    # Only the post-2015 steps are scored (2015-2018), never the baseline.
    assert row["n_time"] == 4.0


def test_the_series_needs_a_pre_registered_index_and_region() -> None:
    """The index and the band are protocol choices, not free text."""
    from climatebench2.diags import AnnualExtremeIndexSeries

    with pytest.raises(ValueError, match="diagnostic_kwargs\\['index'\\]"):
        _run(
            AnnualExtremeIndexSeries,
            [_series_variable("r95ptot", "global_land")],
            [_series_cube({})],
        )
    with pytest.raises(ValueError, match="diagnostic_kwargs\\['region'\\]"):
        _run(
            AnnualExtremeIndexSeries,
            [_series_variable("rx1day", "antarctica")],
            [_series_cube({})],
        )


def test_the_series_and_the_scalar_climatology_use_the_same_index() -> None:
    """`extremes` and `pr_extremes_series` must not drift apart.

    The climatology the scalar entry reports is the mean of the series this
    entry emits, over the same years — same physics call, same cos-weighted
    band. Asserting it here is what stops one of the two acquiring a fix the
    other does not.
    """
    from climatebench2.diags import AnnualExtremeIndexSeries

    spikes = {year: 20.0 + year - SERIES_FIRST_YEAR for year in SERIES_YEARS}
    cube = _series_cube(spikes)

    series = _run(
        AnnualExtremeIndexSeries,
        [_series_variable("rx1day", "global_land")],
        [cube],
    ).raw_output.to_pandas()
    scalars = _run(
        ETCCDIExtremes,
        [Variable("pr", "pr", "day", units="mm day-1")],
        [cube],
    ).raw_output.to_pandas()

    assert scalars["rx1day_global_land_clim"].iloc[0] == pytest.approx(
        float(series["rx1day_global_land"].mean()),
        abs=1e-3,
    )
