import argparse
import logging
import os
import sys
import glob
from pathlib import Path
from typing import List, Optional

import numpy as np
import xarray as xr


def setup_logging(log_level: str = "INFO", log_file: Optional[str] = None) -> None:
    """Set up logging configuration."""
    log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    
    handlers = [logging.StreamHandler(sys.stdout)]
    if log_file:
        handlers.append(logging.FileHandler(log_file))
    
    logging.basicConfig(
        level=getattr(logging, log_level.upper()),
        format=log_format,
        handlers=handlers
    )


def find_model_folders(data_cache_dir: Path, paleo_period: str) -> List[str]:
    """Find model folders containing wget scripts for the specified period."""
    search_pattern = data_cache_dir / "*" / f"{paleo_period}*.sh"
    model_folders = glob.glob(str(search_pattern))
    
    logging.info(f"Found {len(model_folders)} model folders for period '{paleo_period}'")
    for folder in model_folders:
        logging.debug(f"Model folder: {folder}")
    
    return model_folders


def download_data(wget_file: str) -> bool:
    """Download data using wget script."""
    logging.info(f"Downloading data using script: {wget_file}")
    
    try:
        # Make script executable
        os.system(f"chmod +x {wget_file}")
        # Execute download script
        exit_code = os.system(f"{wget_file}")
        
        if exit_code == 0:
            logging.info("Data download completed successfully")
            return True
        else:
            logging.error(f"Download failed with exit code: {exit_code}")
            return False
    except Exception as e:
        logging.error(f"Error during download: {e}")
        return False


def load_netcdf_files(model_dir: str) -> Optional[xr.Dataset]:
    """Load and merge NetCDF files with temperature data."""
    nc_files = glob.glob(f"{model_dir}tas*")
    
    if not nc_files:
        logging.warning(f"No temperature files found in {model_dir}")
        return None
    
    logging.info(f"Loading {len(nc_files)} NetCDF files")
    
    # Variables to drop if they exist
    drop_vars = ["time_bnds", "lat_bnds", "lon_bnds", "height"]
    
    try:
        # First attempt without cftime
        ds = xr.open_mfdataset(nc_files, chunks={}).drop_vars(drop_vars, errors="ignore")
        logging.info("Successfully loaded dataset without cftime")
    except Exception as e:
        logging.warning(f"Failed to load without cftime: {e}")
        try:
            # Second attempt with cftime for non-standard calendars
            ds = xr.open_mfdataset(nc_files, use_cftime=True, chunks={}).drop_vars(drop_vars, errors="ignore")
            logging.info("Successfully loaded dataset with cftime")
        except Exception as e2:
            logging.error(f"Failed to load dataset: {e2}")
            return None
    
    return ds


def calculate_area_weights(ds: xr.Dataset) -> xr.Dataset:
    """Calculate area weights based on latitude."""
    logging.info("Calculating area weights")
    weights = np.cos(np.deg2rad(ds.lat))
    weights = weights.expand_dims({"lon": ds.lon})
    weights.name = "areacella"
    return weights


def process_temperature_data(ds: xr.Dataset, model_dir: str, paleo_period: str) -> None:
    """Process temperature data and save annual and monthly statistics."""
    logging.info("Processing temperature data")
    
    # Calculate area weights
    weights = calculate_area_weights(ds)
    
    # Annual statistics
    logging.info("Calculating annual mean and standard deviation")
    ds_mean_annual = ds.mean(dim="time")
    ds_std_annual = ds.std(dim="time").rename({"tas": "tas_std"})
    
    annual_output = f"{model_dir}{paleo_period}_tas_annual.nc"
    logging.info(f"Saving annual statistics to: {annual_output}")
    xr.merge([ds_mean_annual, ds_std_annual, weights.to_dataset(name="weight")]).to_netcdf(annual_output)
    
    # Monthly statistics
    logging.info("Calculating monthly mean and standard deviation")
    ds_mean_mon = ds.groupby("time.month").mean()
    ds_std_mon = ds.groupby("time.month").std().rename({"tas": "tas_std"})
    
    monthly_output = f"{model_dir}{paleo_period}_tas_monthly.nc"
    logging.info(f"Saving monthly statistics to: {monthly_output}")
    xr.merge([ds_mean_mon, ds_std_mon, weights.to_dataset(name="weight")]).to_netcdf(monthly_output)


