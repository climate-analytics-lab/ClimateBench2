"""Extended Tier I gates: causal-response, daily-data and pattern checks.

Phase 4, plus I.3c and the I.5c rewrite of work package 5.

Previously entirely missing from the protocol implementation
(metrics_reference.md status ❌): geostrophic balance (I.3b),
precipitation–buoyancy (I.3c), GFMIP patch Δλ (I.4a), amip-4xCO2 ERF (I.4b),
ENSO teleconnections (I.5c), MJO Wheeler–Kiladis (I.5d).

Data keys (superset semantics as in ``tier1_physics``):

- ``day`` — daily-frequency output (ua/zg for I.3b, pr for I.5d)
- ``historical`` — the coupled historical run for I.3c
- ``amip`` / ``amip4xco2`` — fixed-SST runs for I.4b
- ``amip`` / ``patch_ep`` / ``patch_wp`` — GFMIP patch runs for I.4a
- ``picontrol`` — coupled control for I.5c

I.3c and I.5c are the only Tier I gates that need **observations**; they take
them through ClimateEval DataSources (GPCP, HadISST, ERA5) over a
satellite-era window from ``thresholds.yml``, and degrade to reporting the
model's own statistic — no gate row, a logged reason — when those data cannot
be fetched and ``fail_on_missing_data`` is False.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

import numpy as np
from esmvalcore.preprocessor import (
    anomalies,
    area_statistics,
    extract_levels,
    extract_region,
)
from loguru import logger

from climateeval import Variable
from climateeval._config import setup_esmvaltool_config_and_logging
from climateeval.data import GPCP, ERA5Monthly, HadISST

from climatebench2 import physics, windows
from climatebench2._thresholds import get_threshold
from climatebench2.diags.pass_fail import GateCheck, gate_requirement, gate_tier
from climatebench2.diags.tier1_physics import (
    CB2ComplexDiagnostic,
    _cube_years_months,
    _filled,
    _mon,
)

if TYPE_CHECKING:
    from iris.cube import Cube, CubeList
    from xarray import Dataset

    from climateeval.data import ComplexDataSource, DataSource


def _day(name: str) -> Variable:
    """Daily input variable."""
    return Variable(name, name, "day")


def _time_keys(cube: Cube) -> np.ndarray:
    """One hashable key per time step, comparable across calendars."""
    coord = cube.coord("time")
    dates = coord.units.num2date(coord.points)
    return np.array(
        [d.year * 10000 + d.month * 100 + d.day for d in dates],
        dtype=np.int64,
    )


def align_on_common_days(*cubes: Cube) -> list[Cube]:
    """Cut every cube to the calendar days all of them have.

    CMIP6 does not publish a model's daily variables over the same period:
    CNRM-CM6-1 has ``day ua`` for 1990-2014 but ``day zg`` only for 2000-2014,
    which made the geostrophic-balance gate try to correlate a 25-year field
    with a 15-year one. Aligning on the leading axis by length would silently
    pair 1990 winds with 2000 heights, so the alignment is by **date**.
    """
    keys = [_time_keys(cube) for cube in cubes]
    common = keys[0]
    for other in keys[1:]:
        common = np.intersect1d(common, other)
    if common.size == 0:
        msg = "The daily variables share no calendar day"
        raise ValueError(msg)
    aligned: list[Cube] = []
    for cube, key in zip(cubes, keys, strict=True):
        if key.size == common.size and np.array_equal(key, common):
            aligned.append(cube)
            continue
        index = np.flatnonzero(np.isin(key, common))
        time_axis = cube.coord_dims("time")[0]
        slicer: list[slice | np.ndarray] = [slice(None)] * cube.ndim
        slicer[time_axis] = index
        aligned.append(cube[tuple(slicer)])
    return aligned


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
            requirement=gate_requirement("tier1.geostrophic_balance"),
            tier=gate_tier("tier1.geostrophic_balance"),
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
        # The two are rarely published over the same period, so pair them by
        # date rather than by position (see `align_on_common_days`).
        ua, zg = align_on_common_days(ua, zg)
        lats = ua.coord("latitude").points.astype(float)

        # `_filled`, never `np.asarray`: CMIP6 publishes `ua`/`zg` on a
        # pressure level that intersects orography as a **masked** array, and
        # `np.asarray` exposes the 1e20 fill value under the mask instead of
        # dropping the point. On CNRM-CM6-1 (6% of the 850 hPa field is
        # sub-surface) that alone drove ρ from 0.99 to 0.09.
        ua_data = np.squeeze(_filled(ua.data))
        zg_data = np.squeeze(_filled(zg.data))

        try:  # optional orography masking via daily surface pressure
            ps = self._cube(daily, _day("ps"))
            ua_ps, zg_ps, ps = align_on_common_days(ua, zg, ps)
            ps_data = np.squeeze(_filled(ps.data))
            ua_data = np.squeeze(_filled(ua_ps.data)).copy()
            zg_data = np.squeeze(_filled(zg_ps.data)).copy()
            mask = ps_data < self._ps_mask_pa
            ua_data[mask] = np.nan
            zg_data[mask] = np.nan
        except Exception as exc:  # noqa: BLE001 - ps genuinely optional
            logger.warning(
                f"Diagnostic '{self.name}': no daily 'ps' to mask sub-surface "
                f"850 hPa points with ({type(exc).__name__}: {exc}); the "
                f"correlation uses whatever the model published there",
            )

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
            requirement=gate_requirement("tier1.gfmip_patch"),
            tier=gate_tier("tier1.gfmip_patch"),
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
            requirement=gate_requirement("tier1.amip_4xco2_erf"),
            tier=gate_tier("tier1.amip_4xco2_erf"),
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
    """I.5c: modelled vs observed ENSO teleconnection *patterns*, 30S–30N.

    The paper's 2026-09 criterion (which superseded the scalar ta500 /
    Maritime-Continent sign checks this class used to implement): regress
    monthly anomalies of surface temperature and of precipitation on the
    **standardized** Niño-3.4 index at every grid point over 30S–30N, do the
    same for the observations, and gate the **centred, cos-weighted spatial
    correlation** of the two regression patterns at
    ``tier1.enso.teleconnection_pattern_corr_min`` (0.7, i.e. spatial
    R² > 0.5) — one gate row per field.

    Model patterns come from the piControl run (the ≥ 100 yr control of I.5,
    with the same *unsmoothed* index definition as I.5a/b); the observed ones
    from ClimateEval DataSources over
    ``tier1.enso.teleconnection_obs_window`` (1979–2014: GPCP begins in 1979,
    and the protocol never touches the reserved post-2015 window).

    Reference products: **HadISST** ``tos`` for temperature and **GPCP**
    ``pr`` for precipitation, with the observed index taken from HadISST so
    both observed patterns are regressed on one index. HadISST being SST-only,
    its pattern is missing over land; the pattern correlation drops non-finite
    pairs, which masks the model's ``ts`` to the same ocean points. (ERA5 is
    the paper's other temperature option but ClimateEval's
    ``ERA5.VARIABLE_MAPPING`` has no ``ts``/skin temperature — an upstream
    gap, see docs/metrics_reference.md I.5c.)

    When the observations cannot be fetched (no network or CDS credentials)
    and ``fail_on_missing_data`` is False, the model's own pattern summary is
    emitted, the reason is logged and **no gate row is written** — the same
    "not run" state the scorecard already renders as a hole.
    """

    _required_data_keys = ("picontrol",)

    #: 30S–30N (paper: extratropical teleconnections are explicitly not gated).
    _band: ClassVar[tuple[float, float]] = (-30.0, 30.0)
    #: Niño-3.4 box (lon0, lon1, lat0, lat1), as in ClimateEval's ``Nino34``.
    _nino34_region: ClassVar[tuple[float, float, float, float]] = (
        190.0,
        240.0,
        -5.0,
        5.0,
    )
    #: Fewest common months a regression pattern is computed from.
    _min_months: ClassVar[int] = 24

    #: Observational references, as classes so a test can substitute them.
    _ts_reference: ClassVar[type[DataSource]] = HadISST
    _pr_reference: ClassVar[type[DataSource]] = GPCP

    _corr_min = get_threshold("tier1.enso.teleconnection_pattern_corr_min")
    _gate_checks = (
        GateCheck(
            check_id="enso_teleconnection_ts",
            column="teleconnection_corr_ts",
            lower=_corr_min,
            requirement=gate_requirement("tier1.enso"),
            tier=gate_tier("tier1.enso"),
        ),
        GateCheck(
            check_id="enso_teleconnection_pr",
            column="teleconnection_corr_pr",
            lower=_corr_min,
            requirement=gate_requirement("tier1.enso"),
            tier=gate_tier("tier1.enso"),
        ),
    )

    # -- the pieces of one regression pattern -------------------------------

    @staticmethod
    def _time_keys(cube: Cube) -> np.ndarray:
        """``year·12 + month`` of every step, for aligning two products."""
        years, months = _cube_years_months(cube)
        return years * 12 + months

    def _nino34_index(self, sst: Cube) -> tuple[np.ndarray, np.ndarray]:
        """(standardized unsmoothed Niño-3.4 index, its time keys).

        The I.5a definition without the operational 3-month running mean
        (``ENSOGate._rolling_window_length = 1``), then standardised so the
        regression slopes are "per σ of Niño-3.4" and comparable between a
        model and the observations.
        """
        lon0, lon1, lat0, lat1 = self._nino34_region
        with setup_esmvaltool_config_and_logging():
            cube = extract_region(
                sst,
                start_longitude=lon0,
                end_longitude=lon1,
                start_latitude=lat0,
                end_latitude=lat1,
            )
            cube = anomalies(cube, period="month")
            cube = area_statistics(cube, "mean")
        return physics.standardised(_filled(cube.data)), self._time_keys(cube)

    def _tropical_anomalies(
        self,
        cube: Cube,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """(monthly anomalies over the band, latitudes, time keys)."""
        with setup_esmvaltool_config_and_logging():
            cube = extract_region(
                cube,
                start_longitude=0.0,
                end_longitude=360.0,
                start_latitude=self._band[0],
                end_latitude=self._band[1],
            )
            cube = anomalies(cube, period="month")
        return (
            _filled(cube.data),
            cube.coord("latitude").points.astype(float),
            self._time_keys(cube),
        )

    def _pattern(
        self,
        field: np.ndarray,
        field_keys: np.ndarray,
        index: np.ndarray,
        index_keys: np.ndarray,
    ) -> np.ndarray | None:
        """Per-gridpoint slope of ``field`` on the index, on common months."""
        common = np.intersect1d(field_keys, index_keys)
        if common.size < self._min_months:
            logger.warning(
                f"Diagnostic '{self.name}': only {common.size} months shared "
                f"between the field and the Niño-3.4 index (need "
                f"{self._min_months}); no regression pattern",
            )
            return None
        y = field[np.isin(field_keys, common)]
        x = index[np.isin(index_keys, common)]
        return physics.gridpoint_regression_slope(y, x[:, None, None])

    # -- model and observations --------------------------------------------

    def _model_patterns(
        self,
        data: CubeList | Dataset,
    ) -> tuple[dict[str, np.ndarray | None], np.ndarray, float]:
        """({field: pattern}, latitudes, σ(Niño-3.4)) from the piControl run."""
        sst = self._cube(data, _mon("tos"))
        index, index_keys = self._nino34_index(sst)
        patterns: dict[str, np.ndarray | None] = {}
        lats = np.array([])
        for name in ("ts", "pr"):
            field, lats, keys = self._tropical_anomalies(self._cube(data, _mon(name)))
            patterns[name] = self._pattern(field, keys, index, index_keys)
        # σ of the raw index: the standardisation above divides it out
        raw = self._nino34_raw_sigma(sst)
        return patterns, lats, raw

    def _nino34_raw_sigma(self, sst: Cube) -> float:
        """σ(Niño-3.4) in K — the I.5a statistic, reported for context."""
        lon0, lon1, lat0, lat1 = self._nino34_region
        with setup_esmvaltool_config_and_logging():
            cube = extract_region(
                sst,
                start_longitude=lon0,
                end_longitude=lon1,
                start_latitude=lat0,
                end_latitude=lat1,
            )
            cube = anomalies(cube, period="month")
            cube = area_statistics(cube, "mean")
        return float(np.nanstd(_filled(cube.data), ddof=1))

    def _observation_cube(self, source: type[DataSource], var_name: str) -> Cube:
        """One observational field over the protocol's satellite-era window."""
        first, last = get_threshold("tier1.enso.teleconnection_obs_window")
        variable = Variable(
            var_name,
            var_name,
            "mon",
            timerange=windows.timerange(int(first), int(last)),
        )
        return source().get_cube(
            self.data_root_dir,
            variable,
            download_missing_data=self._download_missing_data,
        )

    def _observed_patterns(self) -> dict[str, np.ndarray | None]:
        """{field: observed regression pattern} on the common 2° grid."""
        sst = self._regridded(self._observation_cube(self._ts_reference, "tos"))
        index, index_keys = self._nino34_index(sst)
        ts_field, _lats, ts_keys = self._tropical_anomalies(sst)
        precip = self._regridded(self._observation_cube(self._pr_reference, "pr"))
        pr_field, _pr_lats, pr_keys = self._tropical_anomalies(precip)
        return {
            "ts": self._pattern(ts_field, ts_keys, index, index_keys),
            "pr": self._pattern(pr_field, pr_keys, index, index_keys),
        }

    def _calculate_raw_output(
        self,
        complex_data_source: ComplexDataSource,
    ) -> dict[Variable, Cube]:
        picontrol = complex_data_source.data["picontrol"]
        model, lats, nino34_sigma = self._model_patterns(picontrol)

        values: dict[str, float] = {"nino34_std": nino34_sigma}
        for name, pattern in model.items():
            if pattern is not None:
                values[f"{name}_pattern_rms"] = float(
                    np.sqrt(physics.area_weighted_mean(pattern**2, lats)),
                )

        observed = self._observed_patterns_or_none()
        if observed is None:
            return self._scalar_outputs(values)

        first, last = get_threshold("tier1.enso.teleconnection_obs_window")
        values["teleconnection_obs_first_year"] = float(first)
        values["teleconnection_obs_last_year"] = float(last)
        for name in ("ts", "pr"):
            if model[name] is None or observed[name] is None:
                continue
            values[f"teleconnection_corr_{name}"] = physics.banded_pattern_correlation(
                model[name],
                observed[name],
                lats,
                band=self._band,
            )
        return self._scalar_outputs(values)

    def _observed_patterns_or_none(self) -> dict[str, np.ndarray | None] | None:
        """Return the observed patterns, or ``None``, logging the reason."""
        try:
            return self._observed_patterns()
        except Exception as exc:
            if self._fail_on_missing_data:
                raise
            logger.warning(
                f"Diagnostic '{self.name}': no observed ENSO teleconnection "
                f"patterns ({type(exc).__name__}: {exc}); emitting the model's "
                f"own regression-pattern summary without the gate rows",
            )
            return None


