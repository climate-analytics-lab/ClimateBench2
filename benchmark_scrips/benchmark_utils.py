import glob
import io
import logging
import os
import shutil
import sys
from csv import writer

import numpy as np
import pandas as pd
import xarray as xr
import xskillscore as xs
from google.cloud import storage
from pyesgf.search import SearchConnection

sys.path.append("..")

from constants import OBSERVATION_DATA_PATHS, SSP_EXPERIMENT, VARIABLE_FREQUENCY_GROUP
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

    def __init__(self, model: str, variable: str, start_year: int, end_year: int):
        """Initialize DataFinder class.

        Args:
            model (str): Climate model of interest
            variable (str): Short name of climate variable
            start_year (int): Start of time period for model and observational data
            end_year (int): End of time period for model and observational data
        """
        self.model = model
        self.variable = variable
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
        self.grid = "gr" if self.variable_frequency_table == "Omon" else "gn"

        self.obs_data_path_local = (
            "/".join(os.getcwd().split("/")[:-1])
            + "/"
            + OBSERVATION_DATA_PATHS[self.variable]["local"]
        )
        self.obs_data_path_cloud = OBSERVATION_DATA_PATHS[self.variable]["cloud"]
        self.ensemble_members = None

        self.model_ds = None
        self.fx_ds = None
        self.obs_ds = None

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
            ds = standardize_dims(ds)
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
        if os.path.isdir(self.obs_data_path_local):
            logger.info(
                f"reading observations from local store: {self.obs_data_path_local}"
            )
            obs_ds = standardize_dims(xr.open_zarr(self.obs_data_path_local))
        else:
            logger.info(
                f"reading observations from cloud store: {self.obs_data_path_cloud}"
            )
            obs_ds = standardize_dims(xr.open_zarr(self.obs_data_path_cloud))

        return obs_ds.sel(
            time=slice(f"{self.start_year}-01-01", f"{self.end_year}-12-31")
        )

    def find_ensemble_members(
        self,
        experiment: str,
    ) -> list:
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


# little helper functions
def anomaly(ds):
    ds_anom = ds.groupby("time.month") - ds.groupby("time.month").mean("time")
    return ds_anom.drop("month")


def bias_adjustment(model, obs):
    adjustment = model.mean(dim="time") - obs.mean(dim="time")
    return model - adjustment


