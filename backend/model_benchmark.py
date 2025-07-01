import argparse
import logging

import pandas as pd
import xarray as xr
import xesmf as xe

from constants import (
    ENSEMBLE_MEMBERS,
    HIST_END_DATE,
    HIST_START_DATE,
    SSP_END_DATE,
    SSP_EXPERIMENT,
    SSP_START_DATE,
)
from utils import DataFinder, MetricCalculation, SaveResults

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def main(model, variable, adjustments, lat_min, lat_max, save_to_cloud, overwrite):
    logger.info(
        f"Processing model: {model}, variable: {variable}, adjustments: {adjustments}"
    )

    data_finder = DataFinder(model=model, variable=variable)

    logger.info("Reading model data")
    model_ds = data_finder.load_model_ds().sel(
        time=slice(HIST_START_DATE, SSP_END_DATE)
    )
    logger.info("Reading model cell area data")
    cell_var_name = "areacella" if variable != "tos" else "areacello"
    fx_ds = data_finder.load_cell_area_ds(cell_var_name)
    obs_ds = data_finder.load_obs_ds()

    logger.info("Regridding observations")
    # regrid obs data to the model grid
    regridder = xe.Regridder(
        obs_ds, model_ds[["lat", "lon"]], "bilinear", periodic=True
    )
    obs_rg_ds = regridder(obs_ds[variable], keep_attrs=True).to_dataset(name=variable)

    # set up metric calculation class
    metric_calculator = MetricCalculation(
        observations=obs_rg_ds[variable],
        model=model_ds[variable],
        weights=fx_ds,
        lat_min=lat_min,
        lat_max=lat_max,
    )
    # set up data save class
    save_results = SaveResults(variable=variable, experiment="RMSE")
    # if overwrite paramter is set, delete files in the save path
    if overwrite:
        logger.info(f"Deleting stale data in: {save_results.data_path}")
        save_results.overwrite(save_to_cloud=save_to_cloud)

    for adjustment in adjustments:
        logger.info(f"Calculating RMSE with adjustment: {adjustment}")
        data_label = "rmse" if adjustment == "none" else "rmse_" + adjustment
        logger.info("running zonal mean rmse")
        rmse_hist = metric_calculator.calculate_rmse(
            metric="zonal_mean",
            adjustment=adjustment,
            time_slice=slice(HIST_START_DATE, HIST_END_DATE),
        ).values.tolist()
        rmse_ssp245 = metric_calculator.calculate_rmse(
            metric="zonal_mean",
            adjustment=adjustment,
            time_slice=slice(SSP_START_DATE, SSP_END_DATE),
        ).values.tolist()
        result_df = pd.DataFrame(
            {
                "model": [model],
                "variable": [variable],
                "ensemble members": ["_".join(ENSEMBLE_MEMBERS)],
                "metric": [data_label],
                "historical": [rmse_hist],
                SSP_EXPERIMENT: [rmse_ssp245],
            }
        )
        logger.info("running temporal rmse")
        rmse_hist_map = metric_calculator.calculate_rmse(
            metric="temporal",
            adjustment=adjustment,
            time_slice=slice(HIST_START_DATE, HIST_END_DATE),
        )
        rmse_ssp245_map = metric_calculator.calculate_rmse(
            metric="temporal",
            adjustment=adjustment,
            time_slice=slice(SSP_START_DATE, SSP_END_DATE),
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
        ).to_dataset(name=data_label)
        logger.info("running spatial rmse")
        rmse_time_series = metric_calculator.calculate_rmse(
            metric="spatial",
            adjustment=adjustment,
            time_slice=slice(HIST_START_DATE, SSP_END_DATE),
        ).to_dataset(name=data_label)

        # save data
        logger.info("saving data")
        save_results.save_csv(
            result_df, f"zonal_mean_rmse_{lat_min}_{lat_max}_results.csv", save_to_cloud
        )
        save_results.save_zarr(
            ds=rmse_map,
            file_name=f"{model}_temporal_rmse_results.zarr",
            save_to_cloud=save_to_cloud,
        )
        save_results.save_zarr(
            ds=rmse_time_series,
            file_name=f"{model}_spatial_{lat_min}_{lat_max}_rmse_results.zarr",
            save_to_cloud=save_to_cloud,
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Data processing for model benchmarking"
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
        "--adjustments",
        required=True,
        nargs="+",
        choices=["none", "bias_adjusted", "anomaly"],
        help="Global RMSE metric to calculate.",
    )
    parser.add_argument(
        "--lat_min",
        default=-90,
        help="minimum latitude for zonal slice. must be less than lat max but greater than -90",
    )
    parser.add_argument(
        "--lat_max",
        default=90,
        help="maximum latitude for zonal slice. must be greater than lat min but less than 90",
    )
    parser.add_argument(
        "--save_to_cloud",
        action="store_true",
        default=False,
        help="Save data on google cloud if passed, if not passsed saved locally",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        default=False,
        help="Deletes any previously saved data at the save path.",
    )
    args = parser.parse_args()

    main(
        model=args.model,
        variable=args.variable,
        adjustments=args.adjustments,
        lat_min=args.lat_min,
        lat_max=args.lat_max,
        save_to_cloud=args.save_to_cloud,
        overwrite=args.overwrite,
    )
