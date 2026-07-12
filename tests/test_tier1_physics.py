"""Tests for the Tier I gate diagnostics (cube-level plumbing).

Builds small synthetic CMOR-like cubes and runs selected gates end-to-end
through ClimateEval's ComplexDiagnostic machinery (needs climateeval).
"""

from __future__ import annotations

import numpy as np
import pytest

climateeval = pytest.importorskip("climateeval")

import iris  # noqa: E402
from cf_units import Unit  # noqa: E402
from iris.coords import DimCoord  # noqa: E402
from iris.cube import Cube, CubeList  # noqa: E402

from climateeval.data import DataSourceInformation  # noqa: E402

from climatebench2.diags.tier1_physics import (  # noqa: E402
    CB2ComplexDiagnostic,
    ClosureGate,
    EnergyBalanceGate,
)

N_YEARS = 30


def _monthly_cube(
    var_name: str,
    value: float,
    units: str,
    *,
    n_years: int = N_YEARS,
    trend_per_year: float = 0.0,
) -> Cube:
    """Global monthly cube with a constant (optionally drifting) field."""
    n_time = n_years * 12
    time = DimCoord(
        np.arange(n_time, dtype=float) * 30.0 + 15.0,
        standard_name="time",
        units=Unit("days since 1850-01-01", calendar="360_day"),
    )
    lat = DimCoord(
        np.linspace(-85.0, 85.0, 18),
        standard_name="latitude",
        units="degrees",
    )
    lon = DimCoord(
        np.linspace(5.0, 355.0, 36),
        standard_name="longitude",
        units="degrees",
        circular=True,
    )
    lat.guess_bounds()
    lon.guess_bounds()
    time.guess_bounds()
    years = np.arange(n_time, dtype=float) / 12.0
    data = np.broadcast_to(
        (value + trend_per_year * years)[:, None, None],
        (n_time, 18, 36),
    ).astype(np.float32)
    return Cube(
        data.copy(),
        var_name=var_name,
        standard_name=None,
        units=units,
        dim_coords_and_dims=[(time, 0), (lat, 1), (lon, 2)],
    )


def _picontrol_cubes(
    *,
    toa_imbalance: float = 0.0,
    drift: float = 0.0,
) -> CubeList:
    """piControl fluxes: balanced TOA + balanced surface/water budget."""
    pr = 3.0 / 86400.0  # kg m-2 s-1  (3 mm/day)
    hfls = pr * 2.5008e6  # W m-2, closes the water budget (~87)
    hfss = 20.0
    rsdt, rsut = 340.0, 100.0
    rlut = rsdt - rsut - toa_imbalance  # TOA net = toa_imbalance
    # Surface net radiation to close the atmospheric budget exactly:
    # residual = |LP - (-(TOA - SFCrad) + SHF)| = 0
    # => SFCrad = TOA - (SHF - LP)
    sfc_net_rad = toa_imbalance - (hfss - hfls * 1.0) + 0.0
    rsds, rsus = 185.0, 25.0  # net SW = 160
    rlds = sfc_net_rad - (rsds - rsus) + 340.0  # choose rlus = 340
    rlus = 340.0
    cubes = CubeList(
        [
            _monthly_cube("pr", pr, "kg m-2 s-1"),
            _monthly_cube("hfls", hfls, "W m-2"),
            _monthly_cube("hfss", hfss, "W m-2"),
            _monthly_cube("rsdt", rsdt, "W m-2"),
            _monthly_cube("rsut", rsut, "W m-2"),
            _monthly_cube("rlut", rlut, "W m-2", trend_per_year=-drift / 10.0),
            _monthly_cube("rsds", rsds, "W m-2"),
            _monthly_cube("rsus", rsus, "W m-2"),
            _monthly_cube("rlds", rlds, "W m-2"),
            _monthly_cube("rlus", rlus, "W m-2"),
        ],
    )
    return cubes


def _info() -> DataSourceInformation:
    return DataSourceInformation(
        name="SynthModel",
        category="model",
        institute="Synth",
        exp="piControl",
        variant="r1i1p1f1",
    )


@pytest.fixture(scope="module")
def balanced_output():  # noqa: ANN201
    diag = EnergyBalanceGate("energy_balance", fail_on_missing_data=True)
    data = {"picontrol": _picontrol_cubes(toa_imbalance=0.05)}
    return diag.get_output(data, _info())


def test_energy_balance_gate_passes_balanced_control(balanced_output) -> None:  # noqa: ANN001
    metrics = balanced_output.metrics.to_pandas().set_index("var_id")
    assert metrics.loc["energy_balance_mean", "value"] == pytest.approx(0.05, abs=0.02)
    assert metrics.loc["energy_balance_mean", "passes"] == 1.0
    assert metrics.loc["energy_balance_drift", "passes"] == 1.0


def test_energy_balance_gate_raw_output_columns(balanced_output) -> None:  # noqa: ANN001
    raw = balanced_output.raw_output.to_pandas()
    assert {"toa_net_mean_abs", "toa_net_drift_abs", "n_years"} <= set(raw.columns)
    assert raw.iloc[0]["n_years"] == N_YEARS


def test_energy_balance_gate_fails_drifting_control() -> None:
    diag = EnergyBalanceGate("energy_balance", fail_on_missing_data=True)
    data = {"picontrol": _picontrol_cubes(toa_imbalance=0.5, drift=0.5)}
    output = diag.get_output(data, _info())
    metrics = output.metrics.to_pandas().set_index("var_id")
    assert metrics.loc["energy_balance_mean", "passes"] == 0.0  # |0.5| > 0.1
    assert metrics.loc["energy_balance_drift", "passes"] == 0.0  # 0.5 > 0.02


def test_closure_gate_water_budget_passes() -> None:
    diag = ClosureGate("closure", fail_on_missing_data=True)
    data = {"picontrol": _picontrol_cubes()}
    output = diag.get_output(data, _info())
    metrics = output.metrics.to_pandas().set_index("var_id")
    # P and E constructed to balance exactly
    assert metrics.loc["water_budget", "value"] == pytest.approx(0.0, abs=1e-3)
    assert metrics.loc["water_budget", "passes"] == 1.0


def test_superset_keys_accepted() -> None:
    """CB2 complex diagnostics tolerate extra experiment keys (one suite dict)."""
    diag = EnergyBalanceGate("energy_balance", fail_on_missing_data=True)
    data = {
        "picontrol": _picontrol_cubes(),
        "4xco2": CubeList([]),  # extra key, unused
        "histaer": CubeList([]),
    }
    output = diag.get_output(data, _info())
    assert output.metrics is not None

    with pytest.raises(ValueError, match="Missing keys"):
        diag.get_output({"4xco2": CubeList([])}, _info())


def test_all_tier1_gates_are_cb2_complex() -> None:
    from climatebench2 import diags

    for name in (
        "EnergyBalanceGate",
        "ClosureGate",
        "ClearSkyFeedbackGate",
        "LandOceanWarmingGate",
        "ArcticAmplificationGate",
        "AerosolForcingGate",
        "MeridionalHeatTransportGate",
        "ITCZEFEGate",
        "BjerknesGate",
        "CCScalingGate",
    ):
        assert issubclass(getattr(diags, name), CB2ComplexDiagnostic)
        assert getattr(diags, name)._gate_checks  # every gate has checks wired
