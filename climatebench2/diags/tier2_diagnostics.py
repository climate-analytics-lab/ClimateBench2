"""Tier II scalar diagnostics with no ClimateEval provider (Phase 4).

Historical-experiment checks from metrics_reference.md §II.1 that were
entirely missing: the Pinatubo response and the aerosol-era hemispheric
asymmetry. Both are complex diagnostics on the ``historical`` data key and
emit their scalars for the leaderboard alongside sign-based sanity gates;
the full regime-(b) consistency against observations plugs in through the
scoring engine once the observational series are wired
(``climatebench2.scoring.ensemble_consistency``).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
from esmvalcore.preprocessor import (
    annual_statistics,
    area_statistics,
    climate_statistics,
    extract_region,
    extract_time,
    zonal_statistics,
)

from climateeval._config import setup_esmvaltool_config_and_logging

from climatebench2 import physics
from climatebench2._thresholds import get_threshold
from climatebench2.diags.pass_fail import GateCheck
from climatebench2.diags.tier1_physics import CB2ComplexDiagnostic, _mon

if TYPE_CHECKING:
    from iris.cube import Cube, CubeList
    from xarray import Dataset

    from climateeval import Variable
    from climateeval.data import ComplexDataSource


class PinatuboResponseGate(CB2ComplexDiagnostic):
    """Pinatubo (1991–93) response: surface dimming and cooling.

    Global-mean ``rsds`` and ``tas`` anomalies for Jul 1991 – Dec 1993
    relative to the 1990–2020 climatology. Gates: Δrsds < 0 (dimming) and
    Δtas < 0 (cooling). The anomaly magnitudes are emitted for the
    regime-(b) consistency comparison in the leaderboard.
    """

    _required_data_keys = ("historical",)
    _gate_checks = (
        GateCheck(
            check_id="pinatubo_dimming",
            column="pinatubo_rsds_anom",
            upper=get_threshold("tier2.pinatubo.rsds_anomaly_max"),
        ),
        GateCheck(
            check_id="pinatubo_cooling",
            column="pinatubo_tas_anom",
            upper=get_threshold("tier2.pinatubo.tas_anomaly_max"),
        ),
    )

    def _anomaly(self, data: CubeList | Dataset, variable: Variable) -> float:
        clim_years = get_threshold("tier2.climatology_baseline_period")
        cube = self._cube(data, variable)
        with setup_esmvaltool_config_and_logging():
            cube = area_statistics(cube, "mean")
            clim_cube = extract_time(
                cube,
                int(clim_years[0]),
                1,
                1,
                int(clim_years[1]),
                12,
                31,
            )
            clim = float(
                np.asarray(climate_statistics(clim_cube, "mean", "full").data),
            )
            event = extract_time(cube, 1991, 7, 1, 1993, 12, 31)
        return float(np.asarray(event.data, dtype=float).mean() - clim)

    def _calculate_raw_output(
        self,
        complex_data_source: ComplexDataSource,
    ) -> dict[Variable, Cube]:
        historical = complex_data_source.data["historical"]
        return self._scalar_outputs(
            {
                "pinatubo_rsds_anom": self._anomaly(historical, _mon("rsds")),
                "pinatubo_tas_anom": self._anomaly(historical, _mon("tas")),
            },
        )


class HemisphericAsymmetryGate(CB2ComplexDiagnostic):
    """Aerosol-era (1950–1985) hemispheric asymmetry.

    NH−SH tas trend difference (NH suppressed by aerosol forcing → < 0) and
    the associated southward ITCZ shift (trend of the zonal-mean-pr maximum
    latitude < 0). Values emitted for regime-(b) comparison.
    """

    _required_data_keys = ("historical",)
    _era: tuple[int, int] = (1950, 1985)
    _gate_checks = (
        GateCheck(
            check_id="hemispheric_trend_asymmetry",
            column="nh_minus_sh_trend",
            upper=get_threshold("tier2.hemispheric_asymmetry.nh_minus_sh_trend_max"),
        ),
        GateCheck(
            check_id="itcz_southward_shift",
            column="itcz_shift_deg_per_decade",
            upper=get_threshold("tier2.hemispheric_asymmetry.itcz_shift_max"),
        ),
    )

    def _hemisphere_trend(
        self,
        data: CubeList | Dataset,
        lat0: float,
        lat1: float,
    ) -> float:
        cube = self._cube(data, _mon("tas"))
        with setup_esmvaltool_config_and_logging():
            cube = extract_time(cube, self._era[0], 1, 1, self._era[1], 12, 31)
            cube = extract_region(
                cube,
                start_longitude=0.0,
                end_longitude=360.0,
                start_latitude=lat0,
                end_latitude=lat1,
            )
            cube = area_statistics(cube, "mean")
            cube = annual_statistics(cube, "mean")
        return physics.ols_trend(np.asarray(cube.data, dtype=float))

    def _itcz_shift(self, data: CubeList | Dataset) -> float:
        """Trend (°/decade) of the annual zonal-mean-pr maximum latitude."""
        cube = self._cube(data, _mon("pr"))
        with setup_esmvaltool_config_and_logging():
            cube = extract_time(cube, self._era[0], 1, 1, self._era[1], 12, 31)
            cube = annual_statistics(cube, "mean")
            cube = zonal_statistics(cube, "mean")
        pr = np.asarray(cube.data, dtype=float)  # (year, lat)
        lats = cube.coord("latitude").points.astype(float)
        tropics = (lats >= -30.0) & (lats <= 30.0)
        itcz = lats[tropics][np.argmax(pr[:, tropics], axis=1)]
        return physics.ols_trend(itcz) * 10.0  # per decade

    def _calculate_raw_output(
        self,
        complex_data_source: ComplexDataSource,
    ) -> dict[Variable, Cube]:
        historical = complex_data_source.data["historical"]
        nh = self._hemisphere_trend(historical, 0.0, 90.0)
        sh = self._hemisphere_trend(historical, -90.0, 0.0)
        return self._scalar_outputs(
            {
                "nh_minus_sh_trend": nh - sh,
                "nh_trend": nh,
                "sh_trend": sh,
                "itcz_shift_deg_per_decade": self._itcz_shift(historical),
            },
        )
