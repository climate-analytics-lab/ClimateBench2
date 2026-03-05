import argparse
import logging
import os
import sys

import ee
import geemap
import xarray as xr

sys.path.append("..")
from constants import GOOGLE_CLOUD_PROJECT, HIST_START_DATE, SSP_END_DATE
from utils import standardize_dims

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


### Source specific download script ###
SOURCE = "nasa_modis"
VARIABLES = ["clt", "od550aer", "clwvi", "ctp", "ctt"]

DATA_SPECS = {
    "clt": {
        "gee_collection": "MODIS/061/MOD08_M3",
        "source_var": "Cloud_Fraction_Mean_Mean",
        "long_name": "Total Cloud Cover Percentage",
        "standard_name": "cloud_area_fraction",
        "units": "percent",
    },
    "od550aer": {
        "gee_collection": "MODIS/061/MOD08_M3",
        "source_var": "Aerosol_Optical_Depth_Land_Ocean_Mean_Mean",
        "long_name": "Ambient Aerosol Optical Thickness at 550nm",
        "standard_name": "atmosphere_optical_thickness_due_to_ambient_aerosol_particles",
        "units": "NA",
    },
    "clwvi": {
        "gee_collection": "MODIS/061/MOD08_M3",
        "source_var": "Cloud_Water_Path_Liquid_Mean_Mean",
        "long_name": "Liquid Water Cloud Water Path: Mean of Daily Mean",
        "standard_name": "atmosphere_mass_content_of_cloud_condensed_water",
        "units": "kg m**-2",
    },
    "ctp": {
        "gee_collection": "MODIS/061/MOD08_M3",
        "source_var": "Cloud_Top_Pressure_Mean_Mean",
        "long_name": "Cloud Top Pressure: Mean of Daily Mean",
        "standard_name": "cloud_top_pressure",
        "units": "hPa",
    },
    "ctt": {
        "gee_collection": "MODIS/061/MOD08_M3",
        "source_var": "Cloud_Top_Temperature_Mean_Mean",
        "long_name": "Cloud Top Temperature: Mean of Daily Mean",
        "standard_name": "cloud_top_temperature",
        "units": "K",
    },
}

ERROR_SPECS = {
    "clt": {
        "gee_collection": "MODIS/061/MOD08_M3",
        "source_var": "Cloud_Fraction_Std_Deviation_Mean",
        "long_name": "Total Cloud Cover Percentage Standard Deviation",
        "standard_name": "cloud_area_fraction_error",
        "units": "percent",
    },
    "od550aer": {
        # Error derived from land/water mask via modis_od550aer_error_preprocess
        "gee_collection": "MODIS/006/MOD44W",
        "source_var": "water_mask",
        "long_name": "Ambient Aerosol Optical Thickness at 550nm Error",
        "standard_name": "atmosphere_optical_thickness_due_to_ambient_aerosol_particles_error",
        "units": "NA",
        "error_values": {
            "land": {"absolute": 0.5, "relative": 0.15},
            "ocean": {"absolute": 0.4, "relative": 0.1},
        },
    },
    "clwvi": {
        "gee_collection": "MODIS/061/MOD08_M3",
        "source_var": "Cloud_Water_Path_Liquid_Mean_Std",
        "long_name": "Liquid Water Cloud Water Path: Standard Deviation of Daily Mean",
        "standard_name": "atmosphere_mass_content_of_cloud_condensed_water_error",
        "units": "kg m**-2",
    },
    "ctp": {
        "gee_collection": "MODIS/061/MOD08_M3",
        "source_var": "Cloud_Top_Pressure_Mean_Std",
        "long_name": "Cloud Top Pressure: Standard Deviation of Daily Mean",
        "standard_name": "cloud_top_pressure_error",
        "units": "hPa",
    },
    "ctt": {
        "gee_collection": "MODIS/061/MOD08_M3",
        "source_var": "Cloud_Top_Temperature_Mean_Std",
        "long_name": "Cloud Top Temperature: Standard Deviation of Daily Mean",
        "standard_name": "cloud_top_temperature_error",
        "units": "K",
    },
}

# Unit scaling applied after GEE download, raw data spec https://atmosphere-imager.gsfc.nasa.gov/sites/default/files/ModAtmo/MOD08_M3_fs_3045.txt
SCALING = {
    "scale_factor": {
        "clt": 1
        / 100,  # scale factor is 0.0001 but want in percent units so change to 0.01
        "od550aer": 1 / 1000,
        "clwvi": 1 / 1000,  # convert units from g to kg
        "ctp": 1 / 10,
        "ctt": 1 / 100,
    },
    "add_offset": {
        "clt": 0,
        "od550aer": 0,
        "clwvi": 0,
        "ctp": 0,
        "ctt": -15000,
    },
}


