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
