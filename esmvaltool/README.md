# Climate Bench X ESMValTool

## Helpful resources
- [Website](https://esmvaltool.org/)
- [Documentation](https://docs.esmvaltool.org/en/latest/)
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

Run your recipe. If you downloaded it, make sure you use the local path to the recipe. This is the command for the example recipe, which is a modified version of `examples/recipe_python.yml`.
`esmvaltool run recipe_example.yml`

## CMORizing data
To run the portrait plot script, you will need to download and "cmorize" the observational precipitation data. I do this instead of using obs4MIPs data because the obs4MIPs precipitation data on the ESGF server does not have the full temporal coverage we want (2005-2024).
```
# modify with path to your config file
esmvaltool data download --config_file /Users/willatobin/.config/esmvaltool/config-user.yml GPCP-SG
esmvaltool data format --config_file /Users/willatobin/.config/esmvaltool/config-user.yml GPCP-SG
```