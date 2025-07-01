ENSEMBLE_MEMBERS = ["r1i1p1f1", "r2i1p1f1", "r3i1p1f1"]
VARIABLE_FREQUENCY_GROUP = {
    "tas": "Amon",
    "pr": "Amon",
    "clt": "Amon",
    "tos": "Omon",
    "od550aer": "AERmon",
}
HIST_START_DATE = "2005-01-01"
HIST_END_DATE = "2014-12-31"
SSP_START_DATE = "2015-01-01"
SSP_END_DATE = "2024-12-31"
SSP_EXPERIMENT = "ssp245"
GOOGLE_CLOUD_PROJECT = "fluid-script-453604-u5"
CMIP6_MODEL_INSTITUTIONS = {
    "TaiESM1": "AS-RCEC",
    "AWI-CM-1-1-MR": "AWI",
    "AWI-ESM-1-1-LR": "AWI",
    "BCC-CSM2-MR": "BCC",
    "BCC-ESM1": "BCC",
    "CAMS-CSM1-0": "CAMS",
    "CAS-ESM2-0": "CAS",
    "FGOALS-f3-L": "CAS",
    "FGOALS-g3": "CAS",
    "IITM-ESM": "CCCR-IITM",
    "CanESM5": "CCCma",
    "CMCC-CM2-HR4": "CMCC",
    "CMCC-CM2-SR5": "CMCC",
    "CMCC-ESM2": "CMCC",
    "ACCESS-ESM1-5": "CSIRO",
    "ACCESS-CM2": "CSIRO-ARCCSS",
    "MPI-ESM1-2-HR": "MPI-M",
    "E3SM-1-0": "E3SM-Project",
    "E3SM-1-1": "E3SM-Project",
    "E3SM-1-1-ECA": "E3SM-Project",
    "EC-Earth3": "EC-Earth-Consortium",
    "EC-Earth3-AerChem": "EC-Earth-Consortium",
    "EC-Earth3-CC": "EC-Earth-Consortium",
    "EC-Earth3-Veg": "EC-Earth-Consortium",
    "EC-Earth3-Veg-LR": "EC-Earth-Consortium",
    "FIO-ESM-2-0": "FIO-QLNM",
    "MPI-ESM-1-2-HAM": "HAMMOZ-Consortium",
    "INM-CM4-8": "INM",
    "INM-CM5-0": "INM",
    "IPSL-CM5A2-INCA": "IPSL",
    "IPSL-CM6A-LR": "IPSL",
    "IPSL-CM6A-LR-INCA": "IPSL",
    "KIOST-ESM": "KIOST",
    "MIROC6": "MIROC",
    "ICON-ESM-LR": "MPI-M",
    "MPI-ESM1-2-LR": "MPI-M",
    "MRI-ESM2-0": "MRI",
    "GISS-E2-1-G": "NASA-GISS",
    "GISS-E2-1-G-CC": "NASA-GISS",
    "GISS-E2-1-H": "NASA-GISS",
    "GISS-E2-2-H": "NASA-GISS",
    "CESM2": "NCAR",
    "CESM2-FV2": "NCAR",
    "CESM2-WACCM": "NCAR",
    "CESM2-WACCM-FV2": "NCAR",
    "NorCPM1": "NCC",
    "NorESM2-LM": "NCC",
    "NorESM2-MM": "NCC",
    "KACE-1-0-G": "NIMS-KMA",
    "GFDL-CM4": "NOAA-GFDL",
    "GFDL-ESM4": "NOAA-GFDL",
    "NESM3": "NUIST",
    "SAM0-UNICON": "SNU",
    "CIESM": "THU",
    "MCM-UA-1-0": "UA",
}

