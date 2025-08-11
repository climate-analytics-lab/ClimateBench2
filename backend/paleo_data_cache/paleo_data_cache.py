import pandas as pd
import xarray as xr
import glob
import os
import numpy as np
from pyesgf.search import SearchConnection

paleo_period = "lgm"  # 'midHolocene' 'lig127k' 'midPliocene-eoi400'

# for eocene run this command in paleo_data_cache folder
# wget -e robots=off --mirror --no-parent -r --accept "tas_*mean.nc" https://dap.ceda.ac.uk/badc/cmip6/data/CMIP6Plus/DeepMIP/deepmip-eocene-p1/

# # Check ESGF for additional data
# conn = SearchConnection('https://esgf-data.dkrz.de/esg-search', distrib=True)
# ctx = conn.new_context(
#     project='CMIP6',
#     experiment_id=paleo_period,
#     variable='tas',
#     frequency='mon',
#     variant_label='r1i1p1f1',
#     # data_node='esgf-data3.ceda.ac.uk'
#     facets="source_id"
#     )
# print(ctx.hit_count)
# _datasets = []
# for result in ctx.search():
#     _datasets.append(result.dataset_id)
# paleo_datasets = pd.DataFrame(_datasets)[0].str.split('.',expand=True)[[3,5,8]].rename(columns={3:'model',5:'member_id',8:'grid_id'})
# paleo_datasets = paleo_datasets.sort_values('member_id').drop_duplicates(['model','grid_id'])

# # Download files for model and save mean

# for model in paleo_datasets['model'].to_list():
#     os.makedirs(f'/Users/willatobin/Documents/SIO/ClimateBench2/backend/paleo_data_cache/{model}',exist_ok=True)
#     # Download wget scripts from ESGF
#     wget_file = glob.glob(f'/Users/willatobin/Documents/SIO/ClimateBench2/backend/paleo_data_cache/{model}/*')
#     os.system(f'mv {wget_file[0]} /Users/willatobin/Documents/SIO/ClimateBench2/backend/paleo_data_cache/{model}/{paleo_period}_wget_script.sh')
#     # make sure files have permission to run using `chmod +x {file name}`


model_folders = glob.glob(
    f"/Users/willatobin/Documents/SIO/ClimateBench2/backend/paleo_data_cache/*/{paleo_period}*"
)
# print(model_folders[-1:])
for wget_file in model_folders:
    model = "/".join(wget_file.split("/")[:-1]) + "/"
    print(f"processing data for {model}")
    # download files from ESGF
    # wget_file = glob.glob(f'{model}*')
    # you will need to hit enter for username and password
    os.system(f"chmod +x {wget_file}")
    os.system(f"{wget_file}")

    nc_files = glob.glob(f"{model}tas*")

    try:
        ds = xr.open_mfdataset(nc_files, chunks={}).drop_vars(
            ["time_bnds", "lat_bnds", "lon_bnds", "height"], errors="ignore"
        )
    except:
        ds = xr.open_mfdataset(nc_files, use_cftime=True, chunks={}).drop_vars(
            ["time_bnds", "lat_bnds", "lon_bnds", "height"], errors="ignore"
        )

    # get weighted mean of time avg
    weights = np.cos(np.deg2rad(ds.lat))
    weights = weights.expand_dims({"lon": ds.lon})
    weights.name = "areacella"

    # take mean and std over time and save
    ds_mean_annual = ds.mean(dim="time")
    ds_std_annual = ds.std(dim="time").rename({"tas": "tas_std"})

    print("saving annual file")
    xr.merge(
        [ds_mean_annual, ds_std_annual, weights.to_dataset(name="weight")]
    ).to_netcdf(f"{model}{paleo_period}_tas_annual.nc")

    ds_mean_mon = ds.groupby("time.month").mean()
    ds_std_mon = ds.groupby("time.month").std().rename({"tas": "tas_std"})

    print("saving monthly file")
    xr.merge([ds_mean_mon, ds_std_mon, weights.to_dataset(name="weight")]).to_netcdf(
        f"{model}{paleo_period}_tas_monthly.nc"
    )

    # delete raw files
    for file in nc_files:
        os.remove(file)
    # os.remove('.wget_script.sh.status')
