import argparse
import logging
import os
import shutil
import subprocess
import sys

import cdsapi
import numpy as np
import pandas as pd
import xarray as xr

sys.path.append("..")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


### Source specifc download script ###
SOURCE = "OSI_SAF"
VARIABLE = "siconc"
CLOUD_PATH = f"gs://climatebench/observations/{VARIABLE}_{SOURCE}.zarr"
LOCAL_PATH = f"../observations/{VARIABLE}_{SOURCE}.zarr"
RAW_DATA_FOLDER = "../observations/raw_data/"

SOURCE_VARIABLE = "ice_conc"
DATA_SPECS = {
    "long_name": "fully filtered concentration of sea ice using atmospheric correction of brightness temperatures and open water filters",
    "standard_name": "sea_ice_area_fraction",
    "units": "percent",
    "grid_mapping": "Lambert_Azimuthal_Grid",
    "download_url": "https://cds.climate.copernicus.eu/datasets/satellite-sea-ice-concentration",
}


# Need to set up csdapi key for this to work
def download_cdr_data(year: str):
    # climate data record, only downloads up to 2020
    dataset = "satellite-sea-ice-concentration"
    request = {
        "variable": "all",
        "sensor": "ssmis",
        "region": ["northern_hemisphere", "southern_hemisphere"],
        "cdr_type": ["cdr", "icdr"],
        "temporal_aggregation": "monthly",
        "year": [year],
        "month": [
            "01",
            "02",
            "03",
            "04",
            "05",
            "06",
            "07",
            "08",
            "09",
            "10",
            "11",
            "12",
        ],
        "version": "3_1",
    }

    logger.info(f"Submitting CDS API request for dataset '{dataset}'")
    client = cdsapi.Client()
    local_file_path = client.retrieve(dataset, request).download()
    logger.info(f"Download complete. Raw data saved to {local_file_path}")
    return local_file_path


def download_icdr_data():
    # interm climate data record, downloads more recent years
    dataset = "satellite-sea-ice-concentration"
    request = {
        "variable": "all",
        "sensor": "ssmis",
        "region": ["northern_hemisphere", "southern_hemisphere"],
        "cdr_type": ["icdr"],
        "temporal_aggregation": "monthly",
        "year": ["2021", "2022", "2023", "2024", "2025"],
        "month": [
            "01",
            "02",
            "03",
            "04",
            "05",
            "06",
            "07",
            "08",
            "09",
            "10",
            "11",
            "12",
        ],
        "version": "3_0",
    }

    logger.info(f"Submitting CDS API request for dataset '{dataset}'")
    client = cdsapi.Client()
    local_file_path = client.retrieve(dataset, request).download()
    logger.info(f"Download complete. Raw data saved to {local_file_path}")
    return local_file_path


def main(save_cloud: bool):

    logger.info(f"Starting {SOURCE} {VARIABLE} download")
    os.makedirs(RAW_DATA_FOLDER, exist_ok=True)
    for year in range(1978, 2021):
        raw_data_path = download_cdr_data(year=str(year))
        subprocess.run(["unzip", raw_data_path, "-d", RAW_DATA_FOLDER], check=True)
        os.remove(raw_data_path)

    raw_data_path = download_icdr_data()
    subprocess.run(["unzip", raw_data_path, "-d", RAW_DATA_FOLDER], check=True)
    os.remove(raw_data_path)
    logger.info(f"Opening dataset from {raw_data_path}")
    ds_nh_raw = xr.open_mfdataset(f"{RAW_DATA_FOLDER}/*nh*.nc")
    ds_sh_raw = xr.open_mfdataset(f"{RAW_DATA_FOLDER}/*sh*.nc")
    ds_raw = xr.concat(
        [
            ds_nh_raw.expand_dims({"hemisphere": ["North"]}),
            ds_sh_raw.expand_dims({"hemisphere": ["South"]}),
        ],
        dim="hemisphere",
    )

    logger.info("Standardizing dimensions and chunking")
    ds = ds_raw[SOURCE_VARIABLE].to_dataset(name=VARIABLE)
    # add back in projection variable
    ds["Lambert_Azimuthal_Grid"] = ds_raw["Lambert_Azimuthal_Grid"]
    # ds = standardize_dims(ds) # special projection, don't want to force to standard grid
    ds["time"] = ds.time.dt.floor("D") - pd.to_timedelta(ds.time.dt.day - 1, unit="D")
    ds = ds.rename({"xc": "x", "yc": "y"})

    ds[VARIABLE].encoding = {}
    ds = ds.chunk(chunks={"time": 1, "x": -1, "y": -1, "hemisphere": -1})

    ds[VARIABLE].attrs = DATA_SPECS

    if save_cloud:
        save_path = CLOUD_PATH
    else:
        save_path = LOCAL_PATH
    logger.info(f"Saving dataset to {save_path}")
    ds.to_zarr(save_path)
    logger.info(f"Deleting raw download folder {RAW_DATA_FOLDER}")
    shutil.rmtree(RAW_DATA_FOLDER)
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
