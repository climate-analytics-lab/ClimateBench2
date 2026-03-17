import argparse
import logging
import os
import sys

import numpy as np
import pandas as pd
import xarray as xr

sys.path.append("..")
from utils import download_file, standardize_dims

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


### Source specific download script ###
SOURCE = "Berkeley_BEST"
VARIABLE = "tas"
CLOUD_PATH = f"gs://climatebench/observations/{VARIABLE}_{SOURCE}.zarr"
LOCAL_PATH = f"../observations/{VARIABLE}_{SOURCE}.zarr"
DOWNLOAD_URL = "https://berkeley-earth-temperature.s3.us-west-1.amazonaws.com/Global/Gridded/Land_and_Ocean_LatLong1.nc"
RAW_LOCAL_PATH = "../observations/Land_and_Ocean_LatLong1.nc"
DATA_SPECS = {
    "long_name": "Near-Surface Air Temperature",
    "standard_name": "air_temperature",
    "units": "K",
    "source": SOURCE,
    "source_url": DOWNLOAD_URL,
}


def main(save_cloud: bool):

    logger.info(f"Downloading {SOURCE} {VARIABLE} data from {DOWNLOAD_URL}")
    download_file(DOWNLOAD_URL, RAW_LOCAL_PATH)
    logger.info(f"Download complete. Opening dataset from {RAW_LOCAL_PATH}")
    ds = xr.open_dataset(RAW_LOCAL_PATH, chunks={})

    logger.info("Fixing time coordinate")
    years = ds["time"].astype(int)
    months = (ds["time"] - years) * 12 + 0.5
    dates = pd.to_datetime(
        pd.DataFrame({"year": years, "month": months, "day": [1] * years.size})
    )
    ds = ds.assign_coords({"time": dates})
    ds = ds.assign_coords({"month_number": np.arange(1, 13)})
    ds = ds.rename({"month_number": "month"})

    logger.info("Combining anomaly and climatology, converting C to K")
    ds[VARIABLE] = (
        ds["temperature"].groupby("time.month") + ds["climatology"]
    ) + 273.15

    logger.info("Standardizing dimensions and chunking")
    ds = standardize_dims(ds[VARIABLE].to_dataset(name=VARIABLE))
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
