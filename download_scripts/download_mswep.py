import argparse
import calendar
import logging
import shutil
import sys

import pandas as pd
import xarray as xr

sys.path.append("..")
from utils import standardize_dims

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


### Source specific download script ###
# NOTE: MSWEP data must be downloaded manually via rclone from Google Drive before running.
# Example rclone command:
#   rclone sync -v --drive-shared-with-me GoogleDrive:/MSWEP_V315_test {raw_data_dir}
# The raw_data_dir should contain Past/Monthly/ and NRT/Monthly/ subdirectories.
SOURCE = "mswep"
VARIABLE = "pr"
CLOUD_PATH = f"gs://climatebench/observations/{VARIABLE}_{SOURCE}.zarr"
LOCAL_PATH = f"../observations/{VARIABLE}_{SOURCE}.zarr"
DEFAULT_RAW_DATA_DIR = "../observations/mswep_raw"
DATA_SPECS = {
    "long_name": "Average Monthly Rate of Precipitation",
    "standard_name": "precipitation_flux",
    "units": "kg m**-2 s**-1",
    "source": SOURCE,
}


def main(save_cloud: bool, raw_data_dir: str, keep_raw: bool):

    hist_data_path = f"{raw_data_dir}/Past/Monthly/*"
    nrt_data_path = f"{raw_data_dir}/NRT/Monthly/*"

    logger.info(f"Opening historical MSWEP data from {hist_data_path}")
    ds_hist = xr.open_mfdataset(hist_data_path, chunks={})
    logger.info(f"Opening NRT MSWEP data from {nrt_data_path}")
    ds_nrt = xr.open_mfdataset(nrt_data_path, chunks={})

    logger.info("Concatenating historical and NRT data")
    ds = xr.concat(
        [ds_hist.sel(time=slice(ds_hist["time"].min(), ds_nrt["time"].min())), ds_nrt],
        dim="time",
    ).rename({"precipitation": VARIABLE})

    logger.info("Converting units from mm/month to kg m-2 s-1")
    df = pd.DataFrame({"year": ds["time.year"].data, "month": ds["time.month"].data})
    df["num_days"] = df.apply(
        lambda x: calendar.monthrange(x["year"], x["month"])[1], axis=1
    )
    df["time"] = ds["time"]
    time_scale = df.set_index("time")["num_days"].to_xarray()
    ds[VARIABLE] = ds[VARIABLE] * 1000 * 1000 / (time_scale * 24 * 60 * 60)

    ds[VARIABLE].attrs = DATA_SPECS
    ds[VARIABLE].encoding = {}

    logger.info("Standardizing dimensions and chunking")
    ds = standardize_dims(ds=ds)

    if save_cloud:
        save_path = CLOUD_PATH
    else:
        save_path = LOCAL_PATH
    logger.info(f"Saving dataset to {save_path}")
    ds.chunk({"time": 1, "lat": -1, "lon": -1}).to_zarr(save_path)

    if not keep_raw:
        logger.info(f"Deleting raw data directory {raw_data_dir}")
        shutil.rmtree(raw_data_dir)
    logger.info("Done")

    return None


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=f"Process {SOURCE} {VARIABLE} data. NOTE: raw data must be downloaded manually via rclone before running."
    )
    parser.add_argument(
        "--save_cloud",
        action="store_true",
        default=False,
        help="Save output on google cloud. If not set, saves locally.",
    )
    parser.add_argument(
        "--raw_data_dir",
        type=str,
        default=DEFAULT_RAW_DATA_DIR,
        help=f"Path to the directory containing Past/ and NRT/ MSWEP subdirectories. Default: {DEFAULT_RAW_DATA_DIR}",
    )
    parser.add_argument(
        "--keep_raw",
        action="store_true",
        default=False,
        help="Keep the raw data directory after processing. If not set, it will be deleted.",
    )
    args = parser.parse_args()
    main(
        save_cloud=args.save_cloud,
        raw_data_dir=args.raw_data_dir,
        keep_raw=args.keep_raw,
    )