def download_from_gee(gee_collection: str, source_var: str) -> xr.Dataset:
    """Download a variable from a GEE ImageCollection over the full date range."""
    logger.info(f"Downloading {source_var} from GEE collection {gee_collection}")
    gee_images = ee.ImageCollection(gee_collection)
    dataset = gee_images.filterDate(HIST_START_DATE, SSP_END_DATE)
    ds = geemap.ee_to_xarray(dataset.select(source_var))
    return ds


def process_variable(
    ds_raw: xr.Dataset, variable: str, specs: dict, save_path: str, mode: str = "w"
):
    source_var = specs["source_var"]
    ds = ds_raw[source_var].to_dataset(name=variable)
    ds = standardize_dims(ds)
    ds[variable].encoding = {}
    ds = ds.chunk(chunks={"time": 1, "lat": -1, "lon": -1})

    if variable in SCALING:
        logger.info(
            f"Scaling {variable} by scale factor {SCALING["scale_factor"][variable]} and offset {SCALING["add_offset"][variable]}"
        )
        ds[variable] = (ds[variable] * SCALING["scale_factor"][variable]) + SCALING[
            "add_offset"
        ][variable]

    ds[variable].attrs = {
        "long_name": specs["long_name"],
        "standard_name": specs["standard_name"],
        "units": specs["units"],
        "source": SOURCE,
    }
    ds.to_zarr(save_path, mode=mode)


def process_od550aer_error(data_save_path: str, save_path: str):
    """Derive od550aer error from land/water mask and the saved od550aer data."""
    specs = ERROR_SPECS["od550aer"]
    error_values = specs["error_values"]

    logger.info("Downloading water mask from GEE for od550aer error")
    ds_mask = download_from_gee(specs["gee_collection"], specs["source_var"])
    ds_mask = standardize_dims(ds_mask)
    mask = (
        ds_mask[specs["source_var"]]
        .isel(time=0)
        .squeeze()
        .drop_vars("time", errors="ignore")
    )

    # 0 = ocean, 1 = land; build error arrays
    err_da = mask.where(mask == 0, 1)  # 0 for ocean, 1 for land
    err_abs = (err_da * error_values["ocean"]["absolute"]).where(
        err_da * error_values["ocean"]["absolute"] != 0,
        error_values["land"]["absolute"],
    )
    err_rel = (err_da * error_values["ocean"]["relative"]).where(
        err_da * error_values["ocean"]["relative"] != 0,
        error_values["land"]["relative"],
    )

    # Load the saved od550aer data and compute combined error
    logger.info(f"Loading od550aer data from {data_save_path} to compute error")
    var_ds = xr.open_zarr(data_save_path, chunks={})
    ds_err = (var_ds["od550aer"] * err_rel + err_abs).to_dataset(name="error")

    ds_err["error"].encoding = {}
    ds_err = ds_err.chunk(chunks={"time": 1, "lat": -1, "lon": -1})
    ds_err["error"].attrs = {
        "long_name": specs["long_name"],
        "standard_name": specs["standard_name"],
        "units": specs["units"],
        "source": SOURCE,
    }
    ds_err.to_zarr(save_path, mode="a")


def main(save_cloud: bool):

    logger.info("Authenticating with Google Earth Engine")
    ee.Authenticate()
    ee.Initialize(project=GOOGLE_CLOUD_PROJECT)

    for variable in VARIABLES:
        if save_cloud:
            save_path = f"gs://climatebench/observations/{variable}_{SOURCE}.zarr"
        else:
            save_path = f"../observations/{variable}_{SOURCE}.zarr"

        # Download and save data variable
        data_specs = DATA_SPECS[variable]
        logger.info(f"Processing {variable} data -> {save_path}")
        ds_raw = download_from_gee(
            data_specs["gee_collection"], data_specs["source_var"]
        )
        process_variable(ds_raw, variable, data_specs, save_path, mode="w")

        # Download and save error variable
        error_specs = ERROR_SPECS[variable]
        logger.info(f"Processing {variable} error -> {save_path}")
        if variable == "od550aer":
            process_od550aer_error(save_path, save_path)
        else:
            ds_err_raw = download_from_gee(
                error_specs["gee_collection"], error_specs["source_var"]
            )
            process_variable(ds_err_raw, "error", error_specs, save_path, mode="a")

    logger.info("Done")
    return None


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=f"Download and process {SOURCE} cloud/aerosol data via GEE."
    )
    parser.add_argument(
        "--save_cloud",
        action="store_true",
        default=False,
        help="Save output on google cloud. If not set, saves locally.",
    )
    args = parser.parse_args()
    main(save_cloud=args.save_cloud)
