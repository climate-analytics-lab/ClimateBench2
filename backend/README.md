# Backend codes for ClimateBench2
Backend codes are for calculating benchmarking statistics. Results will be saved on the [climatebench google cloud bucket](https://console.cloud.google.com/storage/browser/climatebench;tab=objects?forceOnBucketsSortingFiltering=true&hl=en&inv=1&invt=Ab0dEw&project=fluid-script-453604-u5&prefix=&forceOnObjectsSortingFiltering=false), that will be displayed in the frontend web app.

```bash
# set up the environment
conda env create -f env.yml
conda activate backend_env

# run bash script. If running for all mondels and one variable, it should take ~20 min. 
./run_benchmark.sh

# You can also just run the python script if you only want to run for one combination, which should take ~30s
python model_benchmark.py --org CAS --model FGOALS-g3 --variable pr --adjustments none bias_adjusted anomaly 
```

## model_benchmark.py
This is the main script for running the benchmarking pipeline. The user passes in the model and variable information (along with some additional parameter options) and the following metrics are computed and saved either locally or on google cloud.

### Computed metrics
- Zonal mean RMSE
    - This metric takes the area weighted zonal mean of the observational and model datasets, then using the two time series, calculates the RMSE.
- Temporal RMSE
    - This metric calculates the RMSE of each grid cell through time, returing a map of RMSE values.
- Spatial RMSE
    - This metric calculates the RMSE for each time step across the spatial dimentions. You can pass in latitude bounds, and the RMSE calculation is weighted by cell area.

### Metric adjustment options
The following are optional adjustments that can be applied to the data before the metric calculation. If calculating the zonal mean RMSE, this step is applied after the zonal mean calculation, but before the metric calculation. For the temporal and spatial RMSE, this step is applied to the gridded data.
- Bias adjusted
    - This option will compare the mean value across time for the model - observations, and apply that adjustment to the model data. 
- Anomaly
    - This option will subtract the monthly mean across the whole time dimension from the original dataset. This is applied to both the model and observation data.

### Script arguments
- `--org` The institution/orginization associated with the chose model.
- `--model` The model to be benchmarked.
- `--variable` The variable to be benchmarked. Options are "tas" (near-surface temperature), "pr"  (precipitation), "tos" (sea surface temperature), "clt" (cloud area fraction), "od550aer" (aerosol optical depth at 550nm).
- `--adjustments` The adjustments to apply to the metric calculations. You can pass in a list and the script will loop through all. Options are "none" for no adjustment, "bias_adjustment" and "anomaly" (see above).
- `--lat_min` The minimum latitude for the zonal mean and spatial RMSE calculations. Default is -90.
- `--lat_max` The maximum latitude for the zonal mean and spatial RMSE calculations. Default is 90.
- `--save_to_cloud` A boolean flag to pass if you wish to save the results in the climatebench google cloud bucket. If not passed, saves data locally.
- `--overwrite` A boolean flag to pass if you wish to delete any data that is in the results folder the data will be saved in. 


## download_observations.py
This is the main script for downloading observational data. The user will need to configure an entry in OBSERVATION_DATA_SPECS if they wish to add a new observational dataset. The datasets in OBSERVATION_DATA_SPECS have already been uploaded to [climatebench/observations](https://console.cloud.google.com/storage/browser/climatebench/observations?pageState=(%22StorageObjectListTable%22:(%22f%22:%22%255B%255D%22))&hl=en&inv=1&invt=Ab1AyQ&orgonly=true&project=fluid-script-453604-u5&supportedpurview=organizationId). 

### Datasets
- tas
    - NASA AIRS: This data is from the atmospheric ifrared sounder on Aqua. It is accessed via NASA Goddard Earth Sciences Data Information and Services Center.
- pr
    - NOAA GPCP: This data is from the global precipitation climatology project. It is apart of obs4MIPs, but the obs4MIPs dataset does not have the full dataset we need. This data is accessed directly from NOAA.
- tos
    - NOAA OISST: This data is from the optimim interpolation of sea surface temperatures. It is accessed directly from NOAA.
- clt
    - NASA MODIS: This dataset is downloaded from the MODIS image collection on google earth engine. 
- od550aer
    - NASA MODIS: This dataset is downloaded from the MODIS image collection on google earth engine. 

### Script arguments
- `--variable` The variable of the observations you wish to download.
- `--source` The source of the data, as listed in the OBSERVATION_DATA_SPECS.
- `--save_to_cloud` A boolean flag to pass if you wish to save the results in the climatebench google cloud bucket. If not passed, saves data locally.


## utils.py
This file contains many of the utility functions used in the benchmarking pipeline. They are saved in a seperate file to make it easier to reuse code for data analysis and other scripts. For more information on each function, see the function docstring.

- `standardize_dims()` A function for ensuring all datasets have the same space and time coordinates. The function will rename dimentions to "lat", "lon" and "time". The function expects monthly data, and will set the dates to the first of the month. The function works with rectilinear and curvelinear grids. It will set latitude to be increasing (-90 to 90), and reorder longitude to 0 - 360. The function also has the option to reset the spatial coordinates for rectilinear grids. There are floating point errors that can arise when working with gridded data that causes issues with merging datasets on the same grid. This option will reset the spatial coordinates to have even spacing.

- `build_zarr_store()` A function for building a template zarr store that can be populated with the `ds.to_zarr(region=...)` call. Will probably delete this function as it is not being used right now.

- `DataFinder` This is a class for finding the correct observational, historical, and model datasets based on the parameters passed
    - pass in `org`, `model` and `variable` to initialize the class.
    - exampe usage:
    ```
    data_finder = DataFinder(org="CAS", model="FGOALS-g3", variable="tas")
    model_ds = data_finder.load_model_ds()
    obs_ds = data_finder.load_obs_ds()
    cell_area_ds = data_finder.load_cell_area_ds(cell_var_name = "areacella")
    ```
    - `load_model_ds()` will return the combined historical (2005-2014) and projected (2015-2024) ensemble mean. If you want an individual ensemble member, you can use `read_data()`, which takes more arguments to get the specific dataset you want.

- `MetricCalculation` This is a class for calculating the benchmark metrics.
    - pass in `observations`, `model` and optionally `weights` to initialize the class.
    - `zonal_mean()` this function can take a latitude band and calculate the area weighted mean. It is used the metric calculation options, but could also be used for calculating an independent zonal mean.
    - `calculate_rmse` The core of this fucntion is the final RMSE calculation, but based on the arguments passed, you can do some preprocessing and adjustment to the data, and set the dimensions to calculate over.
    - example usage:
    ```
    metric_calculator = MetricCalculation(
        observations=obs_ds["tas"],
        model=model_ds["tas],
        weights=cell_area_ds["areacella],
    )
    rmse_hist = metric_calculator.calculate_rmse(
        metric="zonal_mean",
        adjustment="bias_adjusted",
        time_slice=slice(HIST_START_DATE, HIST_END_DATE),
        lat_min=-30,
        lat_max=30,
    )
    ```

- `SaveResults` This is a class for saving after the metric calculation operations. The class will build the proper file paths based on the variable and experiment you did. Then for the successive functions, you will need to pass the proper dataset as an argument and use the proper save function based on the structure of your data.
    - pass in `variable` and `experiment` (so far just RMSE) to initilaize the class.
    - `save_to_csv_gcs()` and `save_to_csv_local()` (TODO: make this one function) This will save tabular data in a csv. If the csv already exists, it will append to it.
    - `save_zarr()` This function will save locally or to the cloud based on the `save_to_cloud` argument. The encoding of the dataset will be dropped before saving. The data will be saved as one chunk, as the results from each experiment are very small (wrt storage). 
    - `overwrite()` This will delete all files in the path for the path constructed by the class. Works for local and cloud paths. 
