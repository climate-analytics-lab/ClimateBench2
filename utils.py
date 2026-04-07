import io
import logging
import os
import time
from csv import writer

import dask.array as da
import numpy as np
import pandas as pd
import requests
import xarray as xr
from google.cloud import storage

from constants import EARTH_RADIUS

logger = logging.getLogger(__name__)


def standardize_dims(
    ds: xr.Dataset,
    reset_coorinates: bool = False,
    convert_cftime: bool = False,
) -> xr.Dataset:
    """Fixes common problems with xarray datasets

    Args:
        ds (xr.Dataset): Dataset with spatial and temporal dimensions
        reset_coordinates (bool): Reset coordinates to regular grid. Default is False.
        convert_cftime (bool): Convert cftime datetime coordinates to numpy datetime64.
            Useful when the dataset uses a non-standard calendar (e.g. 360-day, noleap).
            Dates that fall outside the numpy datetime64 range will raise a ValueError.
            Default is False.

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
        if convert_cftime:
            try:
                ds = ds.convert_calendar("standard", use_cftime=False)
            except Exception as e:
                logger.warning(f"Could not convert cftime to datetime: {e}")
        try:
            ds["time"] = pd.to_datetime(ds["time"].dt.floor("D"))
            time_diff = np.median(np.diff(ds.time.values))
            is_monthly = time_diff > np.timedelta64(20, "D")
            if is_monthly:
                # Force all to the 1st of the month
                ds["time"] = ds.time.dt.floor("D") - pd.to_timedelta(
                    ds.time.dt.day - 1, unit="D"
                )
        except (ValueError, TypeError, pd.errors.OutOfBoundsDatetime):
            logger.warning(
                "Could not convert time to pandas datetime (out-of-bounds years); "
                "keeping original time coordinates"
            )
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


def download_file(
    url: str, output_path: str, max_retries: int = 5, headers: dict = {}
) -> None:
    """Download a file with the ability to resume after a Connection broken error."""
    for attempt in range(max_retries):
        resume_byte = 0
        mode = "wb"

        # Check if we already have a partial file
        if os.path.exists(output_path):
            resume_byte = os.path.getsize(output_path)
            mode = "ab"  # Append binary mode
            logger.info(f"Resuming download from byte {resume_byte}")

        # headers = {}
        if resume_byte > 0:
            headers["Range"] = f"bytes={resume_byte}-"

        try:
            # Setting stream=True is vital for large .nc files
            with requests.get(url, headers=headers, stream=True, timeout=30) as r:
                # 416 means the range is unsatisfied (often means file is already done)
                if r.status_code == 416:
                    logger.info("File already fully downloaded.")
                    return

                r.raise_for_status()

                with open(output_path, mode) as f:
                    for chunk in r.iter_content(chunk_size=1024 * 1024):  # 1MB chunks
                        if chunk:
                            f.write(chunk)

            logger.info(f"Download completed: {output_path}")
            return  # Exit loop if successful

        except (
            requests.exceptions.ConnectionError,
            requests.exceptions.ChunkedEncodingError,
        ) as e:
            logger.warning(
                f"Connection lost on attempt {attempt + 1}: {e}. Retrying..."
            )
            time.sleep(2)  # Short pause before retrying
            continue

    raise Exception(f"Failed to download after {max_retries} attempts.")


def compute_weighted_annual_mean(ds, variable, weights, lat_min=None, lat_max=None):
    """Compute area-weighted regional-mean annual-mean time series.

    Args:
        ds: xr.Dataset containing the variable
        variable: variable name string
        weights: cos(lat) weights (full grid)
        lat_min: southern latitude bound (None for global)
        lat_max: northern latitude bound (None for global)

    Returns:
        numpy array of annual-mean regional-mean values
    """
    da = ds[variable]

    if lat_min is not None or lat_max is not None:
        lat = ds["lat"]
        mask = True
        if lat_min is not None:
            mask = mask & (lat >= lat_min)
        if lat_max is not None:
            mask = mask & (lat <= lat_max)
        da = da.where(mask, drop=True)
        w = weights.where(mask, drop=True)
    else:
        w = weights

    regional_mean = da.weighted(w).mean(dim=["lat", "lon"])
    n_months = len(regional_mean)
    n_years = n_months // 12
    regional_mean = regional_mean.isel(time=slice(0, n_years * 12))
    annual_mean = regional_mean.values.reshape(n_years, 12).mean(axis=1)

    return annual_mean


def compute_toa_net(data):
    """TOA net downward flux (W/m2): rsdt - rsut - rlut."""
    return data["rsdt"]["rsdt"] - data["rsut"]["rsut"] - data["rlut"]["rlut"]


def compute_sfc_net(data):
    """Surface net flux into ocean (W/m2).

    F_sfc = (rsds - rsus) + (rlds - rlus) - hfss - hfls

    Sign convention: hfss and hfls are positive upward in CMIP6, so
    subtracting them gives the net downward flux into the surface/ocean.
    """
    return (
        (data["rsds"]["rsds"] - data["rsus"]["rsus"])
        + (data["rlds"]["rlds"] - data["rlus"]["rlus"])
        - data["hfss"]["hfss"]
        - data["hfls"]["hfls"]
    )


def compute_meridional_transport(zonal_mean_flux, lat):
    """Meridional energy transport by cumulative integration from the S pole.

    MET(phi) = 2*pi*a^2 * integral_{-pi/2}^{phi} F(phi') cos(phi') dphi'

    Args:
        zonal_mean_flux: xr.DataArray with at least a 'lat' dim, in W/m2.
        lat: latitude coordinate in degrees.

    Returns:
        xr.DataArray of meridional energy transport (W).
    """
    lat_rad = np.deg2rad(lat)

    dlat = np.abs(np.diff(lat_rad))
    dlat = np.append(dlat, dlat[-1])
    dlat = xr.DataArray(dlat, dims=["lat"], coords={"lat": lat})

    cos_lat = np.cos(lat_rad)
    cos_lat = xr.DataArray(cos_lat, dims=["lat"], coords={"lat": lat})

    integrand = zonal_mean_flux * cos_lat * dlat * 2 * np.pi * EARTH_RADIUS**2
    return integrand.cumsum(dim="lat")


def save_results_csv(result_df, results_file, save_to_cloud, overwrite):
    """Save a results DataFrame to CSV locally or to GCS bucket "climatebench".

    Args:
        result_df: pandas DataFrame with one row of results
        results_file: local path (e.g. "../results/ecs/ecs_results.csv")
        save_to_cloud: if True save to GCS; False saves locally
        overwrite: if True overwrite existing local file instead of appending
    """
    if save_to_cloud:
        gcs_path = results_file[3:]  # strip "../" -> "results/benchmark/file.csv"
        storage_client = storage.Client(project="JCM and Benchmarking")
        bucket = storage_client.bucket("climatebench")
        blob = storage.Blob(bucket=bucket, name=gcs_path)
        if blob.exists(storage_client):
            existing_data = blob.download_as_text()
            output = io.StringIO(existing_data)
            output.seek(0, io.SEEK_END)
            writer_object = writer(output)
            writer_object.writerow(result_df.values.flatten().tolist())
            output.seek(0)
            blob.upload_from_string(output.getvalue(), content_type="text/csv")
        else:
            result_df.to_csv(f"gs://climatebench/{gcs_path}", index=False)
        logger.info(f"Results saved to cloud: gs://climatebench/{gcs_path}")
    else:
        results_dir = os.path.dirname(results_file)
        if overwrite or not os.path.isfile(results_file):
            os.makedirs(results_dir, exist_ok=True)
            result_df.to_csv(results_file, index=False)
        else:
            with open(results_file, "a") as f:
                writer_object = writer(f)
                writer_object.writerow(result_df.values.flatten().tolist())
        logger.info(f"Results saved locally: {results_file}")
