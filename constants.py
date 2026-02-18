VARIABLE_FREQUENCY_GROUP = {
    "tas": "Amon",
    "pr": "Amon",
    "clt": "Amon",
    "tos": "Omon",
    "od550aer": "AERmon",
    "rsut": "Amon",
    "rlut": "Amon",
    "rsutcs": "Amon",
    "rlutcs": "Amon",
    "thetao": "Omon",
    "so": "Omon",
}
HIST_START_DATE = "1960-01-01"
HIST_END_DATE = "2014-12-31"
SSP_START_DATE = "2015-01-01"
SSP_END_DATE = "2024-12-31"
SSP_EXPERIMENT = "ssp245"
GOOGLE_CLOUD_PROJECT = "fluid-script-453604-u5"

OBSERVATION_DATA_SPECS = {
    "tas": {
        "HadCRUT5": {
            "cloud_path": "gs://climatebench/observations/tas_HadCRUT5.zarr",
            "local_path": "observations/tas_HadCRUT5.zarr",
            "download_url": "https://www.metoffice.gov.uk/hadobs/hadcrut5/data/HadCRUT.5.0.2.0/analysis/HadCRUT.5.0.2.0.analysis.anomalies.ensemble_mean.nc",
            "climatology_url": "https://crudata.uea.ac.uk/cru/data/temperature/absolute_v5.nc",
            "climatology_var_name": "tem",
            "source_var_name": "tas_mean",
            "long_name": "Near-Surface Air Temperature",
            "standard_name": "air_temperature",
            "units": "K",
        },
        "HadCRUT5_error": {
            "cloud_path": "gs://climatebench/observations/tas_HadCRUT5_error.zarr",
            "local_path": "observations/tas_HadCRUT5_error.zarr",
            "download_url": "https://www.metoffice.gov.uk/hadobs/hadcrut5/data/HadCRUT.5.0.2.0/non-infilled/HadCRUT.5.0.2.0.uncorrelated.nc",
            "source_var_name": "tas_unc",
            "long_name": "standard_uncertainty in blended air_temperature_anomaly over land with sea_water_temperature_anomaly",
            "standard_name": "tas_unc",
            "units": "K",
        },
        "NASA_GISS": {
            "cloud_path": "gs://climatebench/observations/tas_NASA_GISS.zarr",
            "local_path": "observations/tas_NASA_GISS.zarr",
            "download_url": "https://downloads.psl.noaa.gov/Datasets/gistemp/combined/250km/air.2x2.250.mon.anom.comb.nc",
            "climatology_url": "https://downloads.psl.noaa.gov/Datasets/gistemp/combined/250km/air.2x2.250.mon.1991-2020.ltm.comb.nc",
            "climatology_var_name": "air",
            "source_var_name": "air",
            "long_name": "Near-Surface Air Temperature",
            "standard_name": "air_temperature",
            "units": "K",
        },
        # "Berkeley_BEST": {
        #     "cloud_path": "gs://climatebench/observations/tas_Berkeley_BEST.zarr",
        #     "local_path": "observations/tas_Berkeley_BEST.zarr",
        #     "download_url": "https://berkeley-earth-temperature.s3.us-west-1.amazonaws.com/Global/Gridded/Land_and_Ocean_LatLong1.nc",
        #     "climatology_url": "https://berkeley-earth-temperature.s3.us-west-1.amazonaws.com/Global/Gridded/Land_and_Ocean_LatLong1.nc",
        #     "climatology_var_name": "climatology",
        #     "source_var_name": "temperature",
        #     "long_name": "Near-Surface Air Temperature",
        #     "standard_name": "air_temperature",
        #     "units": "K",
        # },
    },
    "pr": {
        "noaa_gpcp": {
            "cloud_path": "gs://climatebench/observations/pr_noaa_gpcp.zarr",
            "local_path": "observations/pr_noaa_gpcp.zarr",
            "download_url": "https://downloads.psl.noaa.gov/Datasets/gpcp/precip.mon.mean.nc",
            "source_var_name": "precip",
            "long_name": "Average Monthly Rate of Precipitation",
            "standard_name": "precipitation_flux",
            "units": "kg m-2 s-1",
        },
        "noaa_gpcp_error": {
            "cloud_path": "gs://climatebench/observations/pr_noaa_gpcp_error.zarr",
            "local_path": "observations/pr_noaa_gpcp_error.zarr",
            "download_url": "https://downloads.psl.noaa.gov/Datasets/gpcp/precip.mon.mean.error.nc",
            "source_var_name": "precip",
            "long_name": "Absolute Error: Monthly Rate of Precipitation",
            "standard_name": "precipitation_flux_error",
            "units": "kg m-2 s-1",
        },
    },
    "tos": {
        "noaa_oisst": {
            "cloud_path": "gs://climatebench/observations/tos_noaa_oisst.zarr",
            "local_path": "observations/tos_noaa_oisst.zarr",
            "download_url": "https://downloads.psl.noaa.gov/Datasets/noaa.oisst.v2.highres/sst.mon.mean.nc",
            "source_var_name": "sst",
            "long_name": "Sea Surface Temperature",
            "standard_name": "sea_surface_temperature",
            "units": "degC",
        },
        "noaa_oisst_error": {
            "cloud_path": "gs://climatebench/observations/tos_noaa_oisst_error.zarr",
            "local_path": "observations/tos_noaa_oisst_error.zarr",
            "download_url": "https://downloads.psl.noaa.gov/Datasets/noaa.oisst.v2.highres/sst.day.err.{}.nc",
            "download_multiple": True,
            "file_date_range": [1981, 2025],
            "source_var_name": "err",
            "long_name": "Sea Surface Temperature",
            "standard_name": "sea_surface_temperature",
            "units": "degC",
        },
    },
    "clt": {
        "nasa_modis": {
            "cloud_path": "gs://climatebench/observations/clt_nasa_modis.zarr",
            "local_path": "observations/clt_nasa_modis.zarr",
            "gee_image_collection": "MODIS/061/MOD08_M3",
            "source_var_name": "Cloud_Fraction_Mean_Mean",
            "long_name": "Total Cloud Cover Percentage",
            "standard_name": "cloud_area_fraction",
            "units": "percent",
        },
        "nasa_modis_error": {
            "cloud_path": "gs://climatebench/observations/clt_nasa_modis_error.zarr",
            "local_path": "observations/clt_nasa_modis_error.zarr",
            "gee_image_collection": "MODIS/061/MOD08_M3",
            "source_var_name": "Cloud_Fraction_Std_Deviation_Mean",
            "long_name": "Total Cloud Cover Percentage",
            "standard_name": "cloud_area_fraction",
            "units": "percent",
        },
    },
    "od550aer": {
        "nasa_modis": {
            "cloud_path": "gs://climatebench/observations/od550aer_nasa_modis.zarr",
            "local_path": "observations/od550aer_nasa_modis.zarr",
            "gee_image_collection": "MODIS/061/MOD08_M3",
            "source_var_name": "Aerosol_Optical_Depth_Land_Ocean_Mean_Mean",
            "long_name": "Ambient Aerosol Optical Thickness at 550nm",
            "standard_name": "atmosphere_optical_thickness_due_to_ambient_aerosol_particles",
            "units": "NA",
        },
        "nasa_modis_error": {
            "cloud_path": "gs://climatebench/observations/od550aer_nasa_modis_error.zarr",
            "local_path": "observations/od550aer_nasa_modis_error.zarr",
            "gee_image_collection": "MODIS/006/MOD44W",
            "source_var_name": "water_mask",
            "long_name": "Ambient Aerosol Optical Thickness at 550nm",
            "standard_name": "atmosphere_optical_thickness_due_to_ambient_aerosol_particles",
            "units": "NA",
            "error_values": {
                "land": {
                    "absolute": 0.5,
                    "relative": 0.15,
                },
                "ocean": {
                    "absolute": 0.4,
                    "relative": 0.1,
                },
            },
        },
    },
    "rsut": {
        "nasa_ceres": {
            "cloud_path": "gs://climatebench/observations/rsut_nasa_ceres.zarr",
            "local_path": "observations/rsut_nasa_ceres.zarr",
            "raw_local_path": "observations/CERES_EBAF-TOA_Ed4.2.1_Subset_200003-202507.nc",
            "source_var_name": "toa_sw_all_mon",
            "long_name": "Top of The Atmosphere Shortwave Flux, All-Sky conditions, Monthly Means",
            "standard_name": "toa_outgoing_shortwave_flux",
            "units": "W m-2",
        },
    },
    "rsutcs": {
        "nasa_ceres": {
            "cloud_path": "gs://climatebench/observations/rsutcs_nasa_ceres.zarr",
            "local_path": "observations/rsutcs_nasa_ceres.zarr",
            "raw_local_path": "observations/CERES_EBAF-TOA_Ed4.2.1_Subset_200003-202507.nc",
            "source_var_name": "toa_sw_clr_c_mon",
            "long_name": "Top of The Atmosphere Shortwave Flux, Clear-Sky (for cloud-free areas of region) conditions, Monthly Means",
            "standard_name": "TOA Shortwave Flux - Clear-Sky (for cloud-free areas of region)",
            "units": "W m-2",
        },
    },
    "rlut": {
        "nasa_ceres": {
            "cloud_path": "gs://climatebench/observations/rlut_nasa_ceres.zarr",
            "local_path": "observations/rlut_nasa_ceres.zarr",
            "raw_local_path": "observations/CERES_EBAF-TOA_Ed4.2.1_Subset_200003-202507.nc",
            "source_var_name": "toa_lw_all_mon",
            "long_name": "Top of The Atmosphere Longwave Flux, All-Sky conditions, Monthly Means",
            "standard_name": "toa_outgoing_longwave_flux",
            "units": "W m-2",
        },
    },
    "rlutcs": {
        "nasa_ceres": {
            "cloud_path": "gs://climatebench/observations/rlutcs_nasa_ceres.zarr",
            "local_path": "observations/rlutcs_nasa_ceres.zarr",
            "raw_local_path": "observations/CERES_EBAF-TOA_Ed4.2.1_Subset_200003-202507.nc",
            "source_var_name": "toa_lw_clr_c_mon",
            "long_name": "Top of The Atmosphere Longwave Flux, Clear-Sky (for cloud-free areas of region) conditions, Monthly Means",
            "standard_name": "TOA Longwave Flux - Clear-Sky (for cloud-free areas of region)",
            "units": "W m-2",
        },
    },
    "thetao": {
        "argo": {
            "cloud_path": "gs://climatebench/observations/ohc_argo.zarr",
            "local_path": "observations/ohc_argo.zarr",
            "source_var_name": "",
            "long_name": "",
            "standard_name": "",
            "units": "",
        },
    },
    "so": {
        "argo": {
            "cloud_path": "gs://climatebench/observations/ohc_argo.zarr",
            "local_path": "observations/ohc_argo.zarr",
            "source_var_name": "",
            "long_name": "",
            "standard_name": "",
            "units": "",
        },
    },
}

