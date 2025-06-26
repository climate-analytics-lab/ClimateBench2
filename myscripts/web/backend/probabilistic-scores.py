from fastapi import FastAPI, Query
import xarray as xr
from fastapi.middleware.cors import CORSMiddleware
import time
import asyncio
from concurrent.futures import ThreadPoolExecutor
import threading

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

variable_to_zarr_path = {
    "pr": "gs://climatebench/observations/preprocessed/pr/pr_noaa_gpcp.zarr",
    # add others...
}

from google.cloud import storage
from collections import defaultdict

# Global cache for all datasets
dataset_cache = {}
cache_lock = threading.Lock()
is_initialized = False

def load_dataset_sync(path, dataset_type, variable=None, model_name=None):
    """Load a dataset synchronously with error handling"""
    try:
        print(f"📥 Loading {dataset_type} data from {path}...")
        ds = xr.open_zarr(path, consolidated=True)
        
        if dataset_type == "observed":
            data = ds[variable].mean(dim=["lat", "lon"])
            return {
                "time": data["time"].values.astype(str).tolist(),
                "values": data.values.tolist()
            }
        else:  # predicted
            data = ds['rmse']
            return {
                "time": ds['time'].values.astype(str).tolist(),
                "values": data.values.tolist()
            }
    except Exception as e:
        print(f"❌ Error loading {dataset_type} data from {path}: {e}")
        return None

def preload_all_data():
    """Preload all datasets at startup for faster response times"""
    global dataset_cache, is_initialized
    
    print("🚀 Preloading all datasets for faster response times...")
    start_time = time.time()
    
    # Initialize the Cloud Storage client
    client = storage.Client()
    bucket_name = "climatebench"
    
    # Dictionary to hold predicted paths grouped by variable
    predicted_paths = defaultdict(list)
    
    # Marker to identify the specific folder name of interest
    marker = "spatial_-90_90_rmse_results.zarr"
    
    print("📦 Loading predicted paths from Google Cloud Storage...")
    
    # List and process all blobs in the bucket
    for blob in client.list_blobs(bucket_name):
        blob_name = blob.name
        if marker in blob_name:
            idx = blob_name.find(marker)
            truncated_path = blob_name[: idx + len(marker)]
            
            parts = truncated_path.split('/')
            if len(parts) > 3 and parts[0] == "results" and parts[1] == "RMSE":
                variable = parts[2]
                full_gs_path = f"gs://{bucket_name}/{truncated_path}"
                
                if full_gs_path not in predicted_paths[variable]:
                    predicted_paths[variable].append(full_gs_path)
    
    predicted_paths = dict(predicted_paths)
    print(f"✅ Found {len(predicted_paths)} variables with predicted paths")
    
    # Preload observed data
    print("📊 Preloading observed data...")
    for variable in variable_to_zarr_path:
        cache_key = f"obs_{variable}"
        data = load_dataset_sync(variable_to_zarr_path[variable], "observed", variable)
        if data:
            with cache_lock:
                dataset_cache[cache_key] = data
            print(f"✅ Preloaded observed data for {variable}")
    
    # Preload predicted data using ThreadPoolExecutor for parallel loading
    print("📈 Preloading predicted data (this may take a moment)...")
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = []
        
        for variable, paths in predicted_paths.items():
            for pred_path in paths:
                model_name = pred_path.split("/")[-1].replace("_rmse_results.zarr", "")
                cache_key = f"pred_{variable}_{model_name}"
                
                future = executor.submit(load_dataset_sync, pred_path, "predicted", variable, model_name)
                futures.append((cache_key, future))
        
        # Collect results
        for cache_key, future in futures:
            try:
                data = future.result(timeout=30)  # 30 second timeout per dataset
                if data:
                    with cache_lock:
                        dataset_cache[cache_key] = data
                    print(f"✅ Preloaded predicted data: {cache_key}")
            except Exception as e:
                print(f"❌ Failed to preload {cache_key}: {e}")
    
    elapsed_time = time.time() - start_time
    print(f"🎉 All data preloaded in {elapsed_time:.2f} seconds!")
    print(f"📊 Total datasets cached: {len(dataset_cache)}")
    
    is_initialized = True

# Start preloading in a background thread
preload_thread = threading.Thread(target=preload_all_data, daemon=True)
preload_thread.start()

@app.get("/variable")
def get_variable_data(variable: str = Query(...)):
    if variable not in variable_to_zarr_path:
        return {"error": f"Variable '{variable}' not supported."}
    
    if not is_initialized:
        return {"error": "Backend is still initializing. Please wait a moment and try again."}

    try:
        start_time = time.time()
        print(f"🔄 Serving cached data for variable: {variable}")
        
        # Get observed data from cache
        obs_cache_key = f"obs_{variable}"
        if obs_cache_key not in dataset_cache:
            return {"error": f"Observed data for {variable} not found in cache"}
        
        obs_data = dataset_cache[obs_cache_key]
        
        # Get predicted data from cache
        predicted_data = {}
        with cache_lock:
            for cache_key, data in dataset_cache.items():
                if cache_key.startswith(f"pred_{variable}_"):
                    model_name = cache_key.replace(f"pred_{variable}_", "")
                    predicted_data[model_name] = data
        
        elapsed_time = time.time() - start_time
        print(f"⏱️  Data served in {elapsed_time:.3f} seconds")

        return {
            "time": obs_data["time"],
            variable: obs_data["values"],
            "predicted": predicted_data,
        }

    except Exception as e:
        print(f"❌ Error serving data for {variable}: {e}")
        return {"error": f"Failed to serve data: {e}"}

@app.get("/health")
def health_check():
    return {
        "status": "healthy" if is_initialized else "initializing",
        "message": "Probabilistic scores backend is running",
        "cached_datasets": len(dataset_cache),
        "initialized": is_initialized
    }

@app.get("/cache-status")
def cache_status():
    """Get information about cached datasets"""
    with cache_lock:
        return {
            "total_datasets": len(dataset_cache),
            "observed_datasets": [k for k in dataset_cache.keys() if k.startswith("obs_")],
            "predicted_datasets": [k for k in dataset_cache.keys() if k.startswith("pred_")],
            "initialized": is_initialized
        }
