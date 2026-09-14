"""Tier III paleoclimate diagnostics (metrics_reference.md §III.1).

Works with the ``paleo_scripts/`` pipeline (merged ``paleo_data`` PR #114):
that pipeline downloads/processes the PMIP4 model output and proxy
compilations; these diagnostics apply the *protocol* — proxy-aware
regime-(b) consistency scoring and the mid-Holocene Green-Sahara monsoon
gate — through the same ClimateEval machinery as Tiers I/II.

Data keys: ``midholocene`` / ``lgm`` / ``lig127k`` (PMIP4 experiment cubes)
and ``picontrol``.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np
from esmvalcore.preprocessor import (
    climate_statistics,
    extract_region,
)

from climateeval._config import setup_esmvaltool_config_and_logging

from climatebench2 import scoring
from climatebench2._thresholds import get_threshold
from climatebench2.diags.pass_fail import GateCheck, gate_requirement
from climatebench2.diags.tier1_physics import CB2ComplexDiagnostic, _mon

if TYPE_CHECKING:
    from iris.cube import Cube, CubeList
    from xarray import Dataset

    from climateeval import Variable
    from climateeval.data import ComplexDataSource

JJAS_MONTHS = (6, 7, 8, 9)
SECONDS_PER_DAY = 86400.0


class MidHoloceneMonsoonGate(CB2ComplexDiagnostic):
    """III.1 hard requirement: Green-Sahara monsoon amplification.

    mid-Holocene JJAS precipitation anomaly vs piControl, area-mean over
    North Africa (10–30N, 20W–30E; region wraps 0° longitude), must be
    ≥ +0.5 mm/day (``tier3.midholocene_monsoon``).
    """

    _required_data_keys = ("midholocene", "picontrol")

    _region = get_threshold("tier3.midholocene_monsoon.region")
    _gate_checks = (
        GateCheck(
            check_id="midholocene_monsoon",
            column="jjas_pr_anom_mmday",
            lower=get_threshold("tier3.midholocene_monsoon.jjas_pr_anom_min"),
            requirement=gate_requirement("tier3.midholocene_monsoon"),
        ),
    )

    def _jjas_region_mean(self, data: CubeList | Dataset) -> float:
        """JJAS-mean North-Africa precipitation (kg m-2 s-1)."""
        cube = self._cube(data, _mon("pr"))
        with setup_esmvaltool_config_and_logging():
            # extract_region handles the 20W..30E wrap (start > end)
            cube = extract_region(
                cube,
                start_longitude=float(self._region["lon"][0]) % 360.0,
                end_longitude=float(self._region["lon"][1]),
                start_latitude=float(self._region["lat"][0]),
                end_latitude=float(self._region["lat"][1]),
            )
            clim = climate_statistics(cube, "mean", "month")
        months = clim.coord("month_number").points.astype(int)
        jjas = np.isin(months, JJAS_MONTHS)
        data_arr = np.asarray(clim.data, dtype=float)[jjas]
        lats = clim.coord("latitude").points.astype(float)
        w = np.cos(np.deg2rad(lats))[None, :, None]
        w = np.broadcast_to(w, data_arr.shape)
        valid = np.isfinite(data_arr)
        return float((data_arr * w)[valid].sum() / w[valid].sum())

    def _calculate_raw_output(
        self,
        complex_data_source: ComplexDataSource,
    ) -> dict[Variable, Cube]:
        data = complex_data_source.data
        anom = self._jjas_region_mean(data["midholocene"]) - self._jjas_region_mean(
            data["picontrol"],
        )
        return self._scalar_outputs(
            {"jjas_pr_anom_mmday": anom * SECONDS_PER_DAY},
        )


class PaleoProxyConsistencyGate(CB2ComplexDiagnostic):
    """III.1: proxy-aware regime-(b) consistency for a paleo time slice.

    The model's climatological anomaly (period minus piControl) is sampled
    at the proxy sites and tested per site with the proxy error as σ_obs
    (:func:`climatebench2.scoring.proxy_site_consistency`); the emitted
    score is the fraction of consistent sites. The paper sets no pass bound
    on the fraction — it feeds the leaderboard, so no gate check is wired.

    Diagnostic kwargs (per suite entry):

    - ``period_key``: which data key holds the time slice (``lgm``,
      ``lig127k`` or ``midholocene``);
    - ``proxy_csv``: path to a processed proxy compilation from
      ``paleo_scripts/process_paleo_observations.py`` with columns
      ``lat``, ``lon``, ``tas_anom`` (or ``anom``) and ``error``;
    - ``var_name``: model variable (default ``tas``).
    """

    _required_data_keys = ("picontrol",)  # + the period key, checked below
    _gate_checks = ()

    def __init__(
        self,
        name: str,
        *,
        period_key: str = "midholocene",
        proxy_csv: str | Path | None = None,
        var_name: str = "tas",
        **kwargs: Any,
    ) -> None:
        super().__init__(name, **kwargs)
        self._period_key = period_key
        self._proxy_csv = Path(proxy_csv) if proxy_csv else None
        self._var_name = var_name

    def _check_required_dict_keys(self, dict_: dict[str, Any], dict_name: str) -> None:
        missing = {self._period_key, "picontrol"} - set(dict_)
        if missing:
            msg = (
                f"Missing keys {sorted(missing)} for {dict_name} dictionary of "
                f"diagnostic '{self.name}'"
            )
            raise ValueError(msg)

    def _climatology(self, data: CubeList | Dataset) -> Cube:
        cube = self._cube(data, _mon(self._var_name))
        with setup_esmvaltool_config_and_logging():
            return climate_statistics(cube, "mean", "full")

    def _calculate_raw_output(
        self,
        complex_data_source: ComplexDataSource,
    ) -> dict[Variable, Cube]:
        import pandas as pd

        if self._proxy_csv is None or not self._proxy_csv.exists():
            msg = (
                f"Diagnostic '{self.name}' needs proxy_csv (processed proxy "
                f"compilation from paleo_scripts); got {self._proxy_csv}"
            )
            raise FileNotFoundError(msg)
        proxies = pd.read_csv(self._proxy_csv)
        anom_col = "tas_anom" if "tas_anom" in proxies.columns else "anom"

        data = complex_data_source.data
        period = self._climatology(data[self._period_key])
        picontrol = self._climatology(data["picontrol"])
        anom_field = np.asarray(period.data, dtype=float) - np.asarray(
            picontrol.data,
            dtype=float,
        )
        model_at_sites = scoring.sample_at_sites(
            anom_field,
            period.coord("latitude").points.astype(float),
            period.coord("longitude").points.astype(float),
            proxies["lat"].to_numpy(float),
            proxies["lon"].to_numpy(float),
        )
        fraction, z = scoring.proxy_site_consistency(
            model_at_sites,
            proxies[anom_col].to_numpy(float),
            proxies["error"].to_numpy(float),
            p_threshold=get_threshold("tier2.consistency_p_value"),
        )
        return self._scalar_outputs(
            {
                f"{self._period_key}_site_consistency": fraction,
                f"{self._period_key}_n_sites": float(np.isfinite(z).sum()),
                f"{self._period_key}_mean_abs_z": float(
                    np.nanmean(np.abs(z[np.isfinite(z)])),
                ),
            },
        )
