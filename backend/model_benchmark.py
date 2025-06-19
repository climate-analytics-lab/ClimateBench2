import argparse
import logging
import os
from csv import writer

import pandas as pd
import xarray as xr
import xesmf as xe

from constants import (
    ENSEMBLE_MEMBERS,
    HIST_END_DATE,
    HIST_START_DATE,
    RESULTS_FILE_PATH,
    SSP_END_DATE,
    SSP_EXPERIMENT,
    SSP_START_DATE,
)
from utils import DataFinder, MetricCalculation, SaveResults

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def main(org, model, variable, metrics, save_to_cloud):
    logger.info(
        f"Processing model: {model}, variable: {variable}, org: {org}, metrics: {metrics}"
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

    # calculate global mean rmse
    metric_calculator = MetricCalculation(
        observations=obs_rg_ds[variable],
        model=model_ds[variable],
        weights=fx_ds["areacella"],
    )

    for metric in metrics:
        logger.info(f"Calculating {metric}")
        rmse_hist = metric_calculator.calculate_zonal_mean_rmse(
            time_slice=slice(HIST_START_DATE, HIST_END_DATE),
            metric=metric,
            lat_slice=slice(-90, 90),  # should add arg for lat slice
        )
        rmse_ssp245 = metric_calculator.calculate_zonal_mean_rmse(
            time_slice=slice(SSP_START_DATE, SSP_END_DATE),
            metric=metric,
            lat_slice=slice(-90, 90),
        )
        result_df = pd.DataFrame(
            {
                "org": [org],
                "model": [model],
                "variable": [variable],
                "ensemble members": ["_".join(ENSEMBLE_MEMBERS)],
                "metric": [metric],
                "historical": [rmse_hist],
                SSP_EXPERIMENT: [rmse_ssp245],
            }
        )
        rmse_hist_map = metric_calculator.calculate_rmse(
            metric=metric,
            time_slice=slice(HIST_START_DATE, HIST_END_DATE),
            dims=["time"],
        )
        rmse_ssp245_map = metric_calculator.calculate_rmse(
            metric=metric, time_slice=slice(SSP_START_DATE, SSP_END_DATE), dims=["time"]
        )
        rmse_map = xr.concat(
            [
                rmse_hist_map.expand_dims(
                    {"time_slice": [f"{HIST_START_DATE}_{HIST_END_DATE}"]}
                ),
                rmse_ssp245_map.expand_dims(
                    {"time_slice": [f"{SSP_START_DATE}_{SSP_END_DATE}"]}
                ),
            ],
            dim="time_slice",
        ).to_dataset(name=metric)
        rmse_time_series = metric_calculator.calculate_rmse(
            metric=metric,
            time_slice=slice(HIST_START_DATE, SSP_END_DATE),
            dims=["lat", "lon"],
        ).to_dataset(name=metric)

        save_results = SaveResults(
            variable=variable, experiment="RMSE"
        )  # will want to set some experiment groups later
        if save_to_cloud:
            save_results.save_to_csv_gcs(result_df, "global_mean_rmse_results.csv")
        else:
            save_results.save_to_csv_local(result_df, "global_mean_rmse_results.csv")
            save_results.save_zarr_local(rmse_map, f"{org}_{model}_temporal_rmse.zarr")
            save_results.save_zarr_local(
                rmse_time_series, f"{org}_{model}_spatial_rmse.zarr"
            )


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
        "--metrics",
        required=True,
        nargs="+",
        choices=["rmse", "rmse_bias_adjusted", "rmse_anomaly"],
        help="Global RMSE metric to calculate.",
    )
    parser.add_argument(
        "--save_to_cloud",
        action="store_true",
        default=False,
        help="Save data on google cloud if passed, if not passsed saved locally",
    )
    args = parser.parse_args()

    main(args.org, args.model, args.variable, args.metrics, args.save_to_cloud)
