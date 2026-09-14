"""Tests for the two Tier I gates that need observations (I.3c and I.5c).

Both are run end-to-end on synthetic cubes with the observational fetch
monkeypatched — no network, no CDS credentials, no real climate data (see
tests/README.md).
"""

from __future__ import annotations

import numpy as np
import pytest

climateeval = pytest.importorskip("climateeval")

from cf_units import Unit  # noqa: E402
from iris.coords import DimCoord  # noqa: E402
from iris.cube import Cube, CubeList  # noqa: E402

from climatebench2 import physics  # noqa: E402
from climatebench2.diags import ENSOTeleconnectionsGate, PrecipBuoyancyGate  # noqa: E402

from test_tier1_physics import _info, _monthly_cube  # noqa: E402

N_YEARS = 20
LATS = np.linspace(-85.0, 85.0, 18)
LONS = np.linspace(5.0, 355.0, 36)


def _enso_pattern() -> np.ndarray:
    """A smooth (lat, lon) teleconnection pattern, positive over Niño-3.4."""
    return (
        np.cos(np.deg2rad(LATS))[:, None]
        * np.cos(np.deg2rad(LONS - 215.0))[None, :]
        + 0.3
    )


# ---------------------------------------------------------------------------
# I.5c ENSO teleconnection patterns
# ---------------------------------------------------------------------------


def _enso_cubes(
    seed: int,
    *,
    ts_sign: float = 1.0,
    pr_sign: float = 1.0,
    start_year: int = 1850,
) -> dict[str, Cube]:
    """tos (uniform ENSO index) + ts/pr carrying the pattern times that index."""
    rng = np.random.default_rng(seed)
    index = rng.normal(0.0, 1.0, N_YEARS * 12)
    pattern = _enso_pattern()
    common = {"n_years": N_YEARS, "series": index, "start_year": start_year}
    return {
        "tos": _monthly_cube("tos", 27.0, "degC", **common),
        "ts": _monthly_cube("ts", 288.0, "K", field=ts_sign * pattern, **common),
        "pr": _monthly_cube(
            "pr",
            3.0e-5,
            "kg m-2 s-1",
            field=pr_sign * pattern * 1.0e-6,
            **common,
        ),
    }


def _observed_cubes(*, pr_sign: float = 1.0) -> dict[str, Cube]:
    """HadISST-like ``tos`` (SST *and* index) and GPCP-like ``pr``."""
    obs = _enso_cubes(99, pr_sign=pr_sign, start_year=1979)
    # the observed temperature reference is SST, not ts: give tos the pattern
    pattern = _enso_pattern()
    rng = np.random.default_rng(99)
    index = rng.normal(0.0, 1.0, N_YEARS * 12)
    obs["tos"] = _monthly_cube(
        "tos",
        27.0,
        "degC",
        n_years=N_YEARS,
        series=index,
        field=pattern,
        start_year=1979,
    )
    return obs


def _run_teleconnections(
    monkeypatch: pytest.MonkeyPatch,
    model: dict[str, Cube],
    observed: dict[str, Cube] | None,
    *,
    fail_on_missing_data: bool = False,
):  # noqa: ANN201
    def fake_observation_cube(_self, _source, var_name: str) -> Cube:
        if observed is None:
            msg = "no network in the test environment"
            raise RuntimeError(msg)
        return observed[var_name]

    monkeypatch.setattr(
        ENSOTeleconnectionsGate,
        "_observation_cube",
        fake_observation_cube,
    )
    diag = ENSOTeleconnectionsGate(
        "enso_teleconnections",
        fail_on_missing_data=fail_on_missing_data,
    )
    return diag.get_output({"picontrol": CubeList(model.values())}, _info())


