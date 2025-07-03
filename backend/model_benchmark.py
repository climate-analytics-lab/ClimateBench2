import argparse
import logging

import xesmf as xe

from utils import DataFinder, MetricCalculation, SaveResults

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def main(
    model: str,
    variable: str,
    metric: str,
    adjustment: str,
    lat_min: int = -90,
    lat_max: int = 90,
    start_year: int = 2005,
    end_year: int = 2014,
    save_to_cloud: bool = False,
    overwrite: bool = False,
):
    logger.info(
        f"Processing model: {model}, variable: {variable}, metric: {metric}, adjustment: {adjustment}"
    )

    data_finder = DataFinder(
        model=model, variable=variable, start_year=start_year, end_year=end_year
    )

    logger.info("Reading model data")
    model_ds = data_finder.load_model_ds()
    logger.info("Reading model cell area data")
    fx_ds = data_finder.load_cell_area_ds()
    logger.info("Reading observations")
    obs_ds = data_finder.load_obs_ds()

    logger.info("Regridding observations")
    # regrid obs data to the model grid
    regridder = xe.Regridder(
        obs_ds, model_ds[["lat", "lon"]], "bilinear", periodic=True
    )
    obs_rg_ds = regridder(obs_ds[variable], keep_attrs=True)

    # set up metric calculation class
    metric_calculator = MetricCalculation(
        observations=obs_rg_ds,
        model=model_ds[variable],
        weights=fx_ds,
        lat_min=lat_min,
        lat_max=lat_max,
    )

    logger.info(f"Calculating {adjustment} {metric}")
    result = getattr(metric_calculator, metric)(adjustment=adjustment)

    # set up data save class
    save_results = SaveResults(
        model=model,
        variable=variable,
        metric=metric,
        adjustment=adjustment,
        start_year=start_year,
        end_year=end_year,
        lat_max=lat_max,
        lat_min=lat_min,
    )
    # if overwrite paramter is set, delete files in the save path
    if overwrite:
        logger.info(f"Deleting stale data in: {save_results.data_path}")
        save_results.overwrite(save_to_cloud=save_to_cloud)

    save_results.write_data(results=result, save_to_cloud=save_to_cloud)


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
        "--metric",
        required=True,
        choices=["zonal_mean_rmse", "spatial_rmse", "temporal_rmse"],
        help="Metric to calculate. Must be a member of the MetricCalculation class.",
    )
    parser.add_argument(
        "--adjustment",
        required=False,
        choices=[None, "bias_adjusted", "anomaly"],
        help="Adjustment to make to the data before metric calculation",
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
        "--start_year",
        default=2005,
        help="Start year for metric calculatino time period.",
    )
    parser.add_argument(
        "--end_year",
        default=2014,
        help="End year for metric calculatino time period.",
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
        metric=args.metric,
        adjustment=args.adjustment,
        lat_min=args.lat_min,
        lat_max=args.lat_max,
        start_year=args.start_year,
        end_year=args.end_year,
        save_to_cloud=args.save_to_cloud,
        overwrite=args.overwrite,
    )
