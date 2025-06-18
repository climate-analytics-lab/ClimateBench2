import logging
import os

import xarray as xr
from climatebench_exp.backend.utils import standardize_dims

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# data downloaded from here https://psl.noaa.gov/data/gridded/data.noaa.oisst.v2.highres.html


def main():

    url = "http://psl.noaa.gov/thredds/dodsC/Datasets/noaa.oisst.v2.highres/sst.mon.mean.nc"

    logger.info(f"downloading data from : {url}")

    ds = xr.open_dataset(url).sel(time=slice("2005-01-01", "2024-12-31"))
    ds_fixed = standardize_dims(ds)
    ds_fixed.sst.encoding = {}

    ds_attrs = ds_fixed.attrs
    ds_var_attrs = ds_fixed.sst.attrs

    ds_fixed = ds_fixed["sst"].to_dataset(name="tos")
    ds_fixed.attrs = ds_attrs
    ds_fixed["tos"].attrs = ds_var_attrs

    local_data_path = "observational_data/tos_noaa_oisst.zarr"
    logger.info(f"saving data locally : {local_data_path}")
    ds_fixed.chunk({"time": 1, "lat": -1, "lon": -1}).to_zarr(local_data_path)
    # upload to google cloud
    gcs_data_path = (
        "gs://climatebench/observations/preprocessed/tos/tos_noaa_oisst.zarr"
    )
    os.system(f"gsutil -m cp -r {local_data_path} {gcs_data_path}")
    logger.info(f"uploaded data to google cloud: {gcs_data_path}")


if __name__ == "__main__":
    main()
