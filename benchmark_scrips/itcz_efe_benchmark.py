"""Tier I: ITCZ–energy flux equator (EFE) relationship (historical).

Verifies that the seasonal cycle of the ITCZ co-varies with the energy flux
equator (EFE) — the latitude where the vertically integrated meridional
atmospheric energy transport (AMET) vanishes.

AMET is diagnosed from the energy budget residual method:

  F_TOA  = rsdt - rsut - rlut                       (TOA net downward)
  F_sfc  = (rsds - rsus) + (rlds - rlus) - hfss - hfls  (sfc net into ocean)
  div_A  = F_TOA - F_sfc                             (atmos column divergence)

  AMET(phi) = 2*pi*a^2 * integral_{-pi/2}^{phi} div_A(phi') cos(phi') dphi'

  EFE(t)  = latitude where AMET = 0 (near-equatorial zero crossing)
  ITCZ(t) = latitude of zonal-mean precipitation maximum (|lat| <= 30°)

Pass/fail criteria (from Donohoe et al., 2013 and Schneider et al., 2014):
  - Seasonal r(ITCZ, EFE)              > 0.85
  - Scaling slope (ITCZ vs F_xeq)      -1.5 – -5.0 °/PW

Usage:
    python itcz_efe_benchmark.py --model CanESM5
    python itcz_efe_benchmark.py --model CanESM5 --start_year 1950 --end_year 2014

References:
    Kang et al., 2008, J. Climate
    Kang et al., 2009, J. Climate
    Schneider et al., 2014, Nature
    Donohoe et al., 2013, J. Climate
"""

import argparse
import logging
import os
import sys

import numpy as np
import pandas as pd
import xarray as xr

from benchmark_utils import DataFinder

sys.path.append("..")

from utils import (
    compute_meridional_transport,
    compute_sfc_net,
    compute_toa_net,
    save_results_csv,
)

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, force=True)

# Pass/fail thresholds
ITCZ_EFE_CORR_MIN = 0.85  # minimum seasonal Pearson r(ITCZ, EFE)
SCALING_SLOPE_MAX = -1.5  # °/PW — lower bound on ITCZ vs F_xeq regression
SCALING_SLOPE_MIN = -5.0  # °/PW — upper bound

# Tropical search bands
ITCZ_LAT_BAND = 30.0  # search ±30° for precipitation maximum
EFE_SEARCH_BAND = 40.0  # search ±40° for AMET zero crossing

# Required CMIP6 variables (all Amon)
ENERGY_VARS = ["rsdt", "rsut", "rlut", "rsds", "rsus", "rlds", "rlus", "hfss", "hfls"]
PRECIP_VARS = ["pr"]
ALL_VARS = ENERGY_VARS + PRECIP_VARS


# ---------------------------------------------------------------------------
# EFE and ITCZ diagnostics
# ---------------------------------------------------------------------------


def compute_efe(amet_pw, lat_band=EFE_SEARCH_BAND):
    """Find the EFE latitude.

    Args:
        amet_pw: xr.DataArray (time, lat), AMET in PW.
        lat_band: search within ±lat_band degrees.

    Returns:
        np.ndarray (time,): EFE latitude in degrees.
    """
    a = amet_pw.sel(lat=slice(lat_band * -1, lat_band))
    a_deriv = a.differentiate(coord="lat")
    sign_changes = (
        np.concatenate(
            [np.diff(np.sign(a.data), axis=1), False * np.ones((1980, 1))], axis=1
        )
        != 0
    )
    candidates = a_deriv.where(sign_changes)
    abs_lat_masked = np.abs(candidates["lat"]).where(~np.isnan(candidates))
    efe_idx = abs_lat_masked.argmin(dim="lat")
    efe_lat = candidates["lat"].isel(lat=efe_idx)
    return efe_lat.drop(["lat"])


