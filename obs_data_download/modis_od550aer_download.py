import logging

import ee
import geemap
import pandas as pd

from utils import build_zarr_store, standardize_dims

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# reference for unit conversion: https://atmosphere-imager.gsfc.nasa.gov/sites/default/files/ModAtmo/MOD08_M3_fs_3044.txt


def main():
    logger.info("begining download script for MODIS aerosol optical depth data")
    ee.Authenticate()
    ee.Initialize(project="fluid-script-453604-u5")

    modis_images = ee.ImageCollection("MODIS/061/MOD08_M3")

    zarr_store_file_path = "observational_data/od550aer_modis.zarr"
    # do small sample to set up zarr store
    dataset = modis_images.filterDate("2005-01-01", "2005-1-30")
    ds = geemap.ee_to_xarray(
        dataset.select("Aerosol_Optical_Depth_Land_Ocean_Mean_Mean")
    )
    ds_fixed = standardize_dims(ds)
    times = pd.date_range("2005-01-01", "2024-12-01", freq="MS")
    dims_dict = {"time": times, "lat": ds_fixed.lat.values, "lon": ds_fixed.lon.values}

    build_zarr_store(
        var_name="od550aer",
        dims_dict=dims_dict,
        attributes=ds.attrs,
        store_path=zarr_store_file_path,
    )

    # now go through all
    for date in times:
        dataset = modis_images.filterDate(date, date.strftime("%Y-%m-20"))
        ds = geemap.ee_to_xarray(
            dataset.select("Aerosol_Optical_Depth_Land_Ocean_Mean_Mean")
        )
        ds_fixed = standardize_dims(ds)
        ds_fixed = ds_fixed["Aerosol_Optical_Depth_Land_Ocean_Mean_Mean"].to_dataset(
            name="od550aer"
        )
        ds_fixed.od550aer.encoding = {}
        ds_fixed["od550aer"] = (
            ds_fixed["od550aer"] / 1000
        )  # values can range -0.01 to 5 (unitless). see https://darktarget.gsfc.nasa.gov/products/modis/land-10 for range details
        ds_fixed.chunk(chunks={"time": 1, "lat": -1, "lon": -1}).to_zarr(
            zarr_store_file_path, region="auto"
        )
        logger.info(f"wrote {date} to zarr store")

    logger.info(f"data saved to {zarr_store_file_path}")


if __name__ == "__main__":
    main()
