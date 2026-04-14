"""Tier I: Meridional heat transport partitioning (piControl).

Verifies the ocean-dominates-tropics / atmosphere-dominates-extratropics
crossover in meridional heat transport (MHT).

AMET and OMET are diagnosed from the energy budget residual method:

  F_TOA  = rsdt - rsut - rlut                       (TOA net downward)
  F_sfc  = (rsds - rsus) + (rlds - rlus) - hfss - hfls  (sfc net into ocean)
  div_A  = F_TOA - F_sfc                             (atmos column divergence)

  AMET(phi) = cumulative integral of zonal-mean div_A from the S pole
  OMET(phi) = cumulative integral of zonal-mean F_sfc from the S pole

Pass/fail criteria (from Marshall et al., 2007 and ECCO/ERA5 estimates):
  - Peak oceanic transport: 1.5–2.0 PW near 15–20° latitude
  - Peak atmospheric transport: 4–5 PW near 40° latitude

Usage:
    python meridional_heat_transport_benchmark.py --model CanESM5
    python meridional_heat_transport_benchmark.py --model CanESM5 --min_years 200

References:
    Marshall et al., 2007
    Trenberth and Caron, 2001
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

# --- Constants ---
# Expected ranges (PW) from Marshall et al., 2007 / Trenberth and Caron, 2001
OMET_PEAK_MIN = 1.5  # PW
OMET_PEAK_MAX = 2.0  # PW
OMET_PEAK_LAT_MIN = 10.0  # degrees
OMET_PEAK_LAT_MAX = 25.0  # degrees

AMET_PEAK_MIN = 4.0  # PW
AMET_PEAK_MAX = 5.0  # PW
AMET_PEAK_LAT_MIN = 30.0  # degrees
AMET_PEAK_LAT_MAX = 50.0  # degrees

# Required CMIP6 variables (all Amon)
TOA_VARS = ["rsdt", "rsut", "rlut"]
SFC_VARS = ["rsds", "rsus", "rlds", "rlus", "hfss", "hfls"]
ALL_VARS = TOA_VARS + SFC_VARS


def find_nh_peak(transport_profile, lat_min, lat_max):
    """Find peak transport magnitude and latitude in the Northern Hemisphere.

    Args:
        transport_profile: xr.DataArray with dim (lat), time-mean transport in PW.
        lat_min: southern bound of search region (degrees N).
        lat_max: northern bound of search region (degrees N).

    Returns:
        (peak_value_PW, peak_latitude_deg): peak magnitude and its latitude.
    """
    band = transport_profile.sel(lat=slice(lat_min, lat_max))
    peak_idx = int(band.argmax(dim="lat"))
    peak_val = float(band.isel(lat=peak_idx))
    peak_lat = float(band.lat.isel(lat=peak_idx))
    return peak_val, peak_lat


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main(
    model: str,
    min_years: int = 200,
    save_to_cloud: bool = False,
    overwrite: bool = False,
):
    logger.info(f"Running meridional heat transport benchmark for {model} (piControl)")

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
    amet = compute_meridional_transport(div_a_zm, lat)  # atmospheric
    omet = compute_meridional_transport(f_sfc_zm, lat)  # oceanic

    # --- Time-mean transport profiles (convert to PW) ---
    amet_mean = amet.mean(dim="time") / 1e15  # W -> PW
    omet_mean = omet.mean(dim="time") / 1e15

    # --- Find NH peaks ---
    # Oceanic: search 5–30° for peak (broader than pass/fail range)
    omet_peak_pw, omet_peak_lat = find_nh_peak(omet_mean, 5.0, 30.0)
    # Atmospheric: search 25–55° for peak
    amet_peak_pw, amet_peak_lat = find_nh_peak(amet_mean, 25.0, 55.0)

    logger.info(
        f"  Peak oceanic transport (NH): {omet_peak_pw:.2f} PW "
        f"at {omet_peak_lat:.1f}°N"
    )
    logger.info(
        f"  Peak atmospheric transport (NH): {amet_peak_pw:.2f} PW "
        f"at {amet_peak_lat:.1f}°N"
    )

    # --- Pass/fail checks ---
    pass_omet_magnitude = OMET_PEAK_MIN <= omet_peak_pw <= OMET_PEAK_MAX
    pass_omet_latitude = OMET_PEAK_LAT_MIN <= omet_peak_lat <= OMET_PEAK_LAT_MAX
    pass_amet_magnitude = AMET_PEAK_MIN <= amet_peak_pw <= AMET_PEAK_MAX
    pass_amet_latitude = AMET_PEAK_LAT_MIN <= amet_peak_lat <= AMET_PEAK_LAT_MAX

    # Crossover check: oceanic peak should be equatorward of atmospheric peak
    pass_crossover = omet_peak_lat < amet_peak_lat

    pass_all = (
        pass_omet_magnitude
        and pass_omet_latitude
        and pass_amet_magnitude
        and pass_amet_latitude
        and pass_crossover
    )

    logger.info(
        f"  OMET magnitude [{OMET_PEAK_MIN}–{OMET_PEAK_MAX} PW]: "
        f"{'PASS' if pass_omet_magnitude else 'FAIL'}"
    )
    logger.info(
        f"  OMET latitude [{OMET_PEAK_LAT_MIN}–{OMET_PEAK_LAT_MAX}°N]: "
        f"{'PASS' if pass_omet_latitude else 'FAIL'}"
    )
    logger.info(
        f"  AMET magnitude [{AMET_PEAK_MIN}–{AMET_PEAK_MAX} PW]: "
        f"{'PASS' if pass_amet_magnitude else 'FAIL'}"
    )
    logger.info(
        f"  AMET latitude [{AMET_PEAK_LAT_MIN}–{AMET_PEAK_LAT_MAX}°N]: "
        f"{'PASS' if pass_amet_latitude else 'FAIL'}"
    )
    logger.info(
        f"  Crossover (ocean equatorward of atmos): "
        f"{'PASS' if pass_crossover else 'FAIL'}"
    )
    logger.info(f"  Overall MHT benchmark: {'PASS' if pass_all else 'FAIL'}")

    # --- Save results ---
    results_dir = "../results/meridional_heat_transport/"
    results_file = os.path.join(results_dir, "meridional_heat_transport_results.csv")

    result_df = pd.DataFrame(
        {
            "model": [model],
            "omet_peak_PW": [round(omet_peak_pw, 4)],
            "omet_peak_lat": [round(omet_peak_lat, 1)],
            "pass_omet_magnitude": [pass_omet_magnitude],
            "pass_omet_latitude": [pass_omet_latitude],
            "amet_peak_PW": [round(amet_peak_pw, 4)],
            "amet_peak_lat": [round(amet_peak_lat, 1)],
            "pass_amet_magnitude": [pass_amet_magnitude],
            "pass_amet_latitude": [pass_amet_latitude],
            "pass_crossover": [pass_crossover],
            "pass_all": [pass_all],
            "n_years": [n_years_available],
            "ensemble_members": [
                "_".join(ensemble_members) if ensemble_members else ""
            ],
        }
    )

    save_results_csv(result_df, results_file, save_to_cloud, overwrite)

    return {
        "omet_peak_PW": omet_peak_pw,
        "omet_peak_lat": omet_peak_lat,
        "amet_peak_PW": amet_peak_pw,
        "amet_peak_lat": amet_peak_lat,
        "pass_omet_magnitude": pass_omet_magnitude,
        "pass_omet_latitude": pass_omet_latitude,
        "pass_amet_magnitude": pass_amet_magnitude,
        "pass_amet_latitude": pass_amet_latitude,
        "pass_crossover": pass_crossover,
        "pass_all": pass_all,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Tier I: Meridional heat transport partitioning (piControl)"
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
