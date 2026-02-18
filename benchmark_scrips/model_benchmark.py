import argparse
import logging
import os
import shutil

import gsw
import xarray as xr
import xesmf as xe

from benchmark_utils import DataFinder, MetricCalculation, SaveResults

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
    ocean_depth: str = None,
    save_to_cloud: bool = False,
    overwrite: bool = False,
):
    logger.info(
        f"Processing model: {model}, variable: {variable}, metric: {metric}, adjustment: {adjustment}"
    )
    ensemble_mean = False if "crps" in metric else True

    temp_dir = "data_cache"
    os.makedirs(temp_dir, exist_ok=True)

    if variable == "ohc":
        data_finder = DataFinder(
            model=model, variable="thetao", start_year=start_year, end_year=end_year
        )
        data_finder_so = DataFinder(
            model=model, variable="so", start_year=start_year, end_year=end_year
        )
        logger.info("Reading model data")

        model_ds = data_finder.load_model_ds(ensemble_mean=ensemble_mean)
        so_ds = data_finder_so.load_model_ds(ensemble_mean=ensemble_mean)
        model_ds = xr.merge([model_ds, so_ds])

        logger.info("Reading model cell area data")
        fx_ds = data_finder.load_cell_area_ds()

        ###### climatology ######
        logger.info("Reading climatology data")
        df_thetao_pt1 = DataFinder(
            model=model, variable="thetao", start_year=2004, end_year=2014
        )
        df_thetao_pt2 = DataFinder(
            model=model, variable="thetao", start_year=2015, end_year=2018
        )
        thetao_pt1_ds = df_thetao_pt1.load_model_ds(ensemble_mean=True)
        thetao_pt2_ds = df_thetao_pt2.load_model_ds(ensemble_mean=True)

        climatology_ds = xr.concat([thetao_pt1_ds, thetao_pt2_ds], dim="time").mean(
            dim="time"
        )

        ####### ocean heat content #######
        logger.info("calculating ocean heat conent")
        # step 1: convert depth to pressure
        model_ds["pressure"] = gsw.conversions.p_from_z(
            z=model_ds["lev"] * -1, lat=model_ds["lat"]
        )

        # step 2: converty practicacl salinity (ppt) to absolute salinity
        model_ds["SA"] = gsw.conversions.SA_from_SP(
            model_ds["so"], model_ds["pressure"], model_ds["lon"], model_ds["lat"]
        )

        # step 3: convert potential temperature to in situ temp
        model_ds["CT"] = gsw.conversions.CT_from_pt(model_ds["SA"], model_ds["thetao"])
        model_ds["t"] = gsw.conversions.t_from_CT(
            model_ds["SA"], model_ds["CT"], model_ds["pressure"]
        )

        # step 3.5: convert temperature to temperature anomaly
        model_ds["thetao_anom"] = model_ds["thetao"] - climatology_ds["thetao"]
        model_ds["CT_anom"] = gsw.conversions.CT_from_pt(
            model_ds["SA"], model_ds["thetao_anom"]
        )
        model_ds["t_anom"] = gsw.conversions.t_from_CT(
            model_ds["SA"], model_ds["CT_anom"], model_ds["pressure"]
        )

        # step 4: calculate density
        model_ds["rho"] = gsw.density.rho(
            model_ds["SA"], model_ds["CT"], model_ds["pressure"]
        )

        # step 5: calculate heat capacity
        model_ds["cp"] = gsw.cp_t_exact(
            model_ds["SA"], model_ds["t"], model_ds["pressure"]
        )

        # step 6: calculate volume
        model_ds["volume"] = abs(fx_ds * model_ds["lev"].diff(dim="lev"))

        # step 7: calculate heat content
        model_ds["ohc"] = (
            model_ds["volume"] * model_ds["rho"] * model_ds["t_anom"] * model_ds["cp"]
        )

        # step 8: integrate over ocean depth
        model_deep_ds = (
            model_ds["ohc"]
            .sel(lev=slice(0, 2000))
            .sum(dim="lev")
            .expand_dims({"layer": ["deep"]})
        )
        model_mixed_ds = (
            model_ds["ohc"]
            .sel(lev=slice(0, 100))
            .sum(dim="lev")
            .expand_dims({"layer": ["mixed"]})
        )
        model_integrated_ds = xr.concat(
            [model_mixed_ds, model_deep_ds], dim="layer"
        ).drop_encoding()

        # step 9: cache model data
        logger.info(f"caching model data in {temp_dir}")
        data_cache_file_path = f"{temp_dir}/model_ohc.zarr"
        model_integrated_ds.chunk(
            {"layer": 1, "lat": -1, "lon": -1, "time": 100}
        ).to_zarr(data_cache_file_path)

        model_ds = xr.open_zarr(data_cache_file_path, chunks={})

    else:

        data_finder = DataFinder(
            model=model, variable=variable, start_year=start_year, end_year=end_year
        )

        logger.info("Reading model data")
        model_ds = data_finder.load_model_ds(ensemble_mean=ensemble_mean)
        logger.info("Reading model cell area data")
        fx_ds = data_finder.load_cell_area_ds()

    logger.info("Reading observations")
    obs_ds = data_finder.load_obs_ds()
    ensemble_members = data_finder.ensemble_members

    logger.info("Regridding observations")
    # regrid obs data to the model grid
    regridder = xe.Regridder(
        obs_ds, model_ds[["lat", "lon"]], "bilinear", periodic=True
    )
    obs_rg_ds = regridder(obs_ds[variable], keep_attrs=True)

    # select ocean depth layer
    if ocean_depth:
        obs_rg_ds = obs_rg_ds.sel(layer=ocean_depth)
        model_ds = model_ds.sel(layer=ocean_depth)

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

    var_save_name = variable if ocean_depth is None else f"{variable}_{ocean_depth}"

    # set up data save class
    save_results = SaveResults(
        model=model,
        variable=var_save_name,
        ensemble_members=ensemble_members,
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

    # delete temp files
    if os.path.exists(temp_dir):
        shutil.rmtree(temp_dir)


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
        choices=[
            "tas",
            "pr",
            "clt",
            "tos",
            "od550aer",
            "rsut",
            "rsutcs",
            "rlut",
            "rlutcs",
            "ohc",
        ],
    )
    parser.add_argument(
        "--metric",
        required=True,
        choices=[
            "zonal_mean_rmse",
            "zonal_mean_mae",
            "zonal_mean_crps",
            "spatial_rmse",
            "spatial_mae",
            "spatial_crps",
            "temporal_rmse",
        ],
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
        type=int,
        help="minimum latitude for zonal slice. must be less than lat max but greater than -90",
    )
    parser.add_argument(
        "--lat_max",
        default=90,
        type=int,
        help="maximum latitude for zonal slice. must be greater than lat min but less than 90",
    )
    parser.add_argument(
        "--start_year",
        default=2005,
        type=int,
        help="Start year for metric calculatino time period.",
    )
    parser.add_argument(
        "--end_year",
        default=2014,
        type=int,
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
    parser.add_argument(
        "--ocean_depth",
        default=None,
        type=str,
        choices=["deep", "mixed"],
        help="Relevant for ocean heat content benchmark. mixed = 100m, deep = 2,000 m.",
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
        ocean_depth=args.ocean_depth,
        save_to_cloud=args.save_to_cloud,
        overwrite=args.overwrite,
    )