# ---------------------------------------------------------------------------
# I.3c — Tropical precipitation–buoyancy relationship (historical)
# ---------------------------------------------------------------------------


class PrecipBuoyancyGate(CB2ComplexDiagnostic):
    """I.3c: tropical P′-on-column-MSE′ slope within ±30% of GPCP/ERA5.

    Column moist static energy ``h = c_p·ta + g·zg + L_v·hus`` is integrated
    over the pressure levels the monthly Amon data actually carry
    (``∫ h dp/g``, :func:`physics.mass_weighted_column_integral`); the
    monthly anomalies of precipitation and of ⟨h⟩ over 20S–20N are then
    regressed against each other with time and space **pooled**
    (:func:`physics.pooled_regression_slope`). Slope units are
    mm day⁻¹ per MJ m⁻², so the number is O(0.1–1) rather than O(1e-7).

    The reference slope is the same statistic from GPCP ``pr`` and ERA5
    ``ta``/``hus``/``zg`` over ``tier1.precip_buoyancy.obs_window``, computed
    at run time when those data are obtainable and otherwise read from
    ``tier1.precip_buoyancy.reference_slope`` (null until Duncan pins it).
    With neither available the model slope is emitted alone and no gate row
    is written.

    ⚠ ClimateEval's ``ERA5.VARIABLE_MAPPING`` has no ``zg`` (an upstream
    gap), so the reference column is built with a hydrostatic geopotential
    from ERA5 ``ta``/``hus`` (:func:`physics.hydrostatic_height`); the
    missing surface term is constant in time and drops out of the anomalies.
    """

    _required_data_keys = ("historical",)

    #: 20S–20N (paper I.3c).
    _band: ClassVar[tuple[float, float]] = (-20.0, 20.0)
    #: J/m² → MJ/m², so the reported slope is O(0.1–1).
    _mse_scale: ClassVar[float] = 1.0e6

    _gate_checks = (
        GateCheck(
            check_id="precip_buoyancy",
            column="precip_buoyancy_slope_rel_error",
            upper=get_threshold("tier1.precip_buoyancy.rel_tolerance_vs_obs"),
            requirement=gate_requirement("tier1.precip_buoyancy"),
            tier=gate_tier("tier1.precip_buoyancy"),
        ),
    )

    # -- the column integral ------------------------------------------------

    def _column_mse(self, ta: Cube, zg: Cube, hus: Cube) -> tuple[np.ndarray, Cube]:
        """(⟨h⟩ in J/m² with shape (time, lat, lon), the cube it came from)."""
        levels = sorted(
            set(ta.coord("air_pressure").points.astype(float))
            & set(zg.coord("air_pressure").points.astype(float))
            & set(hus.coord("air_pressure").points.astype(float)),
        )
        if len(levels) < 2:  # noqa: PLR2004
            msg = (
                f"need at least two common pressure levels for the column "
                f"integral of I.3c, got {levels}"
            )
            raise ValueError(msg)
        with setup_esmvaltool_config_and_logging():
            ta, zg, hus = (
                extract_levels(cube, levels, "linear") for cube in (ta, zg, hus)
            )
        axis = ta.coord_dims("air_pressure")[0]
        mse = physics.moist_static_energy(
            _filled(ta.data),
            _filled(zg.data),
            _filled(hus.data),
        )
        return (
            physics.mass_weighted_column_integral(
                mse,
                np.asarray(levels, dtype=float),
                axis=axis,
            ),
            ta,
        )

    def _tropical_band(self, cube: Cube) -> Cube:
        with setup_esmvaltool_config_and_logging():
            return extract_region(
                cube,
                start_longitude=0.0,
                end_longitude=360.0,
                start_latitude=self._band[0],
                end_latitude=self._band[1],
            )

    def _slope(self, pr: Cube, ta: Cube, zg: Cube, hus: Cube) -> float:
        """Pooled slope of P′ (mm/day) on ⟨h⟩′ (MJ/m²) over 20S–20N."""
        pr, ta, zg, hus = (self._tropical_band(c) for c in (pr, ta, zg, hus))
        column, level_cube = self._column_mse(ta, zg, hus)
        _years, months = _cube_years_months(level_cube)
        h_anom = physics.deseasonalised_anomalies(column, months) / self._mse_scale
        with setup_esmvaltool_config_and_logging():
            pr = anomalies(pr, period="month")
        p_anom = _filled(pr.data) * physics.SECONDS_PER_DAY  # mm/day
        n = min(p_anom.shape[0], h_anom.shape[0])
        return physics.pooled_regression_slope(p_anom[:n], h_anom[:n])

    # -- the observational reference ----------------------------------------

    def _observation_cube(self, source: type[DataSource], var_name: str) -> Cube:
        from climatebench2 import reference_windows

        first, last = get_threshold("tier1.precip_buoyancy.obs_window")
        product = source()
        # The protocol's observation window is 1979-2014, but GPCP starts in
        # 1983 and ClimateEval refuses a range its record does not cover
        # (MissingDataError), which sends the whole reference slope down the
        # fallback path. Ask for the overlap instead.
        timerange = reference_windows.clip_to_source(
            windows.timerange(int(first), int(last)),
            self.data_root_dir,
            product.id,
            "mon",
            var_name,
        )
        variable = Variable(var_name, var_name, "mon", timerange=timerange)
        return self._regridded(
            product.get_cube(
                self.data_root_dir,
                variable,
                download_missing_data=self._download_missing_data,
            ),
        )

    def _observed_slope(self) -> float:
        """Return the GPCP/ERA5 reference slope over the protocol's window."""
        pr = self._observation_cube(GPCP, "pr")
        ta = self._observation_cube(ERA5Monthly, "ta")
        hus = self._observation_cube(ERA5Monthly, "hus")
        try:
            zg = self._observation_cube(ERA5Monthly, "zg")
        except Exception as exc:  # noqa: BLE001 - ERA5 has no zg upstream
            logger.warning(
                f"Diagnostic '{self.name}': ERA5 provides no 'zg' through "
                f"ClimateEval ({type(exc).__name__}: {exc}) — using the "
                f"hydrostatic geopotential of ta/hus for the reference column",
            )
            zg = ta.copy(
                physics.hydrostatic_height(
                    _filled(ta.data),
                    _filled(hus.data),
                    ta.coord("air_pressure").points.astype(float),
                    axis=ta.coord_dims("air_pressure")[0],
                ),
            )
        return self._slope(pr, ta, zg, hus)

    def _reference_slope(self) -> tuple[float | None, bool]:
        """Return (reference slope, whether it came from the observations)."""
        try:
            return self._observed_slope(), True
        except Exception as exc:
            if self._fail_on_missing_data:
                raise
            logger.warning(
                f"Diagnostic '{self.name}': no GPCP/ERA5 reference slope "
                f"({type(exc).__name__}: {exc}); falling back to "
                f"tier1.precip_buoyancy.reference_slope",
            )
        stored = get_threshold("tier1.precip_buoyancy.reference_slope")
        if stored is None:
            logger.warning(
                f"Diagnostic '{self.name}': tier1.precip_buoyancy."
                f"reference_slope is null, so I.3c reports the model slope "
                f"without a gate row (TODO: pin the reference slope)",
            )
            return None, False
        return float(stored), False

    def _calculate_raw_output(
        self,
        complex_data_source: ComplexDataSource,
    ) -> dict[Variable, Cube]:
        historical = complex_data_source.data["historical"]
        slope = self._slope(
            *(self._cube(historical, _mon(name)) for name in ("pr", "ta", "zg", "hus")),
        )
        values = {"precip_buoyancy_slope": slope}

        reference, from_observations = self._reference_slope()
        if reference is not None and np.isfinite(reference) and reference != 0.0:
            values["precip_buoyancy_slope_ref"] = reference
            values["precip_buoyancy_reference_from_obs"] = float(from_observations)
            values["precip_buoyancy_slope_rel_error"] = abs(slope / reference - 1.0)
        return self._scalar_outputs(values)


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
            requirement=gate_requirement("tier1.mjo"),
            tier=gate_tier("tier1.mjo"),
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
