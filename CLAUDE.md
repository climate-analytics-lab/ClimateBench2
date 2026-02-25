# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Setup

```bash
conda env create -f env.yml
conda activate backend_env
```

Note: directory names use intentional typos — `benchmark_scrips/` and `paleo_scrips/` (not `scripts`).

## Common Commands

**Download observational data:**
```bash
cd download_scripts
python download_observations.py --variable tas --source HadCRUT5
python download_observations.py --variable tas --source HadCRUT5_error
```

**Run a single benchmark:**
```bash
cd benchmark_scrips
python model_benchmark.py --model CanESM5 --variable tas --metric zonal_mean_rmse --lat_min -90 --lat_max 90 --start_year 2005 --end_year 2015
```

Metric options: `zonal_mean_rmse`, `zonal_mean_mae`, `spatial_rmse`, `spatial_mae`, `crps`
Adjustment options: `bias_adjustment`, `anomaly` (or none)

**Bulk benchmark run:**
```bash
cd benchmark_scrips
chmod +x run_benchmark.sh
./run_benchmark.sh
```

**Paleoclimate data download:**
```bash
cd paleo_scrips/paleo_data_cache
python paleo_data_cache.py --paleo-period lgm --data-cache-dir path/to/paleo_scrips/paleo_data_cache
```

## Architecture

### Data Flow

1. **Observational data** is downloaded via `download_scripts/download_observations.py` → saved as zarr to `observations/` (local) or `gs://climatebench/observations/` (GCS)
2. **CMIP6 model data** is read from local storage, the [Pangeo Google Cloud CMIP6 bucket](https://cmip6.storage.googleapis.com/), or ESGF
3. **Benchmarks** are calculated in `benchmark_scrips/` and saved to `results/` or GCS
4. **App data prep** notebooks in `app_data_prep/` transform results for the [ClimateBench web app](https://climate-analytics-lab.github.io/ClimateBench_app/index.html)

### Key Files

- [constants.py](constants.py) — Central config: variable-to-frequency-group mappings (`VARIABLE_FREQUENCY_GROUP`), historical/SSP date ranges, Google Cloud project ID, and `OBSERVATION_DATA_SPECS` dict mapping each variable+source to cloud/local paths and download URLs
- [utils.py](utils.py) — Shared utilities: `standardize_dims()` normalizes heterogeneous coordinate naming across datasets (lat/lon variants, time formatting), `create_zarr()`, `download_file()`
- [benchmark_scrips/benchmark_utils.py](benchmark_scrips/benchmark_utils.py) — Three core classes:
  - `DataFinder` — locates and loads model ensemble data (historical + SSP concatenated) and observational data; downloads CMIP6 catalogue CSV from Pangeo on first run (`pangeo-cmip6.csv`)
  - `MetricCalculation` — computes RMSE, MAE, CRPS with optional zonal mean, bias adjustment, or anomaly preprocessing using xskillscore
  - `SaveResults` — writes results CSV locally or to GCS
- [benchmark_scrips/model_benchmark.py](benchmark_scrips/model_benchmark.py) — CLI entry point orchestrating the three classes; handles `ohc` (ocean heat content) as a special derived variable requiring both `thetao` and `so`

### Variable Reference

| CF Name | Description | Frequency | Observation Source |
|---------|-------------|-----------|-------------------|
| `tas` | Surface air temperature | Amon | HadCRUT5, NASA GISS |
| `pr` | Precipitation | Amon | NOAA GPCP |
| `tos` | Sea surface temperature | Omon | NOAA OISST |
| `clt` | Cloud area fraction | Amon | NASA MODIS (GEE) |
| `od550aer` | Aerosol optical depth | AERmon | NASA MODIS (GEE) |
| `rsut`/`rlut` | TOA SW/LW flux (all-sky) | Amon | NASA CERES |
| `rsutcs`/`rlutcs` | TOA SW/LW flux (clear-sky) | Amon | NASA CERES |
| `thetao` | Ocean potential temperature | Omon | Argo |
| `so` | Ocean salinity | Omon | Argo |
| `ohc` | Ocean heat content (derived) | — | Argo |

CERES variables (`rsut`, `rlut`, `rsutcs`, `rlutcs`) share a single raw NetCDF file (`CERES_EBAF-TOA_Ed4.2.1_Subset_*.nc`) that must be downloaded manually before processing.

### MODIS/Google Earth Engine Variables

`clt` and `od550aer` require Google Earth Engine authentication:
```bash
earthengine authenticate
```

### CMIP6 Data Sources (priority order in DataFinder)

1. Local filesystem paths
2. Pangeo Google Cloud (`gs://cmip6/`) via `pangeo-cmip6.csv` catalogue
3. ESGF via `pyesgf`

### SSP Experiment

Default SSP scenario is `ssp245`, set in `constants.py`. Historical runs cover 1960–2014; SSP covers 2015–2024.
