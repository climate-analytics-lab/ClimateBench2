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
SOURCE = "CRU_TS"
VARIABLE = "tas"
CLOUD_PATH = f"gs://climatebench/observations/{VARIABLE}_{SOURCE}.zarr"
LOCAL_PATH = f"../observations/{VARIABLE}_{SOURCE}.zarr"
DOWNLOAD_URL = "https://dap.ceda.ac.uk/badc/cru/data/cru_ts/cru_ts_4.09/data/tmp/cru_ts4.09.1901.2024.tmp.dat.nc.gz"
RAW_ZIPPED_PATH = "../observations/cru_ts4.09.1901.2024.tmp.dat.nc.gz"
RAW_NC_PATH = "../observations/cru_ts4.09.1901.2024.tmp.dat.nc"
DATA_SPECS = {
    VARIABLE: {
        "long_name": "near-surface temperature",
        "standard_name": "air_temperature",
        "units": "K",
        "source": SOURCE,
        "source_url": DOWNLOAD_URL,
    },
    "error": {
        "long_name": "mean of absolute diffs between interpolant anomalies and interpolated anomaly, where available",
        "standard_name": "mae",
        "units": "K",
        "source": SOURCE,
        "source_url": DOWNLOAD_URL,
    },
}
SOURCE_VARIABLES = {
    VARIABLE: "tmp",
    "error": "mae",
}


def main(save_cloud: bool, access_token: str):

    logger.info(f"Downloading {SOURCE} {VARIABLE} data from {DOWNLOAD_URL}")
    headers = {"Authorization": f"Bearer {access_token}"}
    download_file(DOWNLOAD_URL, RAW_ZIPPED_PATH, headers=headers)

    logger.info(f"Download complete. Decompressing {RAW_ZIPPED_PATH}")
    subprocess.run(["gunzip", RAW_ZIPPED_PATH], check=True)

    logger.info(f"Opening dataset from {RAW_NC_PATH}")
    ds_raw = xr.open_dataset(RAW_NC_PATH)

    if save_cloud:
        save_path = CLOUD_PATH
    else:
        save_path = LOCAL_PATH

    logger.info(f"Processing {VARIABLE}")
    ds_tas = ds_raw[SOURCE_VARIABLES[VARIABLE]].to_dataset(name=VARIABLE)
    ds_tas = standardize_dims(ds_tas)
    ds_tas[VARIABLE].encoding = {}
    ds_tas = ds_tas.chunk(chunks={"time": 1, "lat": -1, "lon": -1})
    # convert units from C to K
    ds_tas[VARIABLE] = ds_tas[VARIABLE] + 273.15
    ds_tas[VARIABLE].attrs = DATA_SPECS[VARIABLE]
    logger.info(f"Saving {VARIABLE} to {save_path}")
    ds_tas.to_zarr(save_path)

    logger.info("Processing error")
    ds_err = ds_raw[SOURCE_VARIABLES["error"]].to_dataset(name="error")
    ds_err = standardize_dims(ds_err)
    ds_err["error"].encoding = {}
    ds_err = ds_err.chunk(chunks={"time": 1, "lat": -1, "lon": -1})
    ds_err["error"].attrs = DATA_SPECS["error"]
    logger.info(f"Appending error to {save_path}")
    ds_err.to_zarr(save_path, mode="a")

    logger.info(f"Deleting raw file {RAW_NC_PATH}")
    os.remove(RAW_NC_PATH)
    logger.info("Done")

    return None


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=f"Download and process {SOURCE} {VARIABLE} data."
    )
    parser.add_argument(
        "--access_token",
        required=True,
        type=str,
        help="Access token for downloading data from CEDA Archive. Register and create access token here: https://services.ceda.ac.uk/account/token/",
    )
    parser.add_argument(
        "--save_cloud",
        action="store_true",
        default=False,
        help="Save output on google cloud. If not set, saves locally.",
    )
    args = parser.parse_args()
    main(save_cloud=args.save_cloud, access_token=args.access_token)
