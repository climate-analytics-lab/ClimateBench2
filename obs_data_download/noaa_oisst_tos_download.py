import xarray as xr

from utils import standardize_dims

# data downloaded from here https://psl.noaa.gov/data/gridded/data.noaa.oisst.v2.highres.html


def main():

    url = "http://psl.noaa.gov/thredds/dodsC/Datasets/noaa.oisst.v2.highres/sst.mon.mean.nc"

    ds = xr.open_dataset(url).sel(time=slice("2005-01-01", "2024-12-31"))
    ds_fixed = standardize_dims(ds)
    ds_fixed.sst.encoding = {}

    ds_attrs = ds_fixed.attrs
    ds_var_attrs = ds_fixed.sst.attrs

    ds_fixed = ds_fixed["sst"].to_dataset(name="tos")
    ds_fixed.attrs = ds_attrs
    ds_fixed["tos"].attrs = ds_var_attrs

    ds_fixed.chunk({"time": 1, "lat": -1, "lon": -1}).to_zarr(
        "observational_data/tos_noaa.zarr"
    )


if __name__ == "__main__":
    main()
