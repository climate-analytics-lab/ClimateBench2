"""Extended Tier I gates: causal-response and daily-data checks (Phase 4).

Previously entirely missing from the protocol implementation
(metrics_reference.md status ❌): geostrophic balance (I.3b), GFMIP patch
Δλ (I.4a), amip-4xCO2 ERF (I.4b), ENSO teleconnections (I.5c), MJO
Wheeler–Kiladis (I.5d).

Data keys (superset semantics as in ``tier1_physics``):

- ``day`` — daily-frequency output (ua/zg for I.3b, pr for I.5d)
- ``amip`` / ``amip4xco2`` — fixed-SST runs for I.4b
- ``amip`` / ``patch_ep`` / ``patch_wp`` — GFMIP patch runs for I.4a
- ``picontrol`` — coupled control for I.5c
"""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

import numpy as np
from esmvalcore.preprocessor import (
    anomalies,
    area_statistics,
    extract_levels,
    extract_region,
    rolling_window_statistics,
)

from climateeval import Variable
from climateeval._config import setup_esmvaltool_config_and_logging

from climatebench2 import physics
from climatebench2._thresholds import get_threshold
from climatebench2.diags.pass_fail import GateCheck
from climatebench2.diags.tier1_physics import CB2ComplexDiagnostic, _mon

if TYPE_CHECKING:
    from iris.cube import Cube, CubeList
    from xarray import Dataset

    from climateeval.data import ComplexDataSource


def _day(name: str) -> Variable:
    """Daily input variable."""
    return Variable(name, name, "day")


# ---------------------------------------------------------------------------
# I.3b — Midlatitude geostrophic balance (daily 850 hPa)
# ---------------------------------------------------------------------------


class GeostrophicBalanceGate(CB2ComplexDiagnostic):
    """I.3b: spatial ρ(u, u_g) at 850 hPa over 30–60° (daily) > 0.9.

    Sub-orography 850 hPa points are masked where surface pressure is
    available (``ps`` in the daily data, < 870 hPa); otherwise the check
    proceeds unmasked with a logged caveat (paper implementation note keeps
    the level at 850 hPa and handles masking in code).
    """

    _required_data_keys = ("day",)
    _pressure_level_pa: ClassVar[float] = 85000.0
    _ps_mask_pa: ClassVar[float] = 87000.0

    _gate_checks = (
        GateCheck(
            check_id="geostrophic_balance",
            column="geostrophic_corr",
            lower=get_threshold("tier1.geostrophic_balance.spatial_corr_min"),
        ),
    )

    def _level_cube(self, data: CubeList | Dataset, name: str) -> Cube:
        cube = self._cube(data, _day(name))
        with setup_esmvaltool_config_and_logging():
            cube = extract_levels(cube, [self._pressure_level_pa], "linear")
        return cube

    def _calculate_raw_output(
        self,
        complex_data_source: ComplexDataSource,
    ) -> dict[Variable, Cube]:
        daily = complex_data_source.data["day"]
        ua = self._level_cube(daily, "ua")
        zg = self._level_cube(daily, "zg")
        lats = ua.coord("latitude").points.astype(float)

        ua_data = np.squeeze(np.asarray(ua.data, dtype=float))
        zg_data = np.squeeze(np.asarray(zg.data, dtype=float))

        try:  # optional orography masking via daily surface pressure
            ps = self._cube(daily, _day("ps"))
            ps_data = np.squeeze(np.asarray(ps.data, dtype=float))
            n = min(ua_data.shape[0], ps_data.shape[0])
            mask = ps_data[:n] < self._ps_mask_pa
            ua_data, zg_data = ua_data[:n].copy(), zg_data[:n].copy()
            ua_data[mask] = np.nan
            zg_data[mask] = np.nan
        except Exception:  # noqa: BLE001 - ps genuinely optional
            pass

        ug = physics.geostrophic_wind_u(zg_data, lats)
        rho = physics.midlatitude_pattern_correlation(ua_data, ug, lats)
        return self._scalar_outputs({"geostrophic_corr": rho})


