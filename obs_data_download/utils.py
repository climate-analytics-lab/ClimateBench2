import dask.array as da
import numpy as np
import pandas as pd
import xarray as xr


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