def cleanup_files(model_dir: str) -> None:
    """Remove temporary NetCDF files after processing."""
    nc_files = glob.glob(f"{model_dir}tas*")
    logging.info(f"Cleaning up {len(nc_files)} temporary files")
    
    for file in nc_files:
        try:
            os.remove(file)
            logging.debug(f"Removed: {file}")
        except Exception as e:
            logging.warning(f"Failed to remove {file}: {e}")


def download_eocene_data() -> None:
    """Handle special case for Eocene data download."""
    logging.info("Downloading Eocene data via direct wget")
    wget_command = (
        'wget -e robots=off --mirror --no-parent -r --accept "tas_*mean.nc" '
        'https://dap.ceda.ac.uk/badc/cmip6/data/CMIP6Plus/DeepMIP/deepmip-eocene-p1/'
    )
    
    exit_code = os.system(wget_command)
    if exit_code == 0:
        logging.info("Eocene data download completed successfully")
    else:
        logging.error(f"Eocene data download failed with exit code: {exit_code}")


def process_paleo_period(data_cache_dir: Path, paleo_period: str, skip_download: bool = False) -> None:
    """Process data for a specific paleoclimate period."""
    logging.info(f"Processing paleoclimate period: {paleo_period}")
    
    # Special handling for Eocene
    if paleo_period == 'eocene':
        download_eocene_data()
        return
    
    # Find model folders
    model_folders = find_model_folders(data_cache_dir, paleo_period)
    
    if not model_folders:
        logging.error(f"No model folders found for period '{paleo_period}'")
        return
    
    # Process each model
    for wget_file in model_folders:
        model_dir = "/".join(wget_file.split("/")[:-1]) + "/"
        model_name = Path(wget_file).parent.name
        logging.info(f"Processing model: {model_name}")
        
        # Download data unless skipped
        if not skip_download:
            if not download_data(wget_file):
                logging.error(f"Skipping model {model_name} due to download failure")
                continue
        
        # Load and process data
        ds = load_netcdf_files(model_dir)
        if ds is None:
            logging.error(f"Skipping model {model_name} due to data loading failure")
            continue
        
        try:
            process_temperature_data(ds, model_dir, paleo_period)
            logging.info(f"Successfully processed model: {model_name}")
        except Exception as e:
            logging.error(f"Failed to process model {model_name}: {e}")
            continue
        finally:
            if not skip_download:
                cleanup_files(model_dir)


def main() -> None:
    """Main function with argument parsing and execution."""
    parser = argparse.ArgumentParser(
        description="Process paleoclimate temperature data from CMIP6 models",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    
    parser.add_argument(
        "--paleo-period",
        type=str,
        choices=["lgm", "midHolocene", "lig127k", "midPliocene-eoi400", "eocene"],
        help="Paleoclimate period to process"
    )
    
    parser.add_argument(
        "--data-cache-dir",
        type=Path,
        required=True,
        help="Path to the paleoclimate data cache directory"
    )
    
    parser.add_argument(
        "--skip-download",
        action="store_true",
        help="Skip data download step (assume data already exists)"
    )
    
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
        help="Logging level"
    )
    
    parser.add_argument(
        "--log-file",
        type=str,
        help="Path to log file (default: log to stdout only)"
    )
    
    args = parser.parse_args()
    
    # Setup logging
    setup_logging(args.log_level, args.log_file)
    
    # Validate data cache directory
    if not args.data_cache_dir.exists():
        logging.error(f"Data cache directory does not exist: {args.data_cache_dir}")
        sys.exit(1)
    
    logging.info("Starting paleoclimate data processing")
    logging.info(f"Period: {args.paleo_period}")
    logging.info(f"Data cache directory: {args.data_cache_dir}")
    logging.info(f"Skip download: {args.skip_download}")
    
    try:
        process_paleo_period(args.data_cache_dir, args.paleo_period, args.skip_download)
        logging.info("Processing completed successfully")
    except Exception as e:
        logging.error(f"Processing failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()