import glob
import io
import logging
import os
import shutil
from csv import writer

import dask.array as da
import numpy as np
import pandas as pd
import xarray as xr
import xskillscore as xs
from google.cloud import storage
from pyesgf.search import SearchConnection

from constants import (
    CMIP6_MODEL_INSTITUTIONS,
    ENSEMBLE_MEMBERS,
    HIST_END_DATE,
    HIST_START_DATE,
    OBSERVATION_DATA_PATHS,
    SSP_END_DATE,
    SSP_START_DATE,
    VARIABLE_FREQUENCY_GROUP,
)

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


def search_gcs(filters: dict, drop_older_versions: bool) -> pd.DataFrame:
    """Look for files in the public cmip6 google cloud bucket. Uses csv of data info to find path instead of a glob. Since files are saved as zarr, glob would return too many.
    Broken out from DataFinder class to make the gcs search more customizable for model variable data vs model cell area data.

    Args:
        filters (dict): Dict with columns as keys and filter values as items
        drop_older_versions (bool): drop duplicate entries, keeping the newer version

    Returns:
        pd.DataFrame: datasets matching filters on google cloud
    """
    df = pd.read_csv("https://cmip6.storage.googleapis.com/pangeo-cmip6.csv")
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
    The class can also find the model cell area data based on variable passed.
    """

    def __init__(self, model: str, variable: str, start_year: int, end_year: int):
        """Initialize DataFinder class.

        Args:
            model (str): Climate model of interest
            variable (str): Short name of climate variable
        """
        self.model = model
        self.variable = variable
        self.start_year = start_year
        self.end_year = end_year

        self.org = CMIP6_MODEL_INSTITUTIONS[self.model]
        self.mip = "CMIP" if self.start_year < 2015 else "ScenarioMIP"
        # If the time range spans the two experiments
        if (self.end_year >= 2015) & (self.mip == "CMIP"):
            self.secondary_mip = "ScenarioMIP"
        else:
            self.secondary_mip = None

        self.variable_frequency_table = VARIABLE_FREQUENCY_GROUP[self.variable]
        self.area_variable_name = "areacello" if self.variable == "tos" else "areacella"
        self.area_frequency_table = "Ofx" if self.variable == "tos" else "fx"

        self.obs_data_path_local = OBSERVATION_DATA_PATHS[self.variable]["local"]
        self.obs_data_path_cloud = OBSERVATION_DATA_PATHS[self.variable]["cloud"]
        self.grid = None

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

        Returns:
            list[str]: list of local file paths
        """
        local_data_path = f"{os.environ['HOME']}/climate_data/CMIP6/{mip}/{self.org}/{self.model}/{experiment}/{ensemble}/{frequency_table}/{variable}/*/*/*"
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
        }
        if self.grid:
            search_keys["grid_label"] = self.grid

        gcs_files = search_gcs(filters=search_keys, drop_older_versions=True)

        if (len(gcs_files) == 0) and ("area" in variable):
            search_keys.pop("member_id")
            search_keys.pop("activity_id")
            search_keys.pop("experiment_id")

            gcs_files = search_gcs(filters=search_keys, drop_older_versions=True)

        if self.grid is None:
            if "gn" in gcs_files["grid_label"].unique():
                self.grid = "gn"
            else:
                self.grid = gcs_files["grid_label"].values[0]

        gcs_files = gcs_files[gcs_files["grid_label"] == self.grid]

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
            data_node (str, optional): Node to search for data on. Sometimes a node is down, in which case you should try another one. Defaults to "esgf-data1.llnl.gov".

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
                        f"can't find data for {mip}, {self.org}, {self.model}, {experiment}, {ensemble}, {frequency_table}, {variable}"
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

    def load_ensemble_mean(self, mip: str, experiment: str) -> xr.Dataset:
        """Finds data for all ensemble members and returns the mean. Ensemble members based on constant.

        Args:
            mip (str): ScenarioMIP or CMIP
            experiment (str): historical or ssp245

        Returns:
            xr.Dataset: Ensemble mean of climate model data
        """
        ensemble_ds_list = []
        for ensemble in ENSEMBLE_MEMBERS:
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
            ds.expand_dims({"ensemble": [ensemble]})
            ensemble_ds_list.append(ds)
        return xr.concat(
            ensemble_ds_list, dim="ensemble", combine_attrs="override"
        ).mean(dim="ensemble")

    def load_model_ds(self) -> xr.Dataset:
        """Loads ensemble mean of historical and projected (ssp245) climate model data. Combines into one dataset and passes through standardizer function. Returned data should have "lat" "lon" and "time" dimensions that are sorted in ascending order. Lon values are from 0-360 and time is monthly on the first of the month.

        Returns:
            xr.Dataset: Analysis ready climate model data. Ensemble mean combination of historical and projected datasets.
        """
        experiment = "historical" if self.mip == "CMIP" else "ssp245"
        model_ds = self.load_ensemble_mean(mip=self.mip, experiment=experiment)
        if self.secondary_mip:
            # historical and projection meet at 2015. Some models overlap in 2015 so setting hard bounds to avoid downstream errors.
            model_ds = model_ds.sel(
                time=slice(f"{self.start_year}-01-01", "2014-12-31")
            )
            second_model_ens_mean = self.load_ensemble_mean(
                mip=self.secondary_mip, experiment="ssp245"
            )
            model_ds = xr.concat(
                [model_ds, second_model_ens_mean],
                dim="time",
                coords="minimal",
                compat="override",
            )
        model_ds = model_ds.sel(
            time=slice(f"{self.start_year}-01-01", f"{self.end_year}-12-31")
        )
        model_ds = standardize_dims(model_ds)
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
            fx_ds = self.read_data(
                mip="CMIP",
                experiment="historical",
                ensemble=ENSEMBLE_MEMBERS[0],
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
            return standardize_dims(xr.open_zarr(self.obs_data_path_local))
        else:
            logger.info(
                f"reading observations from cloud store: {self.obs_data_path_cloud}"
            )
            return standardize_dims(xr.open_zarr(self.obs_data_path_cloud))


# little helper functions
def anomaly(ds):
    ds_anom = ds.groupby("time.month") - ds.groupby("time.month").mean("time")
    return ds_anom.drop("month")


def bias_adjustment(model, obs):
    adjustment = model.mean(dim="time") - obs.mean(dim="time")
    return model - adjustment


class MetricCalculation:
    """The MetricCalculation class is for benchmarking climate model data against observations. It takes in model, observations, and weights datasets.
    The weights dataset should be the cell area, so if one is not provided a proxy will be created by taking the cosine of latitude.
    For now, there is an RMSE calculation option, with none, bias adjustment, and anomaly adjustment options.

    """

    def __init__(
        self,
        observations: xr.Dataset,
        model: xr.Dataset,
        weights: xr.DataArray = None,
        lat_min: int = -90,
        lat_max: int = 90,
    ):
        """Initialize MetricCalculation class. If weights dataarray not passed, a proxy weights dataset will be created.

        Args:
            observations (xr.Dataset): Climate data observations
            model (xr.Dataset): Climate model data (historical and projected data)
            weights (xr.DataArray, optional): weights corresponding to grid cell area. Defaults to None.
            lat_min (int): minimum latitude
            lat_max (int): maximum latitude
        """
        self.obs = observations
        self.model = model
        self.lat_min = lat_min
        self.lat_max = lat_max
        # you can pass in the weights if the areacella or areacello data exists,
        # if not just us the cos of lat, which is proportional to cell area for a regular grid
        if weights is None:
            # need to turn this into a full xarray ds to match areacella/areacello
            weights = np.cos(np.deg2rad(self.model.lat))
            weights = weights.expand_dims({"lon": self.model.lon})
            weights.name = "weights"
            self.weights = weights
        else:
            # check that dims match model
            if ~weights.lat.equals(self.model.lat):
                weights["lat"] = self.model["lat"]
            if ~weights.lon.equals(self.model.lon):
                weights["lon"] = self.model["lon"]
            self.weights = weights

        # setting weights outside bounds to na, this will set their weight to 0 and therefore not includ in calculations
        self.weights = self.weights.where(self.weights.lat > lat_min)
        self.weights = self.weights.where(self.weights.lat < lat_max)

        self.model_zonal_mean = None
        self.obs_zonal_mean = None

        self.spatial_dims = [x for x in self.model.dims if x != "time"]

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

    def calculate_rmse(
        self,
        metric: str,
        adjustment: str,
        time_slice: slice(str, str),
    ) -> xr.DataArray:
        """Calculates RMSE based on metric and adjustment provided. If lat bounds provided, zonal mean and spatial RMSE calculations will use adjusted weights.

        Args:
            metric (str): Type of RMSE to calculate (zonal mean, temporal, or spatial)
            adjustment (str): adjustment to apply to data before RMSE calculation (bias adjustment or anomaly)
            time_slice (slice): time period to calculate RMSE over

        Raises:
            ValueError: If metric provided is not supported

        Returns:
            xr.DataArray: Resulting RMSE calculation. Dimensions vary based on metric provided.
        """
        logger.info(
            f"calculating {metric} for time: {time_slice}, adjustment: {adjustment}"
        )

        if metric == "zonal_mean":
            if self.model_zonal_mean is None:
                self.model_zonal_mean = self.zonal_mean(self.model)
            if self.obs_zonal_mean is None:
                self.obs_zonal_mean = self.zonal_mean(self.obs)
            model_rmse_data = self.model_zonal_mean
            obs_rmse_data = self.obs_zonal_mean
            weights = None
            dims = ["time"]

        elif metric == "spatial":
            model_rmse_data = self.model
            obs_rmse_data = self.obs
            weights = self.weights
            dims = self.spatial_dims

        elif metric == "temporal":
            model_rmse_data = self.model
            obs_rmse_data = self.obs
            weights = None
            dims = ["time"]

        else:
            raise ValueError(f"Metric not supported: {metric}")

        if adjustment == "bias_adjusted":
            model_rmse_data = bias_adjustment(model=model_rmse_data, obs=obs_rmse_data)

        if adjustment == "anomaly":
            model_rmse_data = anomaly(ds=model_rmse_data)
            obs_rmse_data = anomaly(ds=obs_rmse_data)

        return xs.rmse(
            a=model_rmse_data.sel(time=time_slice).chunk({"time": -1}),
            b=obs_rmse_data.sel(time=time_slice).chunk({"time": -1}),
            weights=weights,
            skipna=True,
            keep_attrs=True,
            dim=dims,
        )


class SaveResults:
    """The SaveResults class is for saving outputs from the benchmarking pipeline in an organized mannor.
    The path is determined by the variable and "experiment" (for now, RMSE) but you can specify the specific file name.
    Options for saving data as csv and zarr.
    """

    def __init__(self, variable: str, experiment: str):
        """Initialize SaveResults class, sets local and cloud paths

        Args:
            variable (str): Variable short name
            experiment (str): Set of metric experiments.
        """
        self.variable = variable
        self.experiment = experiment

        self.storage_client = storage.Client(project="JCM and Benchmarking")
        self.bucket_name = "climatebench"
        self.bucket = self.storage_client.bucket(self.bucket_name)
        self.gcs_prefix = f"gs://{self.bucket_name}/"
        self.data_path = f"results/{self.experiment}/{self.variable}/"

    def save_csv(
        self, result_df: pd.DataFrame, file_name: str, save_to_cloud: bool = False
    ):
        """Save tabular data locally or to google cloud

        Args:
            result_df (pd.DataFrame): Dataframe to save
            file_name (str): name of file to save results in. Path determined by class
            save_to_cloud (bool): Save to cloud if passed. Default is False.
        """
        file_path = self.data_path + file_name
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

    def save_zarr(self, ds: xr.Dataset, file_name: str, save_to_cloud: bool = False):
        """Save dimentional data locally or to google cloud

        Args:
            ds (xr.Dataset): Dataset to save
            file_name (str): name of file to save results in. Path determined by class
            save_to_cloud (bool): Save to cloud if passed. Default is False.
        """
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
