import argparse
import logging
import os
import sys

import pandas as pd
import xarray as xr

sys.path.append("..")
from utils import download_file, standardize_dims

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


### Source specific download script ###
SOURCE = "NASA_GISS"
VARIABLE = "tas"
CLOUD_PATH = f"gs://climatebench/observations/{VARIABLE}_{SOURCE}.zarr"
LOCAL_PATH = f"../observations/{VARIABLE}_{SOURCE}.zarr"
DOWNLOAD_ANOM_URL = "https://downloads.psl.noaa.gov/Datasets/gistemp/combined/250km/air.2x2.250.mon.anom.comb.nc"
RAW_ANOM_LOCAL_PATH = f"../observations/{DOWNLOAD_ANOM_URL.split('/')[-1]}"
DOWNLOAD_LTM_URL = "https://downloads.psl.noaa.gov/Datasets/gistemp/combined/250km/air.2x2.250.mon.1991-2020.ltm.comb.nc"
RAW_LTM_LOCAL_PATH = f"../observations/{DOWNLOAD_LTM_URL.split('/')[-1]}"
SOURCE_VARIABLE = "air"
DATA_SPECS = {
    "long_name": "Near-Surface Air Temperature",
    "standard_name": "air_temperature",
    "units": "K",
    "source": SOURCE,
    "source_url": DOWNLOAD_ANOM_URL,
    "climatology_url": DOWNLOAD_LTM_URL,
}


def main(save_cloud: bool):

    logger.info(f"Downloading {SOURCE} {VARIABLE} anomalies from {DOWNLOAD_ANOM_URL}")
    download_file(DOWNLOAD_ANOM_URL, RAW_ANOM_LOCAL_PATH)
    ds_raw_anom = xr.open_dataset(RAW_ANOM_LOCAL_PATH, decode_times=False)
    logger.info(f"Download complete. Opening dataset from {RAW_ANOM_LOCAL_PATH}")

    logger.info(f"Downloading {SOURCE} {VARIABLE} climatology from {DOWNLOAD_LTM_URL}")
    download_file(DOWNLOAD_LTM_URL, RAW_LTM_LOCAL_PATH)
    ds_raw_ltm = xr.open_dataset(RAW_LTM_LOCAL_PATH, decode_times=False)
    logger.info(f"Download complete. Opening dataset from {RAW_LTM_LOCAL_PATH}")

    logger.info("Preprocessing anomaly data into standard temperature")
    ds_raw_anom["time"] = pd.to_datetime("1800-01-01") + pd.to_timedelta(
        ds_raw_anom["time"], unit="D"
    )
    ds_raw_ltm["time"] = pd.date_range("2020-01-01", "2020-12-31", freq="MS")
    ds_raw = (
        (
            ds_raw_anom[SOURCE_VARIABLE].groupby("time.month")
            + ds_raw_ltm[SOURCE_VARIABLE].groupby("time.month").mean()
        )
        .to_dataset(name=SOURCE_VARIABLE)
        .drop_vars("month")
    )

    logger.info("Standardizing dimensions and chunking")
    ds = ds_raw[SOURCE_VARIABLE].to_dataset(name=VARIABLE)
    ds = standardize_dims(ds)
    ds[VARIABLE] = ds[VARIABLE] + 273.15
    ds[VARIABLE].encoding = {}
    ds = ds.chunk(chunks={"time": 1, "lat": -1, "lon": -1})

    ds[VARIABLE].attrs = DATA_SPECS

    if save_cloud:
        save_path = CLOUD_PATH
    else:
        save_path = LOCAL_PATH
    logger.info(f"Saving dataset to {save_path}")
    ds.to_zarr(save_path)
    logger.info(f"Deleting raw files {RAW_ANOM_LOCAL_PATH} and {RAW_LTM_LOCAL_PATH}")
    os.remove(RAW_ANOM_LOCAL_PATH)
    os.remove(RAW_LTM_LOCAL_PATH)
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
