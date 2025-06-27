#!/usr/bin/env python3
"""
TiTiler Setup Script for CMIP6 Data
This script helps set up TiTiler to serve CMIP6 NetCDF data from Google Cloud Storage.
"""

import subprocess
import sys
import os
from pathlib import Path

def check_python_version():
    """Check if Python version is compatible."""
    if sys.version_info < (3, 8):
        print("❌ Python 3.8 or higher is required")
        return False
    print(f"✅ Python {sys.version_info.major}.{sys.version_info.minor} detected")
    return True

def install_titiler():
    """Install TiTiler and dependencies."""
    print("📦 Installing TiTiler and dependencies...")
    
    packages = [
        "titiler[full]",
        "netcdf4",
        "xarray",
        "rioxarray",
        "google-cloud-storage"
    ]
    
    for package in packages:
        try:
            subprocess.run([sys.executable, "-m", "pip", "install", package], check=True)
            print(f"✅ Installed {package}")
        except subprocess.CalledProcessError as e:
            print(f"❌ Failed to install {package}: {e}")
            return False
    
    return True

def create_titiler_config():
    """Create TiTiler configuration file."""
    config_content = """
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
"""
    
    config_path = Path("titler_config.py")
    with open(config_path, "w") as f:
        f.write(config_content)
    
    print(f"✅ Created TiTiler configuration: {config_path}")
    return config_path

def create_startup_script():
    """Create a startup script for TiTiler."""
    script_content = """#!/bin/bash
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
"""
    
    script_path = Path("start_titiler.sh")
    with open(script_path, "w") as f:
        f.write(script_content)
    
    # Make executable on Unix systems
    os.chmod(script_path, 0o755)
    
    print(f"✅ Created startup script: {script_path}")
    return script_path

def test_titiler_connection():
    """Test TiTiler connection."""
    print("🧪 Testing TiTiler connection...")
    
    try:
        import requests
        response = requests.get("http://localhost:8000/health")
        if response.status_code == 200:
            print("✅ TiTiler server is running")
            return True
        else:
            print("❌ TiTiler server returned unexpected status")
            return False
    except requests.exceptions.ConnectionError:
        print("❌ Cannot connect to TiTiler server")
        print("💡 Make sure TiTiler is running: uvicorn titiler.main:app --host 0.0.0.0 --port 8000")
        return False

def main():
    """Main setup function."""
    print("🌍 TiTiler Setup for CMIP6 Data")
    print("=" * 40)
    
    # Check Python version
    if not check_python_version():
        return
    
    # Install TiTiler
    if not install_titiler():
        print("❌ Failed to install TiTiler")
        return
    
    # Create configuration
    config_path = create_titiler_config()
    
    # Create startup script
    script_path = create_startup_script()
    
    print("\n🎉 Setup complete!")
    print("\n📋 Next steps:")
    print("1. Start TiTiler server:")
    print(f"   bash {script_path}")
    print("   OR")
    print("   uvicorn titiler.main:app --host 0.0.0.0 --port 8000")
    print("\n2. Open your HTML file in a browser")
    print("3. Check TiTiler API docs: http://localhost:8000/docs")
    print("\n🔗 Useful TiTiler endpoints:")
    print("- Health check: http://localhost:8000/health")
    print("- API docs: http://localhost:8000/docs")
    print("- Tiles: http://localhost:8000/tiles/WebMercatorQuad/{z}/{x}/{y}.png")
    print("- Info: http://localhost:8000/info?url=<gcs_path>")
    print("- Bounds: http://localhost:8000/bounds?url=<gcs_path>")

if __name__ == "__main__":
    main() 