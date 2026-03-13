import argparse
import logging
import os
import sys

import xarray as xr

sys.path.append("..")
from utils import download_file, standardize_dims

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


### Source specific download script ###
SOURCE = "noaa_gpcp"
VARIABLE = "pr"
CLOUD_PATH = "gs://climatebench/observations/pr_noaa_gpcp.zarr"
LOCAL_PATH = "../observations/pr_noaa_gpcp.zarr"
DOWNLOAD_URL = "https://downloads.psl.noaa.gov/Datasets/gpcp/precip.mon.mean.nc"
RAW_LOCAL_PATH = f"../observations/{DOWNLOAD_URL.split('/')[-1]}"
SOURCE_VARIABLE = "precip"
DATA_SPECS = {
    "long_name": "Average Monthly Rate of Precipitation",
    "standard_name": "precipitation_flux",
    "units": "kg m**-2 s**-1",
    "source": SOURCE,
    "source_url": DOWNLOAD_URL,
}


def main(save_cloud: bool):

    logger.info(f"Downloading {SOURCE} {VARIABLE} data from {DOWNLOAD_URL}")
    download_file(DOWNLOAD_URL, RAW_LOCAL_PATH)
    logger.info(f"Download complete. Opening dataset from {RAW_LOCAL_PATH}")
    ds_raw = xr.open_dataset(RAW_LOCAL_PATH, chunks={})

    logger.info("Standardizing dimensions and chunking")
    ds = ds_raw[SOURCE_VARIABLE].to_dataset(name=VARIABLE)
    ds = standardize_dims(ds)
    ds[VARIABLE].encoding = {}
    ds = ds.chunk(chunks={"time": 1, "lat": -1, "lon": -1})

    logger.info("Converting units from mm/day to kg m**-2 s**-1")
    ds[VARIABLE] = ds[VARIABLE] / 86400

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
