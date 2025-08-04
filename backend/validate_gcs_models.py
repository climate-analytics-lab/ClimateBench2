"""
Simple and fast model validation - check CMIP6 GCS bucket for exact ensemble requirements
"""

import subprocess
import logging
from constants import CMIP6_MODEL_INSTITUTIONS, VARIABLE_FREQUENCY_GROUP, ENSEMBLE_MEMBERS

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def check_gcs_bucket_files(model, variable):
    """Check if ALL required ensemble files exist in gs://cmip6/CMIP6/ScenarioMIP bucket"""
    
    # Get model organization
    org = CMIP6_MODEL_INSTITUTIONS[model]
    
    # Get variable frequency
    frequency_table = VARIABLE_FREQUENCY_GROUP[variable]
    
    # Required ensemble members: ["r1i1p1f1", "r2i1p1f1", "r3i1p1f1"]
    required_ensembles = ENSEMBLE_MEMBERS
    
    # Check GCS bucket paths for ssp245 experiment
    base_gcs_path = f"gs://cmip6/CMIP6/ScenarioMIP/{org}/{model}/ssp245"
    
    found_ensembles = []
    
    for ensemble in required_ensembles:
        # Construct the GCS path pattern
        gcs_path = f"{base_gcs_path}/{ensemble}/{frequency_table}/{variable}"
        
        try:
            # Use gsutil ls to check if zarr directory exists (pattern: variable/gn/v*/zarr_contents)
            result = subprocess.run(
                ["gsutil", "ls", f"{gcs_path}/gn/v*/.zmetadata"], 
                capture_output=True, 
                text=True, 
                timeout=10
            )
            
            # If gsutil found zarr metadata (exit code 0 and has output)
            if result.returncode == 0 and result.stdout.strip():
                found_ensembles.append(ensemble)
                
        except subprocess.TimeoutExpired:
            logger.warning(f"Timeout checking {gcs_path}")
        except Exception as e:
            # Silently continue if path doesn't exist or other errors
            pass
    
    # Must have ALL 3 ensemble members
    has_all_ensembles = len(found_ensembles) == len(required_ensembles)
    
    return has_all_ensembles, found_ensembles

def simple_find_valid_models():
    """Find models with ALL ensemble members for ALL variables (GCS bucket check)"""
    
    # Check ALL CMIP6 models for complete validation
    test_models = list(CMIP6_MODEL_INSTITUTIONS.keys())
    all_variables = list(VARIABLE_FREQUENCY_GROUP.keys())
    
    logger.info(f"GCS BUCKET CHECK: {len(test_models)} models × {len(all_variables)} variables")
    logger.info(f"Bucket: gs://cmip6/CMIP6/ScenarioMIP")
    logger.info(f"Variables: {all_variables}")
    logger.info(f"Required ensembles: {ENSEMBLE_MEMBERS} (ALL required)")
    
    valid_models = []
    
    for i, model in enumerate(test_models):
        logger.info(f"[{i+1}/{len(test_models)}] Checking {model}...")
        
        valid_variables = []
        
        for variable in all_variables:
            has_all, found = check_gcs_bucket_files(model, variable)
            
            if has_all:
                valid_variables.append(variable)
                logger.info(f"  ✅ {variable}: {len(found)}/3 ensembles")
            else:
                logger.info(f"  ❌ {variable}: {len(found)}/3 ensembles (missing: {set(ENSEMBLE_MEMBERS) - set(found)})")
        
        # Model is valid if it has ALL ensembles for ANY ONE variable
        if len(valid_variables) > 0:
            valid_models.append(model)
            logger.info(f"  🎉 {model}: {len(valid_variables)} variables with ALL ensembles ✓")
            logger.info(f"    Valid variables: {valid_variables}")
        else:
            logger.info(f"  ⚠️  {model}: No variables with all 3 ensembles")
    
    # Print summary
    logger.info("\n" + "="*60)
    logger.info("GCS BUCKET VALIDATION RESULTS")
    logger.info("="*60)
    
    logger.info(f"\n✅ Valid models with ALL ensembles ({len(valid_models)}):")
    for model in valid_models:
        logger.info(f"  {model}")
    
    if valid_models:
        logger.info(f"\n📋 COPY THIS TO crps_timeseries_generator.py:")
        logger.info("models = [")
        for model in valid_models:
            logger.info(f"    '{model}',")
        logger.info("]")
    else:
        logger.warning("\n⚠️  NO MODELS found with all ensembles in GCS bucket!")
        logger.info("Check bucket path or ensemble member requirements")
    
    return valid_models

def get_valid_model_variable_combinations():
    """Get a list of valid (model, variable) combinations where model has all ensembles for that variable"""
    
    all_models = list(CMIP6_MODEL_INSTITUTIONS.keys())
    all_variables = list(VARIABLE_FREQUENCY_GROUP.keys())
    
    valid_combinations = []
    
    logger.info("🔍 Finding valid model-variable combinations...")
    
    for model in all_models:
        for variable in all_variables:
            has_all, found = check_gcs_bucket_files(model, variable)
            if has_all:
                valid_combinations.append((model, variable))
                logger.info(f"✅ {model}-{variable}: Valid")
    
    logger.info(f"\n📊 Found {len(valid_combinations)} valid model-variable combinations")
    
    # Group by model for summary
    model_vars = {}
    for model, variable in valid_combinations:
        if model not in model_vars:
            model_vars[model] = []
        model_vars[model].append(variable)
    
    logger.info("\n📋 Valid combinations by model:")
    for model, variables in sorted(model_vars.items()):
        logger.info(f"  {model}: {variables}")
    
    return valid_combinations

if __name__ == "__main__":
    import time
    
    start_time = time.time()
    valid_models = simple_find_valid_models()
    end_time = time.time()
    
    logger.info(f"✅ Found {len(valid_models)} valid models")
    
    # Save results
    with open("gcs_valid_models.txt", "w") as f:
        f.write("# Models with ALL variables and ALL ensemble members (GCS bucket):\n")
        f.write("# Bucket: gs://cmip6/CMIP6/ScenarioMIP\n")
        for model in valid_models:
            f.write(f"{model}\n")
    
    logger.info("Results saved to gcs_valid_models.txt")