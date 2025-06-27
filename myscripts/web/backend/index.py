from fastapi import FastAPI, Query
from google.cloud import storage
import pandas as pd
from io import StringIO
from fastapi.middleware.cors import CORSMiddleware
import xarray as xr
from collections import defaultdict
import time
import threading

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# GCS bucket and file path info
BUCKET_NAME = "climatebench"
BLOB_NAME = "results/RMSE/pr/zonal_mean_rmse_-90_90_results.csv"

# Variable to zarr path mapping
variable_to_zarr_path = {
    "pr": "gs://climatebench/observations/preprocessed/pr/pr_noaa_gpcp.zarr",
    # add others...
}

# Global cache for all data
data_cache = {}
cache_lock = threading.Lock()
is_initialized = False

def read_csv_from_gcs_cached(bucket_name: str, blob_name: str) -> pd.DataFrame:
    """Read CSV from GCS with caching"""
    cache_key = f"csv_{bucket_name}_{blob_name}"
    
    with cache_lock:
        if cache_key in data_cache:
            return data_cache[cache_key]
    
    print(f"📥 Loading CSV data from {blob_name}...")
    client = storage.Client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(blob_name)
    data = blob.download_as_text()
    df = pd.read_csv(StringIO(data))
    
    with cache_lock:
        data_cache[cache_key] = df
    
    print(f"✅ CSV data loaded and cached: {blob_name}")
    return df

def preload_all_data():
    """Preload all data at startup for faster response times"""
    global data_cache, is_initialized
    
    print("🚀 Preloading main backend data for faster response times...")
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
    
    # Preload CSV data
    print("📊 Preloading CSV data...")
    csv_df = read_csv_from_gcs_cached(BUCKET_NAME, BLOB_NAME)
    
    # Preload all RMSE metrics
    metrics = ["rmse", "rmse_bias_adjusted", "rmse_anomaly"]
    for metric in metrics:
        df_metric = csv_df[csv_df['metric'] == metric]
        zonal_mean = df_metric.groupby('model').agg({
            'historical': 'mean',
            'ssp245': 'mean'
        }).reset_index()
        zonal_mean_sorted = zonal_mean.sort_values('historical')
        
        cache_key = f"rmse_{metric}"
        with cache_lock:
            data_cache[cache_key] = zonal_mean_sorted.to_dict(orient='records')
        print(f"✅ Preloaded RMSE data for metric: {metric}")
    
    # Store predicted paths in cache
    with cache_lock:
        data_cache["predicted_paths"] = predicted_paths
    
    elapsed_time = time.time() - start_time
    print(f"🎉 Main backend data preloaded in {elapsed_time:.2f} seconds!")
    print(f"📊 Total datasets cached: {len(data_cache)}")
    
    is_initialized = True

# Start preloading in a background thread
preload_thread = threading.Thread(target=preload_all_data, daemon=True)
preload_thread.start()

@app.get("/rmse-zonal-mean")
def get_zonal_mean_rmse(metric: str = Query("rmse", enum=["rmse", "rmse_bias_adjusted", "rmse_anomaly"])):
    if not is_initialized:
        return {"error": "Backend is still initializing. Please wait a moment and try again."}
    
    try:
        start_time = time.time()
        print(f"🔄 Serving cached RMSE data for metric: {metric}")
        
        cache_key = f"rmse_{metric}"
        with cache_lock:
            if cache_key not in data_cache:
                return {"error": f"RMSE data for metric '{metric}' not found in cache"}
            
            result = data_cache[cache_key]
        
        elapsed_time = time.time() - start_time
        print(f"⏱️  RMSE data served in {elapsed_time:.3f} seconds")
        
        return {"zonal_mean_rmse": result}
        
    except Exception as e:
        print(f"❌ Error serving RMSE data for {metric}: {e}")
        return {"error": f"Failed to serve RMSE data: {e}"}

@app.get("/variable")
def get_variable_data(variable: str = Query(...)):
    if variable not in variable_to_zarr_path:
        return {"error": f"Variable '{variable}' not supported."}

    try:
        start_time = time.time()
        print(f"🔄 Loading variable data for: {variable}")
        
        # Load observed data
        obs_ds = xr.open_zarr(variable_to_zarr_path[variable], consolidated=True)
        obs_data = obs_ds[variable].mean(dim=["lat", "lon"])
        obs_time = obs_data["time"].values.astype(str).tolist()
        obs_values = obs_data.values.tolist()

        # Get predicted paths from cache
        with cache_lock:
            predicted_paths = data_cache.get("predicted_paths", {})

        # Load all predicted data models for this variable
        predicted_data = {}
        for pred_path in predicted_paths.get(variable, []):
            model_name = pred_path.split("/")[-1].replace("_rmse_results.zarr", "")
            pred_ds = xr.open_zarr(pred_path, consolidated=True)
            pred_data = pred_ds['rmse']  # adjust if variable name differs
            pred_time = pred_ds['time'].values.astype(str).tolist()
            pred_values = pred_data.values.tolist()
            predicted_data[model_name] = {
                "time": pred_time,
                "values": pred_values,
            }

        elapsed_time = time.time() - start_time
        print(f"⏱️  Variable data loaded in {elapsed_time:.3f} seconds")

        return {
            "time": obs_time,
            variable: obs_values,
            "predicted": predicted_data,
        }

    except Exception as e:
        print(f"❌ Error loading variable data for {variable}: {e}")
        return {"error": f"Failed to load data: {e}"}

@app.get("/health")
def health_check():
    return {
        "status": "healthy" if is_initialized else "initializing",
        "message": "Main backend is running",
        "cached_datasets": len(data_cache),
        "initialized": is_initialized
    }

@app.get("/cache-status")
def cache_status():
    """Get information about cached datasets"""
    with cache_lock:
        return {
            "total_datasets": len(data_cache),
            "rmse_metrics": [k for k in data_cache.keys() if k.startswith("rmse_")],
            "csv_data": [k for k in data_cache.keys() if k.startswith("csv_")],
            "predicted_paths": "predicted_paths" in data_cache,
            "initialized": is_initialized
        }
