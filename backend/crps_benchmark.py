import logging
import pandas as pd
import numpy as np
from typing import List, Dict, Optional

from constants import (
    ENSEMBLE_MEMBERS,
    VARIABLE_FREQUENCY_GROUP,
    HIST_START_DATE,
    HIST_END_DATE,
    SSP_START_DATE,
    SSP_END_DATE,
    SSP_EXPERIMENT,
    GOOGLE_CLOUD_PROJECT,
    CMIP6_MODEL_INSTITUTIONS,
    OBSERVATION_DATA_PATHS,
)
from utils import DataFinder, MetricCalculation

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Define regions (matching the format used in other benchmark files)
REGIONS = {
    'global': (-90, 90),           # 90°S to 90°N
    'northern_hemisphere': (0, 90),    # 0°N to 90°N
    'southern_hemisphere': (-90, 0),   # 90°S to 0°N
    'tropics': (-23.5, 23.5),         # 23.5°S to 23.5°N
}

def calculate_crps_metrics(model: str, variable: str, start_year: int = 2005, end_year: int = 2024) -> List[Dict]:
    """
    Calculate CRPS metrics for a model-variable combination using the DataFinder and MetricCalculation classes.
    
    Args:
        model: Climate model name
        variable: Variable name (tas, pr, clt, tos, od550aer)
        start_year: Start year for analysis
        end_year: End year for analysis
        
    Returns:
        List of dictionaries containing benchmark results
    """
    try:
        logger.info(f"Processing model {model}, variable {variable}")
        
        # Use DataFinder to load data
        data_finder = DataFinder(model=model, variable=variable, start_year=start_year, end_year=end_year)
        
        # Load model data (ensemble mean)
        model_ds = data_finder.load_model_ds(ensemble_mean=False)  # Keep ensemble dimension for CRPS
        if model_ds is None:
            logger.warning(f"No model data found for {model} {variable}")
            return []
        
        # Load observational data
        obs_ds = data_finder.load_obs_ds()
        if obs_ds is None:
            logger.warning(f"No observational data found for {variable}")
            return []
        
        # Load cell area data for weights
        fx_ds = data_finder.load_cell_area_ds()
        
        # Get the main variable from datasets
        model_var = variable if variable in model_ds.data_vars else list(model_ds.data_vars)[0]
        obs_var = list(obs_ds.data_vars)[0]
        
        # Split data into historical and future periods
        hist_start = "2005-01-01"
        hist_end = "2014-12-31"
        future_start = "2015-01-01"
        future_end = "2024-12-31"
        
        model_hist = model_ds[model_var].sel(time=slice(hist_start, hist_end))
        model_future = model_ds[model_var].sel(time=slice(future_start, future_end))
        obs_hist = obs_ds[obs_var].sel(time=slice(hist_start, hist_end))
        obs_future = obs_ds[obs_var].sel(time=slice(future_start, future_end))
        
        # Create metric calculators for historical and future periods
        metric_calculator_hist = MetricCalculation(
            observations=obs_hist,
            model=model_hist,
            weights=fx_ds,
            lat_min=-90,
            lat_max=90,
        )
        
        metric_calculator_future = MetricCalculation(
            observations=obs_future,
            model=model_future,
            weights=fx_ds,
            lat_min=-90,
            lat_max=90,
        )
        
        # Define metrics and adjustments
        metrics = ["zonal_mean_crps", "spatial_crps"]
        adjustments = [None, "bias_adjusted", "anomaly"]
        
        benchmark_records = []
        
        # Calculate CRPS for each metric, adjustment, and region combination
        for metric_name in metrics:
            for adjustment in adjustments:
                adjustment_name = adjustment if adjustment else "raw"
                logger.info(f"Calculating {metric_name} with {adjustment_name} adjustment for {model} - {variable}")
                
                for region_name, (lat_min, lat_max) in REGIONS.items():
                    logger.info(f"Calculating {metric_name} for {region_name} ({lat_min}° to {lat_max}°) with {adjustment_name}")
                    
                    # Calculate historical CRPS
                    hist_crps = calculate_regional_crps_benchmark(
                        metric_calculator_hist, region_name, lat_min, lat_max, metric_name, adjustment
                    )
                    
                    # Calculate future CRPS
                    future_crps = calculate_regional_crps_benchmark(
                        metric_calculator_future, region_name, lat_min, lat_max, metric_name, adjustment
                    )
                    
                    if hist_crps is not None and future_crps is not None and not (np.isnan(hist_crps) or np.isnan(future_crps)):
                        # Calculate change and percent change
                        change = future_crps - hist_crps
                        percent_change = (change / hist_crps) * 100 if hist_crps != 0 else 0
                        
                        record = {
                            'model': model,
                            'variable': variable,
                            'metric': f"{metric_name}_{adjustment_name}" if adjustment_name != "raw" else metric_name,
                            'region': region_name,
                            'Historical (2005-2014)': hist_crps,
                            'SSP2-4.5': future_crps,
                            'Change (hist 2005)': change,
                            'Percent Change (hist 2005)': percent_change
                        }
                        benchmark_records.append(record)
                        logger.info(f"✅ {model}-{variable}-{metric_name}-{region_name}-{adjustment_name}: Historical={hist_crps:.6f}, Future={future_crps:.6f}, Change={change:.6f}")
                    else:
                        logger.warning(f"❌ {model}-{variable}-{metric_name}-{region_name}-{adjustment_name}: Failed (hist_crps={hist_crps}, future_crps={future_crps})")
        
        logger.info(f"Successfully processed {model} - {variable}: {len(benchmark_records)} benchmark records")
        return benchmark_records
        
    except Exception as e:
        logger.error(f"Error processing {model} - {variable}: {str(e)}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        return []

def calculate_regional_crps_benchmark(metric_calculator, region_name: str, lat_min: float, lat_max: float, 
                                    metric_name: str, adjustment: Optional[str]) -> Optional[float]:
    """
    Calculate CRPS benchmark for a specific region and metric.
    
    Args:
        metric_calculator: MetricCalculation instance
        region_name: Name of the region
        lat_min: Minimum latitude
        lat_max: Maximum latitude
        metric_name: Name of the metric to calculate
        adjustment: Adjustment type (None, 'bias_adjusted', 'anomaly')
        
    Returns:
        CRPS value or None if calculation fails
    """
    try:
        # Check if we have ensemble dimension
        if "ensemble" not in metric_calculator.model.dims:
            logger.error(f"No ensemble dimension found in model data. Available dims: {metric_calculator.model.dims}")
            return None
        
        # Create new metric calculator for the region using the original unfiltered data
        # The MetricCalculation class will handle regional filtering internally
        regional_calculator = MetricCalculation(
            observations=metric_calculator.obs,
            model=metric_calculator.model,
            weights=metric_calculator.weights,
            lat_min=lat_min,
            lat_max=lat_max,
        )
        
        # Try to align the data if coordinates don't match after regional filtering
        try:
            # Regrid observational data to model grid if needed
            if not (regional_calculator.model.lat.equals(regional_calculator.obs.lat) and 
                   regional_calculator.model.lon.equals(regional_calculator.obs.lon)):
                regional_calculator.obs = regional_calculator.obs.interp(
                    lat=regional_calculator.model.lat, 
                    lon=regional_calculator.model.lon, 
                    method='linear'
                )
        except Exception as e:
            logger.error(f"Error during regridding: {e}")
            return None
        
        # Calculate the appropriate metric
        if metric_name == "zonal_mean_crps":
            result = regional_calculator.zonal_mean_crps(adjustment=adjustment)
            # Handle the case where result is a list (from .values.tolist())
            if isinstance(result, list):
                return float(result[0]) if result else None
            else:
                return float(result)
        elif metric_name == "spatial_crps":
            # For spatial CRPS, take the mean over time
            spatial_crps = regional_calculator.spatial_crps(adjustment=adjustment)
            return float(spatial_crps.mean().values)
        else:
            logger.warning(f"Unknown metric: {metric_name}")
            return None
            
    except Exception as e:
        logger.error(f"Error calculating {metric_name} for {region_name}: {str(e)}")
        return None

def main(output_file: str = "crps_benchmark_results.csv", start_year: int = 2005, end_year: int = 2024,
         models: Optional[List[str]] = None, variables: Optional[List[str]] = None):
    """
    Generate CRPS benchmark results for climate models with historical vs future scenario comparisons.
    
    Args:
        output_file: Output CSV file path
        start_year: Start year for analysis
        end_year: End year for analysis
        models: List of models to process (if None, load from gcs_valid_models.txt)
        variables: List of variables to process (if None, process all available variables)
    """
    logger.info("Starting CRPS benchmark generation with historical vs future comparison")
    logger.info(f"Historical period: 2005-2014")
    logger.info(f"Future period: 2015-2024")
    logger.info(f"Output file: {output_file}")
    
    # Load models from gcs_valid_models.txt if not specified
    if models is None:
        try:
            with open("gcs_valid_models.txt", "r") as f:
                models = [line.strip() for line in f if line.strip() and not line.startswith("#")]
            logger.info(f"Loaded {len(models)} models from gcs_valid_models.txt")
        except FileNotFoundError:
            logger.warning("gcs_valid_models.txt not found, using default models")
            models = ["ACCESS-CM2", "CanESM5", "CESM2", "GFDL-CM4", "IPSL-CM6A-LR", "MIROC6", "MPI-ESM1-2-LR", "MRI-ESM2-0"]
    
    if variables is None:
        variables = ["tas", "pr", "clt", "tos", "od550aer"]
    
    logger.info(f"Processing {len(models)} models: {models}")
    logger.info(f"Processing {len(variables)} variables: {variables}")
    
    all_results = []
    
    # Process each model-variable combination
    for i, model in enumerate(models):
        logger.info(f"\n[{i+1}/{len(models)}] Processing model: {model}")
        for j, variable in enumerate(variables):
            logger.info(f"  [{j+1}/{len(variables)}] Processing variable: {variable}")
            if model in CMIP6_MODEL_INSTITUTIONS and variable in VARIABLE_FREQUENCY_GROUP:
                results = calculate_crps_metrics(model, variable, start_year, end_year)
                if results:
                    all_results.extend(results)
                    logger.info(f"    ✅ Generated {len(results)} benchmark records")
                else:
                    logger.warning(f"    ❌ No results generated")
            else:
                logger.warning(f"    ⚠️  Skipping {model}-{variable}: not in supported models/variables")
    
    # Create DataFrame and save to CSV
    if all_results:
        df = pd.DataFrame(all_results)
        df.to_csv(output_file, index=False)
        logger.info(f"\n✅ Saved {len(all_results)} benchmark records to {output_file}")
        logger.info(f"📊 Summary:")
        logger.info(f"  Models processed: {df['model'].nunique()}")
        logger.info(f"  Variables processed: {df['variable'].nunique()}")
        logger.info(f"  Regions: {df['region'].nunique()}")
        logger.info(f"  Metrics: {df['metric'].nunique()}")
    else:
        logger.warning("No results generated")

if __name__ == "__main__":
    # Process all valid models and all variables
    main(
        output_file="crps_benchmark_results.csv",
        start_year=2005,
        end_year=2024,
        # models=None,  # Will load from gcs_valid_models.txt
        # variables=None  # Will process all variables
    )