def test_teleconnection_patterns_matching_observations_score_one(monkeypatch) -> None:  # noqa: ANN001
    """A model whose ts/pr patterns equal the observed ones scores r ≈ 1."""
    output = _run_teleconnections(monkeypatch, _enso_cubes(3), _observed_cubes())
    metrics = output.metrics.to_pandas().set_index("var_id")
    for check in ("enso_teleconnection_ts", "enso_teleconnection_pr"):
        assert metrics.loc[check, "value"] == pytest.approx(1.0, abs=0.02)
        assert metrics.loc[check, "passes"] == 1.0
        assert metrics.loc[check, "bound_lower"] == 0.7
        assert metrics.loc[check, "requirement"] == "required"
    raw = output.raw_output.to_pandas().bfill().iloc[0]
    assert raw["teleconnection_obs_first_year"] == 1979.0
    assert raw["teleconnection_obs_last_year"] == 2014.0
    assert raw["ts_pattern_rms"] > 0.0


def test_sign_flipped_teleconnection_patterns_score_minus_one(monkeypatch) -> None:  # noqa: ANN001
    """Flip the model's ts and the observed pr: both correlations go to −1."""
    output = _run_teleconnections(
        monkeypatch,
        _enso_cubes(3, ts_sign=-1.0),
        _observed_cubes(pr_sign=-1.0),
    )
    metrics = output.metrics.to_pandas().set_index("var_id")
    for check in ("enso_teleconnection_ts", "enso_teleconnection_pr"):
        assert metrics.loc[check, "value"] == pytest.approx(-1.0, abs=0.02)
        assert metrics.loc[check, "passes"] == 0.0


def test_teleconnections_without_observations_emit_no_gate_rows(monkeypatch) -> None:  # noqa: ANN001
    """No network: the model's pattern summary, a logged reason, no gate."""
    output = _run_teleconnections(monkeypatch, _enso_cubes(3), None)
    if output.metrics is not None:
        assert output.metrics.to_pandas().empty
    raw = output.raw_output.to_pandas().bfill().iloc[0]
    assert raw["nino34_std"] == pytest.approx(1.0, abs=0.1)
    assert raw["ts_pattern_rms"] > 0.0
    assert "teleconnection_corr_ts" not in raw.index


def test_teleconnections_reraise_when_failing_on_missing_data(monkeypatch) -> None:  # noqa: ANN001
    with pytest.raises(RuntimeError, match="no network"):
        _run_teleconnections(
            monkeypatch,
            _enso_cubes(3),
            None,
            fail_on_missing_data=True,
        )


# ---------------------------------------------------------------------------
# I.3c tropical precipitation–buoyancy
# ---------------------------------------------------------------------------

PLEV = np.array([100000.0, 85000.0, 50000.0, 25000.0])
PR_PER_UNIT_TA = 4.0e-5  # kg m-2 s-1 per K of the (uniform) ta anomaly


def _level_cube(
    var_name: str,
    value: float,
    units: str,
    *,
    n_years: int,
    series: np.ndarray | None = None,
) -> Cube:
    """A (time, plev, lat, lon) cube, constant in height and space."""
    n_time = n_years * 12
    time = DimCoord(
        np.arange(n_time, dtype=float) * 30.0 + 15.0,
        standard_name="time",
        units=Unit("days since 1850-01-01", calendar="360_day"),
    )
    plev = DimCoord(PLEV, standard_name="air_pressure", units="Pa")
    lat = DimCoord(LATS, standard_name="latitude", units="degrees")
    lon = DimCoord(LONS, standard_name="longitude", units="degrees", circular=True)
    for coord in (time, lat, lon):
        coord.guess_bounds()
    values = np.full(n_time, value, dtype=float)
    if series is not None:
        values = values + np.asarray(series, dtype=float)
    data = np.broadcast_to(
        values[:, None, None, None],
        (n_time, PLEV.size, LATS.size, LONS.size),
    ).astype(np.float32)
    return Cube(
        data.copy(),
        var_name=var_name,
        units=units,
        dim_coords_and_dims=[(time, 0), (plev, 1), (lat, 2), (lon, 3)],
    )


