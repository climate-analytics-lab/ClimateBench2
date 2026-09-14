"""Tests for the Tier I gate diagnostics (cube-level plumbing).

Builds small synthetic CMOR-like cubes and runs selected gates end-to-end
through ClimateEval's ComplexDiagnostic machinery (needs climateeval).
"""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

climateeval = pytest.importorskip("climateeval")

import iris  # noqa: E402
from cf_units import Unit  # noqa: E402
from iris.coords import DimCoord  # noqa: E402
from iris.cube import Cube, CubeList  # noqa: E402

from climateeval.data import DataSourceInformation  # noqa: E402

from climatebench2._thresholds import get_threshold  # noqa: E402
from climatebench2.diags.tier1_physics import (  # noqa: E402
    CB2ComplexDiagnostic,
    ClearSkyFeedbackGate,
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
    series: np.ndarray | None = None,
) -> Cube:
    """Global monthly cube with a constant (optionally drifting) field.

    ``series`` adds a per-timestep offset (length ``n_years * 12``), so a
    cube can carry an arbitrary global-mean time series.
    """
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
    values = value + trend_per_year * years
    if series is not None:
        values = values + np.asarray(series, dtype=float)
    data = np.broadcast_to(
        values[:, None, None],
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
    hfls = pr * 2.5008e6  # W m-2, closes the water budget (~87 = L_v P)
    hfss = 20.0
    rsdt, rsut = 340.0, 100.0
    rlut = rsdt - rsut - toa_imbalance  # TOA net = toa_imbalance
    # Surface net radiation closing the atmospheric energy budget exactly
    # (paper I.2b): Q_rad = SFCrad - TOA = L_v P + SHF
    sfc_net_rad = toa_imbalance + hfls + hfss
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
    # ... and so do Q_rad and L_v P + SHF (paper I.2b arrangement)
    assert metrics.loc["atm_energy_budget", "value"] == pytest.approx(0.0, abs=0.05)
    assert metrics.loc["atm_energy_budget", "passes"] == 1.0


def test_closure_gate_atmospheric_energy_budget_fails_when_open() -> None:
    """A 5 W/m² surface-radiation error breaks the 2 W/m² bound."""
    diag = ClosureGate("closure", fail_on_missing_data=True)
    cubes = _picontrol_cubes()
    cubes.extract_cube(iris.NameConstraint(var_name="rlds")).data += np.float32(5.0)
    output = diag.get_output({"picontrol": cubes}, _info())
    metrics = output.metrics.to_pandas().set_index("var_id")
    assert metrics.loc["atm_energy_budget", "value"] == pytest.approx(5.0, abs=0.05)
    assert metrics.loc["atm_energy_budget", "passes"] == 0.0


def test_energy_balance_gate_uses_only_the_last_evaluation_years(monkeypatch) -> None:  # noqa: ANN001
    """I.1 is evaluated over the last `evaluation_years` of the control."""
    n_eval = int(get_threshold("tier1.energy_balance.evaluation_years"))
    # 50 badly imbalanced years followed by `n_eval` balanced ones: the whole
    # record would average 50*5/(50+n_eval) = 1.67 W/m2 and fail.
    toa_net = np.concatenate([np.full(50, 5.0), np.zeros(n_eval)])
    monkeypatch.setattr(
        EnergyBalanceGate,
        "_toa_net_annual_global",
        lambda self, data: toa_net,  # noqa: ARG005
    )
    diag = EnergyBalanceGate("energy_balance", fail_on_missing_data=True)
    raw = diag._calculate_raw_output(SimpleNamespace(data={"picontrol": None}))
    values = {variable.var_name: float(cube.data) for variable, cube in raw.items()}
    assert values["n_years"] == n_eval
    assert values["toa_net_mean_abs"] == pytest.approx(0.0, abs=1e-9)
    assert values["toa_net_drift_abs"] == pytest.approx(0.0, abs=1e-9)


def test_energy_balance_gate_short_control_uses_whole_record(monkeypatch) -> None:  # noqa: ANN001
    """A control shorter than the window is used whole (with a warning)."""
    toa_net = np.full(30, 0.05)
    monkeypatch.setattr(
        EnergyBalanceGate,
        "_toa_net_annual_global",
        lambda self, data: toa_net,  # noqa: ARG005
    )
    diag = EnergyBalanceGate("energy_balance", fail_on_missing_data=True)
    raw = diag._calculate_raw_output(SimpleNamespace(data={"picontrol": None}))
    values = {variable.var_name: float(cube.data) for variable, cube in raw.items()}
    assert values["n_years"] == 30
    assert values["toa_net_mean_abs"] == pytest.approx(0.05)


def test_clear_sky_feedback_gate_regresses_monthly_anomalies() -> None:
    """I.3a: β from deseasonalised monthly anomalies, not annual means.

    ``ts`` carries a large seasonal cycle, fast (monthly) variability that
    ``rlutcs`` responds to with the target β = 2.2 W/m²/K, and slow (annual)
    variability it responds to with a much larger slope. Annual averaging
    keeps only the slow component and would report β ≈ 4 — outside the
    ±25% gate — so this test fails if the regression reverts to annual means.
    """
    rng = np.random.default_rng(7)
    n_time = N_YEARS * 12
    month = np.arange(n_time) % 12
    fast = rng.normal(0.0, 1.0, n_time)
    slow = np.repeat(rng.normal(0.0, 1.0 / np.sqrt(12.0), N_YEARS), 12)
    seasonal = 5.0 * np.sin(2 * np.pi * month / 12.0)

    ts = _monthly_cube("ts", 288.0, "K", series=seasonal + fast + slow)
    rlutcs = _monthly_cube(
        "rlutcs",
        240.0,
        "W m-2",
        series=2.2 * fast + 6.0 * slow,
    )
    diag = ClearSkyFeedbackGate("clear_sky_feedback", fail_on_missing_data=True)
    output = diag.get_output({"historical": CubeList([ts, rlutcs])}, _info())
    metrics = output.metrics.to_pandas().set_index("var_id")
    beta = metrics.loc["clear_sky_lw_feedback", "value"]
    assert 2.2 <= beta <= 2.75  # monthly anomalies; annual means give ~4
    assert metrics.loc["clear_sky_lw_feedback", "passes"] == 1.0


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
    """The CB2-owned gates (no upstream provider) share the CB2 base class."""
    from climatebench2 import diags

    for name in (
        "EnergyBalanceGate",
        "ClosureGate",
        "ClearSkyFeedbackGate",
        "AerosolForcingGate",
        "ITCZEFEGate",
        "BjerknesGate",
        "CCScalingGate",
    ):
        assert issubclass(getattr(diags, name), CB2ComplexDiagnostic)
        assert getattr(diags, name)._gate_checks  # every gate has checks wired


def test_upstream_gate_wrappers_subclass_climateeval_diagnostics() -> None:
    """I.6a/b/c and I.8a are thin gates over ClimateEval's own diagnostics."""
    from climateeval.diags.complex import (
        ECS,
        ArcticAmplification,
        LandOceanWarmingRatio,
        MeridionalHeatTransport,
    )

    from climatebench2 import diags
    from climatebench2.diags.pass_fail import GateMixin, SupersetExperimentMixin

    for gate, upstream in (
        (diags.ECSGate, ECS),
        (diags.LandOceanWarmingGate, LandOceanWarmingRatio),
        (diags.ArcticAmplificationGate, ArcticAmplification),
        (diags.MeridionalHeatTransportGate, MeridionalHeatTransport),
    ):
        assert issubclass(gate, upstream)
        assert issubclass(gate, GateMixin)
        assert issubclass(gate, SupersetExperimentMixin)
        # No CB2 re-implementation of the upstream computation
        assert "_calculate_raw_output" not in vars(gate)


def test_upstream_gate_wrappers_carry_the_protocol_thresholds() -> None:
    from climatebench2 import diags

    (land_ocean,) = diags.LandOceanWarmingGate._gate_checks
    assert land_ocean.check_id == "land_ocean_warming"
    assert land_ocean.column == "land_ocean_warming_ratio"
    assert (land_ocean.lower, land_ocean.upper) == (1.2, 1.6)

    (arctic,) = diags.ArcticAmplificationGate._gate_checks
    assert arctic.column == "arctic_amplification"
    assert (arctic.lower, arctic.upper) == (1.5, None)

    bounds = {
        check.check_id: (check.column, check.lower, check.upper)
        for check in diags.MeridionalHeatTransportGate._gate_checks
    }
    assert bounds["omet_peak"] == ("omet_peak", 1.5, 2.0)
    assert bounds["omet_peak_lat"] == ("omet_peak_lat", 15.0, 20.0)
    assert bounds["amet_peak"] == ("amet_peak", 4.0, 5.0)
    assert bounds["amet_peak_lat"] == ("amet_peak_lat", 40.0, 50.0)


def test_upstream_gate_wrappers_feed_thresholds_into_upstream_kwargs() -> None:
    """Protocol constants reach the upstream diagnostic, not the suite YAML."""
    from climatebench2 import diags

    land_ocean = diags.LandOceanWarmingGate("land_ocean_warming")
    assert land_ocean._equilibrium_years == 50

    arctic = diags.ArcticAmplificationGate("arctic_amplification")
    assert arctic._equilibrium_years == 50
    assert arctic._arctic_latitude == pytest.approx(66.5)

    mht = diags.MeridionalHeatTransportGate("meridional_heat_transport")
    assert tuple(mht._omet_search_band) == (5, 30)
    assert tuple(mht._amet_search_band) == (25, 55)

    # An explicit suite kwarg still wins over the thresholds.yml default
    override = diags.ArcticAmplificationGate("arctic", arctic_latitude=70.0)
    assert override._arctic_latitude == pytest.approx(70.0)
