"""Legacy DataFinder (model/observation data location + loading).

MetricCalculation and SaveResults were retired in delineation-plan Phase 2:
deterministic metrics + CRPS scoring now live in ClimateEval + 
climatebench2.scoring (CRPS with ESS correction, ensemble-consistency).
DataFinder remains until the last Tier I script is ported (Phase 3).
"""
import glob
import io
import logging
import os
import shutil
import sys

import numpy as np
import pandas as pd
import xarray as xr
from google.cloud import storage
from pyesgf.search import SearchConnection

sys.path.append("..")

from constants import OBSERVATION_DATA_SOURCES, SSP_EXPERIMENT, VARIABLE_FREQUENCY_GROUP
from utils import download_file, standardize_dims

logger = logging.getLogger(__name__)


def search_gcs(filters: dict, drop_older_versions: bool) -> pd.DataFrame:
    """Look for files in the public cmip6 google cloud bucket. Uses csv of data info to find path instead of a glob. Since files are saved as zarr, glob would return too many.
    Broken out from DataFinder class to make the gcs search more customizable for model variable data vs model cell area data.

    Args:
        filters (dict): Dict with columns as keys and filter values as items
        drop_older_versions (bool): drop duplicate entries, keeping the newer version

    Returns:
        pd.DataFrame: datasets matching filters on google cloud
    """
    # download because it is slow to read from GCS. should save locally for future runs
    cmip6_catalogue = "pangeo-cmip6.csv"
    if os.path.exists(cmip6_catalogue):
        df = pd.read_csv(cmip6_catalogue)
    else:
        download_file(
            "https://cmip6.storage.googleapis.com/pangeo-cmip6.csv", cmip6_catalogue
        )

    for column, value in filters.items():
        df = df[df[column] == value]

    if drop_older_versions:
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

    return df


