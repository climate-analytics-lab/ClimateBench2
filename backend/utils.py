import glob
import logging
import os

import dask.array as da
import numpy as np
import pandas as pd
import xarray as xr
from pyesgf.search import SearchConnection

from constants import (
    ENSEMBLE_MEMBERS,
    HIST_END_DATE,
    HIST_START_DATE,
    OBSERVATION_DATA_PATHS,
    SSP_END_DATE,
    SSP_START_DATE,
    VARIABLE_FREQUENCY_GROUP,
)

logger = logging.getLogger(__name__)


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
    if "time" in ds.dims:
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
        store_path, compute=False, mode="w", consolidated=True
    )  # save template, will write each model to its region slice


class DataFinder:

    def __init__(self, org, model, variable):
        self.org = org
        self.model = model
        self.variable = variable
        self.frequency = VARIABLE_FREQUENCY_GROUP[self.variable]
        self.obs_data_path = OBSERVATION_DATA_PATHS[self.variable]

    def check_local_files(
        self,
        mip: str,
        experiment: str,
        ensemble: str,
    ) -> list[str]:
        local_data_path = f"{os.environ['HOME']}/climate_data/CMIP6/{mip}/{self.org}/{self.model}/{experiment}/{ensemble}/{self.frequency}/{self.variable}/*/*/*"
        local_files = glob.glob(local_data_path)
        self.local_files = local_files
        return local_files

    def check_gcs_files(self, mip, experiment, ensemble):
        df = pd.read_csv("https://cmip6.storage.googleapis.com/pangeo-cmip6.csv")
        df = df[
            (df["member_id"] == ensemble)
            & (df["activity_id"] == mip)
            & (df["experiment_id"] == experiment)
            & (df["variable_id"] == self.variable)
            & (df["table_id"] == self.frequency)
            & (df["institution_id"] == self.org)
            & (df["source_id"] == self.model)
        ]
        if len(df) > 1:
            # potentially two versions, so take the newer one
            df["version_date"] = pd.to_datetime(df["version"], format="%Y%m%d")
            df = (
                df.sort_values("version_date", ascending=False)
                .drop_duplicates(
                    [
                        "activity_id",
                        "institution_id",
                        "source_id",
                        "experiment_id",
                        "member_id",
                        "table_id",
                        "variable_id",
                        "grid_label",
                    ]
                )
                .drop(columns=["version_date"])
            )
        elif len(df) == 0:
            logger.warning("No results found on GCS.")
            return None

        return df["zstore"].values[0]

    def check_esgf_files(
        self,
        experiment: str,
        ensemble: str,
        data_node="esgf-data1.llnl.gov",
    ) -> list[str]:
        conn = SearchConnection("https://esgf-data.dkrz.de/esg-search", distrib=True)
        ctx = conn.new_context(
            project="CMIP6",
            source_id=self.model,
            experiment_id=experiment,
            variable=self.variable,
            variant_label=ensemble,
            frequency=self.frequency[-3:],  # fx for area, mon for variables
            data_node=data_node,
        )
        results = ctx.search()

        if len(results) < 1:
            logger.warning(
                f"No results found on ESGF node {data_node}. Try another node."
            )
            return None

        elif len(results) > 1:
            logger.warning(
                f"{len(results)} results returned. Please filter more (e.g. grid, version)."
            )
            return None

        else:
            file_url_list = []
            files = results[0].file_context().search()
            for file in files:
                file_url_list.append(file.opendap_url)
            df = pd.DataFrame(file_url_list, columns=["file_url"])
            if self.frequency != "fx":
                df["file_start_year"] = (
                    df["file_url"].str.split("_", expand=True)[7].str[:4].astype(int)
                )
                df["file_end_year"] = (
                    df["file_url"].str.split("_", expand=True)[7].str[7:11].astype(int)
                )
                if experiment == "historical":
                    df = df[df["file_end_year"] > 2005]
                else:
                    df = df[df["file_start_year"] < 2025]
            return df["file_url"].tolist()

    def read_data(self, mip: str, experiment: str, ensemble: str) -> xr.Dataset:
        local_file_path = self.check_local_files(mip, experiment, ensemble)
        if not local_file_path:
            gcs_file_path = self.check_gcs_files(mip, experiment, ensemble)
            if not gcs_file_path:
                esgf_file_path = self.check_esgf_files(experiment, ensemble)
                if not esgf_file_path:
                    raise ValueError(
                        f"can't find data for {mip}, {self.org}, {self.model}, {experiment}, {ensemble}, {self.frequency}, {self.variable}"
                    )
                else:
                    # read data from esgf
                    ds_list = []
                    for file in esgf_file_path:
                        ds_list.append(xr.open_dataset(file))
                    ds = xr.concat(ds_list)
            else:
                # read from google storage
                # gcs should only return one path since zarr, not folder of netCDFs
                ds = xr.open_zarr(gcs_file_path, chunks={})
        else:
            # read from local
            ds = xr.open_mfdataset(local_file_path)

        return ds

    def load_ensemble_mean(self, mip, experiment, time_slice):
        ensemble_ds_list = []
        for ensemble in ENSEMBLE_MEMBERS:
            ds = self.read_data(
                mip=mip,
                experiment=experiment,
                ensemble=ensemble,
            )
            ds = ds.sel(time=time_slice)
            ds.expand_dims({"ensemble": [ensemble]})
            ensemble_ds_list.append(ds)
        return xr.concat(
            ensemble_ds_list, dim="ensemble", combine_attrs="override"
        ).mean(dim="ensemble")

    def load_model_ds(self):
        historical_ens_mean = self.load_ensemble_mean(
            mip="CMIP",
            experiment="historical",
            time_slice=slice(HIST_START_DATE, HIST_END_DATE),
        )
        ssp_ens_mean = self.load_ensemble_mean(
            mip="ScenarioMIP",
            experiment="ssp245",
            time_slice=slice(SSP_START_DATE, SSP_END_DATE),
        )

        model_ds = xr.concat([historical_ens_mean, ssp_ens_mean], dim="time")
        # should standardize data?
        return standardize_dims(model_ds)

    def load_cell_area_ds(self, cell_var_name):
        # patch for now
        old_var_name = self.variable
        old_freq_name = self.frequency
        self.variable = cell_var_name
        self.frequency = "fx"
        fx_ds = self.read_data(
            mip="CMIP",
            experiment="historical",
            ensemble=ENSEMBLE_MEMBERS[0],
        )
        self.variable = old_var_name
        self.frequency = old_freq_name
        return standardize_dims(fx_ds)

    def load_obs_ds(self):
        return standardize_dims(xr.open_zarr(self.obs_data_path))
