import argparse
import logging
import os
import shutil
import subprocess
import sys

import cftime as cft
import gsw
import numpy as np
import xarray as xr
import xesmf as xe

sys.path.append("..")
from utils import download_file

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


### Source specific download script ###
SOURCE = "ARGO"
VARIABLE = "ohc"
CLOUD_PATH = f"gs://climatebench/observations/{VARIABLE}_{SOURCE}.zarr"
LOCAL_PATH = f"../observations/{VARIABLE}_{SOURCE}.zarr"
RAW_DATA_DIR = "../observations/argo_raw_data"
RAW_ZARR_PATH = "../observations/argo_raw.zarr"
TEMP_BASE_URL = "https://sio-argo.ucsd.edu/RG/RG_ArgoClim_Temperature_2019.nc.gz"
SAL_BASE_URL = "https://sio-argo.ucsd.edu/RG/RG_ArgoClim_Salinity_2019.nc.gz"
EXTRA_YEAR_URL_TEMPLATE = (
    "https://sio-argo.ucsd.edu/RG/RG_ArgoClim_{year}{month}_2019.nc.gz"
)
EXTRA_YEARS = range(2019, 2025)
DATA_SPECS = {
    "long_name": "Ocean Heat Content",
    "standard_name": "ocean_heat_content",
    "units": "J",
    "source": SOURCE,
    "source_url": "https://sio-argo.ucsd.edu/RG_Climatology.html",
}


def fix_time(ds):
    ds["TIME"] = cft.num2date(times=ds.TIME, units=ds.TIME.units, calendar="360_day")
    ds["TIME"] = ds.indexes["TIME"].to_datetimeindex(time_unit="ns")
    return ds


def download_base_climatology():
    os.makedirs(RAW_DATA_DIR, exist_ok=True)

    temp_gz = os.path.join(RAW_DATA_DIR, "RG_ArgoClim_Temperature_2019.nc.gz")
    sal_gz = os.path.join(RAW_DATA_DIR, "RG_ArgoClim_Salinity_2019.nc.gz")

    logger.info(f"Downloading base temperature climatology from {TEMP_BASE_URL}")
    download_file(TEMP_BASE_URL, temp_gz)
    logger.info(f"Downloading base salinity climatology from {SAL_BASE_URL}")
    download_file(SAL_BASE_URL, sal_gz)

    logger.info("Decompressing base climatology files")
    subprocess.run(["gunzip", temp_gz], check=True)
    subprocess.run(["gunzip", sal_gz], check=True)

    temp_nc = temp_gz[:-3]
    sal_nc = sal_gz[:-3]

    logger.info("Merging temperature and salinity, saving to intermediate zarr")
    ds_temp = xr.open_dataset(temp_nc, decode_times=False)
    ds_sal = xr.open_dataset(sal_nc, decode_times=False)
    ds = xr.merge([ds_temp, ds_sal])
    ds = fix_time(ds)
    ds.chunk({"TIME": 1, "LATITUDE": -1, "LONGITUDE": -1, "PRESSURE": -1}).to_zarr(
        RAW_ZARR_PATH
    )
    logger.info(f"Base climatology saved to {RAW_ZARR_PATH}")


def append_extra_years():
    for year in EXTRA_YEARS:
        for month in range(1, 13):
            month_str = f"{month:02d}"
            file_name = f"RG_ArgoClim_{year}{month_str}_2019.nc.gz"
            url = EXTRA_YEAR_URL_TEMPLATE.format(year=year, month=month_str)
            gz_path = os.path.join(RAW_DATA_DIR, file_name)
            nc_path = gz_path[:-3]

            logger.info(f"Downloading extra year file {year}-{month_str}")
            download_file(url, gz_path)
            subprocess.run(["gunzip", gz_path], check=True)

            ds = xr.open_dataset(nc_path, decode_times=False)
            ds = fix_time(ds)
            ds.chunk(
                {"TIME": 1, "LATITUDE": -1, "LONGITUDE": -1, "PRESSURE": -1}
            ).to_zarr(RAW_ZARR_PATH, append_dim="TIME")
            os.remove(nc_path)


def compute_and_save_ohc(save_path):
    logger.info(f"Loading intermediate zarr from {RAW_ZARR_PATH}")
    ds = xr.open_zarr(RAW_ZARR_PATH, chunks={})
    ds = ds.rename(
        {"LATITUDE": "lat", "LONGITUDE": "lon", "PRESSURE": "pressure", "TIME": "time"}
    )

    logger.info("Computing absolute temperature and salinity")
    ds["salinity"] = ds["ARGO_SALINITY_MEAN"] + ds["ARGO_SALINITY_ANOMALY"]
    ds["temperature"] = ds["ARGO_TEMPERATURE_MEAN"] + ds["ARGO_TEMPERATURE_ANOMALY"]

    logger.info("Computing gsw thermodynamic properties")
    ds["CT"] = gsw.conversions.CT_from_t(
        SA=ds["salinity"], t=ds["temperature"], p=ds["pressure"]
    )
    ds["rho"] = gsw.density.rho(SA=ds["salinity"], CT=ds["CT"], p=ds["pressure"])
    ds["cp"] = gsw.cp_t_exact(SA=ds["salinity"], t=ds["temperature"], p=ds["pressure"])

    logger.info("Computing cell area, depth, and volume")
    ds["area_km2"] = xe.util.cell_area(ds[["lat", "lon"]], earth_radius=6378)
    ds["depth_km"] = gsw.conversions.z_from_p(p=ds["pressure"], lat=ds["lat"]) / 1000
    ds["volume"] = (
        abs(ds["area_km2"] * ds["depth_km"].diff(dim="pressure")) * 1e9
    )  # km3 to m3

    logger.info("Computing OHC")
    ds["ohc"] = ds["volume"] * ds["rho"] * ds["ARGO_TEMPERATURE_ANOMALY"] * ds["cp"]

    logger.info("Summing over mixed (0-100 dbar) and deep (0-2000 dbar) layers")
    ds_mixed = (
        ds.sel(pressure=slice(0, 100))
        .sum(dim="pressure")
        .expand_dims({"layer": ["mixed"]})
    )
    ds_deep = (
        ds.sel(pressure=slice(0, 2000))
        .sum(dim="pressure")
        .expand_dims({"layer": ["deep"]})
    )

    ds_combined = xr.concat([ds_mixed, ds_deep], dim="layer").chunk(
        {"layer": 1, "lat": -1, "lon": -1, "time": 100}
    )[["ohc"]]

    ds_combined["ohc"].attrs = DATA_SPECS

    logger.info(f"Saving OHC dataset to {save_path}")
    ds_combined.to_zarr(save_path)


def main(save_cloud: bool):

    download_base_climatology()
    append_extra_years()

    if save_cloud:
        save_path = CLOUD_PATH
    else:
        save_path = LOCAL_PATH

    compute_and_save_ohc(save_path)

    logger.info(f"Deleting raw data directory {RAW_DATA_DIR}")
    shutil.rmtree(RAW_DATA_DIR)
    logger.info(f"Deleting intermediate zarr {RAW_ZARR_PATH}")
    shutil.rmtree(RAW_ZARR_PATH)
    logger.info("Done")

    return None


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=f"Download and process {SOURCE} {VARIABLE} data."
    )
    parser.add_argument(
        "--save_cloud",
        action="store_true",
        default=False,
        help="Save output on google cloud. If not set, saves locally.",
    )
    args = parser.parse_args()
    main(save_cloud=args.save_cloud)
