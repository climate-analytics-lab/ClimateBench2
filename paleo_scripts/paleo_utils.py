"""Small self-contained helpers for the paleo pipeline.

Lifted verbatim from the repository-root ``utils.py`` when the legacy
``constants.py`` / ``utils.py`` / ``benchmark_scrips/`` island was retired
(delineation plan §9): these three functions were the only part of it the
paleo scripts still used, and keeping a 400-line module and its
`google.cloud` / `dask` / `requests` dependency tree alive for them was the
last thing standing between the repository and the plan's "no legacy code
remains" condition.

Everything here is deliberately ordinary xarray/pandas — nothing in it is
protocol. The protocol's own Tier III scoring lives in
``climatebench2/diags/tier3_paleo.py`` and reads this pipeline's *output*,
not its code.
"""

from __future__ import annotations

import io
import logging
import os
from csv import writer

import numpy as np
import pandas as pd
import xarray as xr

logger = logging.getLogger(__name__)


def is_curvilinear(da):
    """Return True if lat/lon are 2D coordinates rather than 1D dimension coords."""
    return "lat" not in da.dims


def spatial_dims(da):
    """Return the names of the horizontal spatial dimensions."""
    if is_curvilinear(da):
        return list(da["lat"].dims)  # e.g. ["j", "i"]
    return ["lat", "lon"]


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
    if not is_curvilinear(ds):
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
        # check that lat is increasing
        j_dim, i_dim = spatial_dims(ds)
        sample_idx = 1
        test_lats = ds["lat"].isel({i_dim: sample_idx})
        if test_lats[0] > test_lats[-1]:
            ds = ds.assign_coords({j_dim: ds[j_dim][::-1]})
            ds = ds.sortby(j_dim)
        test_lons = ds["lon"].isel({j_dim: sample_idx})

        # and that lon is 0 - 360
        ds["lon"] = ds["lon"] % 360
        if test_lons["lon"][0] != 0:
            # for sorting purposes
            ds = ds.assign_coords({i_dim: test_lons["lon"].values})
            ds = ds.sortby(i_dim)
            # reset to int array
            ds = ds.assign_coords({i_dim: np.arange(len(test_lons["lon"].values))})

    return ds


def save_results_csv(result_df, results_file, save_to_cloud, overwrite):
    """Save a results DataFrame to CSV locally or to GCS bucket "climatebench".

    Args:
        result_df: pandas DataFrame with one row of results
        results_file: local path (e.g. "../results/ecs/ecs_results.csv")
        save_to_cloud: if True save to GCS; False saves locally
        overwrite: if True overwrite existing local file instead of appending
    """
    if save_to_cloud:
        # Imported here, not at module scope: google-cloud-storage is only
        # needed by `--save-to-cloud`, and requiring it to run a local
        # benchmark is what made the old utils.py hard to retire.
        from google.cloud import storage

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
