
# TiTiler configuration for CMIP6 data
import os
from titiler.core.factory import TilerFactory
from titiler.core.settings import ApiSettings
from titiler.mosaic.factory import MosaicTilerFactory

# Enable Google Cloud Storage support
os.environ["GDAL_DISABLE_READDIR_ON_OPEN"] = "EMPTY_DIR"
os.environ["GDAL_HTTP_VERSION"] = "2"

# API settings
settings = ApiSettings(
    title="TiTiler CMIP6",
    description="TiTiler server for CMIP6 climate data",
    version="1.0.0",
    cors_origins=["*"],  # Configure appropriately for production
)

# Create tiler factory
tiler = TilerFactory(
    reader_options={
        "nodata": 0,
        "unscale": True,
        "resampling_method": "bilinear"
    }
)

# Create mosaic tiler factory for time series
mosaic_tiler = MosaicTilerFactory(
    reader_options={
        "nodata": 0,
        "unscale": True,
        "resampling_method": "bilinear"
    }
)

# Add routes
app = tiler.app
app.include_router(mosaic_tiler.router, prefix="/mosaic", tags=["mosaic"])

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
