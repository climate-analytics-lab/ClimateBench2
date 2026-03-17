import argparse
import logging
import os
import subprocess
import sys

import xarray as xr

sys.path.append("..")
from utils import download_file, standardize_dims

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


### Source specific download script ###
SOURCE = "HadISST"
VARIABLE = "tos"
CLOUD_PATH = f"gs://climatebench/observations/{VARIABLE}_{SOURCE}.zarr"
LOCAL_PATH = f"../observations/{VARIABLE}_{SOURCE}.zarr"
DOWNLOAD_URL = "https://www.metoffice.gov.uk/hadobs/hadisst/data/HadISST_sst.nc.gz"
RAW_ZIPPED_PATH = "../observations/HadISST_sst.nc.gz"
RAW_NC_PATH = "../observations/HadISST_sst.nc"
SOURCE_VARIABLE = "sst"
FILL_VALUE = -1000
DATA_SPECS = {
    "long_name": "Sea Surface Temperature",
    "standard_name": "sea_surface_temperature",
    "units": "degC",
    "source": SOURCE,
    "source_url": DOWNLOAD_URL,
}


def main(save_cloud: bool):

    logger.info(f"Downloading {SOURCE} {VARIABLE} data from {DOWNLOAD_URL}")
    download_file(DOWNLOAD_URL, RAW_ZIPPED_PATH)
    logger.info(f"Download complete. Decompressing {RAW_ZIPPED_PATH}")
    subprocess.run(["gunzip", RAW_ZIPPED_PATH], check=True)

    logger.info(f"Opening dataset from {RAW_NC_PATH}")
    ds_raw = xr.open_dataset(RAW_NC_PATH)

    logger.info(f"Masking fill values ({FILL_VALUE})")
    ds_raw[SOURCE_VARIABLE] = ds_raw[SOURCE_VARIABLE].where(
        ds_raw[SOURCE_VARIABLE] != FILL_VALUE
    )

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
    logger.info(f"Deleting raw file {RAW_NC_PATH}")
    os.remove(RAW_NC_PATH)
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
