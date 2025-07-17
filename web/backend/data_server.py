import os
import subprocess

import aiohttp_cors
import xarray as xr
from aiohttp import web
from ndpyramid import pyramid_regrid

root_dir = os.path.abspath(".")

data_folder = os.path.join(root_dir, "public")
if not os.path.isdir(data_folder):
    cmd = f"gsutil -m cp -r gs://climatebench/results/public {root_dir}/."
    print(f"Local data not found. Downloading via {cmd}")
    subprocess.run(cmd.split(" "))

    print("constructing zarr pyramid")
    map_ds = xr.open_zarr("public/map_data_subset.zarr")
    full_ds = map_ds.rename({"lon": "x", "lat": "y"}).squeeze()
    full_ds = full_ds.rio.write_crs("EPSG:4326")

    levels = 2
    regridded_pyramid = pyramid_regrid(
        full_ds, levels=levels, method="bilinear", parallel_weights=False
    )
    regridded_pyramid.to_zarr(
        "public/map_data_subset_pyramid.zarr", consolidated=True, mode="w"
    )


async def handle(request):
    file_path = os.path.join(root_dir, request.match_info["filename"])
    if not os.path.exists(file_path):
        return web.Response(status=404, text="File not found")
    return web.FileResponse(file_path)


app = web.Application()
cors = aiohttp_cors.setup(
    app,
    defaults={
        "*": aiohttp_cors.ResourceOptions(
            allow_credentials=True, expose_headers="*", allow_headers="*"
        )
    },
)
resource = cors.add(app.router.add_resource("/{filename:.*}"))
cors.add(resource.add_route("GET", handle))

print("Serving on http://localhost:8000")
web.run_app(app, host="localhost", port=8000)