def compute_itcz(pr_zm, lat_band=ITCZ_LAT_BAND):
    """Find the ITCZ latitude.

    Args:
        pr_zm: xr.DataArray (time, lat), zonal-mean precipitation.
        lat_band: search within ±lat_band degrees.

    Returns:
        np.ndarray (time,): ITCZ latitude in degrees.
    """
    pr_t = pr_zm.sel(lat=slice(lat_band * -1, lat_band))
    return pr_t.idxmax(dim="lat")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main(
    model: str,
    start_year: int = 1850,
    end_year: int = 2014,
    save_to_cloud: bool = False,
    overwrite: bool = False,
):
    logger.info(
        f"Running ITCZ–EFE benchmark for {model} "
        f"(historical {start_year}–{end_year})"
    )

    # --- Load all variables from historical ---
    hist_data = {}
    ensemble_members = None

    for var in ALL_VARS:
        logger.info(f"  Loading historical {var} ...")
        df = DataFinder(
            model=model, variable=var, start_year=start_year, end_year=end_year
        )
        try:
            ds = df.load_model_ds(ensemble_mean=True)
            hist_data[var] = ds
            if ensemble_members is None:
                ensemble_members = df.ensemble_members
            logger.info(
                f"    {var}: {len(ds.time)} months " f"({len(ds.time) // 12} years)"
            )
        except Exception as e:
            logger.error(f"    Failed to load historical {var}: {e}")
            raise

    # Trim all datasets to common length
    n_months_common = min(len(hist_data[v].time) for v in ALL_VARS)
    n_years_available = n_months_common // 12
    n_months_common = n_years_available * 12
    for var in ALL_VARS:
        hist_data[var] = hist_data[var].isel(time=slice(0, n_months_common))

    logger.info(f"  Using {n_years_available} years of historical data")

    # --- Compute atmospheric column divergence ---
    logger.info("  Computing TOA and surface net fluxes ...")
    f_toa = compute_toa_net(hist_data)
    f_sfc = compute_sfc_net(hist_data)
    div_a = f_toa - f_sfc

    # --- Zonal means ---
    logger.info("  Computing zonal means ...")
    div_a_zm = div_a.mean(dim="lon")
    pr_zm = hist_data["pr"]["pr"].mean(dim="lon")

    lat = div_a_zm["lat"].values

    # --- AMET for every time step ---
    logger.info("  Computing AMET ...")
    amet = compute_meridional_transport(div_a_zm, lat)
    amet_pw = amet / 1e15

    # --- EFE and ITCZ latitude for every time step ---
    logger.info("  Diagnosing EFE and ITCZ latitudes ...")
    efe_lats = compute_efe(amet_pw)
    itcz_lats = compute_itcz(pr_zm)
    xeq_flux_pw = amet_pw.interp(lat=0.0).values

    # Drop any time steps where EFE could not be determined
    valid = ~np.isnan(efe_lats)
    n_valid = int(valid.sum())
    n_invalid = n_months_common - n_valid
    if n_invalid > 0:
        logger.warning(
            f"  {n_invalid}/{n_months_common} time steps had no valid EFE crossing "
            "and will be excluded."
        )

    efe_v = efe_lats[valid]
    itcz_v = itcz_lats[valid]
    fxeq_v = xeq_flux_pw[valid]

    # --- Statistics ---
    # 1. Seasonal correlation: r(ITCZ, EFE)
    r_itcz_efe = float(np.corrcoef(efe_v[:-2], itcz_v[2:])[0, 1])

    # 2. Scaling regression: ITCZ = slope * F_xeq + intercept  (°/PW)
    slope, intercept = np.polyfit(fxeq_v[:-2], itcz_v[2:], 1)
    slope = float(slope)
    intercept = float(intercept)

    logger.info(f"  Using {n_valid}/{n_months_common} valid time steps")
    logger.info(f"  r(ITCZ, EFE):                  {r_itcz_efe:.3f}")
    logger.info(f"  Scaling slope (°/PW):          {slope:.2f}")

    # --- Pass/fail checks ---
    pass_correlation = r_itcz_efe >= ITCZ_EFE_CORR_MIN
    pass_scaling = SCALING_SLOPE_MIN <= slope <= SCALING_SLOPE_MAX

    pass_all = pass_correlation and pass_scaling

    logger.info(
        f"  r(ITCZ, EFE) >= {ITCZ_EFE_CORR_MIN}: "
        f"{'PASS' if pass_correlation else 'FAIL'}"
    )
    logger.info(
        f"  Scaling slope [{SCALING_SLOPE_MIN}–{SCALING_SLOPE_MAX} °/PW]: "
        f"{'PASS' if pass_scaling else 'FAIL'}"
    )

    logger.info(f"  Overall ITCZ–EFE benchmark: {'PASS' if pass_all else 'FAIL'}")

    # --- Save results ---
    results_dir = "../results/itcz_efe/"
    results_file = os.path.join(results_dir, "itcz_efe_results.csv")

    result_df = pd.DataFrame(
        {
            "model": [model],
            "start_year": [start_year],
            "end_year": [end_year],
            "n_years": [n_years_available],
            "n_valid_timesteps": [n_valid],
            "r_itcz_efe": [round(r_itcz_efe, 4)],
            "scaling_slope_deg_per_PW": [round(slope, 3)],
            "scaling_intercept_deg": [round(intercept, 3)],
            "pass_correlation": [pass_correlation],
            "pass_scaling": [pass_scaling],
            "pass_all": [pass_all],
            "ensemble_members": [
                "_".join(ensemble_members) if ensemble_members else ""
            ],
        }
    )

    save_results_csv(result_df, results_file, save_to_cloud, overwrite)

    return {
        "r_itcz_efe": r_itcz_efe,
        "scaling_slope_deg_per_PW": slope,
        "scaling_intercept_deg": intercept,
        "pass_correlation": pass_correlation,
        "pass_scaling": pass_scaling,
        "pass_all": pass_all,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Tier I: ITCZ–energy flux equator relationship (historical)"
    )
    parser.add_argument(
        "--model",
        required=True,
        help="CMIP6 model name (e.g., CanESM5, UKESM1-0-LL)",
    )
    parser.add_argument(
        "--start_year",
        default=1850,
        type=int,
        help="Start year of historical period (default: 1850)",
    )
    parser.add_argument(
        "--end_year",
        default=2014,
        type=int,
        help="End year of historical period (default: 2014)",
    )
    parser.add_argument(
        "--save_to_cloud",
        action="store_true",
        default=False,
        help="Save results to Google Cloud Storage",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        default=False,
        help="Overwrite existing results file",
    )
    args = parser.parse_args()

    main(
        model=args.model,
        start_year=args.start_year,
        end_year=args.end_year,
        save_to_cloud=args.save_to_cloud,
        overwrite=args.overwrite,
    )
