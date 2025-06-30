import os
from aiohttp import web
import aiohttp_cors
import dask  # noqa
import xarray as xr
import zarr
from ndpyramid.regrid import pyramid_regrid

# --- Check for Zarr, create if needed ---
zarr_path = 'public/data/regridded.zarr'

if not os.path.exists(zarr_path):
    print(f"Zarr not found at {zarr_path}, creating pyramid...")
    # Load, preprocess, and regrid
    ds = xr.open_zarr(
        'gs://cmip6/CMIP6/ScenarioMIP/IPSL/IPSL-CM6A-LR/ssp245/r1i1p1f1/Amon/tas/gr/v20190119',
        decode_cf=False,
        chunks={}
    )
    ds = ds.isel(time=0).reset_coords(["time", "height", "time_bounds"], drop=True).rename({'lon': 'x', 'lat': 'y'}).squeeze()
    ds = ds.rio.write_crs("EPSG:4326")

    levels = 4
    regridded_pyramid = pyramid_regrid(ds, levels=levels, method="bilinear", parallel_weights=False)
    regridded_pyramid.to_zarr(zarr_path, consolidated=True, mode="w")

    print(f"Pyramid created at: {zarr_path}")
else:
    print(f"Found existing Zarr at {zarr_path}, skipping creation.")

# --- Start the HTTP Server with CORS ---
root_dir = os.path.abspath(".")

async def handle(request):
    file_path = os.path.join(root_dir, request.match_info['filename'])
    if not os.path.exists(file_path):
        return web.Response(status=404, text='File not found')
    return web.FileResponse(file_path)

app = web.Application()
cors = aiohttp_cors.setup(app, defaults={
    "*": aiohttp_cors.ResourceOptions(
        allow_credentials=True,
        expose_headers="*",
        allow_headers="*"
    )
})
resource = cors.add(app.router.add_resource("/{filename:.*}"))
cors.add(resource.add_route("GET", handle))

print("Serving on http://localhost:8000")
web.run_app(app, host='localhost', port=8000)
