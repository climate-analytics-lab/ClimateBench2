import argparse
import glob
import logging
import os
from csv import writer

import numpy as np
import pandas as pd
import xarray as xr
import xesmf as xe
import xskillscore as xs
from google.cloud import storage
from pyesgf.search import SearchConnection

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


############## CONSTANTS ##############
ENSEMBLE_MEMBERS = ["r1i1p1f1", "r2i1p1f1", "r3i1p1f1"]
VARIABLE_FREQUENCY_GROUP = {
    "tas": "Amon",
    "pr": "Amon",
    "clt": "Amon",
    "tos": "Omon",
    "od550aer": "AERmon",
}
HIST_START_DATE = "2005-01-01"
HIST_END_DATE = "2014-12-31"
SSP_START_DATE = "2015-01-01"
SSP_END_DATE = "2024-12-31"
RESULTS_FILE_PATH = "model_benchmarking_results.csv"
SSP_EXPERIMENT = "ssp245"


############## FUNCTIONS ##############
def standardize_dims(ds: xr.Dataset) -> xr.Dataset:
    """Fixes some common issues with geospatial data

    Args:
        ds (xr.Dataset): input data that should have latitude and longitude coordinates

    Returns:
        xr.Dataset: dataset with normalized coordinate values and names
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
        ds = ds.sortby("time")

    # Shift longitudes
    ds = ds.assign_coords(lon=(ds.lon % 360))
    ds = ds.sortby("lon")

    # make sure lat is -90 to 90
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


def check_local_files(
    mip: str,
    org: str,
    model: str,
    experiment: str,
    ensemble: str,
    frequency: str,
    variable: str,
) -> list[str]:
    """Look for climate data files saved locally in the HOME/climate_data/CMIP6 directory. This is data cached from esmvaltool.

    Args:
        mip (str): CMIP or ScenarioMIP
        org (str): Climate model org
        model (str): Climate model name
        experiment (str): historical or sspXXX
        ensemble (str): rXiXpXfX
        frequency (str): Amon, Omon, fx
        variable (str): pr, tas, clt, tos, od550aer

    Returns:
        list[str]: list of local file paths
    """
    local_data_path = f"{os.environ['HOME']}/climate_data/CMIP6/{mip}/{org}/{model}/{experiment}/{ensemble}/{frequency}/{variable}/*/*/*"
    local_files = glob.glob(local_data_path)
    return local_files


def check_esgf_files(
    model: str,
    experiment: str,
    ensemble: str,
    frequency: str,
    variable: str,
    data_node="esgf-data1.llnl.gov",
) -> list[str]:
    """Look for climate data on ESGF server.

    Args:
        model (str): Climate model name
        experiment (str): historical or sspXXX
        ensemble (str): rXiXpXfX
        frequency (str): Amon, Omon, fx
        variable (str): pr, tas, clt, tos, od550aer
        data_node (str, optional): ESGF node to look for data on. Defaults to "esgf-data1.llnl.gov".

    Returns:
        list[str]: list of remote file path URLs
    """
    conn = SearchConnection("https://esgf-data.dkrz.de/esg-search", distrib=True)
    ctx = conn.new_context(
        project="CMIP6",
        source_id=model,
        experiment_id=experiment,
        variable=variable,
        variant_label=ensemble,
        frequency=frequency[-3:],  # fx for area, mon for variables
        data_node=data_node,
    )
    results = ctx.search()

    if len(results) < 1:
        logger.info(f"No results found on ESGF node {data_node}. Try another node.")
        return None

    elif len(results) > 1:
        logger.info(
            f"{len(results)} results returned. Please filter more (e.g. grid, version)."
        )
        return None

    else:
        file_url_list = []
        files = results[0].file_context().search()
        for file in files:
            file_url_list.append(file.opendap_url)
        df = pd.DataFrame(file_url_list, columns=["file_url"])
        if frequency != "fx":
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


def check_gcs_files(
    mip: str,
    org: str,
    model: str,
    experiment: str,
    ensemble: str,
    frequency: str,
    variable: str,
) -> str:
    """Look for cimate data on google cloud storage public cmip6 bucket. This data is cloud optimized (zarr) so only one path returned.

    Args:
        mip (str): CMIP or ScenarioMIP
        org (str): Climate model org
        model (str): Climate model name
        experiment (str): historical or sspXXX
        ensemble (str): rXiXpXfX
        frequency (str): Amon, Omon, fx
        variable (str): pr, tas, clt, tos, od550aer

    Returns:
        str: Google cloud storage path
    """
    storage_client = storage.Client(project="JCM and Benchmarking")

    gcs_data_path = (
        f"CMIP6/{mip}/{org}/{model}/{experiment}/{ensemble}/{frequency}/{variable}/"
    )
    blobs = storage_client.list_blobs(
        bucket_or_name="cmip6",
        prefix=gcs_data_path,
    )
    blob_list = []
    for blob in blobs:
        blob_list.append(blob.name)
    df = pd.DataFrame(blob_list)
    if not df.empty:
        df_exp = (
            df[0]
            .str.split("/", expand=True)
            .drop(columns=[10, 11], errors="ignore")
            .rename(
                columns={
                    0: "project",
                    1: "mip",
                    2: "org",
                    3: "model",
                    4: "experiment",
                    5: "ensemble",
                    6: "frequency",
                    7: "variable",
                    8: "grid",
                    9: "version",
                }
            )
            .drop_duplicates()
        )
        df_exp["version_date"] = pd.to_datetime(
            df_exp["version"].str[1:], format="%Y%m%d"
        )
        df_exp = (
            df_exp.sort_values("version_date", ascending=False)
            .drop_duplicates(
                [
                    "project",
                    "mip",
                    "org",
                    "model",
                    "experiment",
                    "ensemble",
                    "frequency",
                    "variable",
                    "grid",
                ]
            )
            .drop(columns=["version_date"])
        )
        # combine to make gcs file path
        grid = df_exp["grid"].values[0]
        version = df_exp["version"].values[0]
        return "gs://cmip6/" + gcs_data_path + f"{grid}/{version}"
    else:
        return None


def read_data(
    mip: str,
    org: str,
    model: str,
    experiment: str,
    ensemble: str,
    frequency: str,
    variable: str,
) -> xr.Dataset:
    """Reads climate data first from local, then checks google cloud, then checks esgf.

    Args:
        mip (str): CMIP or ScenarioMIP
        org (str): Climate model org
        model (str): Climate model name
        experiment (str): historical or sspXXX
        ensemble (str): rXiXpXfX
        frequency (str): Amon, Omon, fx
        variable (str): pr, tas, clt, tos, od550aer

    Raises:
        ValueError: Error if no data found in any location for combination of parameters.

    Returns:
        xr.Dataset: climate data for combination of parameters
    """
    file_paths = check_local_files(
        mip, org, model, experiment, ensemble, frequency, variable
    )
    if not file_paths:
        file_paths = check_gcs_files(
            mip, org, model, experiment, ensemble, frequency, variable
        )
        if not file_paths:
            file_paths = check_esgf_files(
                model, experiment, ensemble, frequency, variable
            )
            if not file_paths:
                raise ValueError(
                    f"can't find data for {mip}, {org}, {model}, {experiment}, {ensemble}, {frequency}, {variable}"
                )
            else:
                # read data from esgf
                ds_list = []
                for file in file_paths:
                    ds_list.append(xr.open_dataset(file))
                ds = xr.concat(ds_list)
        else:
            # read from google storage
            # gcs should only return one path since zarr, not folder of netCDFs
            ds = xr.open_zarr(file_paths, chunks={})
    else:
        # read from local
        ds = xr.open_mfdataset(file_paths)

    return ds


# Find observational data
# can read in from local obs or cmorized obs or search esgf for obs4mips data?
# do something simple for now, can go back later
def read_obs_data(variable):
    if variable == "pr":
        ds = xr.open_dataset(
            f"{os.environ['HOME']}/climate_data/cmorized_obs/Tier2/GPCP-SG/OBS_GPCP-SG_atmos_2.3_Amon_pr_197901-202504.nc"
        )
    else:
        obs_data_path = glob.glob(f"obs_data_download/observational_data/{variable}*")[0]
        ds = xr.open_zarr(obs_data_path, chunks={})

    # unit conversions
    if variable == "clt":
        # make sure both observations and model data are 0-100
        ds["clt"] = ds["clt"] / 100

    return ds


def main(org, model, variable):
    logger.info(f"Processing model: {model}, variable: {variable}, org: {org}")
    frequency = VARIABLE_FREQUENCY_GROUP[variable]

    logger.info("Reading data")

    #### ssp245 data ####
    ssp_ensemble = []
    for ensemble in ENSEMBLE_MEMBERS:
        ds = read_data(
            mip="ScenarioMIP",
            org=org,
            model=model,
            experiment=SSP_EXPERIMENT,
            ensemble=ensemble,
            frequency=frequency,
            variable=variable,
        )
        ds = ds.sel(time=slice(SSP_START_DATE, SSP_END_DATE))
        ds.expand_dims({"ensemble": [ensemble]})
        ssp_ensemble.append(ds)
    ssp245_ds = xr.concat(ssp_ensemble, dim="ensemble", combine_attrs="override").mean(
        dim="ensemble"
    )
    ssp245_ds = standardize_dims(ssp245_ds)

    #### historical data ####
    historical_ensemble = []
    for ensemble in ENSEMBLE_MEMBERS:
        ds = read_data(
            mip="CMIP",
            org=org,
            model=model,
            experiment="historical",
            ensemble=ensemble,
            frequency=frequency,
            variable=variable,
        )
        ds = ds.sel(time=slice(HIST_START_DATE, HIST_END_DATE))
        ds.expand_dims({"ensemble": [ensemble]})
        historical_ensemble.append(ds)
    historical_ds = xr.concat(
        historical_ensemble, dim="ensemble", combine_attrs="override"
    ).mean(dim="ensemble")
    historical_ds = standardize_dims(historical_ds)

    #### cell area data ####
    fx_ds = read_data(
        mip="CMIP",
        org=org,
        model=model,
        experiment="historical",
        ensemble=ENSEMBLE_MEMBERS[0],
        frequency="fx",
        variable="areacella",
    )
    fx_ds = standardize_dims(fx_ds)
    weights_ds = (fx_ds["areacella"] / fx_ds["areacella"].sum()).to_dataset(
        name="weight"
    )

    #### obervation data ####
    obs_ds = read_obs_data(variable)
    obs_ds = standardize_dims(obs_ds)

    logger.info("Regridding observations")
    # regrid obs data to the model grid
    regridder = xe.Regridder(obs_ds, historical_ds[["lat", "lon"]], "conservative")
    obs_rg_ds = regridder(obs_ds[variable], keep_attrs=True).to_dataset(name=variable)

    logger.info("Calculations")
    # calculate global mean
    hist_global_mean = (historical_ds[variable] * weights_ds["weight"]).sum(
        dim=["lat", "lon"]
    )
    ssp245_global_mean = (ssp245_ds[variable] * weights_ds["weight"]).sum(
        dim=["lat", "lon"]
    )
    obs_global_mean = (obs_rg_ds[variable] * weights_ds["weight"]).sum(
        dim=["lat", "lon"]
    )

    # calculate metric and save results.
    # could save as csv that is added to every time?
    # org, model, variable, ensemble members, historical value, ssp245 value
    rmse_hist = xs.rmse(
        a=hist_global_mean.chunk({"time": -1}),
        b=obs_global_mean.sel(time=slice(HIST_START_DATE, HIST_END_DATE)).chunk(
            {"time": -1}
        ),
        skipna=True,
        keep_attrs=True,
    )
    rmse_ssp245 = xs.rmse(
        a=ssp245_global_mean.chunk({"time": -1}),
        b=obs_global_mean.sel(time=slice(SSP_START_DATE, SSP_END_DATE)).chunk(
            {"time": -1}
        ),
        skipna=True,
        keep_attrs=True,
    )
    results_line = [
        org,
        model,
        variable,
        "_".join(ENSEMBLE_MEMBERS),
        "rmse",
        rmse_hist.values.tolist(),
        rmse_ssp245.values.tolist(),
    ]

    logger.info("Saving results")
    # write results to csv (add new line if csv already exists)
    if os.path.isfile(RESULTS_FILE_PATH):
        with open(RESULTS_FILE_PATH, "a") as f_object:
            writer_object = writer(f_object)
            writer_object.writerow(results_line)
            f_object.close()
    else:
        pd.DataFrame(
            {
                "org": [results_line[0]],
                "model": [results_line[1]],
                "variable": [results_line[2]],
                "ensemble members": [results_line[3]],
                "metric": [results_line[4]],
                "historical": [results_line[5]],
                SSP_EXPERIMENT: [results_line[6]],
            }
        ).to_csv(RESULTS_FILE_PATH, index=False)

    logger.info(f"Results saved: {RESULTS_FILE_PATH}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Data processing for model benchmarking"
    )
    parser.add_argument(
        "--org",
        help="Input value for the main function",
    )
    parser.add_argument(
        "--model",
        help="Input value for the main function",
    )
    parser.add_argument(
        "--variable",
        help="Input value for the main function",
        choices=["tas", "pr", "clt", "tos", "od550aer"],
    )
    args = parser.parse_args()

    main(args.org, args.model, args.variable)
