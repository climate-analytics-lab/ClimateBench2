"""Tier I physical-consistency gates as ClimateEval complex diagnostics.

Each diagnostic loads its experiments from the data dict handed to the suite
(``{"picontrol": ..., "4xco2": ..., "histaer": ..., "historical": ...}``),
computes the paper-spec quantity (pure math in ``climatebench2.physics``),
emits it as scalar raw output, and gates it against ``thresholds.yml`` via
the ``pass_fail`` machinery (metrics rows with a ``passes`` column).

Unlike ClimateEval's ``ECS``, CB2 complex diagnostics accept a *superset* of
their required data keys, so one Tier I suite can run every gate from a
single experiment dict. Specs: docs/metrics_reference.md (section numbers on
each class).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar

import numpy as np
from esmvalcore.preprocessor import (
    annual_statistics,
    area_statistics,
    climate_statistics,
    extract_region,
    mask_landsea,
    regrid,
    zonal_statistics,
)
from iris.cube import Cube

from climateeval import Coordinate, Variable
from climateeval._config import setup_esmvaltool_config_and_logging
from climateeval._utils import get_prepared_cube
from climateeval.diags._utils import DEFAULT_GRID
from climateeval.diags.complex import ECS
from climateeval.diags.complex._base import ComplexDiagnostic

from climatebench2 import physics
from climatebench2._thresholds import get_threshold
from climatebench2.diags.pass_fail import GateCheck, GateMixin

if TYPE_CHECKING:
    from iris.cube import CubeList
    from xarray import Dataset

    from climateeval.data import ComplexDataSource


@dataclass(frozen=True)
class ScalarVariable(Variable):
    """A scalar diagnostic-output variable outside ClimateEval's registry.

    ``Variable.__post_init__`` hard-fails for names missing from
    ``variables.yml`` (ClimateEval added ``ecs``/``lambda``/… there for its
    own ECS diagnostic). CB2 gates emit many protocol-specific scalars, so
    this subclass fills the minimal metadata directly instead of requiring a
    registry entry. (Upstream-PR candidate: ad-hoc scalar outputs.)
    """

    def __post_init__(self) -> None:
        object.__setattr__(self, "long_name", self.long_name or self.var_name)
        object.__setattr__(self, "ndim", len(self.coordinates))


def _fx(name: str) -> Variable:
    """Scalar output variable."""
    return ScalarVariable(name, name, "fx")


# Standard CMIP variables absent from ClimateEval's variables.yml (as of the
# pinned commit). Defined CB2-side with full metadata; also queued as an
# upstream variables.yml addition (delineation plan §7).
_MISSING_FROM_REGISTRY: dict[str, dict[str, str]] = {
    "rsds": {
        "long_name": "Surface Downwelling Shortwave Radiation",
        "standard_name": "surface_downwelling_shortwave_flux_in_air",
    },
    "rsus": {
        "long_name": "Surface Upwelling Shortwave Radiation",
        "standard_name": "surface_upwelling_shortwave_flux_in_air",
    },
    "rlds": {
        "long_name": "Surface Downwelling Longwave Radiation",
        "standard_name": "surface_downwelling_longwave_flux_in_air",
    },
    "rlus": {
        "long_name": "Surface Upwelling Longwave Radiation",
        "standard_name": "surface_upwelling_longwave_flux_in_air",
    },
}


@dataclass(frozen=True)
class RegistryFreeVariable(Variable):
    """A monthly atmos input variable not (yet) in ClimateEval's registry."""

    def __post_init__(self) -> None:
        meta = _MISSING_FROM_REGISTRY[self.var_name]
        object.__setattr__(
            self,
            "coordinates",
            tuple(Coordinate(c) for c in ("time", "lat", "lon")),
        )
        object.__setattr__(self, "units", self.units or "W m-2")
        object.__setattr__(self, "long_name", meta["long_name"])
        object.__setattr__(self, "standard_name", meta["standard_name"])
        object.__setattr__(self, "realm", "atmos")
        object.__setattr__(self, "cmip6_table_id", "Amon")
        object.__setattr__(self, "ndim", len(self.coordinates))


def _mon(name: str) -> Variable:
    """Monthly input variable (registry first, CB2 fallback for gaps)."""
    if name in _MISSING_FROM_REGISTRY:
        return RegistryFreeVariable(name, name, "mon")
    return Variable(name, name, "mon")