class MetricCalculation:
    """The MetricCalculation class is for benchmarking climate model data against observations. It takes in model, observations, and weights datasets.
    The weights dataset should be the cell area.
    For now, there are 3 RMSE calculation options (zonal mean, spatial, temporal) with 2 optional adjustment options (bias_adjusted, anomaly).
    To add new metric calculation options, a function should be added that can be called as an agrument from the main script.
    """

    def __init__(
        self,
        observations: xr.Dataset,
        model: xr.Dataset,
        weights: xr.DataArray,
        lat_min: int = -90,
        lat_max: int = 90,
    ):
        """Initialize MetricCalculation class. If weights dataarray not passed, a proxy weights dataset will be created.

        Args:
            observations (xr.Dataset): Climate data observations
            model (xr.Dataset): Climate model data (historical and projected data)
            weights (xr.DataArray): weights corresponding to grid cell area.
            lat_min (int): minimum latitude. Defaults to -90.
            lat_max (int): maximum latitude. Defaults to 90.
        """
        self.obs = observations
        self.model = model

        self.lat_min = lat_min
        self.lat_max = lat_max

        # check that dims match model
        if ~weights.lat.equals(self.model.lat):
            weights["lat"] = self.model["lat"]
        if ~weights.lon.equals(self.model.lon):
            weights["lon"] = self.model["lon"]

        # setting weights outside bounds to na, this will set their weight to 0 and therefore not includ in calculations
        weights = weights.where(weights.lat > lat_min)
        weights = weights.where(weights.lat < lat_max)

        self.weights = weights

        self.model_zonal_mean = None
        self.obs_zonal_mean = None

        self.spatial_dims = [
            x for x in self.model.dims if (x != "time") and (x != "ensemble")
        ]

    def zonal_mean(self, ds: xr.Dataset):
        """Calculates zonal mean of model and observational datasets, weighted by the provided weights dataset

        Args:
            ds (xr.Dataset): observations or model dataset to weight by cell area weights

        Returns:
            xr.Dataset: zonal mean of model dataset
            xr.Dataset: zonal mean of observations dataset
        """
        weighted_ds = ds.weighted(self.weights.fillna(0)).mean(
            dim=self.spatial_dims, keep_attrs=True
        )
        return weighted_ds

    def zonal_mean_rmse(self, adjustment: str = None) -> float:
        """First calculates the zonal mean of the model and observations datasets, then calculates the RMSE of the two time series.
        Bias adjustment centers the model time series on the observations. Anomaly adjustment calculates the monthly anomalies for both datasets.

        Args:
            adjustment (str, optional): Adjustment option to apply. Defaults to None.

        Returns:
            float: RMSE value
        """
        if self.model_zonal_mean is None:
            self.model_zonal_mean = self.zonal_mean(self.model)
        if self.obs_zonal_mean is None:
            self.obs_zonal_mean = self.zonal_mean(self.obs)
        model_rmse_data = self.model_zonal_mean
        obs_rmse_data = self.obs_zonal_mean

        if adjustment == "bias_adjusted":
            model_rmse_data = bias_adjustment(model=model_rmse_data, obs=obs_rmse_data)

        if adjustment == "anomaly":
            model_rmse_data = anomaly(ds=model_rmse_data)
            obs_rmse_data = anomaly(ds=obs_rmse_data)

        return xs.rmse(
            a=model_rmse_data.chunk({"time": -1}),
            b=obs_rmse_data.chunk({"time": -1}),
            skipna=True,
            keep_attrs=True,
            dim=["time"],
        ).values.tolist()

    def zonal_mean_mae(self, adjustment: str = None) -> float:
        """First calculates the zonal mean of the model and observations datasets, then calculates the MAE of the two time series.
        Bias adjustment centers the model time series on the observations. Anomaly adjustment calculates the monthly anomalies for both datasets.

        Args:
            adjustment (str, optional): Adjustment option to apply. Defaults to None.

        Returns:
            float: RMSE value
        """
        if self.model_zonal_mean is None:
            self.model_zonal_mean = self.zonal_mean(self.model)
        if self.obs_zonal_mean is None:
            self.obs_zonal_mean = self.zonal_mean(self.obs)
        model_rmse_data = self.model_zonal_mean
        obs_rmse_data = self.obs_zonal_mean

        if adjustment == "bias_adjusted":
            model_rmse_data = bias_adjustment(model=model_rmse_data, obs=obs_rmse_data)

        if adjustment == "anomaly":
            model_rmse_data = anomaly(ds=model_rmse_data)
            obs_rmse_data = anomaly(ds=obs_rmse_data)

        return xs.mae(
            a=model_rmse_data.chunk({"time": -1}),
            b=obs_rmse_data.chunk({"time": -1}),
            skipna=True,
            keep_attrs=True,
            dim=["time"],
        ).values.tolist()

    def zonal_mean_crps(self, adjustment: str = None) -> float:
        """First calculates the zonal mean of the model and observations datasets, then calculates the CRPS of the two time series.
        Bias adjustment centers the model time series on the observations. Anomaly adjustment calculates the monthly anomalies for both datasets.

        Args:
            adjustment (str, optional): Adjustment option to apply. Defaults to None.

        Returns:
            float: RMSE value
        """
        if self.model_zonal_mean is None:
            self.model_zonal_mean = self.zonal_mean(self.model)
        if self.obs_zonal_mean is None:
            self.obs_zonal_mean = self.zonal_mean(self.obs)
        model_rmse_data = self.model_zonal_mean
        obs_rmse_data = self.obs_zonal_mean

        # check for ensemble dim in model ds
        if "ensemble" not in model_rmse_data.dims:
            ValueError("no ensemble dimension")

        if adjustment == "bias_adjusted":
            model_rmse_data = bias_adjustment(model=model_rmse_data, obs=obs_rmse_data)

        if adjustment == "anomaly":
            model_rmse_data = anomaly(ds=model_rmse_data)
            obs_rmse_data = anomaly(ds=obs_rmse_data)

        return xs.crps_ensemble(
            forecasts=model_rmse_data.chunk({"time": -1, "ensemble": -1}),
            observations=obs_rmse_data.chunk({"time": -1}),
            member_dim="ensemble",
            keep_attrs=True,
        ).values.tolist()

    def spatial_rmse(self, adjustment: str = None) -> xr.DataArray:
        """For each time step, calculate the RMSE across the spatial dimensions. Data returned will be a time series.
        Bias adjustment centers the model time series on the observations. Anomaly adjustment calculates the monthly anomalies for both datasets.
        Args:
            adjustment (str, optional): Adjustment option to apply. Defaults to None.

        Returns:
            xr.DataArray: Time series of RMSE.
        """
        model_rmse_data = self.model
        obs_rmse_data = self.obs

        if adjustment == "bias_adjusted":
            model_rmse_data = bias_adjustment(model=model_rmse_data, obs=obs_rmse_data)

        if adjustment == "anomaly":
            model_rmse_data = anomaly(ds=model_rmse_data)
            obs_rmse_data = anomaly(ds=obs_rmse_data)

        return xs.rmse(
            a=model_rmse_data.chunk({"time": -1}),
            b=obs_rmse_data.chunk({"time": -1}),
            weights=self.weights,
            skipna=True,
            keep_attrs=True,
            dim=self.spatial_dims,
        )

    def spatial_mae(self, adjustment: str = None) -> xr.DataArray:
        """For each time step, calculate the RMSE across the spatial dimensions. Data returned will be a time series.
        Bias adjustment centers the model time series on the observations. Anomaly adjustment calculates the monthly anomalies for both datasets.
        Args:
            adjustment (str, optional): Adjustment option to apply. Defaults to None.

        Returns:
            xr.DataArray: Time series of RMSE.
        """
        model_rmse_data = self.model
        obs_rmse_data = self.obs

        if adjustment == "bias_adjusted":
            model_rmse_data = bias_adjustment(model=model_rmse_data, obs=obs_rmse_data)

        if adjustment == "anomaly":
            model_rmse_data = anomaly(ds=model_rmse_data)
            obs_rmse_data = anomaly(ds=obs_rmse_data)

        return xs.mae(
            a=model_rmse_data.chunk({"time": -1}),
            b=obs_rmse_data.chunk({"time": -1}),
            weights=self.weights,
            skipna=True,
            keep_attrs=True,
            dim=self.spatial_dims,
        )

    def spatial_crps(self, adjustment: str = None) -> xr.DataArray:
        """For each time step, calculate the CRPS across the spatial dimensions. Data returned will be a time series.
        Bias adjustment centers the model time series on the observations. Anomaly adjustment calculates the monthly anomalies for both datasets.
        Args:
            adjustment (str, optional): Adjustment option to apply. Defaults to None.

        Returns:
            xr.DataArray: Time series of RMSE.
        """
        model_rmse_data = self.model
        obs_rmse_data = self.obs

        # check for ensemble dim in model ds
        if "ensemble" not in model_rmse_data.dims:
            ValueError("no ensemble dimension")

        if adjustment == "bias_adjusted":
            model_rmse_data = bias_adjustment(model=model_rmse_data, obs=obs_rmse_data)

        if adjustment == "anomaly":
            model_rmse_data = anomaly(ds=model_rmse_data)
            obs_rmse_data = anomaly(ds=obs_rmse_data)

        return xs.crps_ensemble(
            forecasts=model_rmse_data.chunk({"time": -1, "ensemble": -1}),
            observations=obs_rmse_data.chunk({"time": -1}),
            weights=self.weights.fillna(0),
            member_dim="ensemble",
            keep_attrs=True,
            dim=self.spatial_dims,
        )

    def temporal_rmse(self, adjustment: str = None) -> xr.DataArray:
        """For grid cell, calculate the RMSE across the time dimension. Data returned will be a map.
        Bias adjustment centers the model time series on the observations. Anomaly adjustment calculates the monthly anomalies for both datasets.
        Args:
            adjustment (str, optional): Adjustment option to apply. Defaults to None.

        Returns:
            xr.DataArray: Map of RMSE.
        """
        model_rmse_data = self.model
        obs_rmse_data = self.obs

        if adjustment == "bias_adjusted":
            model_rmse_data = bias_adjustment(model=model_rmse_data, obs=obs_rmse_data)

        if adjustment == "anomaly":
            model_rmse_data = anomaly(ds=model_rmse_data)
            obs_rmse_data = anomaly(ds=obs_rmse_data)

        return xs.rmse(
            a=model_rmse_data.chunk({"time": -1}),
            b=obs_rmse_data.chunk({"time": -1}),
            skipna=True,
            keep_attrs=True,
            dim=["time"],
        )


