"""Tests for the Tier II seasonal-cycle metrics (§II.1, work package 6b).

``LandAnnualTemperatureRange``, ``SSTLowCloudCovariance`` and
``SeasonalCloudRadiativeFeedback`` run on synthetic monthly cubes whose
seasonal cycle is analytic, with every observational fetch replaced by a
second synthetic cube — so the tests cover the statistic, the stratocumulus
boxes and the ``reference`` rows the scoring pass needs, and download
nothing.
"""

from __future__ import annotations

import numpy as np
import pytest

climateeval = pytest.importorskip("climateeval")

from cf_units import Unit  # noqa: E402
from iris.coords import DimCoord  # noqa: E402
from iris.cube import Cube, CubeList  # noqa: E402

from climateeval.data import DataSourceInformation  # noqa: E402

from climatebench2 import windows  # noqa: E402
from climatebench2._thresholds import get_threshold  # noqa: E402
from climatebench2.diags.tier2_diagnostics import (  # noqa: E402
    LandAnnualTemperatureRange,
    SeasonalCloudRadiativeFeedback,
    SSTLowCloudCovariance,
)
from climatebench2.scoring_pass import is_scalar_output, score_scalar_output  # noqa: E402

BASE_FIRST, BASE_LAST = windows.baseline_window_years()
#: Five years inside the 1985-2014 seasonal-cycle window keep the cubes small.
FIRST_YEAR = BASE_FIRST
N_YEARS = 5
N_MONTHS = N_YEARS * 12


def _monthly_cube(data: np.ndarray, var_name: str, units: str) -> Cube:
    n_time, n_lat, n_lon = data.shape
    time = DimCoord(
        np.arange(n_time, dtype=float) * 30.0 + 15.0 + (FIRST_YEAR - 1850) * 360.0,
        standard_name="time",
        units=Unit("days since 1850-01-01", calendar="360_day"),
    )
    lat = DimCoord(
        np.linspace(-85.0, 85.0, n_lat),
        standard_name="latitude",
        units="degrees",
    )
    lon = DimCoord(
        np.linspace(2.5, 357.5, n_lon),
        standard_name="longitude",
        units="degrees",
        circular=True,
    )
    for coord in (time, lat, lon):
        coord.guess_bounds()
    return Cube(
        data.astype(np.float32),
        var_name=var_name,
        units=units,
        dim_coords_and_dims=[(time, 0), (lat, 1), (lon, 2)],
    )


def _months() -> np.ndarray:
    return np.tile(np.arange(1, 13), N_YEARS)


def _seasonal(amplitude: float, phase_month: float = 1.0) -> np.ndarray:
    """A 12-month wave of known peak-to-trough range ``2 * amplitude``."""
    months = _months()
    return amplitude * np.cos(2 * np.pi * (months - phase_month) / 12.0)


def _field(series: np.ndarray, n_lat: int = 18, n_lon: int = 36) -> np.ndarray:
    return np.broadcast_to(series[:, None, None], (series.size, n_lat, n_lon)).copy()


def _info(variant: str = "r1i1p1f1") -> DataSourceInformation:
    return DataSourceInformation(
        name="SynthModel",
        category="model",
        exp="historical",
        variant=variant,
    )


def _run(diag_class, cubes, observed, variant: str = "r1i1p1f1"):  # noqa: ANN001, ANN202
    """Run a seasonal diagnostic with every observational fetch stubbed.

    ``observed`` maps a CMOR ``var_name`` to the synthetic cube the (real)
    DataSource would have returned; ``None`` makes every fetch fail, which is
    how the model-only degradation is exercised.
    """
    diag = diag_class(diag_class.__name__.lower(), fail_on_missing_data=False)

    def _cube(_self, var_name, _timerange, source=None):  # noqa: ANN001, ANN202
        if observed is None or var_name not in observed:
            msg = f"no synthetic observations for {var_name}"
            raise FileNotFoundError(msg)
        return observed[var_name].copy()

    diag._observation_cube = _cube.__get__(diag)
    return diag.get_output({"historical": CubeList(cubes)}, _info(variant))


