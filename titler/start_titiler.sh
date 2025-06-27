#!/bin/bash
# TiTiler startup script for CMIP6 data

echo "🚀 Starting TiTiler server for CMIP6 data..."

# Set environment variables for Google Cloud Storage
export GDAL_DISABLE_READDIR_ON_OPEN=EMPTY_DIR
export GDAL_HTTP_VERSION=2

# Start TiTiler server
uvicorn titiler.main:app --host 0.0.0.0 --port 8000 --reload

echo "✅ TiTiler server started at http://localhost:8000"
echo "📊 API documentation: http://localhost:8000/docs"
echo "🗺️  Tile endpoint: http://localhost:8000/tiles/WebMercatorQuad/{z}/{x}/{y}.png"
