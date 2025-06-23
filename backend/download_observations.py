import argparse
import glob
import logging
import os

import ee
import geemap
import pandas as pd
import xarray as xr

from constants import (
    GOOGLE_CLOUD_PROJECT,
    HIST_START_DATE,
    OBSERVATION_DATA_SPECS,
    SSP_END_DATE,
)
from utils import standardize_dims

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class DownloadObservations:

    def __init__(self, variable, source):
        self.source = source
        self.variable = variable

        self.data_specs = OBSERVATION_DATA_SPECS[self.variable][self.source]
        self.local_data_path = self.data_specs["local_path"]
        self.cloud_data_path = self.data_specs["cloud_path"]
        self.source_var_name = self.data_specs["source_var_name"]

        self.temp_dir = "raw_data"

        self.ds_cleaned = None
        self.ds_raw = None
        self.var_attrs = None

    def download_raw_data(self):

        if self.data_specs.get("download_url", False):
            logger.info(f"downloading data from : {self.data_specs['download_url']}")
            ds = xr.open_dataset(self.data_specs["download_url"]).sel(
                time=slice(HIST_START_DATE, SSP_END_DATE)
            )

            self.var_attrs = ds[self.source_var_name].attrs

        elif self.data_specs.get("gee_image_collection", False):
            logger.info(
                f"downloading data from google earth engine image collection: {self.data_specs["gee_image_collection"]}"
            )
            ee.Authenticate()
            ee.Initialize(project=GOOGLE_CLOUD_PROJECT)

            gee_images = ee.ImageCollection(self.data_specs["gee_image_collection"])
            dataset = gee_images.filterDate(HIST_START_DATE, SSP_END_DATE)
            ds = geemap.ee_to_xarray(dataset.select(self.source_var_name))

            self.var_attrs = ds[self.source_var_name].attrs

        elif self.data_specs.get("wget_file_list", False):
            logger.info(
                f"downloading data from file paths in: {self.data_specs['wget_file_list']}"
            )
            # make temp dir to save data in
            if not os.path.exists(self.temp_dir):
                os.makedirs(self.temp_dir)
            os.system(
                f'wget --load-cookies ~/.urs_cookies --save-cookies ~/.urs_cookies --keep-session-cookies  --content-disposition -i "{self.data_specs['wget_file_list']}" -P {self.temp_dir}'
            )
            files = glob.glob(f"{self.temp_dir}/*")
            # tas files are one netcdf per year with no time dim. need to add time dims before combining
            # if other wget options are added, will need to generalize this
            ds_list = []
            for file in files:
                year = file.split(".")[1]
                month = file.split(".")[2]
                date = pd.to_datetime(f"{year}-{month}-01")
                temp_ds = xr.open_dataset(file, decode_times=False)
                temp_ds = temp_ds.expand_dims({"time": [date]})
                ds_list.append(temp_ds)
            ds = xr.concat(ds_list, dim="time")
            self.var_attrs = ds_list[0][self.source_var_name].attrs

        else:
            raise ValueError(
                f"No download method for variable: {self.variable} and source: {self.source}"
            )

        self.ds_raw = ds

    def unit_conversion(self, ds):
        if self.variable == "pr":
            logger.info("converting pr units to kg m-2 s-1")
            ds[self.variable] = ds[self.variable] / 86400
        if self.variable == "clt":
            logger.info("converting clt units to percet 0-100")
            ds[self.variable] = (
                ds[self.variable] / 100
            )  # values should range 0 - 100 (units %)

        return ds

    def standardize_data(self):
        if self.ds_raw is None:
            self.download_raw_data()

        logger.info("standardizing data")
        ds = self.ds_raw[self.source_var_name].to_dataset(name=self.variable)
        ds = standardize_dims(ds)
        ds[self.variable].encoding = {}
        ds = ds.chunk(chunks={"time": 1, "lat": -1, "lon": -1})

        self.var_attrs["long_name"] = self.data_specs["long_name"]
        self.var_attrs["standard_name"] = self.data_specs["standard_name"]

        if ds[self.variable].attrs.get("units", None) != self.data_specs["units"]:
            ds = self.unit_conversion(ds)
        self.var_attrs["units"] = self.data_specs["units"]
        ds[self.variable].attrs = self.var_attrs

        self.ds_cleaned = ds

    def save_data(self, save_to_cloud=False):
        if self.ds_cleaned is None:
            self.standardize_data()

        logger.info(f"saving data locally: {self.local_data_path}")
        self.ds_cleaned.to_zarr(self.local_data_path)

        if save_to_cloud:
            logger.info(f"uploading to cloud : {self.cloud_data_path}")
            os.system(f"gsutil -m cp -r {self.local_data_path} {self.cloud_data_path}")

        if os.path.exists(self.temp_dir):
            logger.info("Deleting raw data files")
            raw_files = glob.glob(f"{self.temp_dir}/*")
            for file in raw_files:
                os.remove(file)
            os.rmdir(self.temp_dir)


def main(variable, source, save_to_cloud):
    logger.info(f"Starting download for variable: {variable} from: {source}")
    downloader = DownloadObservations(variable, source)
    downloader.save_data(save_to_cloud=save_to_cloud)
    logger.info("Download complete")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Data processing for model benchmarking"
    )
    parser.add_argument(
        "--variable",
        help="Input value for the main function",
    )
    parser.add_argument(
        "--source",
        help="Input value for the main function",
    )
    parser.add_argument(
        "--save_to_cloud",
        action="store_true",
        default=False,
        help="Save data on google cloud if passed, if not passsed saved locally",
    )
    args = parser.parse_args()
    main(variable=args.variable, source=args.source, save_to_cloud=args.save_to_cloud)
