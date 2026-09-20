"""Tests for the extended Tier I gates (I.3b, I.3c and I.5c).

I.3c and I.5c are run end-to-end on synthetic cubes with the observational
fetch monkeypatched — no network, no CDS credentials, no real climate data
(see tests/README.md). I.3b needs no observations, so its synthetic daily
fields go straight through the gate.
"""

from __future__ import annotations

from types import SimpleNamespace

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


# ---------------------------------------------------------------------------
# I.3b geostrophic balance — through the gate, on a masked pressure level
# ---------------------------------------------------------------------------

#: The common 2°×2° grid every CB2 gate regrids to (``DEFAULT_GRID``), so the
#: gate's own regrid is the identity and the test measures only its physics.
_GEO_LATS = np.arange(-89.0, 90.0, 2.0)
_GEO_LONS = np.arange(1.0, 360.0, 2.0)
_GEO_PLEV = np.array([100000.0, 85000.0, 70000.0])
_GEO_N_DAYS = 8


def _balanced_zg_and_ua() -> tuple[np.ndarray, np.ndarray]:
    """A geostrophically balanced ``(zg, ua)`` pair, analytically exact.

    ``Z = ½(A + a₁s₁) cos²φ + B s₂ cos λ cos²φ`` has, through
    ``u_g = −(g/f) ∂Z/∂y`` with ``f = 2Ω sin φ``,

        ``u_g = g(A + a₁s₁) cos φ / (2Ω a) + g B s₂ cos λ cos φ / (Ω a)``

    — no finite differences on either side, so a gate that recovers the
    balance must return ρ ≈ 1.
    """
    phi = np.deg2rad(_GEO_LATS)[None, :, None]
    lam = np.deg2rad(_GEO_LONS)[None, None, :]
    day = np.arange(_GEO_N_DAYS, dtype=float)[:, None, None]
    s_1 = np.sin(2.0 * np.pi * day / _GEO_N_DAYS)
    s_2 = np.cos(2.0 * np.pi * day / _GEO_N_DAYS)
    amp, amp_1, amp_wave = 500.0, 150.0, 80.0
    c = amp + amp_1 * s_1
    d = amp_wave * s_2
    zg = 0.5 * c * np.cos(phi) ** 2 + d * np.cos(lam) * np.cos(phi) ** 2
    scale = physics.GRAVITY / (2.0 * physics.OMEGA_EARTH * physics.EARTH_RADIUS_M)
    ua = scale * c * np.cos(phi) + 2.0 * scale * d * np.cos(lam) * np.cos(phi)
    return (
        np.broadcast_to(zg, (_GEO_N_DAYS,) + zg.shape[1:]).copy(),
        np.broadcast_to(ua, (_GEO_N_DAYS,) + ua.shape[1:]).copy(),
    )


def _daily_level_cube(var_name: str, units: str, field: np.ndarray) -> Cube:
    """``(time, plev, lat, lon)`` daily cube carrying ``field`` at every level.

    ``field`` is a ``(time, lat, lon)`` masked array; the mask is kept, which
    is the point of the fixture — CMIP6 publishes 850 hPa ``ua``/``zg`` as a
    masked array wherever the level is below ground.
    """
    time = DimCoord(
        np.arange(field.shape[0], dtype=float) + 0.5,
        standard_name="time",
        units=Unit("days since 2000-01-01", calendar="360_day"),
    )
    plev = DimCoord(
        _GEO_PLEV,
        standard_name="air_pressure",
        units="Pa",
        attributes={"positive": "down"},
    )
    lat = DimCoord(_GEO_LATS, standard_name="latitude", units="degrees")
    lon = DimCoord(_GEO_LONS, standard_name="longitude", units="degrees", circular=True)
    for coord in (lat, lon, time):
        coord.guess_bounds()
    data = np.ma.stack([field] * _GEO_PLEV.size, axis=1)
    return Cube(
        data,
        var_name=var_name,
        units=units,
        dim_coords_and_dims=[(time, 0), (plev, 1), (lat, 2), (lon, 3)],
    )


def _sub_surface_mask() -> np.ndarray:
    """A plateau: 30–60°N, 90–150°E, where 850 hPa is below ground."""
    lat_hit = (_GEO_LATS >= 30.0) & (_GEO_LATS <= 60.0)
    lon_hit = (_GEO_LONS >= 90.0) & (_GEO_LONS <= 150.0)
    return (lat_hit[:, None] & lon_hit[None, :])[None, :, :] & np.ones(
        (_GEO_N_DAYS, 1, 1),
        dtype=bool,
    )


def _geostrophic_correlation(*, masked: bool) -> float:
    from climatebench2.diags import GeostrophicBalanceGate

    zg, ua = _balanced_zg_and_ua()
    if masked:
        # ...exactly as iris hands a CMIP6 file over: values *under* the mask
        # are the file's 1e20 fill value, not anything physical.
        mask = _sub_surface_mask()
        zg = np.ma.masked_array(np.where(mask, 1.0e20, zg), mask=mask)
        ua = np.ma.masked_array(np.where(mask, 1.0e20, ua), mask=mask)
    data = CubeList(
        [
            _daily_level_cube("zg", "m", zg),
            _daily_level_cube("ua", "m s-1", ua),
        ],
    )
    gate = GeostrophicBalanceGate("geostrophic_balance")
    output = gate._calculate_raw_output(SimpleNamespace(data={"day": data}))  # noqa: SLF001
    (cube,) = (c for v, c in output.items() if v.var_name == "geostrophic_corr")
    return float(cube.data)


def test_geostrophic_gate_recovers_a_balanced_wind() -> None:
    """An exactly balanced zg/ua pair must correlate at ρ > 0.99."""
    assert _geostrophic_correlation(masked=False) > 0.99


def test_geostrophic_gate_ignores_sub_surface_fill_values() -> None:
    """A masked 850 hPa plateau must not enter the correlation.

    Regression test: reading the cube with ``np.asarray`` instead of
    ``_filled`` exposed the 1e20 under the mask and drove ρ on real
    CNRM-CM6-1 daily data from 0.99 to 0.09.
    """
    assert _geostrophic_correlation(masked=True) > 0.99
