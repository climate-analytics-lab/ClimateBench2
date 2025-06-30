#!/bin/bash

# Paired org-model list (same index = same pair)
# orgs=("AS-RCEC" "AWI" "BCC" "CAMS" "CAS" "CAS" "CAS" "CCCR-IITM" "CCCma" "CMCC" "CMCC" "CSIRO-ARCCSS" "DKRZ" "E3SM-Project" "EC-Earth-Consortium" "EC-Earth-Consortium" "EC-Earth-Consortium" "EC-Earth-Consortium" "FIO-QLNM" "INM" "INM" "IPSL" "KIOST" "MIROC" "MPI-M" "MRI" "NCAR" "NCC" "NCC" "NIMS-KMA" "NOAA-GFDL" "NOAA-GFDL" "NUIST" "THU")
# models=("TaiESM1" "AWI-CM-1-1-MR" "BCC-CSM2-MR" "CAMS-CSM1-0" "CAS-ESM2-0" "FGOALS-f3-L" "FGOALS-g3" "IITM-ESM" "CanESM5" "CMCC-CM2-SR5" "CMCC-ESM2" "ACCESS-CM2" "MPI-ESM1-2-HR" "E3SM-1-1" "EC-Earth3" "EC-Earth3-CC" "EC-Earth3-Veg" "EC-Earth3-Veg-LR" "FIO-ESM-2-0" "INM-CM4-8" "INM-CM5-0" "IPSL-CM6A-LR" "KIOST-ESM" "MIROC6" "MPI-ESM1-2-LR" "MRI-ESM2-0" "CESM2-WACCM" "NorESM2-LM" "NorESM2-MM" "KACE-1-0-G" "GFDL-CM4" "GFDL-ESM4" "NESM3" "CIESM")

# orgs=("CAS" "CCCma" "CSIRO-ARCCSS" "EC-Earth-Consortium" "EC-Earth-Consortium" "FIO-QLNM" "IPSL" "MIROC" "MPI-M" "MRI" "NCAR" "NCC" "NOAA-GFDL")
models=("FGOALS-g3" "CanESM5" "ACCESS-CM2" "EC-Earth3-Veg" "EC-Earth3-Veg-LR" "FIO-ESM-2-0" "IPSL-CM6A-LR" "MIROC6" "MPI-ESM1-2-LR" "MRI-ESM2-0" "CESM2-WACCM" "NorESM2-LM" "GFDL-ESM4")

# errors from clt
# ValueError: can't find data for CMIP, NOAA-GFDL, GFDL-ESM4, historical, r2i1p1f1, Amon, clt
# ValueError: can't find data for ScenarioMIP, MRI, MRI-ESM2-0, ssp245, r2i1p1f1, Amon, clt
# ValueError: can't find data for CMIP, EC-Earth-Consortium, EC-Earth3-Veg, historical, r1i1p1f1, Amon, clt

# errors for od550aer
# ValueError: can't find data for CMIP, NOAA-GFDL, GFDL-ESM4, historical, r2i1p1f1, AERmon, od550aer
# ValueError: can't find data for CMIP, NCC, NorESM2-LM, historical, r2i1p1f1, AERmon, od550aer
# ValueError: can't find data for CMIP, MRI, MRI-ESM2-0, historical, r3i1p1f1, AERmon, od550aer
# ValueError: can't find data for CMIP, MIROC, MIROC6, historical, r1i1p1f1, AERmon, od550aer
# ValueError: can't find data for CMIP, FIO-QLNM, FIO-ESM-2-0, historical, r1i1p1f1, AERmon, od550aer
# ValueError: can't find data for CMIP, EC-Earth-Consortium, EC-Earth3-Veg-LR, historical, r1i1p1f1, AERmon, od550aer
# ValueError: can't find data for CMIP, EC-Earth-Consortium, EC-Earth3-Veg, historical, r1i1p1f1, AERmon, od550aer
# ValueError: can't find data for CMIP, CSIRO-ARCCSS, ACCESS-CM2, historical, r1i1p1f1, AERmon, od550aer
# ValueError: can't find data for CMIP, CAS, FGOALS-g3, historical, r1i1p1f1, AERmon, od550aer


# List of variables to loop over
variables=("tos") # "pr" "tas" "clt" "od550aer") ##### <--- can modify this to only run for a subset

# Loop through paired org-model entries
for i in "${!models[@]}"; do
  model="${models[$i]}"

  for variable in "${variables[@]}"; do
    echo "Running for MODEL=$model, VARIABLE=$variable"
    python model_benchmark.py --model "$model" --variable "$variable" --adjustments none bias_adjusted anomaly ##### <--- can modify this to be a subset of metrics
  done
done