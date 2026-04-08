VARIABLE_FREQUENCY_GROUP = {
    "tas": "Amon",
    "pr": "Amon",
    "clt": "Amon",
    "tos": "Omon",
    "od550aer": "AERmon",
    "rsdt": "Amon",
    "rsut": "Amon",
    "rlut": "Amon",
    "rsutcs": "Amon",
    "rlutcs": "Amon",
    "hfss": "Amon",
    "hfls": "Amon",
    "rlds": "Amon",
    "rlus": "Amon",
    "rsds": "Amon",
    "rsus": "Amon",
    "thetao": "Omon",
    "so": "Omon",
}
HIST_START_DATE = "1850-01-01"
HIST_END_DATE = "2014-12-31"
SSP_START_DATE = "2015-01-01"
SSP_END_DATE = "2025-12-31"
SSP_EXPERIMENT = "ssp245"
GOOGLE_CLOUD_PROJECT = "fluid-script-453604-u5"

OBSERVATION_DATA_SOURCES = {
    "tas": ["NOAA_GLOBALTEMP", "Berkeley_BEST", "CRU_TS", "HadCRUT5", "NASA_GISS"],
    "tos": ["HadISST", "HadSST", "noaa_oisst"],
    "pr": ["IMERG", "MSWEP", "NOAA_GPCP"],
    "clt": ["isccp", "nasa_ceres", "nasa_modis"],
    "od550aer": ["nasa_modis"],
    "rsut": ["nasa_ceres"],
    "rsutcs": ["nasa_ceres"],
    "rlut": ["nasa_ceres"],
    "rlutcs": ["nasa_ceres"],
    "thetao": ["ARGO"],
    "so": ["ARGO"],
    "clwvi": ["isccp"],
    "ctp": ["isccp", "nasa_modis"],
    "ctt": ["isccp", "nasa_modis"],
    "siconc": [],
    "tasmax": ["HadGHCND"],
    "tasmin": ["HadGHCND"],
    "tcwv": ["ERA5", "RSS"],
}

EARTH_RADIUS = 6.371e6  # metres

# Observational global-mean reference bounds for sanity/pass-fail checks.
#
# Source: Adapted from ICONEval recipe_sanity_checks.yml
# (https://github.com/EyringMLClimateGroup/ICONEval)
# Values are min/max global-mean across all months and all reference
# datasets (observations + reanalyses).
#
# Usage: quick-reject validation and Tier I energy balance context.

REFERENCE_BOUNDS = {
    "tas": {
        "units": "K",
        "global_mean": [283.9, 293.7],
        "sources": ["ERA5", "MERRA2", "HadCRUT5"],
    },
    "rlut": {
        "units": "W m-2",
        "global_mean": [226.4, 246.3],
        "sources": ["CERES-EBAF", "ESACCI-CLOUD", "ISCCP-FH", "ERA5"],
    },
    "rsut": {
        "units": "W m-2",
        "global_mean": [91.1, 128.8],
        "sources": ["CERES-EBAF", "ESACCI-CLOUD", "ISCCP-FH"],
    },
    "clt": {
        "units": "%",
        "global_mean": [58.7, 74.9],
        "sources": ["ESACCI-CLOUD", "CLARA-AVHRR", "MODIS", "ERA5", "PATMOS-x"],
    },
    "pr": {
        "units": "mm day-1",
        "global_mean": [2.50, 3.21],
        "sources": ["GPCP", "ERA5", "MERRA2"],
    },
    "lwcre": {
        "units": "W m-2",
        "global_mean": [23.6, 30.5],
        "sources": ["CERES-EBAF", "ESACCI-CLOUD", "ISCCP-FH"],
    },
    "swcre": {
        "units": "W m-2",
        "global_mean": [-73.5, -40.6],
        "sources": ["CERES-EBAF", "ESACCI-CLOUD", "ISCCP-FH"],
    },
    # TOA net flux (rsdt - rsut - rlut) for a balanced climate should be
    # near zero. In piControl, drift should be < 0.1 W/m2/decade.
    "toa_net_flux": {
        "units": "W m-2",
        "picontrol_drift_threshold": 0.1, # W/m2/decade
        "picontrol_imbalance_range": [-1.0, 1.0], # W/m2 (acceptable long-term mean)
    },
}
