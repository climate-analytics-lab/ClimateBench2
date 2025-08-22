#!/bin/bash

# List of models to loop over
models=("TaiESM1" "AWI-CM-1-1-MR" "BCC-CSM2-MR" "CAMS-CSM1-0" "CAS-ESM2-0" "FGOALS-f3-L" "FGOALS-g3" "IITM-ESM" "CanESM5" "CMCC-CM2-SR5" "CMCC-ESM2" "ACCESS-CM2" "MPI-ESM1-2-HR" "E3SM-1-1" "EC-Earth3" "EC-Earth3-CC" "EC-Earth3-Veg" "EC-Earth3-Veg-LR" "FIO-ESM-2-0" "INM-CM4-8" "INM-CM5-0" "IPSL-CM6A-LR" "KIOST-ESM" "MIROC6" "MPI-ESM1-2-LR" "MRI-ESM2-0" "CESM2-WACCM" "NorESM2-LM" "NorESM2-MM" "KACE-1-0-G" "GFDL-CM4" "GFDL-ESM4" "NESM3" "CIESM")

# List of variables to loop over
variables=("tos") # "pr" "tas" "clt" "od550aer") ##### <--- can modify this to only run for a subset

# Loop through paired org-model entries
for i in "${!models[@]}"; do
  model="${models[$i]}"

  for variable in "${variables[@]}"; do
    echo "Running for MODEL=$model, VARIABLE=$variable"
    python model_benchmark.py --model "$model" --variable "$variable" --metric zonal_mean_rmse ##### <--- can modify this to be a subset of metrics
  done
done