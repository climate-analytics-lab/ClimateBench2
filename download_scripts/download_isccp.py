import argparse
import logging
import os
import shutil
import sys

import xarray as xr

sys.path.append("..")
from utils import download_file, standardize_dims

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


### Source specific download script ###
SOURCE = "isccp"
VARIABLES = ["clt", "ctp", "ctt", "clwvi"]
DOWNLOAD_FOLDER = "../observations/isccp_raw"
URL_BASE = "https://www.ncei.noaa.gov/thredds/fileServer/cdr/isccp_hgm_agg/files/isccp-basic/hgm/ISCCP-Basic.HGM.v01r00.GLOBAL.{year}.{month}.99.9999.GPC.10KM.CS00.EA1.00.nc"

DATA_SPECS = {
    "clt": {
        "source_var": "cldamt",
        "long_name": "Cloud Area Fraction",
        "standard_name": "cloud_area_fraction",
        "units": "percent",
    },
    "ctp": {
        "source_var": "pc",
        "long_name": "Mean cloud pressure",
        "standard_name": "air_pressure_at_cloud_top",
        "units": "hpa",
    },
    "ctt": {
        "source_var": "tc",
        "long_name": "Mean cloud temperature",
        "standard_name": "air_temperature_at_cloud_top",
        "units": "K",
    },
    "clwvi": {
        "source_var": "wp",
        "long_name": "Mean cloud water path",
        "standard_name": "cloud_liquid_water_path",
        "units": "cm",
    },
}

# clt has no isccp error variable
ERROR_SPECS = {
    "ctp": {
        "source_var": "sigma_pc_time",
        "long_name": "cloud-top pressure (PC) mean standard deviation over time",
        "standard_name": "air_pressure_at_cloud_top_error",
        "units": "hpa",
    },
    "ctt": {
        "source_var": "sigma_tc_time",
        "long_name": "cloud-top temperature (TC) mean standard deviation over time",
        "standard_name": "air_temperature_at_cloud_top_error",
        "units": "K",
    },
    "clwvi": {
        "source_var": "sigma_wp_time",
        "long_name": "cloud water path (WP) mean standard deviation over time",
        "standard_name": "cloud_liquid_water_path_error",
        "units": "cm",
    },
}


def download_isccp_files():
    os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)
    for year in range(2012, 2018):
        for month in range(1, 13):
            if ((year == 2012) and month < 5) or ((year == 2017) and month > 6):
                continue
            month_str = f"{month:02d}"
            url = URL_BASE.format(year=year, month=month_str)
            local_path = f"{DOWNLOAD_FOLDER}/{url.split('/')[-1]}"
            logger.info(f"Downloading {year}-{month_str}: {url}")
            download_file(url, local_path)


def process_variable(ds_raw, variable, specs, save_path, mode="w"):
    source_var = specs["source_var"]
    ds = ds_raw[source_var].to_dataset(name=variable)

    valid_min = ds[variable].attrs.get("valid_min")
    valid_max = ds[variable].attrs.get("valid_max")

    ds = standardize_dims(ds)

    if valid_min is not None and valid_max is not None:
        ds[variable] = (
            ds[variable]
            .where(ds[variable] >= valid_min)
            .where(ds[variable] <= valid_max)
        )

    ds[variable].encoding = {}
    ds = ds.chunk(chunks={"time": 1, "lat": -1, "lon": -1})
    ds[variable].attrs = {
        "long_name": specs["long_name"],
        "standard_name": specs["standard_name"],
        "units": specs["units"],
        "source": SOURCE,
        "source_url": URL_BASE,
    }
    ds.to_zarr(save_path, mode=mode)


def main(save_cloud: bool):

    logger.info(f"Downloading {SOURCE} files")
    # download_isccp_files()

    logger.info(f"Opening dataset from {DOWNLOAD_FOLDER}")
    ds_raw = xr.open_mfdataset(f"{DOWNLOAD_FOLDER}/*")

    for variable in VARIABLES:
        if save_cloud:
            save_path = f"gs://climatebench/observations/{variable}_{SOURCE}.zarr"
        else:
            save_path = f"../observations/{variable}_{SOURCE}.zarr"

        logger.info(f"Processing {variable} data -> {save_path}")
        process_variable(ds_raw, variable, DATA_SPECS[variable], save_path, mode="w")

        if variable in ERROR_SPECS:
            logger.info(f"Processing {variable} error -> {save_path}")
            process_variable(
                ds_raw, "error", ERROR_SPECS[variable], save_path, mode="a"
            )
        else:
            logger.info(f"No error variable for {variable}, skipping")

    logger.info(f"Deleting raw download folder {DOWNLOAD_FOLDER}")
    shutil.rmtree(DOWNLOAD_FOLDER)
    logger.info("Done")

    return None


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=f"Download and process {SOURCE} cloud property data."
    )
    parser.add_argument(
        "--save_cloud",
        action="store_true",
        default=False,
        help="Save output on google cloud. If not set, saves locally.",
    )
    args = parser.parse_args()
    main(save_cloud=args.save_cloud)