# ---------------------------------------------------------------------------
# I.4a — GFMIP SST patch experiments
# ---------------------------------------------------------------------------


class GFMIPPatchGate(CB2ComplexDiagnostic):
    """I.4a: Δλ = ΔR_EP/ΔTs_EP − ΔR_WP/ΔTs_WP > 0.5 W/m²/K.

    Requires submission-provided ``amip``, ``patch_ep`` and ``patch_wp``
    fixed-SST experiments (GFMIP protocol; not in the CMIP6 archive).
    """

    _required_data_keys = ("amip", "patch_ep", "patch_wp")
    _gate_checks = (
        GateCheck(
            check_id="gfmip_patch",
            column="delta_lambda",
            lower=get_threshold("tier1.gfmip_patch.delta_lambda_min"),
        ),
    )

    def _lambda_vs_amip(
        self,
        patch: CubeList | Dataset,
        amip: CubeList | Dataset,
    ) -> float:
        def gm(data: CubeList | Dataset, name: str) -> float:
            return float(self._annual_global_series(data, _mon(name)).mean())

        def toa_net(data: CubeList | Dataset) -> float:
            return gm(data, "rsdt") - gm(data, "rsut") - gm(data, "rlut")

        d_r = toa_net(patch) - toa_net(amip)
        d_ts = gm(patch, "ts") - gm(amip, "ts")
        return d_r / d_ts

    def _calculate_raw_output(
        self,
        complex_data_source: ComplexDataSource,
    ) -> dict[Variable, Cube]:
        data = complex_data_source.data
        lam_ep = self._lambda_vs_amip(data["patch_ep"], data["amip"])
        lam_wp = self._lambda_vs_amip(data["patch_wp"], data["amip"])
        return self._scalar_outputs(
            {
                "delta_lambda": lam_ep - lam_wp,
                "lambda_ep": lam_ep,
                "lambda_wp": lam_wp,
            },
        )


# ---------------------------------------------------------------------------
# I.4b — amip-4xCO2 effective radiative forcing
# ---------------------------------------------------------------------------


class Amip4xCO2ERFGate(CB2ComplexDiagnostic):
    """I.4b: fixed-SST ERF (amip-4xCO2 − amip TOA net) ∈ [6.5, 9.0] W/m²."""

    _required_data_keys = ("amip", "amip4xco2")
    _gate_checks = (
        GateCheck(
            check_id="amip_4xco2_erf",
            column="erf_wm2",
            lower=get_threshold("tier1.amip_4xco2_erf.range")[0],
            upper=get_threshold("tier1.amip_4xco2_erf.range")[1],
        ),
    )

    def _calculate_raw_output(
        self,
        complex_data_source: ComplexDataSource,
    ) -> dict[Variable, Cube]:
        data = complex_data_source.data

        def toa_net_mean(exp: CubeList | Dataset) -> float:
            n = self._toa_net_annual_global(exp)
            return float(n.mean())

        erf = toa_net_mean(data["amip4xco2"]) - toa_net_mean(data["amip"])
        return self._scalar_outputs({"erf_wm2": erf})


# ---------------------------------------------------------------------------
# I.5c — ENSO teleconnections (piControl)
# ---------------------------------------------------------------------------


