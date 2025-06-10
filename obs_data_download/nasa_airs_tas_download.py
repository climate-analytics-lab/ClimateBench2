import datetime as dt
import glob
import logging
import os

import dask.array as da
import numpy as np
import pandas as pd
import xarray as xr

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def standardize_dims(ds: xr.Dataset) -> xr.Dataset:
    """Fixes common problems with xarray datasets

    Args:
        ds (xr.Dataset): Dataset with spatial and temporal dimensions

    Returns:
        xr.Dataset: Normalized dataset
    """
    # Rename dims if needed
    rename_dims = {}
    if "latitude" in ds.dims:
        rename_dims["latitude"] = "lat"
    if "longitude" in ds.dims:
        rename_dims["longitude"] = "lon"
    if "Latitude" in ds.dims:
        rename_dims["Latitude"] = "lat"
    if "Longitude" in ds.dims:
        rename_dims["Longitude"] = "lon"
    if "datetime" in ds.dims:
        rename_dims["datetime"] = "time"
    if rename_dims:
        ds = ds.rename(rename_dims)

    # fix time
    ds["time"] = pd.to_datetime(ds["time"].dt.strftime("%Y-%m-01"))

    # Shift longitudes
    ds = ds.assign_coords(lon=(ds.lon % 360))
    ds = ds.sortby("lon")

    ds = ds.sortby("lat")

    # fix coordinates
    lat_len = len(ds.lat)
    lon_len = len(ds.lon)
    lat_res = 180 / lat_len
    lon_res = 360 / lon_len
    lats = np.arange(-90 + lat_res / 2, 90, lat_res)
    lons = np.arange(lon_res / 2, 360, lon_res)
    ds = ds.assign_coords({"lat": lats, "lon": lons})

    return ds


def build_zarr_store(var_name: str, dims_dict: dict, attributes: dict, store_path: str):
    """Build the template for the zarr file that will be populated with data later on

    Args:
        var_name (str): Name of variable to save data as
        dims_dict (dict): dictionairy with dimesion names as keys and dimension values as items
        attributes (dict): dataset attribures
        store_path (str): where to save data
    """
    array_size = []
    chunk_size = []
    for key, item in dims_dict.items():
        array_size.append(len(item))
        chunk_size.append(1) if key == "time" else chunk_size.append(-1)
    data = da.zeros(array_size, chunks=(chunk_size))
    # Build dataset
    ds = xr.Dataset(
        data_vars={var_name: (dims_dict.keys(), data)},
        coords=dims_dict,
    )
    ds.attrs = attributes
    ds.to_zarr(
        store_path, compute=False, mode="w"
    )  # save template, will write each model to its region slice


def main():
    logger.info("begining download script for NASA AIRS surface temperature data")
    # download raw files
    # takes ~20 min to download
    os.system(
        'wget --load-cookies ~/.urs_cookies --save-cookies ~/.urs_cookies --keep-session-cookies  --content-disposition -i "subset_AIRS3STM_7.0_20250521_202757_.txt"'
    )

    logger.info("raw data download complete. beginning zarr creation process.")

    # save zarr template
    zarr_store_file_path = "observational_data/tas_nasa_airs.zarr"
    tas_files = glob.glob("AIRS*")
    times = pd.date_range("2005-01-01", "2024-12-01", freq="MS")
    ds = xr.open_dataset(tas_files[0], decode_times=False)
    ds = ds.expand_dims({"time": [times[0]]})  # placeholder
    ds_fixed = standardize_dims(ds)
    dims_dict = {"time": times, "lat": ds_fixed.lat.values, "lon": ds_fixed.lon.values}
    build_zarr_store(
        var_name="tas",
        dims_dict=dims_dict,
        attributes=ds.attrs,
        store_path=zarr_store_file_path,
    )

    # now go through all
    for date in times:
        year = date.year
        month = "0" + str(date.month)
        file_name = glob.glob(f"AIRS.{year}.{month[-2:]}*")[0]
        ds = xr.open_dataset(file_name, decode_times=False)
        ds = ds.expand_dims({"time": [date]})

        ds_fixed = standardize_dims(ds)
        ds_fixed = ds_fixed["SurfAirTemp_A"].to_dataset(name="tas")
        ds_fixed.tas.encoding = {}
        ds_fixed.chunk(chunks={"time": 1, "lat": -1, "lon": -1}).to_zarr(
            zarr_store_file_path, region="auto"
        )
        logger.info(f"wrote {date} to zarr store")
        # delete file
        os.remove(file_name)

    os.remove("Overview_of_the_AIRS_Mission.pdf")
    os.remove("V7_L3_User_Guide.pdf")
    # save data on google cloud --> need to set up google cloud storage bucket
    logger.info(f"data saved to {zarr_store_file_path}")


if __name__ == "__main__":
    main()
