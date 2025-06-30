# simple-map-demo

Extremely minimal demo of using the [`@carbonplan/maps`](https://github.com/carbonplan/maps) library. 
This demo is modified from the original which is cloned from [this repo](https://github.com/carbonplan/simple-map-demo/tree/main).

## How to run
```
# step 1: set up env
conda env create -f env.yml
conda activate cp_demo_env

# step 2: create zarr pyramid and set up local server
python zarr_server.py

# step 3: (in a seperate terminal) run the app 
conda activate cp_demo_env # if not already activated
npm install
npm run dev # try this. if it gives errors, try the following command
NODE_OPTIONS=--openssl-legacy-provider npm run dev

# go to http://localhost:3000 to see app
```

## How to modify
You can change the data in the map by changing the zarr pyramid creation in `zarr_server.py`. The default (shown below) is using temperature data from one model. To keep the demo simple, I use just one time step. 
```
ds = xr.open_zarr(
    'gs://cmip6/CMIP6/ScenarioMIP/IPSL/IPSL-CM6A-LR/ssp245/r1i1p1f1/Amon/tas/gr/v20190119',
    decode_cf=False,
    chunks={}
)
ds = ds.isel(time=0).reset_coords(["time", "height", "time_bounds"], drop=True).rename({'lon': 'x', 'lat': 'y'}).squeeze()
ds = ds.rio.write_crs("EPSG:4326")
```
To then make this data visible in the web app, we have to make a few minor changes to the source code (`pages/index.js`). All the changes occur in the `Raster` component which is in the `Map` component.
```
<Raster
    colormap={colormap}
    # we have to modify this. clim == color limimt. values outside the bounds will not be colored. This is the general temperature range in K.
    clim={[100, 300]} 
    display={true}
    opacity={1}
    mode={'texture'}
    # we have to modify the source to be the local server we set up.
    source={
    "http://localhost:8000/public/data/regridded.zarr/"
    }
    # we have to modify the variable name to match our zarr file.=
    variable={'tas'}
/>
```
Play around with changing each variable to see how it affects the app. This is a starting point, but we will want to have dynamic data selection in the app, so try to make small changes such as adding a second time step (or a second variable) and some way to toggle between the two.