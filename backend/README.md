# Backend codes for ClimateBench2
Backend codes are for calculating benchmarking statistics. Results will be saved on the [climatebench google cloud bucket](https://console.cloud.google.com/storage/browser/climatebench;tab=objects?forceOnBucketsSortingFiltering=true&hl=en&inv=1&invt=Ab0dEw&project=fluid-script-453604-u5&prefix=&forceOnObjectsSortingFiltering=false), that will be displayed in the frontend web app.

```bash
# set up the environment
conda env create -f env.yml
conda activate backend_env

# run bash script. If running for all mondels and one variable, it should take ~20 min. 
./run_benchmark.sh

# You can also just run the python script if you only want to run for one combination
python model_benchmark.py --org CAS --model FGOALS-g3 --variable pr --metrics rmse rmse_bias_adjusted rmse_anomaly 
```

### Notes
- env.yml is for running backend codes, but not obs download codes. For some obs download scripts you will need to install/set up the google earth engine api.
- run_benchmark.sh -- this bash script contains all institute/model pairs, but not all pairs have all the data we need. The benchmarking script will fail if the itteration does not have all three ensemble members for the historical and projected simulations, but the bash script will continue to the next combination. You can modify the script to run for a subset of institution/models, variables, and statistical metric. For now, the "tos" variable is not working.
- DataFinder -- this class is in utils.py. Given the org, model, and variable, it will get the observational and model data that you need. Can be used for exploratory data analysis as well.
- MetricCalculator -- this is a class in utils.py. It takes in the model, observations, and optionally spatial weights data. For now, it will calculate 3 global mean RMSE metrics. The metric options will expand in the future. 


### obs_data_download
Download scripts for observational data for our five variables of interest. Data is saved on google cloud in the [climatebench bucket](https://console.cloud.google.com/storage/browser/climatebench;tab=objects?forceOnBucketsSortingFiltering=true&hl=en&inv=1&invt=Ab0dEw&project=fluid-script-453604-u5&prefix=&forceOnObjectsSortingFiltering=false), so scripts do not need to be run again.
- nasa_airs_tas_download.py -- downloads surface temperature data from NASA. Uses wget command with list of files in the "subset_AIRS3STM....txt".
- noaa_gpcp_pr_download.py -- downloads precipitation data from [NOAA](https://psl.noaa.gov/data/gridded/data.gpcp.html).
- noaa_oisst_tos_download.py -- downloads sea surface temperature data from [NOAA](https://psl.noaa.gov/data/gridded/data.noaa.oisst.v2.highres.html). 
- modis_clt_download.py -- downloads cloud area fraction data from [google earth engine](https://atmosphere-imager.gsfc.nasa.gov/sites/default/files/ModAtmo/MOD08_M3_fs_3045.txt).
- modis_od550aer_download.py -- downloads aerosol optical depth data from [google earth engine](https://atmosphere-imager.gsfc.nasa.gov/sites/default/files/ModAtmo/MOD08_M3_fs_3044.txt).
