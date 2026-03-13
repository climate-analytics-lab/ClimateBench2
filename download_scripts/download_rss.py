import argparse
import logging
import os
import sys

import numpy as np
import pandas as pd
import xarray as xr

sys.path.append("..")
# from .. import utils
from utils import download_file, standardize_dims

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


### Source specifc download script ###
SOURCE = "RSS"
VARIABLE = "tcwv"
CLOUD_PATH = f"gs://climatebench/observations/{VARIABLE}_{SOURCE}.zarr"
LOCAL_PATH = f"../observations/{VARIABLE}_{SOURCE}.zarr"
DOWNLOAD_URL = "https://data.remss.com/vapor/monthly_1deg/merged_vapor_1988-2025.nc"
RAW_LOCAL_PATH = "../observations/merged_vapor_1988-2025.nc"
SOURCE_VARIABLE = "merged_vapor"
DATA_SPECS = {
    "long_name": "Total column vertically-integrated water vapour",
    "standard_name": "total_column_water_vapor",
    "units": "kg m**-2",
    "source": SOURCE,
    "source_url": DOWNLOAD_URL,
}


def main(save_cloud: bool):

    logger.info(f"Downloading {SOURCE} {VARIABLE} data from {DOWNLOAD_URL}")
    download_file(DOWNLOAD_URL, RAW_LOCAL_PATH)
    logger.info(f"Download complete. Opening dataset from {RAW_LOCAL_PATH}")
    ds_raw = xr.open_dataset(RAW_LOCAL_PATH)

    logger.info("Fixing time coordinate")
    years = ds_raw["time"].astype(int)
    months = ((ds_raw["time"] - years) * 12 + 1).astype(int)
    dates = pd.to_datetime(
        pd.DataFrame({"year": years, "month": months, "day": [1] * years.size})
    )
    ds_raw = ds_raw.assign_coords({"time": dates})
    ds_raw = ds_raw.assign_coords({"month_number": np.arange(1, 13)})
    ds_raw = ds_raw.rename({"month_number": "month"})

    logger.info("Standardizing dimensions and chunking")
    ds = ds_raw[SOURCE_VARIABLE].to_dataset(name=VARIABLE)
    ds = standardize_dims(ds)
    ds[VARIABLE].encoding = {}
    ds = ds.chunk(chunks={"time": 1, "lat": -1, "lon": -1})

    ds[VARIABLE].attrs = DATA_SPECS

    if save_cloud:
        save_path = CLOUD_PATH
    else:
        save_path = LOCAL_PATH
    logger.info(f"Saving dataset to {save_path}")
    ds.to_zarr(save_path)
    logger.info(f"Deleting raw file {RAW_LOCAL_PATH}")
    os.remove(RAW_LOCAL_PATH)
    logger.info("Done")

    return None


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=f"Download and process {SOURCE} {VARIABLE} data."
    )
    parser.add_argument(
        "--save_cloud",
        action="store_true",
        default=False,
        help="Save output on google cloud. If not set, saves locally.",
    )
    args = parser.parse_args()
    main(save_cloud=args.save_cloud)
