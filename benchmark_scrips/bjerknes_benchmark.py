"""Tier I: Bjerknes compensation at northern mid-latitudes (piControl).

Verifies anti-correlation between atmospheric and oceanic meridional
energy transport (AMET and OMET) anomalies at 40-70N on decadal
timescales.  The compensation should be primarily a boreal-winter
phenomenon.

AMET and OMET are diagnosed from the energy budget residual method:

  F_TOA  = rsdt - rsut - rlut                       (TOA net downward)
  F_sfc  = (rsds - rsus) + (rlds - rlus) - hfss - hfls  (sfc net into ocean)
  div_A  = F_TOA - F_sfc                             (atmos column divergence)

  AMET(phi) = cumulative integral of zonal-mean div_A from the S pole
  OMET(phi) = cumulative integral of zonal-mean F_sfc from the S pole

Usage:
    python bjerknes_benchmark.py --model CanESM5
    python bjerknes_benchmark.py --model UKESM1-0-LL --min_years 200

References:
    Bjerknes, 1964
    Shaffrey and Sutton, 2006
    Outten et al., 2018
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
    anomaly,
    compute_meridional_transport,
    compute_sfc_net,
    compute_toa_net,
    save_results_csv,
)

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, force=True)

# --- Constants ---
COMPENSATION_LAT_MIN = 40.0  # degrees N
COMPENSATION_LAT_MAX = 70.0  # degrees N
DECADAL_WINDOW = 121  # months (~10 years, odd for centred rolling)
CORRELATION_THRESHOLD = -0.3  # pass if r < this (anti-correlation)

# Required CMIP6 variables (all Amon)
TOA_VARS = ["rsdt", "rsut", "rlut"]
SFC_VARS = ["rsds", "rsus", "rlds", "rlus", "hfss", "hfls"]
ALL_VARS = TOA_VARS + SFC_VARS


def extract_midlat_transport(
    transport, lat_min=COMPENSATION_LAT_MIN, lat_max=COMPENSATION_LAT_MAX
):
    """Average transport over a latitude band.

    Args:
        transport: xr.DataArray with dims (time, lat), in W.
        lat_min: southern bound.
        lat_max: northern bound.

    Returns:
        xr.DataArray time series (monthly).
    """
    band = transport.sel(lat=slice(lat_min, lat_max))
    return band.mean(dim="lat")


def decadal_filter(ts, window=DECADAL_WINDOW):
    """Apply a centred running-mean low-pass filter (decadal)."""
    return ts.rolling(time=window, center=True, min_periods=window // 2).mean()


def main(
    model: str,
    min_years: int = 200,
    save_to_cloud: bool = False,
    overwrite: bool = False,
):
    logger.info(f"Running Bjerknes compensation benchmark for {model} (piControl)")

    # --- Load all 9 variables from piControl ---
    picontrol_data = {}
    ensemble_members = None

    for var in ALL_VARS:
        logger.info(f"  Loading piControl {var} ...")
        df = DataFinder(model=model, variable=var, start_year=1850, end_year=2000)
        try:
            ds = df.load_experiment_ds(experiment="piControl", ensemble_mean=True)
            picontrol_data[var] = ds
            if ensemble_members is None:
                ensemble_members = df.ensemble_members
            logger.info(
                f"    {var}: {len(ds.time)} months " f"({len(ds.time) // 12} years)"
            )
        except Exception as e:
            logger.error(f"    Failed to load piControl {var}: {e}")
            raise

    # Check available length
    n_months_available = min(len(picontrol_data[v].time) for v in ALL_VARS)
    n_years_available = n_months_available // 12
    if n_years_available < min_years:
        logger.warning(
            f"  Only {n_years_available} years available, "
            f"less than requested minimum of {min_years}"
        )

    # Trim all datasets to common length
    n_months_common = n_years_available * 12
    for var in ALL_VARS:
        picontrol_data[var] = picontrol_data[var].isel(time=slice(0, n_months_common))

    # --- Compute flux fields ---
    logger.info("  Computing TOA and surface net flux fields ...")
    f_toa = compute_toa_net(picontrol_data)
    f_sfc = compute_sfc_net(picontrol_data)

    # Atmospheric column divergence
    div_a = f_toa - f_sfc

    # --- Zonal means ---
    logger.info("  Computing zonal means ...")
    div_a_zm = div_a.mean(dim="lon")
    f_sfc_zm = f_sfc.mean(dim="lon")

    lat = div_a_zm["lat"]

    # --- Meridional energy transport ---
    logger.info("  Computing meridional energy transport ...")
    amet = compute_meridional_transport(div_a_zm, lat)  # AMET
    omet = compute_meridional_transport(f_sfc_zm, lat)  # OMET

    # --- Extract 40-70N band averages ---
    amet_ts = extract_midlat_transport(amet)
    omet_ts = extract_midlat_transport(omet)

    logger.info(f"  Mean AMET at 40-70N: {float(amet_ts.mean()) / 1e15:.3f} PW")
    logger.info(f"  Mean OMET at 40-70N: {float(omet_ts.mean()) / 1e15:.3f} PW")

    # --- Remove seasonal cycle and apply decadal filter ---
    logger.info("  Removing seasonal cycle and applying decadal filter ...")
    amet_anom = anomaly(amet_ts)
    omet_anom = anomaly(omet_ts)

    amet_decadal = decadal_filter(amet_anom)
    omet_decadal = decadal_filter(omet_anom)

    # Drop NaN edges from rolling mean
    valid = amet_decadal.notnull() & omet_decadal.notnull()
    amet_filt = amet_decadal.where(valid, drop=True)
    omet_filt = omet_decadal.where(valid, drop=True)

    # --- Annual correlation ---
    if len(amet_filt) < 24:
        logger.error("  Insufficient data after filtering for correlation.")
        annual_corr = np.nan
    else:
        annual_corr = float(np.corrcoef(amet_filt.values, omet_filt.values)[0, 1])
    pass_annual = annual_corr < CORRELATION_THRESHOLD

    logger.info(f"  Annual AMET-OMET correlation (decadal): {annual_corr:.4f}")
    logger.info(f"  Pass (r < {CORRELATION_THRESHOLD}): {pass_annual}")

    # --- DJF correlation ---
    logger.info("  Computing DJF seasonal check ...")
    amet_djf_anom = amet_anom.sel(time=amet_anom["time.month"].isin([12, 1, 2]))
    omet_djf_anom = omet_anom.sel(time=omet_anom["time.month"].isin([12, 1, 2]))

    amet_djf_decadal = decadal_filter(amet_djf_anom, window=DECADAL_WINDOW // 4)
    omet_djf_decadal = decadal_filter(omet_djf_anom, window=DECADAL_WINDOW // 4)

    valid_djf = amet_djf_decadal.notnull() & omet_djf_decadal.notnull()
    amet_djf_filt = amet_djf_decadal.where(valid_djf, drop=True)
    omet_djf_filt = omet_djf_decadal.where(valid_djf, drop=True)

    if len(amet_djf_filt) < 12:
        logger.warning("  Insufficient DJF data after filtering.")
        djf_corr = np.nan
    else:
        djf_corr = float(np.corrcoef(amet_djf_filt.values, omet_djf_filt.values)[0, 1])

    pass_djf = djf_corr < CORRELATION_THRESHOLD
    winter_stronger = (
        not np.isnan(djf_corr)
        and not np.isnan(annual_corr)
        and abs(djf_corr) > abs(annual_corr)
    )

    logger.info(f"  DJF AMET-OMET correlation (decadal): {djf_corr:.4f}")
    logger.info(f"  Pass DJF (r < {CORRELATION_THRESHOLD}): {pass_djf}")
    logger.info(f"  Winter stronger than annual: {winter_stronger}")

    pass_all = pass_annual and pass_djf
    logger.info(f"  Overall Bjerknes benchmark: {'PASS' if pass_all else 'FAIL'}")

    # --- Save results ---
    results_dir = "../results/bjerknes_compensation/"
    results_file = os.path.join(results_dir, "bjerknes_results.csv")

    result_df = pd.DataFrame(
        {
            "model": [model],
            "annual_correlation": [round(annual_corr, 4)],
            "pass_annual": [pass_annual],
            "djf_correlation": [round(djf_corr, 4)],
            "pass_djf": [pass_djf],
            "winter_stronger": [winter_stronger],
            "pass_all": [pass_all],
            "mean_amet_PW": [round(float(amet_ts.mean()) / 1e15, 4)],
            "mean_omet_PW": [round(float(omet_ts.mean()) / 1e15, 4)],
            "n_years": [n_years_available],
            "ensemble_members": [
                "_".join(ensemble_members) if ensemble_members else ""
            ],
        }
    )

    save_results_csv(result_df, results_file, save_to_cloud, overwrite)

    return {
        "annual_correlation": annual_corr,
        "djf_correlation": djf_corr,
        "pass_annual": pass_annual,
        "pass_djf": pass_djf,
        "winter_stronger": winter_stronger,
        "pass_all": pass_all,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Tier I: Bjerknes compensation at northern "
        "mid-latitudes (piControl)"
    )
    parser.add_argument(
        "--model",
        required=True,
        help="CMIP6 model name (e.g., CanESM5, UKESM1-0-LL)",
    )
    parser.add_argument(
        "--min_years",
        default=200,
        type=int,
        help="Minimum years of piControl required (default: 200)",
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
        min_years=args.min_years,
        save_to_cloud=args.save_to_cloud,
        overwrite=args.overwrite,
    )
