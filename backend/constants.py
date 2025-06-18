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
RESULTS_FILE_PATH = "model_benchmarking_results.csv"
SSP_EXPERIMENT = "ssp245"
OBSERVATION_DATA_PATHS = {
    "tas": "gs://climatebench/observations/preprocessed/tas/tas_nasa_airs.zarr",
    "tos": "gs://climatebench/observations/preprocessed/tos/tos_noaa_oisst.zarr",
    "pr": "gs://climatebench/observations/preprocessed/pr/pr_noaa_gpcp.zarr",
    "clt": "gs://climatebench/observations/preprocessed/clt/clt_nasa_modis.zarr",
    "od550aer": "gs://climatebench/observations/preprocessed/od550aer/od550aer_nasa_modis.zarr",
}