# using nested dict incase we have multiple obs datasets for one var. This dict should use the main obs dataset.
OBSERVATION_DATA_PATHS = {
    "tas": {
        "cloud": OBSERVATION_DATA_SPECS["tas"]["HadCRUT5"]["cloud_path"],
        "local": OBSERVATION_DATA_SPECS["tas"]["HadCRUT5"]["local_path"],
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
    "rsut": {
        "cloud": OBSERVATION_DATA_SPECS["rsut"]["nasa_ceres"]["cloud_path"],
        "local": OBSERVATION_DATA_SPECS["rsut"]["nasa_ceres"]["local_path"],
    },
    "rsutcs": {
        "cloud": OBSERVATION_DATA_SPECS["rsutcs"]["nasa_ceres"]["cloud_path"],
        "local": OBSERVATION_DATA_SPECS["rsutcs"]["nasa_ceres"]["local_path"],
    },
    "rlut": {
        "cloud": OBSERVATION_DATA_SPECS["rlut"]["nasa_ceres"]["cloud_path"],
        "local": OBSERVATION_DATA_SPECS["rlut"]["nasa_ceres"]["local_path"],
    },
    "rlutcs": {
        "cloud": OBSERVATION_DATA_SPECS["rlutcs"]["nasa_ceres"]["cloud_path"],
        "local": OBSERVATION_DATA_SPECS["rlutcs"]["nasa_ceres"]["local_path"],
    },
    "thetao": {
        "cloud": OBSERVATION_DATA_SPECS["thetao"]["argo"]["cloud_path"],
        "local": OBSERVATION_DATA_SPECS["thetao"]["argo"]["local_path"],
    },
    "so": {
        "cloud": OBSERVATION_DATA_SPECS["so"]["argo"]["cloud_path"],
        "local": OBSERVATION_DATA_SPECS["so"]["argo"]["local_path"],
    },
}