class DataFinder:
    """The DataFinder class locates observational and model based on the variable and model passed.
    The model data returned is the ensemble mean of the historical and ssp experiments, concatenated together.
    The ensemble members and ssp experiment can be set in the constants file.
    The class can also find the model cell area data based on variable passed. If it can't be found, a proxy is created.
    """

    def __init__(
        self,
        model: str,
        variable: str,
        start_year: int,
        end_year: int,
        source: str = None,
    ):
        """Initialize DataFinder class.

        Args:
            model (str): Climate model of interest
            variable (str): Short name of climate variable
            start_year (int): Start of time period for model and observational data
            end_year (int): End of time period for model and observational data
            source (str): Observation data source. optional if just want model data.
        """
        self.model = model
        self.variable = variable
        self.source = source
        self.start_year = start_year
        self.end_year = end_year

        self.mip = "CMIP" if self.start_year < 2015 else "ScenarioMIP"
        # If the time range spans the two experiments
        if (self.end_year >= 2015) & (self.mip == "CMIP"):
            logger.warning(
                "Historical simulation data ends in 2014. End year will be set to 2014."
            )
            self.end_year = 2014

        self.variable_frequency_table = VARIABLE_FREQUENCY_GROUP[self.variable]
        self.area_variable_name = (
            "areacello" if self.variable_frequency_table == "Omon" else "areacella"
        )
        self.area_frequency_table = (
            "Ofx" if self.variable_frequency_table == "Omon" else "fx"
        )
        self.grid = "gn"  # resolved to "gr" on first catalog lookup if available
        if self.source:
            self.obs_data_path_local = (
                f"../observations/{self.variable}_{self.source}.zarr"
            )
            self.obs_data_path_cloud = (
                f"gs://climatebench/observations/{self.variable}_{self.source}.zarr"
            )
        self.ensemble_members = None

        self.model_ds = None
        self.fx_ds = None
        self.obs_ds = None

    def _resolve_grid(self, experiment: str) -> None:
        """For Omon variables, prefer 'gr' but fall back to 'gn' if unavailable.

        Checks the pangeo-cmip6 catalogue and updates self.grid in place.
        No-op for non-Omon tables (gn is already set).
        """
        if self.variable_frequency_table != "Omon":
            return
        cmip6_catalogue = "pangeo-cmip6.csv"
        if os.path.exists(cmip6_catalogue):
            df = pd.read_csv(cmip6_catalogue)
        else:
            download_file(
                "https://cmip6.storage.googleapis.com/pangeo-cmip6.csv",
                cmip6_catalogue,
            )
            df = pd.read_csv(cmip6_catalogue)
        base_query = dict(
            source_id=self.model,
            table_id=self.variable_frequency_table,
            variable_id=self.variable,
            experiment_id=experiment,
        )
        subset = df.loc[(df[list(base_query)] == pd.Series(base_query)).all(axis=1)]
        if "gr" in subset["grid_label"].values:
            self.grid = "gr"
            logger.info(f"  Grid resolved to 'gr' for {self.model} {self.variable}")
        else:
            self.grid = "gn"
            logger.info(
                f"  No 'gr' data found; falling back to 'gn' for {self.model} {self.variable}"
            )

    def check_local_files(
        self,
        mip: str,
        experiment: str,
        ensemble: str,
        frequency_table: str,
        variable: str,
    ) -> list[str]:
        """Find local file paths of climate model data. This is only relevant if using ESMValTool.

        Args:
            mip (str): ScenarioMIP or CMIP
            experiment (str): historical or ssp245
            ensemble (str): ensemble id rXiXpXfX
            frequency_table (str): Amon, Omon, Ofx, fx
            variable (str): short name of variable (ex: tas or areacella)

        Returns:
            list[str]: list of local file paths
        """
        local_data_path = f"{os.environ['HOME']}/climate_data/CMIP6/{mip}/*/{self.model}/{experiment}/{ensemble}/{frequency_table}/{variable}/*/*/*"
        local_files = glob.glob(local_data_path)
        self.local_files = local_files
        return local_files

    def check_gcs_files(
        self,
        mip: str,
        experiment: str,
        ensemble: str,
        frequency_table: str,
        variable: str,
    ) -> str:
        """Look for files in the public cmip6 google cloud bucket. Customize search keys for variable data vs cell area data.
        Sets the type of grid being used (gn for native grid, this is best), and returns the cloud storage path string ex: gs://path/to/data

        Args:
            mip (str): ScenarioMIP or CMIP
            experiment (str): historical or ssp245
            ensemble (str): ensemble id rXiXpXfX
            frequency_table (str): Amon, Omon, Ofx, fx
            variable (str): short name of variable (ex: tas or areacella)

        Returns:
            str: cloud storage file path
        """
        self._resolve_grid(experiment)
        search_keys = {
            "source_id": self.model,
            "table_id": frequency_table,
            "variable_id": variable,
            "member_id": ensemble,
            "activity_id": mip,
            "experiment_id": experiment,
            "grid_label": self.grid,
        }

        gcs_files = search_gcs(filters=search_keys, drop_older_versions=True)

        if (len(gcs_files) == 0) and ("area" in variable):
            search_keys.pop("member_id")
            search_keys.pop("activity_id")
            search_keys.pop("experiment_id")

            gcs_files = search_gcs(filters=search_keys, drop_older_versions=True)

        return gcs_files["zstore"].values[0]

    def check_esgf_files(
        self,
        experiment: str,
        ensemble: str,
        frequency_table: str,
        variable: str,
    ) -> list[str]:
        """Check the ESGF llnl node for data. This is a slower process than the google cloud search and will return multiple netcdf paths. Should be used as last resort if data can not be found on the cloud.

        Args:
            experiment (str): historical or ssp245
            ensemble (str): ensemble id rXiXpXfX
            frequency_table (str): Amon, Omon, Ofx, fx
            variable (str): short name of variable (ex: tas or areacella)

        Returns:
            list[str]: netcdf paths for accessing data
        """
        conn = SearchConnection("https://esgf-data.dkrz.de/esg-search", distrib=True)
        ctx = conn.new_context(
            project="CMIP6",
            source_id=self.model,
            experiment_id=experiment,
            variable=variable,
            variant_label=ensemble,
            frequency=frequency_table[-3:],  # O/fx for area, mon for variables
            facets="grid_label,version",
        )

        if ctx.hit_count == 0:
            logger.warning(
                "No results found on ESGF using https://esgf-data.dkrz.de/esg-search . Try another node."
            )
            return None

        else:
            results = ctx.search()
            file_url_list = []
            files = results[0].file_context().search()
            for file in files:
                file_url_list.append(file.opendap_url)
            df = pd.DataFrame(file_url_list, columns=["file_url"])
            return df["file_url"].tolist()

    def read_data(
        self,
        mip: str,
        experiment: str,
        ensemble: str,
        frequency_table: str,
        variable: str,
    ) -> xr.Dataset:
        """First check local files, then check google cloud storage, then check ESGF. For reading CMIP6 data.

        Args:
            mip (str): ScenarioMIP or CMIP
            experiment (str): historical or ssp245
            ensemble (str): ensemble id rXiXpXfX
            frequency_table (str): Amon, Omon, Ofx, fx
            variable (str): short name of variable (ex: tas or areacella)

        Raises:
            ValueError: Can't find data

        Returns:
            xr.Dataset: Climate model data for single experiment/ensemble
        """
        local_file_path = self.check_local_files(
            mip, experiment, ensemble, frequency_table, variable
        )
        if not local_file_path:
            gcs_file_path = self.check_gcs_files(
                mip, experiment, ensemble, frequency_table, variable
            )
            if not gcs_file_path:
                esgf_file_path = self.check_esgf_files(
                    experiment, ensemble, frequency_table, variable
                )
                if not esgf_file_path:
                    raise ValueError(
                        f"can't find data for {mip}, {self.model}, {experiment}, {ensemble}, {frequency_table}, {variable}"
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

    def load_ensemble_mean(
        self, mip: str, experiment: str, ensemble_mean: bool = True
    ) -> xr.Dataset:
        """Finds data for all ensemble members and returns the mean. Ensemble members based on constant.

        Args:
            mip (str): ScenarioMIP or CMIP
            experiment (str): historical or ssp245

        Returns:
            xr.Dataset: Ensemble mean of climate model data
        """
        ensemble_ds_list = []
        if self.ensemble_members is None:
            ensemble_members = self.find_ensemble_members(experiment=experiment)
            self.ensemble_members = ensemble_members
        for ensemble in self.ensemble_members:
            ds = self.read_data(
                mip=mip,
                experiment=experiment,
                ensemble=ensemble,
                frequency_table=self.variable_frequency_table,
                variable=self.variable,
            )
            ds = ds.drop_vars(
                ["lat_bnds", "lon_bnds", "time_bnds", "height", "wavelength"],
                errors="ignore",
            )
            ds = standardize_dims(ds, reset_coorinates=True, convert_cftime=True)
            ds = ds.expand_dims({"ensemble": [ensemble]})
            ensemble_ds_list.append(ds)
        model_ens_ds = xr.concat(
            ensemble_ds_list, dim="ensemble", combine_attrs="override"
        )
        if ensemble_mean:
            return model_ens_ds.mean(dim="ensemble")
        else:
            return model_ens_ds

    def load_model_ds(self, ensemble_mean=True) -> xr.Dataset:
        """Loads ensemble mean of historical and projected (ssp245) climate model data. Combines into one dataset and passes through standardizer function. Returned data should have "lat" "lon" and "time" dimensions that are sorted in ascending order. Lon values are from 0-360 and time is monthly on the first of the month.

        Returns:
            xr.Dataset: Analysis ready climate model data. Ensemble mean combination of historical and projected datasets.
        """
        if self.mip == "CMIP":
            experiment = "historical"
            time_slice = slice(f"{self.start_year}-01-01", "2014-12-31")
        else:
            experiment = SSP_EXPERIMENT
            time_slice = slice("2015-01-01", f"{self.end_year}-12-31")

        model_ds = self.load_ensemble_mean(
            mip=self.mip, experiment=experiment, ensemble_mean=ensemble_mean
        ).sel(time=time_slice)

        self.model_ds = model_ds
        return self.model_ds

    def load_experiment_ds(
        self,
        experiment: str,
        n_years: int = None,
        ensemble_mean: bool = True,
        mip: str = "CMIP",
    ) -> xr.Dataset:
        """Load data for a single CMIP6 experiment (e.g., piControl, abrupt-4xCO2).

        Args:
            experiment (str): CMIP6 experiment name (e.g., "piControl", "abrupt-4xCO2")
            n_years (int, optional): Number of years from start to load. None for all.
            ensemble_mean (bool): Return ensemble mean if True.
            mip (str): CMIP6 activity_id (default "CMIP"). Use "DAMIP" for hist-aer etc.

        Returns:
            xr.Dataset: Model data for the specified experiment.
        """
        ds = self.load_ensemble_mean(
            mip=mip, experiment=experiment, ensemble_mean=ensemble_mean
        )
        if n_years is not None:
            # Select first n_years by counting monthly time steps
            n_timesteps = n_years * 12
            if len(ds.time) > n_timesteps:
                ds = ds.isel(time=slice(0, n_timesteps))
        return ds

    def load_cell_area_ds(self) -> xr.DataArray:
        """Reads model cell area data. fx if atmospheric variable, Ofx if ocean variable. If data not found, prints warning and returns none. Can use cos(lat) as proxy for cell area. Passed through standardizer function to make sure dims are named correctly.

        Args:
            cell_var_name (str): areacella or areacello

        Returns:
            xr.DataArray: Dataarray of cell area data if available, else returns None
        """
        try:
            logger.info("Reading cell area data")
            if self.ensemble_members is None:
                ensemble_members = self.find_ensemble_members(experiment="historical")
                self.ensemble_members = ensemble_members
            fx_ds = self.read_data(
                mip="CMIP",
                experiment="historical",
                ensemble=self.ensemble_members[0],
                frequency_table=self.area_frequency_table,
                variable=self.area_variable_name,
            )
            # fill value issue with areacello data
            if "_FillValue" in fx_ds[self.area_variable_name].encoding:
                fill_val = fx_ds[self.area_variable_name].encoding["_FillValue"]
                fx_ds = fx_ds.where(fx_ds[self.area_variable_name] <= fill_val)
            self.fx_ds = standardize_dims(fx_ds)[self.area_variable_name]
        except:
            logger.warning(
                "No areacella/o data found. Using cos(lat) for cell weights."
            )
            if self.model_ds is None:
                _ = self.load_model_ds()
            weights = np.cos(np.deg2rad(self.model_ds.lat))
            weights = weights.expand_dims({"lon": self.model_ds.lon})
            weights.name = self.area_variable_name
            self.fx_ds = weights
        return self.fx_ds

    def load_obs_ds(self) -> xr.Dataset:
        """Reads observational data from climatebench google cloud bucket. passes data through standardizer function.

        Returns:
            xr.Dataset: Observational dataset
        """
        if not self.source:
            raise ValueError(
                f"No observational data source passed. Options are {OBSERVATION_DATA_SOURCES[self.variable]}"
            )
        if os.path.isdir(self.obs_data_path_local):
            logger.info(
                f"reading observations from local store: {self.obs_data_path_local}"
            )
            obs_ds = standardize_dims(
                xr.open_zarr(self.obs_data_path_local), convert_cftime=True
            )
        else:
            logger.info(
                f"reading observations from cloud store: {self.obs_data_path_cloud}"
            )
            obs_ds = standardize_dims(
                xr.open_zarr(self.obs_data_path_cloud), convert_cftime=True
            )

        return obs_ds.sel(
            time=slice(f"{self.start_year}-01-01", f"{self.end_year}-12-31")
        )

    def find_ensemble_members(
        self,
        experiment: str,
    ) -> list:
        self._resolve_grid(experiment)
        # download because it is slow to read from GCS. should save locally for future runs
        cmip6_catalogue = "pangeo-cmip6.csv"
        if os.path.exists(cmip6_catalogue):
            df = pd.read_csv(cmip6_catalogue)
        else:
            download_file(
                "https://cmip6.storage.googleapis.com/pangeo-cmip6.csv", cmip6_catalogue
            )

        query = dict(
            experiment_id=experiment,
            table_id=self.variable_frequency_table,
            variable_id=self.variable,
            source_id=self.model,
            grid_label=self.grid,
        )
        col_subset_df = df.loc[(df[list(query)] == pd.Series(query)).all(axis=1)]
        # check for duplicates
        # ensemble members are repeated, need to take ensemble member from most recent verion
        if len(col_subset_df["member_id"]) != len(col_subset_df["member_id"].unique()):
            idx = (
                col_subset_df.groupby("member_id")["version"].transform("max")
                == col_subset_df["version"]
            )
            col_subset_df = col_subset_df[idx]

        col_subset_df = col_subset_df[col_subset_df["member_id"].str.contains("i1p1f1")]
        return col_subset_df["member_id"].tolist()

