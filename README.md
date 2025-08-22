# ClimateBench2

## Directory Structure

- `constants.py`, `utils.py`, `env.yml` – Environment setup and shared codes
- `app_data_prep/` – Data preparation notebooks
- `benchmark_scripts/` – Benchmarking scripts
- `download_scripts/` – Data download scripts
- `esmvaltool/` – ESMValTool example benchmarking recipe
- `observations/` – Where downloaded observations will be saved
- `results/` – Where calculated benchmarks will be saved
- `paleo_scripts/` – Paleoclimate benchmarking and data prep

## Setup

```
conda env create -f env.yml
conda activate backend_env
```

## Observational Data

Observational data can be downloaded locally or read from the ClimateBench google cloud bucket. To download observations locally, use the `download_scripts`

```
conda activate backend_env
cd download_scripts
python download_observations.py --variable tas --source HadCRUT5
python download_observations.py --variable tas --source HadCRUT5_error
```

There are currently observational datasets for:
- Surface air temperature (tas)     -- [HadCRUT5](https://www.metoffice.gov.uk/hadobs/hadcrut5/)
- Precipitation (pr)                -- [GPCP](https://psl.noaa.gov/data/gridded/data.gpcp.html)
- Sea surface temperature           -- [OISST](https://www.ncei.noaa.gov/products/optimum-interpolation-sst)
- Cloud area fraction               -- [MODIS](https://developers.google.com/earth-engine/datasets/catalog/MODIS_061_MOD08_M3)
- Aerosol optical depth             -- [MODIS](https://developers.google.com/earth-engine/datasets/catalog/MODIS_061_MOD08_M3)

## Benchmarking
The ClimateBench framework allows users to customize the calculated score to the region and time period of interest. There are three skill measures (RMSE, MAE, CRPS) with the option to calculate on the zonal mean, or across all pixels. Users can also use the bias adjustment or anomaly option for additionally preprocessing. 

To calculate a benchmark for one combination of parameters, use the `model_benchmark.py`
```
conda activate backend_env
cd benchmark_scripts
python model_benchmark.py --model CanESM5 --variable tas --metric zonal_mean_rmse --lat_min -90 --lat_max 90 --start_year 2005 --end_year 2015
```
If you would like to do a bulk run of all potential combinations, you can use the `run_benchmark.sh` script, and modify to the desired combinations.
```
# make sure permissions are set
chmod +x run_benchmark.sh
# run bash script
./run_benchmark.sh
```

## App Data Preparation

The app data preparation notebooks create the figures displayed in the [ClimateBench web app](https://climate-analytics-lab.github.io/ClimateBench_app/index.html). These include:
- Overview scorecard (weather_bench_scorecard.ipynb) 
    - This notebook is a slightly modified version of [WB_X_Website_Scorecard.ipynb](https://github.com/google-research/weatherbenchX/blob/main/public_benchmark/WB_X_Website_Scorecard.ipynb) from the [WeatherBench](https://sites.research.google/gr/weatherbench/) team.
- Input data maps (prep_map_images.ipynb)
    - This notebook plots the climate model data and error as projected maps and saves to a ClimateBench_app folder. If you have the ClimateBench_app repo locally, it will save the files there.

- store_zonal_means.ipynb calculates the zonal mean time series for the models and observations. 
- process_results.ipynb reformats benchmark results for easier reading in the web app.

## Paleoclimate Benchmarks

The paleoclimate model simulations can be downloaded locally using `paleo_scripts/paleo_data_cache/paleo_data_cache.py`. Downloading all the paleo periods may take a while.

```
conda activate backend_env
cd paleo_scripts/paleo_data_cache
python paleo_data_cache.py --paleo-period lgm --data-cache-dir path/to/ClimateBench2/paleo_scripts/paleo_data_cache
```

Then you can download and organize the paleo proxy data using the `paleo_scripts/prep_paleo_obs.ipynb`.
And finally, you can calculate the error in the global mean surface temperature anomaly using `paleo_scripts/paleo_benchmarks.ipynb`.

## ESMValTool

ESMValTool is a helpful evaluation tool for existing climate models. See the `esmvaltool/README.md` for more details.
