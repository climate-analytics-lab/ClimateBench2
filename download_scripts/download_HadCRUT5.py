import argparse
import logging
import os
import sys

import numpy as np
import xarray as xr

sys.path.append("..")
from utils import download_file, standardize_dims

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


### Source specific download script ###
SOURCE = "HadCRUT5"
VARIABLE = "tas"
CLOUD_PATH = "gs://climatebench/observations/tas_HadCRUT5.zarr"
LOCAL_PATH = "../observations/tas_HadCRUT5.zarr"
DOWNLOAD_URL = "https://www.metoffice.gov.uk/hadobs/hadcrut5/data/HadCRUT.5.0.2.0/analysis/HadCRUT.5.0.2.0.analysis.anomalies.ensemble_mean.nc"
CLIMATOLOGY_URL = "https://crudata.uea.ac.uk/cru/data/temperature/absolute_v5.nc"
RAW_LOCAL_PATH = f"../observations/{DOWNLOAD_URL.split('/')[-1]}"
CLIM_LOCAL_PATH = f"../observations/{CLIMATOLOGY_URL.split('/')[-1]}"
SOURCE_VARIABLE = "tas_mean"
CLIMATOLOGY_VARIABLE = "tem"
DATA_SPECS = {
    "long_name": "Near-Surface Air Temperature",
    "standard_name": "air_temperature",
    "units": "K",
    "source": SOURCE,
    "source_url": DOWNLOAD_URL,
}


def main(save_cloud: bool):

    logger.info(f"Downloading {SOURCE} {VARIABLE} anomalies from {DOWNLOAD_URL}")
    download_file(DOWNLOAD_URL, RAW_LOCAL_PATH)
    logger.info(f"Download complete. Opening dataset from {RAW_LOCAL_PATH}")
    ds_anom = xr.open_dataset(RAW_LOCAL_PATH, chunks={})
    ds_anom = standardize_dims(ds_anom)

    logger.info(f"Downloading climatology from {CLIMATOLOGY_URL}")
    download_file(CLIMATOLOGY_URL, CLIM_LOCAL_PATH)
    ds_clim = xr.open_dataset(CLIM_LOCAL_PATH, chunks={})
    ds_clim["time"] = np.arange(1, 13)
    ds_clim = ds_clim.rename({"time": "month"})
    ds_clim = standardize_dims(ds_clim)

    logger.info("Adding climatology to anomalies")
    ds_raw = (
        (ds_anom[SOURCE_VARIABLE].groupby("time.month") + ds_clim[CLIMATOLOGY_VARIABLE])
        .to_dataset(name=SOURCE_VARIABLE)
        .drop_vars("month")
    )

    logger.info("Standardizing dimensions and chunking")
    ds = ds_raw[SOURCE_VARIABLE].to_dataset(name=VARIABLE).drop_vars("realization")
    ds = standardize_dims(ds)
    ds[VARIABLE].encoding = {}
    ds = ds.chunk(chunks={"time": 1, "lat": -1, "lon": -1})

    logger.info("Converting units from degC to K")
    ds[VARIABLE] = ds[VARIABLE] + 273.15

    ds[VARIABLE].attrs = DATA_SPECS

    if save_cloud:
        save_path = CLOUD_PATH
    else:
        save_path = LOCAL_PATH
    logger.info(f"Saving dataset to {save_path}")
    ds.to_zarr(save_path)

    logger.info("Deleting raw files")
    os.remove(RAW_LOCAL_PATH)
    os.remove(CLIM_LOCAL_PATH)
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
