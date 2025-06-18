import argparse
import logging
import os
from csv import writer

import pandas as pd
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


def main(org, model, variable, metrics):
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
        rmse_hist = metric_calculator.global_mean_rmse(
            time_slice=slice(HIST_START_DATE, HIST_END_DATE), metric=metric
        )
        rmse_ssp245 = metric_calculator.global_mean_rmse(
            time_slice=slice(SSP_START_DATE, SSP_END_DATE), metric=metric
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

        save_results = SaveResults(
            variable=variable, experiment="RMSE"
        )  # will want to set some experiment groups later
        save_results.save_to_csv(result_df, "global_mean_rmse_results.csv")


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
    args = parser.parse_args()

    main(args.org, args.model, args.variable, args.metrics)
