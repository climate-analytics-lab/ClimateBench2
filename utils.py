import logging

import dask.array as da
import numpy as np
import pandas as pd
import xarray as xr

logger = logging.getLogger(__name__)


def standardize_dims(ds: xr.Dataset, reset_coorinates: bool = False) -> xr.Dataset:
    """Fixes common problems with xarray datasets

    Args:
        ds (xr.Dataset): Dataset with spatial and temporal dimensions
        reset_coordinates (bool): Reset coordinates to regular grid. Default is False.

    Returns:
        xr.Dataset: Normalized dataset
    """
    # Rename dims if needed
    # first rename lat/lon
    rename_lat_lon = {}
    if ("latitude" in ds.dims) or ("latitude" in ds.variables):
        rename_lat_lon["latitude"] = "lat"
    if ("longitude" in ds.dims) or ("longitude" in ds.variables):
        rename_lat_lon["longitude"] = "lon"
    if ("Latitude" in ds.dims) or ("Latitude" in ds.variables):
        rename_lat_lon["Latitude"] = "lat"
    if ("Longitude" in ds.dims) or ("Longitude" in ds.variables):
        rename_lat_lon["Longitude"] = "lon"
    if ("nav_lat" in ds.dims) or ("nav_lat" in ds.variables):
        rename_lat_lon["nav_lat"] = "lat"
    if ("nav_lon" in ds.dims) or ("nav_lon" in ds.variables):
        rename_lat_lon["nav_lon"] = "lon"
    if rename_lat_lon:
        ds = ds.rename(rename_lat_lon)
    # atp, lat and lon should be dimensions if regular grid, or coordinates if curvlinear grid
    rename_dims = {}
    if "nlon" in ds.dims:
        rename_dims["nlon"] = "i"
    if "nlat" in ds.dims:
        rename_dims["nlat"] = "j"
    if "x" in ds.dims:
        rename_dims["x"] = "i" if "lon" in ds.variables else "lon"
    if "y" in ds.dims:
        rename_dims["y"] = "j" if "lat" in ds.variables else "lat"
    if "datetime" in ds.dims:
        rename_dims["datetime"] = "time"
    if rename_dims:
        ds = ds.rename(rename_dims)

    # fix time
    if "time" in ds.dims:
        ds["time"] = pd.to_datetime(ds["time"].dt.strftime("%Y-%m-01"))
        ds = ds.sortby("time")  # make sure its in the right order before slicing

    # only if rectilinear grid (tos is curvelinear grid)
    if (len(ds["lat"].dims) == 1) and (len(ds["lon"].dims) == 1):
        # Shift longitudes
        ds = ds.assign_coords(lon=(ds.lon % 360))
        ds = ds.sortby("lon")

        ds = ds.sortby("lat")

        if reset_coorinates:
            # fix coordinates
            lat_len = len(ds.lat)
            lon_len = len(ds.lon)
            lat_res = 180 / lat_len
            lon_res = 360 / lon_len
            lats = np.arange(-90 + lat_res / 2, 90, lat_res)
            lons = np.arange(lon_res / 2, 360, lon_res)
            ds = ds.assign_coords({"lat": lats, "lon": lons})

    else:
        # check that lat is increaseing
        sample_idx = 1
        test_lats = ds["lat"].isel(i=sample_idx)
        if test_lats[0] > test_lats[-1]:
            ds = ds.assign_coords(j=ds["j"][::-1])
            ds = ds.sortby("j")
        test_lons = ds["lon"].isel(j=sample_idx)

        # and that lon is 0 - 360
        ds["lon"] = ds["lon"] % 360
        if test_lons["lon"][0] != 0:
            # for sorting purposes
            ds = ds.assign_coords(i=test_lons["lon"].values)
            ds = ds.sortby("i")
            # reset to int array
            ds = ds.assign_coords(i=np.arange(len(test_lons["lon"].values)))

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
        store_path, compute=False, mode="w", consolidated=True
    )  # save template, will write each model to its region slice
