import os
from aiohttp import web
import aiohttp_cors
import dask  # noqa
import xarray as xr
import zarr
from ndpyramid.regrid import pyramid_regrid

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