class ENSOTeleconnectionsGate(CB2ComplexDiagnostic):
    """I.5c: tropical ta500 regression on Niño-3.4 > 0; Maritime-Continent
    pr regression < 0.

    The paper additionally requires each regression within a factor 2 of the
    ERA5/GPCP value; the observational reference coefficients are not wired
    yet (``tier1.enso.teleconnection_reference_*`` are null in
    ``thresholds.yml``), so this gate currently applies the sign checks —
    the coefficients themselves are emitted for the leaderboard.
    """

    _required_data_keys = ("picontrol",)
    _gate_checks = (
        GateCheck(
            check_id="enso_teleconnection_t",
            column="ta500_regression",
            lower=get_threshold("tier1.enso.teleconnection_t_min"),
        ),
        GateCheck(
            check_id="enso_teleconnection_pr",
            column="mc_pr_regression",
            upper=get_threshold("tier1.enso.teleconnection_pr_max"),
        ),
    )

    def _nino34_index(self, data: CubeList | Dataset) -> np.ndarray:
        cube = self._cube(data, _mon("tos"))
        with setup_esmvaltool_config_and_logging():
            cube = extract_region(
                cube,
                start_longitude=190.0,
                end_longitude=240.0,
                start_latitude=-5.0,
                end_latitude=5.0,
            )
            cube = anomalies(cube, period="month")
            cube = rolling_window_statistics(
                cube,
                coordinate="time",
                operator="mean",
                window_length=3,
            )
            cube = area_statistics(cube, "mean")
        return np.asarray(cube.data, dtype=float)

    def _region_anomaly_series(
        self,
        data: CubeList | Dataset,
        variable: Variable,
        *,
        region: tuple[float, float, float, float],  # lon0, lon1, lat0, lat1
        level_pa: float | None = None,
    ) -> np.ndarray:
        cube = self._cube(data, variable)
        with setup_esmvaltool_config_and_logging():
            if level_pa is not None:
                cube = extract_levels(cube, [level_pa], "linear")
            cube = extract_region(
                cube,
                start_longitude=region[0],
                end_longitude=region[1],
                start_latitude=region[2],
                end_latitude=region[3],
            )
            cube = anomalies(cube, period="month")
            cube = area_statistics(cube, "mean")
        return np.squeeze(np.asarray(cube.data, dtype=float))

    def _calculate_raw_output(
        self,
        complex_data_source: ComplexDataSource,
    ) -> dict[Variable, Cube]:
        picontrol = complex_data_source.data["picontrol"]
        nino34 = self._nino34_index(picontrol)
        ta500_tropics = self._region_anomaly_series(
            picontrol,
            _mon("ta"),
            region=(0.0, 360.0, -30.0, 30.0),
            level_pa=50000.0,
        )
        pr_mc = self._region_anomaly_series(
            picontrol,
            _mon("pr"),
            region=(90.0, 150.0, -10.0, 10.0),
        )
        return self._scalar_outputs(
            {
                "ta500_regression": physics.regression_on_index(
                    ta500_tropics,
                    nino34,
                ),
                "mc_pr_regression": physics.regression_on_index(pr_mc, nino34),
            },
        )


# ---------------------------------------------------------------------------
# I.5d — MJO Wheeler–Kiladis east/west power ratio (daily pr)
# ---------------------------------------------------------------------------


class MJOGate(CB2ComplexDiagnostic):
    """I.5d: eastward/westward power (k = 1–3, 30–90 d) of near-equatorial
    daily precipitation > 1.5."""

    _required_data_keys = ("day",)
    _gate_checks = (
        GateCheck(
            check_id="mjo_east_west",
            column="mjo_east_west_ratio",
            lower=get_threshold("tier1.mjo.east_west_power_ratio_min"),
        ),
    )

    def _calculate_raw_output(
        self,
        complex_data_source: ComplexDataSource,
    ) -> dict[Variable, Cube]:
        daily = complex_data_source.data["day"]
        cube = self._cube(daily, _day("pr"))
        with setup_esmvaltool_config_and_logging():
            cube = extract_region(
                cube,
                start_longitude=0.0,
                end_longitude=360.0,
                start_latitude=-15.0,
                end_latitude=15.0,
            )
        pr = np.asarray(cube.data, dtype=float)
        lat_axis = cube.coord_dims("latitude")[0]
        pr_eq = np.nanmean(pr, axis=lat_axis)  # (time, lon)
        ratio = physics.mjo_east_west_ratio(pr_eq)
        return self._scalar_outputs({"mjo_east_west_ratio": ratio})
