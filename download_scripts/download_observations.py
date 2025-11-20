import argparse
import glob
import logging
import os
import shutil
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Optional

import ee
import geemap
import numpy as np
import pandas as pd
import requests
import xarray as xr

sys.path.append("..")

from constants import (
    GOOGLE_CLOUD_PROJECT,
    HIST_START_DATE,
    OBSERVATION_DATA_SPECS,
    SSP_END_DATE,
)
from utils import standardize_dims

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

@contextmanager
def temporary_directory():
    """Context manager for temporary directory"""
    temp_dir = tempfile.mkdtemp()
    try:
        yield temp_dir
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def download_file(url: str, output_path: str) -> None:
    """Download a file with basic error handling"""
    logger.info(f"Downloading {url}")
    try:
        with requests.get(url, stream=True, timeout=300) as response:
            response.raise_for_status()
            with open(output_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
        logger.info(f"Download completed: {output_path}")
    except Exception as e:
        logger.error(f"Download failed: {e}")
        raise


class DownloadObservations:
    """Main class for downloading and processing observation data"""

    def __init__(self, variable: str, source: str):
        self.source = source
        self.variable = variable

        if variable not in OBSERVATION_DATA_SPECS:
            raise ValueError(f"Variable '{variable}' not supported")
        if source not in OBSERVATION_DATA_SPECS[variable]:
            raise ValueError(
                f"Source '{source}' not available for variable '{variable}'"
            )

        self.data_specs = OBSERVATION_DATA_SPECS[self.variable][self.source]
        self.local_data_path = (
            "/".join(os.getcwd().split("/")[:-1]) + "/" + self.data_specs["local_path"]
        )
        self.cloud_data_path = self.data_specs["cloud_path"]
        self.source_var_name = self.data_specs["source_var_name"]

        # Ensure output directory exists
        os.makedirs(os.path.dirname(self.local_data_path), exist_ok=True)

        self.ds_cleaned = None
        self.ds_raw = None
        self.var_attrs = None

    def download_raw_data(self):
        """Download raw data based on data specifications"""
        logger.info(f"Starting download for {self.variable} from {self.source}")

        with temporary_directory() as temp_dir:
            if self.data_specs.get("download_url"):
                self._download_from_url(temp_dir)
            elif self.data_specs.get("gee_image_collection"):
                self._download_from_gee()
            elif self.data_specs.get("wget_file_list"):
                self._download_from_wget_list(temp_dir)
            elif self.data_specs.get("raw_local_path"):
                self._read_manual_download()
            else:
                raise ValueError(
                    f"No download method for {self.variable}/{self.source}"
                )

    def _read_manual_download(self):
        local_path = (
            "/".join(os.getcwd().split("/")[:-1])
            + "/"
            + self.data_specs["raw_local_path"]
        )
        ds = xr.open_dataset(local_path, chunks={})
        self.var_attrs = ds[self.source_var_name].attrs
        self.ds_raw = ds

    def _download_from_url(self, temp_dir: str):
        """Download data from URL(s)"""
        if self.data_specs.get("download_multiple", False):
            # Handle multiple file downloads
            start_year = self.data_specs["file_date_range"][0]
            end_year = self.data_specs["file_date_range"][1]

            for year in range(start_year, end_year):
                download_url = self.data_specs["download_url"].format(year)
                temp_file_name = f"{temp_dir}/{download_url.split('/')[-1]}"
                try:
                    download_file(download_url, temp_file_name)
                except Exception as e:
                    logger.warning(f"Failed to download year {year}: {e}")

            ds = xr.open_mfdataset(f"{temp_dir}/*", chunks={}).sel(
                time=slice(HIST_START_DATE, SSP_END_DATE)
            )
            ds = ds.resample(time="MS").mean()
        else:
            # Single file download
            temp_file_name = (
                f"{temp_dir}/{self.data_specs['download_url'].split('/')[-1]}"
            )
            download_file(self.data_specs["download_url"], temp_file_name)

            ds = xr.open_dataset(temp_file_name, chunks={}).sel(
                time=slice(HIST_START_DATE, SSP_END_DATE)
            )

        self.var_attrs = ds[self.source_var_name].attrs
        self.ds_raw = ds

    def _download_from_gee(self):
        """Download data from Google Earth Engine"""
        logger.info(f"Downloading from GEE: {self.data_specs['gee_image_collection']}")

        try:
            ee.Authenticate()
            ee.Initialize(project=GOOGLE_CLOUD_PROJECT)

            gee_images = ee.ImageCollection(self.data_specs["gee_image_collection"])
            dataset = gee_images.filterDate(HIST_START_DATE, SSP_END_DATE)
            ds = geemap.ee_to_xarray(dataset.select(self.source_var_name))

            self.var_attrs = ds[self.source_var_name].attrs
            self.ds_raw = ds
        except Exception as e:
            logger.error(f"GEE download failed: {e}")
            raise

    def _download_from_wget_list(self, temp_dir: str):
        """Download data using wget file list"""
        logger.info(f"Downloading from file list: {self.data_specs['wget_file_list']}")

        result = os.system(
            f"wget --load-cookies ~/.urs_cookies --save-cookies ~/.urs_cookies "
            f'--keep-session-cookies --content-disposition -i "{self.data_specs["wget_file_list"]}" -P {temp_dir}'
        )

        if result != 0:
            logger.error("Wget download failed")
            raise RuntimeError("Wget download failed")

        files = glob.glob(f"{temp_dir}/*")
        ds_list = []

        for file in files:
            try:
                # This logic is specific to your file naming convention
                year = file.split(".")[1]
                month = file.split(".")[2]
                date = pd.to_datetime(f"{year}-{month}-01")
                temp_ds = xr.open_dataset(file, decode_times=False, chunks={})
                temp_ds = temp_ds.expand_dims({"time": [date]})
                ds_list.append(temp_ds)
            except Exception as e:
                logger.warning(f"Failed to process file {file}: {e}")

        if not ds_list:
            raise RuntimeError("No valid datasets from wget files")

        ds = xr.concat(ds_list, dim="time")
        self.var_attrs = ds_list[0][self.source_var_name].attrs
        self.ds_raw = ds

    def hadcrut5_anomaly_preprocess(self):
        """Preprocess HadCRUT5 anomaly data by adding climatology"""
        logger.info("Processing HadCRUT5 anomaly data with climatology")

        with temporary_directory() as temp_dir:
            clim_file_path = (
                f"{temp_dir}/{self.data_specs['climatology_url'].split('/')[-1]}"
            )
            download_file(self.data_specs["climatology_url"], clim_file_path)

            ds = xr.open_dataset(clim_file_path, chunks={})
            ds["time"] = np.arange(1, 13)
            ds = ds.rename({"time": "month", "lat": "latitude", "lon": "longitude"})

            self.ds_raw = (
                self.ds_raw[self.source_var_name].groupby("time.month")
                + ds[self.data_specs["climatology_var_name"]]
            ).to_dataset(name=self.source_var_name)

            self.ds_raw[self.source_var_name].attrs["units"] = ds[
                self.data_specs["climatology_var_name"]
            ].attrs["units"]

    def modis_od550aer_error_preprocess(self):
        """Create error data from land/water mask"""
        logger.info("Creating error from land/water mask")
        ds = self.ds_raw.isel(time=0).squeeze().drop_vars("time", errors="ignore")

        err_da = ds[self.source_var_name].where(ds[self.source_var_name] == 0, 1).T
        err_abs_da = err_da * self.data_specs["error_values"]["ocean"]["absolute"]
        err_ds = err_abs_da.where(
            err_abs_da != 0, self.data_specs["error_values"]["land"]["absolute"]
        ).to_dataset(name="absolute_error")
        err_rel_da = err_da * self.data_specs["error_values"]["ocean"]["relative"]
        err_ds["relative_error"] = err_rel_da.where(
            err_rel_da != 0, self.data_specs["error_values"]["land"]["relative"]
        )

        err_ds = err_ds.assign_coords(lon=(err_ds.lon % 360))
        err_ds = err_ds.sortby("lon")

        # Read od550aer values
        local_var_path = (
            "/".join(os.getcwd().split("/")[:-1])
            + "/"
            + OBSERVATION_DATA_SPECS[self.variable]["nasa_modis"]["local_path"]
        )
        if os.path.exists(local_var_path):
            var_ds = xr.open_zarr(local_var_path, chunks={})
        else:
            var_ds = xr.open_zarr(
                OBSERVATION_DATA_SPECS[self.variable]["nasa_modis"]["cloud_path"],
                chunks={},
            )

        self.ds_raw = (
            var_ds[self.variable] * err_ds["relative_error"] + err_ds["absolute_error"]
        ).to_dataset(name=self.source_var_name)

    def unit_conversion(self, ds):
        """Apply unit conversions based on variable type"""
        if self.variable == "pr":
            logger.info("Converting pr units to kg m-2 s-1")
            ds[self.variable] = ds[self.variable] / 86400
        if self.variable == "clt":
            logger.info("Converting clt units to percent 0-100")
            ds[self.variable] = ds[self.variable] / 100
        if self.variable == "tas":
            logger.info("Converting tas units to K")
            ds[self.variable] = ds[self.variable] + 273.15
        if (self.variable == "od550aer") & ("error" not in self.source):
            logger.info("Scaling od550aer data by 0.001")
            ds[self.variable] = ds[self.variable] / 1000
        return ds

    def standardize_data(self):
        """Standardize the dataset format"""
        if self.ds_raw is None:
            self.download_raw_data()

        logger.info("Standardizing data")
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
        """Save processed data"""
        if self.ds_cleaned is None:
            self.standardize_data()

        logger.info(f"Saving data locally: {self.local_data_path}")
        self.ds_cleaned.to_zarr(self.local_data_path)

        if save_to_cloud:
            logger.info(f"Uploading to cloud: {self.cloud_data_path}")
            result = os.system(
                f"gsutil -m cp -r {self.local_data_path} {self.cloud_data_path}"
            )
            if result != 0:
                logger.warning("Cloud upload failed")


def main():
    parser = argparse.ArgumentParser(
        description="Download and process observational climate data"
    )
    parser.add_argument(
        "--variable", required=True, help="Climate variable to download"
    )
    parser.add_argument("--source", required=True, help="Data source")
    parser.add_argument(
        "--save_to_cloud", action="store_true", help="Upload to Google Cloud Storage"
    )

    args = parser.parse_args()

    downloader = DownloadObservations(args.variable, args.source)
    downloader.download_raw_data()

    # Apply preprocessing based on source
    if args.source == "HadCRUT5":
        downloader.hadcrut5_anomaly_preprocess()
    if args.source == "nasa_modis_error" and args.variable == "od550aer":
        downloader.modis_od550aer_error_preprocess()

    downloader.standardize_data()
    downloader.save_data(save_to_cloud=args.save_to_cloud)
    logger.info("Processing completed successfully")


if __name__ == "__main__":
    main()