def _buoyancy_cubes(seed: int = 5, n_years: int = 5) -> CubeList:
    """pr responding to a uniform ta anomaly — but only inside 25S–25N."""
    rng = np.random.default_rng(seed)
    anomaly = rng.normal(0.0, 1.0, n_years * 12)
    # 1 in the tropics, 5 outside: a global regression would see a steeper
    # slope than the 20S-20N one the protocol asks for
    weight = np.where(np.abs(LATS) <= 25.0, 1.0, 5.0)[:, None] * np.ones(LONS.size)
    return CubeList(
        [
            _monthly_cube(
                "pr",
                3.0e-5,
                "kg m-2 s-1",
                n_years=n_years,
                series=PR_PER_UNIT_TA * anomaly,
                field=weight,
            ),
            _level_cube("ta", 250.0, "K", n_years=n_years, series=anomaly),
            _level_cube("zg", 5000.0, "m", n_years=n_years),
            _level_cube("hus", 0.005, "1", n_years=n_years),
        ],
    )


def _expected_slope() -> float:
    """mm/day per MJ/m² for the synthetic column (only c_p·ta varies)."""
    d_pressure = PLEV.max() - PLEV.min()
    d_column = (
        physics.SPECIFIC_HEAT_DRY_AIR * d_pressure / physics.GRAVITY / 1.0e6
    )  # MJ/m2 per K
    return PR_PER_UNIT_TA * physics.SECONDS_PER_DAY / d_column


def _run_precip_buoyancy(
    monkeypatch: pytest.MonkeyPatch,
    reference: float | None,
):  # noqa: ANN201
    def fake_observed_slope(_self) -> float:
        if reference is None:
            msg = "no network in the test environment"
            raise RuntimeError(msg)
        return reference

    monkeypatch.setattr(PrecipBuoyancyGate, "_observed_slope", fake_observed_slope)
    diag = PrecipBuoyancyGate("precip_buoyancy", fail_on_missing_data=False)
    return diag.get_output({"historical": _buoyancy_cubes()}, _info())


def test_precip_buoyancy_slope_is_the_tropical_pooled_regression(monkeypatch) -> None:  # noqa: ANN001
    """The recovered slope is the 20S–20N one, not the global one."""
    expected = _expected_slope()
    output = _run_precip_buoyancy(monkeypatch, expected / 1.1)
    raw = output.raw_output.to_pandas().bfill().iloc[0]
    assert raw["precip_buoyancy_slope"] == pytest.approx(expected, rel=0.02)
    assert raw["precip_buoyancy_reference_from_obs"] == 1.0
    metrics = output.metrics.to_pandas().set_index("var_id")
    # |slope/ref - 1| = 0.1 <= 0.30
    assert metrics.loc["precip_buoyancy", "value"] == pytest.approx(0.1, abs=0.02)
    assert metrics.loc["precip_buoyancy", "passes"] == 1.0
    assert metrics.loc["precip_buoyancy", "bound_upper"] == 0.3


def test_precip_buoyancy_fails_a_slope_outside_the_tolerance(monkeypatch) -> None:  # noqa: ANN001
    output = _run_precip_buoyancy(monkeypatch, _expected_slope() / 2.0)
    metrics = output.metrics.to_pandas().set_index("var_id")
    assert metrics.loc["precip_buoyancy", "value"] == pytest.approx(1.0, abs=0.05)
    assert metrics.loc["precip_buoyancy", "passes"] == 0.0


def test_precip_buoyancy_without_a_reference_emits_the_model_slope(monkeypatch) -> None:  # noqa: ANN001
    """No observations and a null stored slope: report, do not gate."""
    output = _run_precip_buoyancy(monkeypatch, None)
    raw = output.raw_output.to_pandas().bfill().iloc[0]
    assert raw["precip_buoyancy_slope"] == pytest.approx(_expected_slope(), rel=0.02)
    assert "precip_buoyancy_slope_rel_error" not in raw.index
    if output.metrics is not None:
        assert output.metrics.to_pandas().empty
