import logging
import os

import xarray as xr
from climatebench_exp.backend.utils import standardize_dims

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# data downloaded from here https://psl.noaa.gov/data/gridded/data.gpcp.html


def main():

    url = "http://psl.noaa.gov/thredds/dodsC/Datasets/gpcp/precip.mon.mean.nc"

    logger.info(f"downloading data from : {url}")

    ds = xr.open_dataset(url).sel(time=slice("2005-01-01", "2024-12-31"))
    ds_fixed = standardize_dims(ds)
    ds_fixed.precip.encoding = {}

    ds_attrs = ds_fixed.attrs
    ds_var_attrs = ds_fixed.precip.attrs

    ds_fixed = ds_fixed["precip"].to_dataset(name="pr")
    ds_fixed.attrs = ds_attrs
    ds_fixed["pr"].attrs = ds_var_attrs

    # convert units from mm/day to kg/(s*m2)
    ds_fixed["pr"] = ds_fixed["pr"] / 86400
    ds_fixed.pr.attrs["units"] = "kg m-2 s-1"
    ds_fixed.pr.attrs["long_name"] = "Precipitation"
    ds_fixed.pr.attrs["standard_name"] = "precipitation_flux"

    local_data_path = "observational_data/pr_noaa.zarr"
    logger.info(f"saving data locally : {local_data_path}")
    ds_fixed.chunk({"time": 1, "lat": -1, "lon": -1}).to_zarr(local_data_path)
    # upload to google cloud
    gcs_data_path = "gs://climatebench/observations/preprocessed/pr/pr_noaa_gpcp.zarr"
    os.system(f"gsutil -m cp -r {local_data_path} {gcs_data_path}")
    logger.info(f"uploaded data to google cloud: {gcs_data_path}")


if __name__ == "__main__":
    main()
