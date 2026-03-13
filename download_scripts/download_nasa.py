import argparse
import logging
import os
import sys

import xarray as xr

sys.path.append("..")
from utils import standardize_dims

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


### Source specific download script ###
SOURCE = "nasa_ceres"
VARIABLES = ["clt", "ctp", "ctt", "rsut", "rsutcs", "rlut", "rlutcs"]

# NOTE: CERES data must be ordered and downloaded from:
# https://ceres.larc.nasa.gov/data/
# Place the downloaded .nc files in the observations/ directory before running.

DOWNLOADED_FILE_NAME = "CERES_EBAF-TOA_Ed4.2.1_Subset_200003-202509.nc"

DATA_SPECS = {
    "clt": {
        "raw_local_path": f"../observations/{DOWNLOADED_FILE_NAME}",
        "source_var": "cldarea_total_daynight_mon",
        "long_name": "Cloud Area Fraction, Daytime-and-Nighttime conditions, Monthly Means",
        "standard_name": "cloud_area_fraction",
        "units": "percent",
    },
    "ctp": {
        "raw_local_path": f"../observations/{DOWNLOADED_FILE_NAME}",
        "source_var": "cldpress_total_daynight_mon",
        "long_name": "Cloud Effective Pressure, Daytime-and-Nighttime conditions, Monthly Means",
        "standard_name": "Cloud Effective Pressure - Daytime-and-Nighttime",
        "units": "hpa",
    },
    "ctt": {
        "raw_local_path": f"../observations/{DOWNLOADED_FILE_NAME}",
        "source_var": "cldtemp_total_daynight_mon",
        "long_name": "Cloud Effective Temperature, Daytime-and-Nighttime conditions, Monthly Means",
        "standard_name": "Cloud Effective Temperature - Daytime-and-Nighttime",
        "units": "K",
    },
    "rsut": {
        "raw_local_path": f"../observations/{DOWNLOADED_FILE_NAME}",
        "source_var": "toa_sw_all_mon",
        "long_name": "Top of The Atmosphere Shortwave Flux, All-Sky conditions, Monthly Means",
        "standard_name": "toa_outgoing_shortwave_flux",
        "units": "W m-2",
    },
    "rsutcs": {
        "raw_local_path": f"../observations/{DOWNLOADED_FILE_NAME}",
        "source_var": "toa_sw_clr_c_mon",
        "long_name": "Top of The Atmosphere Shortwave Flux, Clear-Sky (for cloud-free areas of region) conditions, Monthly Means",
        "standard_name": "TOA Shortwave Flux - Clear-Sky (for cloud-free areas of region)",
        "units": "W m-2",
    },
    "rlut": {
        "raw_local_path": f"../observations/{DOWNLOADED_FILE_NAME}",
        "source_var": "toa_lw_all_mon",
        "long_name": "Top of The Atmosphere Longwave Flux, All-Sky conditions, Monthly Means",
        "standard_name": "toa_outgoing_longwave_flux",
        "units": "W m-2",
    },
    "rlutcs": {
        "raw_local_path": f"../observations/{DOWNLOADED_FILE_NAME}",
        "source_var": "toa_lw_clr_c_mon",
        "long_name": "Top of The Atmosphere Longwave Flux, Clear-Sky (for cloud-free areas of region) conditions, Monthly Means",
        "standard_name": "TOA Longwave Flux - Clear-Sky (for cloud-free areas of region)",
        "units": "W m-2",
    },
}


def process_variable(ds_raw: xr.Dataset, variable: str, specs: dict, save_path: str):
    source_var = specs["source_var"]
    ds = ds_raw[source_var].to_dataset(name=variable)
    ds = standardize_dims(ds)
    ds[variable].encoding = {}
    ds = ds.chunk(chunks={"time": 1, "lat": -1, "lon": -1})

    ds[variable].attrs = {
        "long_name": specs["long_name"],
        "standard_name": specs["standard_name"],
        "units": specs["units"],
        "source": SOURCE,
    }
    logger.info(f"Saving {variable} to {save_path}")
    ds.to_zarr(save_path)


def main(save_cloud: bool):

    # Group variables by their source file to open each file only once
    files_to_variables: dict[str, list[str]] = {}
    for variable in VARIABLES:
        raw_path = DATA_SPECS[variable]["raw_local_path"]
        files_to_variables.setdefault(raw_path, []).append(variable)

    for raw_local_path, variables in files_to_variables.items():
        if not os.path.exists(raw_local_path):
            raise FileNotFoundError(
                f"Raw CERES file not found: {raw_local_path}\n"
                "Please manually download the CERES EBAF data and place it in observations/."
            )

        logger.info(f"Opening {raw_local_path}")
        ds_raw = xr.open_dataset(raw_local_path, chunks={})

        for variable in variables:
            if save_cloud:
                save_path = f"gs://climatebench/observations/{variable}_{SOURCE}.zarr"
            else:
                save_path = f"../observations/{variable}_{SOURCE}.zarr"

            logger.info(f"Processing {variable} -> {save_path}")
            process_variable(ds_raw, variable, DATA_SPECS[variable], save_path)

        ds_raw.close()

    logger.info("Done")
    return None


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=f"Process {SOURCE} TOA radiation and cloud data."
    )
    parser.add_argument(
        "--save_cloud",
        action="store_true",
        default=False,
        help="Save output on google cloud. If not set, saves locally.",
    )
    args = parser.parse_args()
    main(save_cloud=args.save_cloud)
