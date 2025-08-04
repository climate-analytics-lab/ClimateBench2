import argparse
import logging
import pandas as pd
import numpy as np
from pathlib import Path
import xesmf as xe
from multiprocessing import Pool
from functools import partial

from utils import DataFinder, MetricCalculation
from constants import CMIP6_MODEL_INSTITUTIONS, VARIABLE_FREQUENCY_GROUP
from validate_gcs_models import get_valid_model_variable_combinations

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Configure basic logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Note: Regional CRPS calculation would require running spatial_crps 
# separately for each region. For now, we use global CRPS for all regions.

def process_model_variable(model, variable, start_year=2005, end_year=2014):
    """Process a single model-variable combination and return CRPS time series"""
    logger.info(f"Processing {model} - {variable}")
    
    try:
        # Initialize DataFinder
        data_finder = DataFinder(
            model=model, 
            variable=variable, 
            start_year=start_year, 
            end_year=end_year
        )
        
        # Load data (ensemble_mean=False for CRPS calculation)
        logger.info(f"Loading model data for {model} - {variable}")
        model_ds = data_finder.load_model_ds(ensemble_mean=False)
        
        # Optimize chunking for better performance
        model_ds = model_ds.chunk({'time': 12, 'ensemble': 3})  # Monthly + ensemble chunks
        
        logger.info(f"Loading cell area data for {model} - {variable}")
        fx_ds = data_finder.load_cell_area_ds()
        
        logger.info(f"Loading observations for {variable}")
        obs_ds = data_finder.load_obs_ds()
        
        # Regrid observations to model grid
        logger.info(f"Regridding observations for {model} - {variable}")
        # Handle both regular (lat,lon) and curvilinear (i,j) grids
        if 'lat' in model_ds.dims and 'lon' in model_ds.dims:
            grid_coords = ["lat", "lon"]
        else:
            grid_coords = ["lat", "lon"]  # Use coordinate variables even for i,j grids
        
        regridder = xe.Regridder(
            obs_ds, model_ds[grid_coords], "bilinear", periodic=True
        )
        obs_rg_ds = regridder(obs_ds[variable], keep_attrs=True)
        
        # Set up metric calculation
        metric_calculator = MetricCalculation(
            observations=obs_rg_ds,
            model=model_ds[variable],
            weights=fx_ds,
            lat_min=-90,
            lat_max=90,
        )
        
        # Calculate spatial CRPS time series (already spatially aggregated to global)
        logger.info(f"Calculating spatial CRPS for {model} - {variable}")
        crps_spatial_ts = metric_calculator.spatial_crps(adjustment=None)
        
        # The spatial_crps function already returns a global time series
        # Convert to records for CSV
        complete_records = []
        for time_idx, time_val in enumerate(crps_spatial_ts.time.values):
            crps_val = float(crps_spatial_ts.isel(time=time_idx).values)
            if not np.isnan(crps_val):
                record = {
                    'time': pd.to_datetime(time_val).strftime('%Y-%m-%d'),
                    'model': model,
                    'variable': variable,
                    'global': crps_val,
                    'northern_hemisphere': crps_val,  # For now, use global value for all regions
                    'southern_hemisphere': crps_val,  # TODO: Calculate actual regional CRPS
                    'tropics': crps_val,
                    'metric': 'CRPS'
                }
                complete_records.append(record)
        
        logger.info(f"Successfully processed {model} - {variable}: {len(complete_records)} time steps")
        return complete_records
        
    except Exception as e:
        logger.error(f"Error processing {model} - {variable}: {str(e)}")
        return []

def process_model_variable_wrapper(args):
    """Wrapper function for parallel processing"""
    model, variable, start_year, end_year = args
    return process_model_variable(model, variable, start_year, end_year)

def main(output_file="benchmark_results_crps_time_series.csv", start_year=2005, end_year=2014, test_mode=False, n_workers=4):
    """Generate CRPS time series for available models and variables"""
    
    logger.info("Starting CRPS time series generation")
    logger.info(f"Time period: {start_year}-{end_year}")
    logger.info(f"Output file: {output_file}")
    
    if test_mode:
        # Use only known working combinations for quick testing
        logger.info("🧪 Test mode: Using known working combinations")
        combinations = [
            ('CanESM5', 'tas', start_year, end_year),
            ('CESM2-WACCM', 'tas', start_year, end_year)
        ]
    else:
        # Get ALL valid model-variable combinations dynamically
        logger.info("🔍 Finding all valid model-variable combinations...")
        valid_combinations = get_valid_model_variable_combinations()
        
        # Convert to the format needed for processing
        combinations = [(model, variable, start_year, end_year) 
                       for model, variable in valid_combinations]
        
        logger.info(f"✅ Found {len(combinations)} valid model-variable combinations")
    
    logger.info(f"Processing {len(combinations)} combinations with {n_workers} parallel workers")
    
    all_records = []
    successful_combinations = 0
    failed_combinations = 0
    
    # Process combinations in parallel
    if n_workers > 1:
        logger.info(f"🔄 Using parallel processing with {n_workers} workers")
        with Pool(n_workers) as pool:
            results = pool.map(process_model_variable_wrapper, combinations)
    else:
        logger.info("🔄 Using sequential processing")
        results = [process_model_variable_wrapper(combo) for combo in combinations]
    
    # Process results
    for i, (model, variable, _, _) in enumerate(combinations):
        records = results[i]
        if records:
            all_records.extend(records)
            successful_combinations += 1
            logger.info(f"✅ {model}-{variable}: {len(records)} records")
        else:
            failed_combinations += 1
            logger.warning(f"❌ {model}-{variable}: No records generated")
        
        # Progress update every 5 combinations
        if (i + 1) % 5 == 0:
            logger.info(f"Progress: {successful_combinations} successful, {failed_combinations} failed, {len(all_records)} total records")
    
    if all_records:
        # Convert to DataFrame and save
        df = pd.DataFrame(all_records)
        
        # Sort by time, model, variable
        df = df.sort_values(['time', 'model', 'variable'])
        
        # Save to CSV
        output_path = Path(output_file)
        df.to_csv(output_path, index=False)
        
        logger.info(f"Successfully saved {len(df)} records to {output_path}")
        logger.info(f"File size: {output_path.stat().st_size / 1024 / 1024:.2f} MB")
        
        # Print summary statistics
        logger.info("Summary:")
        logger.info(f"  Models: {df['model'].nunique()}")
        logger.info(f"  Variables: {df['variable'].nunique()}")
        logger.info(f"  Time steps: {df['time'].nunique()}")
        logger.info(f"  Total records: {len(df)}")
        
    else:
        logger.error("No records generated!")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate CRPS time series for climate models")
    parser.add_argument(
        "--output-file", 
        type=str, 
        default="benchmark_results_crps_time_series.csv",
        help="Output CSV file path"
    )
    parser.add_argument(
        "--start-year", 
        type=int, 
        default=2005, 
        help="Start year for time series"
    )
    parser.add_argument(
        "--end-year", 
        type=int, 
        default=2014, 
        help="End year for time series"
    )
    parser.add_argument(
        "--test-mode", 
        action="store_true",
        help="Run in test mode (2 models, 2005-2007)"
    )
    parser.add_argument(
        "--workers", 
        type=int, 
        default=4, 
        help="Number of parallel workers (default: 4)"
    )
    
    args = parser.parse_args()
    
    if args.test_mode:
        logger.info("🧪 Running in TEST MODE")
        main("test_crps_production.csv", 2005, 2007, test_mode=True, n_workers=args.workers)
    else:
        main(args.output_file, args.start_year, args.end_year, test_mode=False, n_workers=args.workers)