def _frame(output):  # noqa: ANN001, ANN202
    return output.raw_output.to_pandas()


def _value(frame, data_type: str, column: str) -> float:  # noqa: ANN001
    """One scalar of one data type.

    A CB2 complex diagnostic writes **one row per scalar** with every other
    column NULL (``CB2ComplexDiagnostic._scalar_outputs``), which is the
    layout ``scoring_pass.score_scalar_output`` reads with its own
    first-finite lookup — so a test must do the same rather than take row 0.
    """
    series = frame[frame["data_type"] == data_type][column].dropna()
    return float(series.iloc[0]) if not series.empty else float("nan")


# ---------------------------------------------------------------------------
# (i) land annual temperature range
# ---------------------------------------------------------------------------


def test_land_annual_temperature_range_is_the_gridpoint_range() -> None:
    """A uniform 12 K-amplitude cycle has a 24 K annual range everywhere."""
    tas = _monthly_cube(_field(288.0 + _seasonal(12.0)), "tas", "K")
    output = _run(LandAnnualTemperatureRange, [tas], {"tas": tas})
    frame = _frame(output)
    assert _value(frame, "to_benchmark", "land_annual_temperature_range") == (
        pytest.approx(24.0, abs=0.2)
    )
    # the window used is provenance, emitted on the model side only
    assert _value(frame, "to_benchmark", "seasonal_window_first_year") == float(
        BASE_FIRST,
    )
    assert _value(frame, "to_benchmark", "seasonal_window_last_year") == float(
        BASE_LAST,
    )


def test_land_annual_temperature_range_emits_a_reference_row() -> None:
    """Without the reference row the scoring pass has nothing to score."""
    model = _monthly_cube(_field(288.0 + _seasonal(12.0)), "tas", "K")
    observed = _monthly_cube(_field(288.0 + _seasonal(9.0)), "tas", "K")
    output = _run(LandAnnualTemperatureRange, [model], {"tas": observed})
    frame = _frame(output)
    assert (frame["data_type"] == "reference").any()
    assert _value(frame, "reference", "land_annual_temperature_range") == (
        pytest.approx(18.0, abs=0.2)
    )
    # ... and the provenance columns are NOT on the reference row, so the
    # pass never mistakes the window for a scored statistic
    assert not np.isfinite(_value(frame, "reference", "seasonal_window_first_year"))
    assert is_scalar_output(frame)


def test_land_annual_temperature_range_degrades_without_observations() -> None:
    tas = _monthly_cube(_field(288.0 + _seasonal(12.0)), "tas", "K")
    frame = _frame(_run(LandAnnualTemperatureRange, [tas], None))
    assert not (frame["data_type"] == "reference").any()
    assert np.isfinite(_value(frame, "to_benchmark", "land_annual_temperature_range"))


# ---------------------------------------------------------------------------
# (ii)/(iii) stratocumulus regressions
# ---------------------------------------------------------------------------

DECKS = tuple(get_threshold("tier2.seasonal.stratocumulus_regions"))


def _tos_and_clt(slope: float) -> tuple[Cube, Cube]:
    """SST with a seasonal cycle and cloud cover linear in it."""
    tos_series = 295.0 + _seasonal(2.0)
    clt_series = 70.0 + slope * (tos_series - 295.0)
    return (
        _monthly_cube(_field(tos_series), "tos", "K"),
        _monthly_cube(_field(clt_series), "clt", "%"),
    )


def test_sst_low_cloud_covariance_recovers_the_slope_in_every_deck() -> None:
    tos, clt = _tos_and_clt(-4.0)
    output = _run(SSTLowCloudCovariance, [tos, clt], {"tos": tos, "clt": clt})
    frame = _frame(output)
    for deck in DECKS:
        assert _value(frame, "to_benchmark", f"sst_low_cloud_slope_{deck}") == (
            pytest.approx(-4.0, abs=0.05)
        ), deck
    assert _value(frame, "to_benchmark", "sst_low_cloud_slope_mean") == (
        pytest.approx(-4.0, abs=0.05)
    )
    # the same statistic is emitted for the observations
    assert _value(frame, "reference", "sst_low_cloud_slope_mean") == (
        pytest.approx(-4.0, abs=0.05)
    )


