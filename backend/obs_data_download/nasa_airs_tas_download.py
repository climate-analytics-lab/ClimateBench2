import glob
import logging
import os

import pandas as pd
import xarray as xr
from climatebench_exp.backend.utils import build_zarr_store, standardize_dims

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def main():
    logger.info("begining download script for NASA AIRS surface temperature data")
    # download raw files
    # takes ~20 min to download
    os.system(
        'wget --load-cookies ~/.urs_cookies --save-cookies ~/.urs_cookies --keep-session-cookies  --content-disposition -i "subset_AIRS3STM_7.0_20250521_202757_.txt"'
    )

    logger.info("raw data download complete. beginning zarr creation process.")

    # save zarr template
    zarr_store_file_path = "observational_data/tas_nasa_airs.zarr"
    tas_files = glob.glob("AIRS*")
    times = pd.date_range("2005-01-01", "2024-12-01", freq="MS")
    ds = xr.open_dataset(tas_files[0], decode_times=False)
    ds = ds.expand_dims({"time": [times[0]]})  # placeholder
    ds_fixed = standardize_dims(ds)
    dims_dict = {"time": times, "lat": ds_fixed.lat.values, "lon": ds_fixed.lon.values}
    build_zarr_store(
        var_name="tas",
        dims_dict=dims_dict,
        attributes=ds.attrs,
        store_path=zarr_store_file_path,
    )

    # now go through all
    for date in times:
        year = date.year
        month = "0" + str(date.month)
        file_name = glob.glob(f"AIRS.{year}.{month[-2:]}*")[0]
        ds = xr.open_dataset(file_name, decode_times=False)
        ds = ds.expand_dims({"time": [date]})

        ds_fixed = standardize_dims(ds)
        ds_fixed = ds_fixed["SurfAirTemp_A"].to_dataset(name="tas")
        ds_fixed.tas.encoding = {}
        ds_fixed.chunk(chunks={"time": 1, "lat": -1, "lon": -1}).to_zarr(
            zarr_store_file_path, region="auto"
        )
        logger.info(f"wrote {date} to zarr store")
        # delete file
        os.remove(file_name)

    os.remove("Overview_of_the_AIRS_Mission.pdf")
    os.remove("V7_L3_User_Guide.pdf")
    # save data on google cloud --> need to set up google cloud storage bucket
    logger.info(f"data saved to {zarr_store_file_path}")
    # upload to google cloud
    gcs_data_path = "gs://climatebench/observations/preprocessed/tas/tas_nasa_airs.zarr"
    os.system(f"gsutil -m cp -r {zarr_store_file_path} {gcs_data_path}")
    logger.info(f"uploaded data to google cloud: {gcs_data_path}")


if __name__ == "__main__":
    main()
