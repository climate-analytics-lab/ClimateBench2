import argparse
import glob
import logging
import os
import shutil
import subprocess
import sys

import pandas as pd
import xarray as xr

sys.path.append("..")
from utils import download_file, standardize_dims

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


### Source specific download script ###
SOURCE = "HadGHCND"
VARIABLES = ["tasmax", "tasmin"]
DOWNLOAD_URL = "https://www.metoffice.gov.uk/hadobs/hadghcnd/data/HadGHCND_TXTN_acts_1950-2014_15102015.nc.tgz"
RAW_ZIPPED_PATH = "../observations/HadGHCND_TXTN_acts_1950-2014_15102015.nc.tgz"
RAW_EXTRACT_DIR = "../observations/HadGHCND_raw"
SOURCE_VARIABLES = {
    "tasmax": "tmax",
    "tasmin": "tmin",
}
DATA_SPECS = {
    "tasmax": {
        "long_name": "Daily Actual Maximum (TMAX) Surface (2m) Air Temperature",
        "standard_name": "air_temperature",
        "units": "K",
        "source": SOURCE,
        "source_url": DOWNLOAD_URL,
    },
    "tasmin": {
        "long_name": "Daily Actual Minimum (TMIN) Surface (2m) Air Temperature",
        "standard_name": "air_temperature",
        "units": "K",
        "source": SOURCE,
        "source_url": DOWNLOAD_URL,
    },
}


def main(save_cloud: bool):

    logger.info(f"Downloading {SOURCE} data from {DOWNLOAD_URL}")
    download_file(DOWNLOAD_URL, RAW_ZIPPED_PATH)
    logger.info(
        f"Download complete. Extracting {RAW_ZIPPED_PATH} into {RAW_EXTRACT_DIR}"
    )
    os.makedirs(RAW_EXTRACT_DIR, exist_ok=True)
    subprocess.run(["tar", "-xzf", RAW_ZIPPED_PATH, "-C", RAW_EXTRACT_DIR], check=True)
    os.remove(RAW_ZIPPED_PATH)

    raw_nc_files = glob.glob(f"{RAW_EXTRACT_DIR}/*.nc")
    logger.info(f"Opening dataset from {len(raw_nc_files)} files: {raw_nc_files}")
    ds_raw = xr.open_mfdataset(raw_nc_files, decode_times=False)
    ds_raw["time"] = pd.to_datetime(ds_raw["time"] - 719529, unit="d")

    for variable in VARIABLES:
        logger.info(f"Processing {variable}")
        ds = ds_raw[SOURCE_VARIABLES[variable]].to_dataset(name=variable)
        ds = standardize_dims(ds)
        ds[variable].encoding = {}
        ds = ds.chunk(chunks={"time": 1, "lat": -1, "lon": -1})

        # convert units from C to K
        ds[variable] = ds[variable] + 273.15

        ds[variable].attrs = DATA_SPECS[variable]

        if save_cloud:
            save_path = f"gs://climatebench/observations/{variable}_{SOURCE}.zarr"
        else:
            save_path = f"../observations/{variable}_{SOURCE}.zarr"
        logger.info(f"Saving {variable} to {save_path}")
        ds.to_zarr(save_path)

    logger.info(f"Deleting raw extract directory {RAW_EXTRACT_DIR}")
    shutil.rmtree(RAW_EXTRACT_DIR)
    logger.info("Done")

    return None


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=f"Download and process {SOURCE} tasmax and tasmin data."
    )
    parser.add_argument(
        "--save_cloud",
        action="store_true",
        default=False,
        help="Save output on google cloud. If not set, saves locally.",
    )
    args = parser.parse_args()
    main(save_cloud=args.save_cloud)