OBSERVATION_DATA_SPECS = {
    "tas": {
        "nasa_airs": {
            "cloud_path": "gs://climatebench/observations/preprocessed/tas/tas_nasa_airs.zarr",
            "local_path": "observational_data/tas_nasa_airs.zarr",
            "wget_file_list": "observational_data/subset_AIRS3STM_7.0_20250521_202757_.txt",
            "source_var_name": "SurfAirTemp_A",
            "long_name": "Near-Surface Air Temperature",
            "standard_name": "air_temperature",
            "units": "K",
        },
    },
    "pr": {
        "noaa_gpcp": {
            "cloud_path": "gs://climatebench/observations/preprocessed/pr/pr_noaa_gpcp.zarr",
            "local_path": "observational_data/pr_noaa_gpcp.zarr",
            "download_url": "http://psl.noaa.gov/thredds/dodsC/Datasets/gpcp/precip.mon.mean.nc",
            "source_var_name": "precip",
            "long_name": "Average Monthly Rate of Precipitation",
            "standard_name": "precipitation_flux",
            "units": "kg m-2 s-1",
        },
    },
    "tos": {
        "noaa_oisst": {
            "cloud_path": "gs://climatebench/observations/preprocessed/tos/tos_noaa_oisst.zarr",
            "local_path": "observational_data/tos_noaa_oisst.zarr",
            "download_url": "http://psl.noaa.gov/thredds/dodsC/Datasets/noaa.oisst.v2.highres/sst.mon.mean.nc",
            "source_var_name": "sst",
            "long_name": "Sea Surface Temperature",
            "standard_name": "sea_surface_temperature",
            "units": "degC",
        },
    },
    "clt": {
        "nasa_modis": {
            "cloud_path": "gs://climatebench/observations/preprocessed/clt/clt_nasa_modis.zarr",
            "local_path": "observational_data/clt_nasa_modis.zarr",
            "gee_image_collection": "MODIS/061/MOD08_M3",
            "source_var_name": "Cloud_Fraction_Mean_Mean",
            "long_name": "Total Cloud Cover Percentage",
            "standard_name": "cloud_area_fraction",
            "units": "percent",
        },
    },
    "od550aer": {
        "nasa_modis": {
            "cloud_path": "gs://climatebench/observations/preprocessed/od550aer/od550aer_nasa_modis.zarr",
            "local_path": "observational_data/od550aer_nasa_modis.zarr",
            "gee_image_collection": "MODIS/061/MOD08_M3",
            "source_var_name": "Aerosol_Optical_Depth_Land_Ocean_Mean_Mean",
            "long_name": "Ambient Aerosol Optical Thickness at 550nm",
            "standard_name": "atmosphere_optical_thickness_due_to_ambient_aerosol_particles",
            "units": None,
        },
    },
}
# using nested dict incase we have multiple obs datasets for one var. This dict should use the main obs dataset.
OBSERVATION_DATA_PATHS = {
    "tas": {
        "cloud": OBSERVATION_DATA_SPECS["tas"]["nasa_airs"]["cloud_path"],
        "local": OBSERVATION_DATA_SPECS["tas"]["nasa_airs"]["local_path"],
    },
    "tos": {
        "cloud": OBSERVATION_DATA_SPECS["tos"]["noaa_oisst"]["cloud_path"],
        "local": OBSERVATION_DATA_SPECS["tos"]["noaa_oisst"]["local_path"],
    },
    "pr": {
        "cloud": OBSERVATION_DATA_SPECS["pr"]["noaa_gpcp"]["cloud_path"],
        "local": OBSERVATION_DATA_SPECS["pr"]["noaa_gpcp"]["local_path"],
    },
    "clt": {
        "cloud": OBSERVATION_DATA_SPECS["clt"]["nasa_modis"]["cloud_path"],
        "local": OBSERVATION_DATA_SPECS["clt"]["nasa_modis"]["local_path"],
    },
    "od550aer": {
        "cloud": OBSERVATION_DATA_SPECS["od550aer"]["nasa_modis"]["cloud_path"],
        "local": OBSERVATION_DATA_SPECS["od550aer"]["nasa_modis"]["local_path"],
    },
}
