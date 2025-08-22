# Climate Bench X ESMValTool
`recipe_pr_rmse.yml` is a sample ESMValTool recipe for benchmarking CMIP6 models against observations. It computes the zonal mean time series, and then calculates the error vs the GPCP time series. This recipe can be modified to use different models or variables, and is meant to be used as a template for benchmarking calculations done with ESMValTool. 


## Helpful resources
- [Website](https://esmvaltool.org/)
- [Documentation](https://docs.esmvaltool.org/en/latest/)
- [Install instructions](https://docs.esmvaltool.org/en/latest/quickstart/installation.html)
- [Datasets with CMORizer scripts](https://docs.esmvaltool.org/en/latest/input.html#supported-datasets-for-which-a-cmorizer-script-is-available)
- [Preprocessor functions](https://docs.esmvaltool.org/projects/ESMValCore/en/latest/api/esmvalcore.preprocessor.html)
- [Available recipes](https://github.com/ESMValGroup/ESMValTool/tree/main/esmvaltool/recipes)
- [Available diagnostics](https://github.com/ESMValGroup/ESMValTool/tree/main/esmvaltool/diag_scripts)

## How to run a recipe
List preset recipes.
`esmvaltool recipes list`

Look at a specific recipe. Replace `examples/recipe_python.yml` with any recipe from the github link above.
`esmvaltool recipes show examples/recipe_python.yml`

Download the recipe you want.
`esmvaltool recipes get examples/recipe_python.yml`

Run your recipe. If you downloaded it, make sure you use the local path to the recipe. 
`esmvaltool run recipe_pr_rmse.yml`

## CMORizing data
To run the portrait plot script, you will need to download and "cmorize" the observational precipitation data. I do this instead of using obs4MIPs data because the obs4MIPs precipitation data on the ESGF server does not have the full temporal coverage we want (2005-2024).
```
# modify with path to your config file
esmvaltool data download --config_file <path to config> GPCP-SG
esmvaltool data format --config_file <path to config> GPCP-SG
```