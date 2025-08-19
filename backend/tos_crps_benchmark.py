#!/usr/bin/env python3
"""
Sea Surface Temperature (TOS) CRPS Benchmark Results Generator
Generates CRPS benchmark results for sea surface temperature.
"""

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

def calculate_tos_crps_metrics(model: str, start_year: int = 2005, end_year: int = 2024) -> List[Dict]:
    """
    Calculate CRPS metrics for sea surface temperature (tos) for a specific model.
    
    Args:
        model: Climate model name
        start_year: Start year for analysis
        end_year: End year for analysis
        
    Returns:
        List of dictionaries containing benchmark results
    """
    try:
        logger.info(f"Processing model {model} for sea surface temperature (tos)")
        
        # Use DataFinder to load data
        data_finder = DataFinder(model=model, variable="tos", start_year=start_year, end_year=end_year)
        
        # Load model data (ensemble mean)
        model_ds = data_finder.load_model_ds(ensemble_mean=False)  # Keep ensemble dimension for CRPS
        if model_ds is None:
            logger.warning(f"No model data found for {model} tos")
            return []
        
        # Load observational data
        obs_ds = data_finder.load_obs_ds()
        if obs_ds is None:
            logger.warning(f"No observational data found for tos")
            return []
        
        # Load cell area data for weights
        fx_ds = data_finder.load_cell_area_ds()
        
        # Get the main variable from datasets
        model_var = "tos" if "tos" in model_ds.data_vars else list(model_ds.data_vars)[0]
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
        
        results = []
        
        # Define metrics to calculate
        metrics = [
            ("zonal_mean_crps", None),
            ("zonal_mean_crps", "bias_adjusted"),
            ("zonal_mean_crps", "anomaly"),
            ("spatial_crps", None),
            ("spatial_crps", "bias_adjusted"),
            ("spatial_crps", "anomaly"),
        ]
        
        # Calculate metrics for each region
        for region_name, (lat_min, lat_max) in REGIONS.items():
            logger.info(f"Calculating metrics for {region_name} region")
            
            for metric_name, adjustment in metrics:
                try:
                    # Calculate historical value
                    hist_value = calculate_regional_crps_benchmark(
                        metric_calculator_hist, region_name, lat_min, lat_max, metric_name, adjustment
                    )
                    
                    # Calculate future value
                    future_value = calculate_regional_crps_benchmark(
                        metric_calculator_future, region_name, lat_min, lat_max, metric_name, adjustment
                    )
                    
                    if hist_value is not None and future_value is not None:
                        # Calculate change
                        change = future_value - hist_value
                        pct_change = (change / hist_value) * 100 if hist_value != 0 else 0
                        
                        # Create metric name with adjustment suffix
                        full_metric_name = metric_name
                        if adjustment:
                            full_metric_name = f"{metric_name}_{adjustment}"
                        
                        results.append({
                            'model': model,
                            'variable': 'tos',
                            'metric': full_metric_name,
                            'region': region_name,
                            'Historical (2005-2014)': hist_value,
                            'SSP2-4.5': future_value,
                            'Change (hist 2005)': change,
                            'Percent Change (hist 2005)': pct_change
                        })
                    else:
                        logger.warning(f"Could not calculate {metric_name} for {region_name}")
                        
                except Exception as e:
                    logger.error(f"Error calculating {metric_name} for {region_name}: {e}")
        
        logger.info(f"Completed processing {model} tos - generated {len(results)} metrics")
        return results
        
    except Exception as e:
        logger.error(f"Error processing {model} tos: {e}")
        return []

def main():
    """Main function to run TOS CRPS benchmark calculations for all models."""
    
    # Get list of valid models from clean_valid_models.txt
    try:
        with open('clean_valid_models.txt', 'r') as f:
            models = [line.strip() for line in f if line.strip() and not line.startswith('#')]
    except FileNotFoundError:
        logger.error("clean_valid_models.txt not found")
        return
    
    logger.info(f"Processing {len(models)} models for TOS CRPS benchmarks")
    
    all_results = []
    
    for model in models:
        logger.info(f"Processing {model}")
        results = calculate_tos_crps_metrics(model)
        all_results.extend(results)
    
    # Convert to DataFrame and save
    if all_results:
        df = pd.DataFrame(all_results)
        
        # Save individual model files
        for model in models:
            model_df = df[df['model'] == model]
            if not model_df.empty:
                filename = f"tos_crps_benchmark_{model}.csv"
                model_df.to_csv(filename, index=False)
                logger.info(f"Saved {filename} with {len(model_df)} rows")
        
        # Save combined file
        combined_filename = "tos_crps_benchmarks_combined.csv"
        df.to_csv(combined_filename, index=False)
        logger.info(f"Saved {combined_filename} with {len(df)} total rows")
        
        logger.info("TOS CRPS benchmark calculations completed successfully!")
    else:
        logger.warning("No results generated")

if __name__ == "__main__":
    main()