class CB2ComplexDiagnostic(GateMixin, ComplexDiagnostic):
    """Base for the Tier I gates: superset data keys + esmvalcore helpers."""

    def _check_required_dict_keys(self, dict_: dict[str, Any], dict_name: str) -> None:
        """Require a *subset* match so one suite dict feeds every gate."""
        missing = set(self._required_data_keys) - set(dict_)
        if missing:
            msg = (
                f"Missing keys {sorted(missing)} for {dict_name} dictionary of "
                f"diagnostic '{self.name}' (required: {self._required_data_keys})"
            )
            raise ValueError(msg)

    # -- preprocessing helpers (all regrid to the common 2x2 grid first) ----

    def _cube(
        self,
        data: CubeList | Dataset,
        variable: Variable,
    ) -> Cube:
        cube = get_prepared_cube(data, variable)
        with setup_esmvaltool_config_and_logging():
            cube = regrid(cube, DEFAULT_GRID, "linear", cache_weights=True)
        return cube

    def _annual_global_series(
        self,
        data: CubeList | Dataset,
        variable: Variable,
    ) -> np.ndarray:
        cube = self._cube(data, variable)
        with setup_esmvaltool_config_and_logging():
            cube = area_statistics(cube, "mean")
            cube = annual_statistics(cube, "mean")
        return np.asarray(cube.data, dtype=float)

    def _monthly_global_series(
        self,
        data: CubeList | Dataset,
        variable: Variable,
    ) -> np.ndarray:
        cube = self._cube(data, variable)
        with setup_esmvaltool_config_and_logging():
            cube = area_statistics(cube, "mean")
        return np.asarray(cube.data, dtype=float)

    def _toa_net_annual_global(self, data: CubeList | Dataset) -> np.ndarray:
        rsdt = self._annual_global_series(data, _mon("rsdt"))
        rsut = self._annual_global_series(data, _mon("rsut"))
        rlut = self._annual_global_series(data, _mon("rlut"))
        n = min(rsdt.size, rsut.size, rlut.size)
        return rsdt[:n] - rsut[:n] - rlut[:n]

    def _timemean_zonal(
        self,
        data: CubeList | Dataset,
        variable: Variable,
    ) -> tuple[np.ndarray, np.ndarray]:
        """(zonal-mean time-mean profile, latitudes)."""
        cube = self._cube(data, variable)
        with setup_esmvaltool_config_and_logging():
            cube = climate_statistics(cube, "mean", "full")
            cube = zonal_statistics(cube, "mean")
        return (
            np.asarray(cube.data, dtype=float),
            cube.coord("latitude").points.astype(float),
        )

    def _scalar_outputs(self, values: dict[str, float]) -> dict[Variable, Cube]:
        return {
            _fx(name): Cube(np.float64(value), var_name=name)
            for name, value in values.items()
        }

    # -- flux profiles shared by MHT / Bjerknes / ITCZ-EFE ------------------

    _SFC_FLUXES: ClassVar[tuple[tuple[str, float], ...]] = (
        # (variable, sign in F_sfc = net downward surface flux)
        ("rsds", +1.0),
        ("rsus", -1.0),
        ("rlds", +1.0),
        ("rlus", -1.0),
        ("hfss", -1.0),
        ("hfls", -1.0),
    )

    def _transport_profiles(
        self,
        data: CubeList | Dataset,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """(AMET, OMET, lats) in W from time-mean zonal-mean fluxes (I.8a)."""
        toa_parts = {
            name: self._timemean_zonal(data, _mon(name))
            for name in ("rsdt", "rsut", "rlut")
        }
        lats = next(iter(toa_parts.values()))[1]
        toa_net = toa_parts["rsdt"][0] - toa_parts["rsut"][0] - toa_parts["rlut"][0]
        f_sfc = np.zeros_like(toa_net)
        for name, sign in self._SFC_FLUXES:
            f_sfc = f_sfc + sign * self._timemean_zonal(data, _mon(name))[0]
        amet = physics.meridional_transport(toa_net - f_sfc, lats)
        omet = physics.meridional_transport(f_sfc, lats)
        return amet, omet, lats


# ---------------------------------------------------------------------------
# I.6c — ECS gate (superset-tolerant wrapper of ClimateEval's ECS)
# ---------------------------------------------------------------------------


def _subset_keys_check(
    diag: ComplexDiagnostic,
    dict_: dict[str, Any],
    dict_name: str,
) -> None:
    missing = set(diag._required_data_keys) - set(dict_)
    if missing:
        msg = f"Missing keys {sorted(missing)} for {dict_name} dictionary"
        raise ValueError(msg)


class ECSGate(GateMixin, ECS):
    """I.6c: ECS (Gregory, 150 yr) ∈ tier1.ecs.range = [1, 7] K."""

    _gate_checks = (
        GateCheck(
            check_id="ecs_gate",
            column="ecs",
            lower=get_threshold("tier1.ecs.range")[0],
            upper=get_threshold("tier1.ecs.range")[1],
        ),
    )

    def _check_required_dict_keys(self, dict_: dict[str, Any], dict_name: str) -> None:
        _subset_keys_check(self, dict_, dict_name)


# ---------------------------------------------------------------------------
# I.1 — Energy balance closure (piControl)
# ---------------------------------------------------------------------------


class EnergyBalanceGate(CB2ComplexDiagnostic):
    """I.1: |μ(N)| < 0.1 W/m² and 10-yr-running-mean drift < 0.02 W/m²/dec."""

    _required_data_keys = ("picontrol",)
    _gate_checks = (
        GateCheck(
            check_id="energy_balance_mean",
            column="toa_net_mean_abs",
            upper=get_threshold("tier1.energy_balance.mean_toa_net_abs_max"),
        ),
        GateCheck(
            check_id="energy_balance_drift",
            column="toa_net_drift_abs",
            upper=get_threshold("tier1.energy_balance.drift_10yr_running_abs_max"),
        ),
    )

    def _calculate_raw_output(
        self,
        complex_data_source: ComplexDataSource,
    ) -> dict[Variable, Cube]:
        picontrol = complex_data_source.data["picontrol"]
        n = self._toa_net_annual_global(picontrol)
        return self._scalar_outputs(
            {
                "toa_net_mean_abs": abs(float(n.mean())),
                "toa_net_drift_abs": abs(physics.running_mean_drift(n)),
                "n_years": float(n.size),
            },
        )


# ---------------------------------------------------------------------------
# I.2 — Closure constraints (piControl)
# ---------------------------------------------------------------------------


class ClosureGate(CB2ComplexDiagnostic):
    """I.2a/b: water budget < 0.05 mm/day; atm energy budget < 2 W/m²."""

    _required_data_keys = ("picontrol",)
    _gate_checks = (
        GateCheck(
            check_id="water_budget",
            column="water_budget_residual_mmday",
            upper=get_threshold("tier1.water_budget.p_minus_e_abs_max"),
        ),
        GateCheck(
            check_id="atm_energy_budget",
            column="atm_energy_residual_wm2",
            upper=get_threshold("tier1.atm_energy_budget.residual_abs_max"),
        ),
    )

    def _calculate_raw_output(
        self,
        complex_data_source: ComplexDataSource,
    ) -> dict[Variable, Cube]:
        picontrol = complex_data_source.data["picontrol"]
        means = {
            name: float(self._annual_global_series(picontrol, _mon(name)).mean())
            for name in (
                "pr",
                "hfls",
                "hfss",
                "rsdt",
                "rsut",
                "rlut",
                "rsds",
                "rsus",
                "rlds",
                "rlus",
            )
        }
        toa_net = means["rsdt"] - means["rsut"] - means["rlut"]
        sfc_net_rad = (
            means["rsds"] - means["rsus"] + means["rlds"] - means["rlus"]
        )
        return self._scalar_outputs(
            {
                "water_budget_residual_mmday": physics.water_budget_residual(
                    means["pr"],
                    means["hfls"],
                ),
                "atm_energy_residual_wm2": physics.atmospheric_energy_residual(
                    means["pr"],
                    toa_net,
                    sfc_net_rad,
                    means["hfss"],
                ),
            },
        )


# ---------------------------------------------------------------------------
# I.3a — Clear-sky longwave feedback (historical)
# ---------------------------------------------------------------------------


class ClearSkyFeedbackGate(CB2ComplexDiagnostic):
    """I.3a: area-mean gridpoint ∂rlutcs/∂Ts within ±25% of 2.2 W/m²/K."""

    _required_data_keys = ("historical",)

    _reference = float(get_threshold("tier1.clear_sky_lw_feedback.reference"))
    _tolerance = float(get_threshold("tier1.clear_sky_lw_feedback.rel_tolerance"))
    _gate_checks = (
        GateCheck(
            check_id="clear_sky_lw_feedback",
            column="clear_sky_lw_beta",
            lower=_reference * (1.0 - _tolerance),
            upper=_reference * (1.0 + _tolerance),
        ),
    )

    def _calculate_raw_output(
        self,
        complex_data_source: ComplexDataSource,
    ) -> dict[Variable, Cube]:
        historical = complex_data_source.data["historical"]
        rlutcs = self._cube(historical, _mon("rlutcs"))
        ts = self._cube(historical, _mon("ts"))
        with setup_esmvaltool_config_and_logging():
            rlutcs = annual_statistics(rlutcs, "mean")
            ts = annual_statistics(ts, "mean")
        n = min(rlutcs.shape[0], ts.shape[0])
        beta_field = physics.gridpoint_regression_slope(
            np.asarray(rlutcs.data[:n], dtype=float),
            np.asarray(ts.data[:n], dtype=float),
        )
        beta = physics.area_weighted_mean(
            beta_field,
            rlutcs.coord("latitude").points.astype(float),
        )
        return self._scalar_outputs({"clear_sky_lw_beta": beta})


# ---------------------------------------------------------------------------
# I.6a/b — Land–ocean warming ratio & Arctic amplification (a4x vs piControl)
# ---------------------------------------------------------------------------


class _WarmingResponseGate(CB2ComplexDiagnostic):
    """Shared machinery: equilibrium a4x anomaly vs the piControl mean."""

    _required_data_keys = ("picontrol", "4xco2")

    @property
    def _equilibrium_years(self) -> int:
        raise NotImplementedError

    def _domain_mean_anomaly(
        self,
        complex_data_source: ComplexDataSource,
        *,
        region: tuple[float, float] | None = None,
        mask_out: str | None = None,
    ) -> float:
        """a4x (last N yr) minus piControl (full) domain-mean tas."""

        def domain_series(data: CubeList | Dataset) -> np.ndarray:
            cube = self._cube(data, _mon("tas"))
            with setup_esmvaltool_config_and_logging():
                if region is not None:
                    cube = extract_region(
                        cube,
                        start_longitude=0.0,
                        end_longitude=360.0,
                        start_latitude=region[0],
                        end_latitude=region[1],
                    )
                if mask_out is not None:
                    cube = mask_landsea(cube, mask_out)
                cube = area_statistics(cube, "mean")
                cube = annual_statistics(cube, "mean")
            return np.asarray(cube.data, dtype=float)

        a4x = domain_series(complex_data_source.data["4xco2"])
        picontrol = domain_series(complex_data_source.data["picontrol"])
        n_eq = self._equilibrium_years
        return float(a4x[-n_eq:].mean() - picontrol.mean())


class LandOceanWarmingGate(_WarmingResponseGate):
    """I.6a: ΔT_land/ΔT_ocean > 1 required; expected range [1.2, 1.6]."""

    _gate_checks = (
        GateCheck(
            check_id="land_ocean_warming_required",
            column="land_ocean_warming_ratio",
            lower=get_threshold("tier1.land_ocean_warming.required_min"),
        ),
        GateCheck(
            check_id="land_ocean_warming_expected",
            column="land_ocean_warming_ratio",
            lower=get_threshold("tier1.land_ocean_warming.expected_range")[0],
            upper=get_threshold("tier1.land_ocean_warming.expected_range")[1],
        ),
    )

    @property
    def _equilibrium_years(self) -> int:
        return int(get_threshold("tier1.land_ocean_warming.equilibrium_years"))

    def _calculate_raw_output(
        self,
        complex_data_source: ComplexDataSource,
    ) -> dict[Variable, Cube]:
        dt_land = self._domain_mean_anomaly(complex_data_source, mask_out="sea")
        dt_ocean = self._domain_mean_anomaly(complex_data_source, mask_out="land")
        return self._scalar_outputs(
            {
                "land_ocean_warming_ratio": dt_land / dt_ocean,
                "delta_t_land": dt_land,
                "delta_t_ocean": dt_ocean,
            },
        )


class ArcticAmplificationGate(_WarmingResponseGate):
    """I.6b: ΔT(>66.5N)/ΔT(global) ≥ 1.5."""

    _gate_checks = (
        GateCheck(
            check_id="arctic_amplification",
            column="arctic_amplification_ratio",
            lower=get_threshold("tier1.arctic_amplification.ratio_min"),
        ),
    )

    @property
    def _equilibrium_years(self) -> int:
        return int(get_threshold("tier1.arctic_amplification.equilibrium_years"))

    def _calculate_raw_output(
        self,
        complex_data_source: ComplexDataSource,
    ) -> dict[Variable, Cube]:
        lat_min = float(get_threshold("tier1.arctic_amplification.lat_min"))
        dt_arctic = self._domain_mean_anomaly(
            complex_data_source,
            region=(lat_min, 90.0),
        )
        dt_global = self._domain_mean_anomaly(complex_data_source)
        return self._scalar_outputs(
            {
                "arctic_amplification_ratio": dt_arctic / dt_global,
                "delta_t_arctic": dt_arctic,
                "delta_t_global": dt_global,
            },
        )


# ---------------------------------------------------------------------------
# I.7 — Aerosol forcing (DAMIP hist-aer)
# ---------------------------------------------------------------------------


class AerosolForcingGate(CB2ComplexDiagnostic):
    """I.7: aerosol ERF ∈ [−2.0, −0.5] W/m² and end-of-record cooling."""

    _required_data_keys = ("picontrol", "4xco2", "histaer")
    _end_period_years: ClassVar[int] = 30

    _gate_checks = (
        GateCheck(
            check_id="aerosol_erf",
            column="aerosol_erf_wm2",
            lower=get_threshold("tier1.aerosol_forcing.erf_range")[0],
            upper=get_threshold("tier1.aerosol_forcing.erf_range")[1],
        ),
        GateCheck(
            check_id="aerosol_cooling",
            column="delta_t_end",
            upper=0.0,
        ),
    )

    def _calculate_raw_output(
        self,
        complex_data_source: ComplexDataSource,
    ) -> dict[Variable, Cube]:
        data = complex_data_source.data
        n_years_ecs = int(get_threshold("tier1.ecs.n_years"))

        pi_tas = self._annual_global_series(data["picontrol"], _mon("tas"))
        pi_n = self._toa_net_annual_global(data["picontrol"])

        a4x_tas = self._annual_global_series(data["4xco2"], _mon("tas"))
        a4x_n = self._toa_net_annual_global(data["4xco2"])
        n = min(a4x_tas.size, a4x_n.size, n_years_ecs)
        lambda_4x, _f4x, _r2 = physics.gregory_regression(
            a4x_tas[:n] - pi_tas.mean(),
            a4x_n[:n] - pi_n.mean(),
        )

        aer_tas = self._annual_global_series(data["histaer"], _mon("tas"))
        aer_n = self._toa_net_annual_global(data["histaer"])
        end = self._end_period_years
        dt_end = float(aer_tas[-end:].mean() - pi_tas.mean())
        dn_end = float(aer_n[-end:].mean() - pi_n.mean())

        return self._scalar_outputs(
            {
                "aerosol_erf_wm2": physics.aerosol_erf(dn_end, dt_end, lambda_4x),
                "delta_t_end": dt_end,
                "lambda_4x": lambda_4x,
            },
        )


# ---------------------------------------------------------------------------
# I.8a — Meridional heat transport partitioning (piControl)
# ---------------------------------------------------------------------------


class MeridionalHeatTransportGate(CB2ComplexDiagnostic):
    """I.8a: OMET peak 1.5–2.0 PW near 15–20N; AMET peak 4–5 PW near 45N."""

    _required_data_keys = ("picontrol",)

    _omet_lat = get_threshold("tier1.meridional_heat_transport.omet_peak_lat_range")
    _amet_lat_ref = float(get_threshold("tier1.meridional_heat_transport.amet_peak_lat"))
    _amet_lat_tol = float(
        get_threshold("tier1.meridional_heat_transport.amet_peak_lat_tolerance"),
    )
    _gate_checks = (
        GateCheck(
            check_id="omet_peak",
            column="omet_peak_pw",
            lower=get_threshold("tier1.meridional_heat_transport.omet_peak_range")[0],
            upper=get_threshold("tier1.meridional_heat_transport.omet_peak_range")[1],
        ),
        GateCheck(
            check_id="omet_peak_lat",
            column="omet_peak_lat",
            lower=float(_omet_lat[0]),
            upper=float(_omet_lat[1]),
        ),
        GateCheck(
            check_id="amet_peak",
            column="amet_peak_pw",
            lower=get_threshold("tier1.meridional_heat_transport.amet_peak_range")[0],
            upper=get_threshold("tier1.meridional_heat_transport.amet_peak_range")[1],
        ),
        GateCheck(
            check_id="amet_peak_lat",
            column="amet_peak_lat",
            lower=_amet_lat_ref - _amet_lat_tol,
            upper=_amet_lat_ref + _amet_lat_tol,
        ),
    )

    def _calculate_raw_output(
        self,
        complex_data_source: ComplexDataSource,
    ) -> dict[Variable, Cube]:
        amet, omet, lats = self._transport_profiles(
            complex_data_source.data["picontrol"],
        )
        omet_peak, omet_lat = physics.nh_peak(omet / 1e15, lats, 5.0, 30.0)
        amet_peak, amet_lat = physics.nh_peak(amet / 1e15, lats, 25.0, 55.0)
        return self._scalar_outputs(
            {
                "omet_peak_pw": omet_peak,
                "omet_peak_lat": omet_lat,
                "amet_peak_pw": amet_peak,
                "amet_peak_lat": amet_lat,
            },
        )


# ---------------------------------------------------------------------------
# I.8b — ITCZ–EFE relationship (historical, 12-month climatology)
# ---------------------------------------------------------------------------


class ITCZEFEGate(CB2ComplexDiagnostic):
    """I.8b: ITCZ-lat-vs-F_xeq slope within ±50% of 3°/PW and |r| > 0.9.

    Uses the 12-month climatology (paper spec; the retired script used every
    monthly timestep and carried a hard-coded array-length bug).
    """

    _required_data_keys = ("historical",)

    _slope_ref = float(get_threshold("tier1.itcz_efe.slope_reference"))
    _slope_tol = float(get_threshold("tier1.itcz_efe.slope_rel_tolerance"))
    _gate_checks = (
        GateCheck(
            check_id="itcz_efe_slope",
            column="itcz_efe_slope_abs",
            lower=_slope_ref * (1.0 - _slope_tol),
            upper=_slope_ref * (1.0 + _slope_tol),
        ),
        GateCheck(
            check_id="itcz_efe_correlation",
            column="itcz_efe_r_abs",
            lower=get_threshold("tier1.itcz_efe.corr_min"),
        ),
    )

    def _monthly_clim_zonal(
        self,
        data: CubeList | Dataset,
        variable: Variable,
    ) -> tuple[np.ndarray, np.ndarray]:
        """(12, lat) climatological zonal means."""
        cube = self._cube(data, variable)
        with setup_esmvaltool_config_and_logging():
            cube = climate_statistics(cube, "mean", "month")
            cube = zonal_statistics(cube, "mean")
        return (
            np.asarray(cube.data, dtype=float),
            cube.coord("latitude").points.astype(float),
        )

    def _calculate_raw_output(
        self,
        complex_data_source: ComplexDataSource,
    ) -> dict[Variable, Cube]:
        historical = complex_data_source.data["historical"]

        parts = {
            name: self._monthly_clim_zonal(historical, _mon(name))
            for name in ("rsdt", "rsut", "rlut")
        }
        lats = next(iter(parts.values()))[1]
        toa_net = parts["rsdt"][0] - parts["rsut"][0] - parts["rlut"][0]
        f_sfc = np.zeros_like(toa_net)
        for name, sign in self._SFC_FLUXES:
            f_sfc = f_sfc + sign * self._monthly_clim_zonal(historical, _mon(name))[0]
        div_a = toa_net - f_sfc  # (12, lat)

        pr_clim, pr_lats = self._monthly_clim_zonal(historical, _mon("pr"))
        tropics = (pr_lats >= -30.0) & (pr_lats <= 30.0)

        itcz_lats = np.empty(12)
        f_xeq_pw = np.empty(12)
        for month in range(12):
            amet = physics.meridional_transport(div_a[month], lats)
            f_xeq_pw[month] = np.interp(0.0, lats, amet) / 1e15
            pr_band = pr_clim[month][tropics]
            itcz_lats[month] = float(pr_lats[tropics][np.argmax(pr_band)])

        slope, r = physics.itcz_efe_regression(itcz_lats, f_xeq_pw)
        return self._scalar_outputs(
            {
                "itcz_efe_slope_abs": abs(slope),
                "itcz_efe_r_abs": abs(r),
                "itcz_efe_slope": slope,
            },
        )


# ---------------------------------------------------------------------------
# Extras (code-only, pending paper reconciliation)
# ---------------------------------------------------------------------------


class BjerknesGate(CB2ComplexDiagnostic):
    """Extra: decadal AMET–OMET anti-correlation at 40–70N (r < −0.3)."""

    _required_data_keys = ("picontrol",)
    _band: ClassVar[tuple[float, float]] = (40.0, 70.0)

    _gate_checks = (
        GateCheck(
            check_id="bjerknes_compensation",
            column="bjerknes_r",
            upper=get_threshold("tier1.bjerknes.corr_max"),
        ),
    )

    def _band_transport_series(
        self,
        data: CubeList | Dataset,
    ) -> tuple[np.ndarray, np.ndarray]:
        """Monthly 40–70N band-mean AMET and OMET series."""
        monthly_zonal: dict[str, np.ndarray] = {}
        lats: np.ndarray | None = None
        for name in ("rsdt", "rsut", "rlut", *(n for n, _ in self._SFC_FLUXES)):
            cube = self._cube(data, _mon(name))
            with setup_esmvaltool_config_and_logging():
                cube = zonal_statistics(cube, "mean")
            monthly_zonal[name] = np.asarray(cube.data, dtype=float)  # (t, lat)
            lats = cube.coord("latitude").points.astype(float)
        assert lats is not None
        toa_net = (
            monthly_zonal["rsdt"] - monthly_zonal["rsut"] - monthly_zonal["rlut"]
        )
        f_sfc = np.zeros_like(toa_net)
        for name, sign in self._SFC_FLUXES:
            f_sfc = f_sfc + sign * monthly_zonal[name]
        band = (lats >= self._band[0]) & (lats <= self._band[1])
        n_time = toa_net.shape[0]
        amet = np.empty(n_time)
        omet = np.empty(n_time)
        for t in range(n_time):
            amet[t] = physics.meridional_transport(toa_net[t] - f_sfc[t], lats)[
                band
            ].mean()
            omet[t] = physics.meridional_transport(f_sfc[t], lats)[band].mean()
        return amet, omet

    def _calculate_raw_output(
        self,
        complex_data_source: ComplexDataSource,
    ) -> dict[Variable, Cube]:
        amet, omet = self._band_transport_series(complex_data_source.data["picontrol"])
        r = physics.bjerknes_correlation(amet, omet)
        return self._scalar_outputs({"bjerknes_r": r})


class CCScalingGate(CB2ComplexDiagnostic):
    """Extra: Clausius–Clapeyron scaling Δprw vs Δtas slope in 7 ± 2 %/K."""

    _required_data_keys = ("picontrol",)
    _gate_checks = (
        GateCheck(
            check_id="cc_scaling",
            column="cc_scaling_slope",
            lower=get_threshold("tier1.cc_scaling.slope_range")[0],
            upper=get_threshold("tier1.cc_scaling.slope_range")[1],
        ),
    )

    def _calculate_raw_output(
        self,
        complex_data_source: ComplexDataSource,
    ) -> dict[Variable, Cube]:
        picontrol = complex_data_source.data["picontrol"]
        prw = self._annual_global_series(picontrol, _mon("prw"))
        tas = self._annual_global_series(picontrol, _mon("tas"))
        n = min(prw.size, tas.size)
        return self._scalar_outputs(
            {"cc_scaling_slope": physics.cc_scaling_slope(prw[:n], tas[:n])},
        )
