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
from utils import DataFinder, MetricCalculation

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

        # This method of saving results works for single value metrics, but we will want to expand to time series and spatial metrics.
        results_line = [
            org,
            model,
            variable,
            "_".join(ENSEMBLE_MEMBERS),
            metric,
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
        "--metrics",
        required=True,
        nargs="+",
        choices=["rmse", "rmse_bias_adjusted", "rmse_anomaly"],
        help="Global RMSE metric to calculate.",
    )
    args = parser.parse_args()

    main(args.org, args.model, args.variable, args.metrics)
