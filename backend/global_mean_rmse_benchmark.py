import argparse
import logging
import os
from csv import writer

import pandas as pd
import xarray as xr
import xesmf as xe
import xskillscore as xs

from constants import (
    ENSEMBLE_MEMBERS,
    HIST_END_DATE,
    HIST_START_DATE,
    RESULTS_FILE_PATH,
    SSP_END_DATE,
    SSP_EXPERIMENT,
    SSP_START_DATE,
)
from utils import DataFinder

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def global_mean_rmse(
    model_da: xr.DataArray,
    obs_da: xr.DataArray,
    weights_da: xr.DataArray,
    time_slice: slice(str, str),
    metric: str = None,
) -> float:
    """RMSE of the global mean time series. Can apply a scalar bias adjustment or anomaly calculation before RMSE calculation.

    Args:
        model_da (xr.DataArray): Model data
        obs_da (xr.DataArray): Observational data
        weights_da (xr.DataArray): Weights for global mean calculation (should be grid area)
        time_slice (slice): time period to calculate RMSE over. Need full time series for metric adjustments.
        metric (str, optional): Can be bias_adjustment or anomaly. Defaults to None and regular RMSE is calculated.

    Returns:
        float: RMSE
    """

    model_global_mean = model_da.weighted(weights_da.fillna(0)).mean(
        dim=["lat", "lon"], keep_attrs=True
    )
    obs_global_mean = obs_da.weighted(weights_da.fillna(0)).mean(
        dim=["lat", "lon"], keep_attrs=True
    )

    if metric == "bias_adjusted":
        adjustment = model_global_mean.mean() - obs_global_mean.mean()
        model_global_mean = model_global_mean - adjustment

    if metric == "anomaly":
        model_global_mean = model_global_mean.groupby(
            "time.month"
        ) - model_global_mean.groupby("time.month").mean("time")
        obs_global_mean = obs_global_mean.groupby(
            "time.month"
        ) - obs_global_mean.groupby("time.month").mean("time")

    rmse = xs.rmse(
        a=model_global_mean.sel(time=time_slice).chunk({"time": -1}),
        b=obs_global_mean.sel(time=time_slice).chunk({"time": -1}),
        skipna=True,
        keep_attrs=True,
    )

    return rmse.values.tolist()


def main(org, model, variable, metric):
    logger.info(
        f"Processing model: {model}, variable: {variable}, org: {org}, metric: {metric}"
    )

    data_finder = DataFinder(org=org, model=model, variable=variable)

    logger.info("Reading model data")
    model_ds = data_finder.load_model_ds()
    logger.info("Reading model cell area data")
    cell_var_name = "areacella" if variable != "tos" else "areacello"
    fx_ds = data_finder.load_cell_area_ds(cell_var_name)
    logger.info(f"Reading observation data: {data_finder.obs_data_path}")
    obs_ds = data_finder.load_obs_ds()

    logger.info("Regridding observations")
    # regrid obs data to the model grid
    regridder = xe.Regridder(obs_ds, model_ds[["lat", "lon"]], "bilinear")
    obs_rg_ds = regridder(obs_ds[variable], keep_attrs=True).to_dataset(name=variable)

    logger.info("Calculations")
    # calculate global mean rmse
    rmse_hist = global_mean_rmse(
        model_da=model_ds[variable],
        obs_da=obs_rg_ds[variable],
        weights_da=fx_ds["areacella"],
        time_slice=slice(HIST_START_DATE, HIST_END_DATE),
        metric=metric,
    )
    rmse_ssp245 = global_mean_rmse(
        model_da=model_ds[variable],
        obs_da=obs_rg_ds[variable],
        weights_da=fx_ds["areacella"],
        time_slice=slice(SSP_START_DATE, SSP_END_DATE),
        metric=metric,
    )

    results_line = [
        org,
        model,
        variable,
        "_".join(ENSEMBLE_MEMBERS),
        "_".join(["rmse", metric]) if metric else "rmse",
        rmse_hist,
        rmse_ssp245,
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
    parser.add_argument(
        "--metric",
        required=False,
        help="Global RMSE metric. Can leave blank for unadjusted global mean rmse, or can set to 'bias_adjusted' or 'anomaly'",
    )
    args = parser.parse_args()

    main(args.org, args.model, args.variable, args.metric)