def test_seasonal_cloud_feedback_regresses_swcre_on_sst() -> None:
    tos_series = 295.0 + _seasonal(2.0)
    swcre_series = -50.0 + 3.0 * (tos_series - 295.0)
    tos = _monthly_cube(_field(tos_series), "tos", "K")
    swcre = _monthly_cube(_field(swcre_series), "swcre", "W m-2")
    output = _run(
        SeasonalCloudRadiativeFeedback,
        [tos, swcre],
        {"tos": tos, "swcre": swcre},
    )
    frame = _frame(output)
    assert _value(frame, "to_benchmark", "seasonal_swcre_slope_mean") == (
        pytest.approx(3.0, abs=0.05)
    )
    for deck in DECKS:
        assert f"seasonal_swcre_slope_{deck}" in frame.columns


def test_stratocumulus_decks_are_distinct_regions() -> None:
    """A signal confined to one deck must not appear in the others."""
    tos_series = 295.0 + _seasonal(2.0)
    n_lat, n_lon = 18, 36
    clt = _field(70.0 - 4.0 * (tos_series - 295.0), n_lat, n_lon)
    lats = np.linspace(-85.0, 85.0, n_lat)
    lons = np.linspace(2.5, 357.5, n_lon)
    # Double the sensitivity inside the Peruvian box only
    box = get_threshold("tier2.seasonal.stratocumulus_regions")["peruvian"]
    in_lat = (lats >= box["lat"][0]) & (lats <= box["lat"][1])
    in_lon = ((lons - 360.0) >= box["lon"][0]) & ((lons - 360.0) <= box["lon"][1])
    mask = np.outer(in_lat, in_lon)
    clt[:, mask] = (70.0 - 8.0 * (tos_series - 295.0))[:, None]
    tos = _monthly_cube(_field(tos_series), "tos", "K")
    output = _run(
        SSTLowCloudCovariance,
        [tos, _monthly_cube(clt, "clt", "%")],
        {"tos": tos, "clt": _monthly_cube(clt, "clt", "%")},
    )
    frame = _frame(output)
    # The doubled sensitivity is diluted a little at the box edges by the
    # regrid onto the 2 degree analysis grid, so the Peruvian slope lands
    # near -8 rather than on it; the point is that it is nowhere near -4.
    assert _value(frame, "to_benchmark", "sst_low_cloud_slope_peruvian") == (
        pytest.approx(-8.0, abs=1.0)
    )
    assert _value(frame, "to_benchmark", "sst_low_cloud_slope_namibian") == (
        pytest.approx(-4.0, abs=0.1)
    )


def test_seasonal_scalars_are_scored_by_the_pass() -> None:
    """Two members plus the reference row give a fair CRPS and a window label."""
    import pandas as pd

    observed = _tos_and_clt(-4.0)
    frames = []
    for i, variant in enumerate(("r1i1p1f1", "r2i1p1f1")):
        tos, clt = _tos_and_clt(-3.0 - i)
        frames.append(
            _frame(
                _run(
                    SSTLowCloudCovariance,
                    [tos, clt],
                    {"tos": observed[0], "clt": observed[1]},
                    variant=variant,
                ),
            ),
        )
    frame = pd.concat(frames, ignore_index=True)
    assert is_scalar_output(frame)
    sources = pd.DataFrame(
        {
            "id": [_info("r1i1p1f1").id, _info("r2i1p1f1").id],
            "name": ["SynthModel", "SynthModel"],
            "category": ["model", "model"],
        },
    )
    rows = score_scalar_output(frame, sources, diagnostic="sst_low_cloud_covariance")
    scored = {
        r["var_id"]: r
        for r in rows
        if r["data_id"] == "SynthModel" and not r["var_id"].endswith("_consistency")
    }
    row = scored["sst_low_cloud_slope_mean"]
    assert row["n_members"] == 2.0
    assert np.isfinite(row["crps"])
    assert row["window"] == "in-sample"
    # the provenance columns are never scored (no reference value for them)
    assert "seasonal_window_first_year" not in scored
