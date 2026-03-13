import argparse
import logging
import shutil
import sys

import earthaccess
import xarray as xr

sys.path.append("..")
from utils import standardize_dims

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


### Source specific download script ###
SOURCE = "NASA_IMERG"
VARIABLE = "pr"
CLOUD_PATH = f"gs://climatebench/observations/{VARIABLE}_{SOURCE}.zarr"
LOCAL_PATH = f"../observations/{VARIABLE}_{SOURCE}.zarr"
RAW_DOWNLOAD_DIR = "../observations/imerg_raw"
EARTHDATA_SHORT_NAME = "GPM_3IMERGM"
EARTHDATA_VERSION = "07"
TEMPORAL_RANGE = ("2005-01-01", "2024-12-31")
# conversion from mm/min to kg m-2 s-1: * 1000 [mm/m] * 1000 [kg/m3] / (60 [min/hr] * 60 [s/min])
UNIT_CONVERSION = 1000 * 1000 / (60 * 60)
DATA_SPECS = {
    VARIABLE: {
        "long_name": "Average Monthly Rate of Precipitation",
        "standard_name": "precipitation_flux",
        "units": "kg m-2 s-1",
        "source": SOURCE,
    },
    "error": {
        "long_name": "Absolute Error: Monthly Rate of Precipitation",
        "standard_name": "precipitation_flux_error",
        "units": "kg m**-2 s**-1",
        "source": SOURCE,
    },
}


def main(save_cloud: bool):

    logger.info("Authenticating with NASA Earthdata")
    earthaccess.login()

    logger.info(
        f"Searching for {EARTHDATA_SHORT_NAME} v{EARTHDATA_VERSION} granules from {TEMPORAL_RANGE[0]} to {TEMPORAL_RANGE[1]}"
    )
    results = earthaccess.search_data(
        short_name=EARTHDATA_SHORT_NAME,
        version=EARTHDATA_VERSION,
        temporal=TEMPORAL_RANGE,
        bounding_box=(-180, -90, 180, 90),
    )
    logger.info(f"Found {len(results)} granules. Downloading to {RAW_DOWNLOAD_DIR}")
    downloaded_files = earthaccess.download(results, local_path=RAW_DOWNLOAD_DIR)

    logger.info(f"Opening {len(downloaded_files)} files")
    ds = xr.open_mfdataset(downloaded_files, group="Grid")
    ds = ds[["precipitation", "randomError"]]
    ds["time"] = ds.indexes["time"].to_datetimeindex(time_unit="ns")
    ds = standardize_dims(ds=ds)

    ds = ds.rename({"precipitation": VARIABLE, "randomError": "error"})

    logger.info("Converting units from mm/min to kg m-2 s-1")
    ds[VARIABLE] = ds[VARIABLE] * UNIT_CONVERSION
    ds["error"] = ds["error"] * UNIT_CONVERSION

    ds[VARIABLE].encoding = {}
    ds["error"].encoding = {}
    ds[VARIABLE].attrs = DATA_SPECS[VARIABLE]
    ds["error"].attrs = DATA_SPECS["error"]

    if save_cloud:
        save_path = CLOUD_PATH
    else:
        save_path = LOCAL_PATH
    logger.info(f"Saving dataset to {save_path}")
    ds.chunk({"time": 1, "lat": -1, "lon": -1}).to_zarr(save_path)

    logger.info(f"Deleting raw download directory {RAW_DOWNLOAD_DIR}")
    shutil.rmtree(RAW_DOWNLOAD_DIR)
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