class SaveResults:
    """The SaveResults class is for saving outputs from the benchmarking pipeline in an organized mannor.
    Options for saving data as csv and zarr.
    """

    def __init__(
        self,
        model: str,
        variable: str,
        ensemble_members: list,
        metric: str,
        adjustment: str,
        start_year: int,
        end_year: int,
        lat_min: int = -90,
        lat_max: int = 90,
    ):
        """Initialize SaveResults class, sets local and cloud paths

        Args:
            model (str): CMIP6 model name
            variable (str): Variable short name
            metric (str): Name of metric calculated (function from MetricCalculation)
            adjustment (str): Adjustment applied to the metric calculation
            start_year (int): start of time period for calculated metric
            end_year (int): end of time period for calculated metric
            lat_min (int): spatial bound for calculated metric
            lat_max (int): spatial bound for calculated metric
        """
        self.variable = variable
        self.model = model
        self.ensemble_members = ensemble_members
        self.metric = metric
        self.adjustment = adjustment
        self.start_year = start_year
        self.end_year = end_year
        self.lat_min = lat_min
        self.lat_max = lat_max

        self.data_label = (
            self.metric
            if self.adjustment is None
            else f"{self.metric}_{self.adjustment}"
        )

        self.storage_client = storage.Client(project="JCM and Benchmarking")
        self.bucket_name = "climatebench"
        self.bucket = self.storage_client.bucket(self.bucket_name)
        self.gcs_prefix = f"gs://{self.bucket_name}/"
        self.data_path = f"../results/{self.variable}/"

    def write_data(self, results, save_to_cloud: bool):
        """Save data. Datatype determines how data is saved. Options are csv for float, and zarr for xr.DataArray

        Args:
            results: data to be saved
            save_to_cloud (bool): Save data locally if false
        """
        if isinstance(results, float):
            logger.info("Saving data to csv")
            self.save_csv(results, save_to_cloud)

        if isinstance(results, xr.DataArray):
            logger.info("Saving data to zarr")
            self.save_zarr(results, save_to_cloud)

    def save_csv(self, value: float, save_to_cloud: bool = False):
        """Save tabular data locally or to google cloud

        Args:
            value (float): Value to save in results csv
            save_to_cloud (bool): Save to cloud if passed. Default is False.
        """
        result_df = pd.DataFrame(
            {
                "model": [self.model],
                "variable": [self.variable],
                "ensemble members": ["_".join(self.ensemble_members)],
                "metric": [self.data_label],
                "lat_min": [self.lat_min],
                "lat_max": [self.lat_max],
                "start_year": [self.start_year],
                "end_year": [self.end_year],
                "value": [value],
            }
        )

        file_path = self.data_path + "benchmark_results.csv"
        if save_to_cloud:
            full_gcs_path = self.gcs_prefix + file_path
            blob = storage.Blob(bucket=self.bucket, name=file_path)
            # if file already exists
            if blob.exists(self.storage_client):
                # download existing content
                existing_data = blob.download_as_text()
                output = io.StringIO(existing_data)

                # Append the new row
                output.seek(0, io.SEEK_END)
                writer_object = writer(output)
                writer_object.writerow(result_df.values.flatten().tolist())

                # Upload the updated content
                output.seek(0)
                blob.upload_from_string(output.getvalue(), content_type="text/csv")
            else:
                result_df.to_csv(full_gcs_path, index=False)
            logger.info(f"Results saved to cloud: {full_gcs_path}")
        else:
            if os.path.isfile(file_path):
                with open(file_path, "a") as f_object:
                    writer_object = writer(f_object)
                    writer_object.writerow(result_df.values.flatten().tolist())
                    f_object.close()
            else:
                if not os.path.exists(self.data_path):
                    os.makedirs(self.data_path)
                result_df.to_csv(file_path, index=False)

            logger.info(f"Results saved locally: {file_path}")

    # this could still use work. the file names are horrible. could expand dimensions?
    def save_zarr(self, ds: xr.DataArray, save_to_cloud: bool = False):
        """Save dimentional data locally or to google cloud

        Args:
            ds (xr.Dataset): Dataset to save
            save_to_cloud (bool): Save to cloud if passed. Default is False.
        """
        file_name = f"{self.model}_{self.metric}_{self.lat_min}_{self.lat_max}_{self.start_year}_{self.end_year}_results.zarr"
        ds = ds.to_dataset(name=self.data_label)
        for var in list(ds.data_vars) + list(ds.coords):
            ds[var].encoding = {}
        # file name should be org_model_....
        file_path = self.data_path + file_name
        if save_to_cloud:
            file_path = self.gcs_prefix + file_path
        chunks = {}
        for dim in ds.dims:
            chunks[dim] = -1
        ds = ds.chunk(chunks)
        # save
        ds.to_zarr(file_path, mode="a")
        logger.info(f"data saved: {file_path}")

    def overwrite(self, save_to_cloud: bool = False):
        """Delete all data at the path created by the class

        Args:
            save_to_cloud (bool, optional): If passed, delete data saved on the cloud. Defaults to False.
        """
        if save_to_cloud:
            # remove google cloud files
            blobs = self.bucket.list_blobs(prefix=self.data_path)
            for blob in blobs:
                blob.delete()
                print(f"Blob {blob.name} deleted.")
        else:
            # remove local files
            local_files = glob.glob(self.data_path + "*")
            for file in local_files:
                logger.info(f"deleting file: {file}")
                if file[-4:] == "zarr":
                    shutil.rmtree(file)
                else:
                    os.remove(file)
