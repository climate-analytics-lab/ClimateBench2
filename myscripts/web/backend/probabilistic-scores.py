from fastapi import FastAPI, Query
import xarray as xr
from fastapi.middleware.cors import CORSMiddleware

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

# Initialize the Cloud Storage client
client = storage.Client()
bucket_name = "climatebench"

# Dictionary to hold predicted paths grouped by variable (e.g., "pr", "tas")
predicted_paths = defaultdict(list)

# Marker to identify the specific folder name of interest
marker = "spatial_-90_90_rmse_results.zarr"

# List and process all blobs in the bucket
for blob in client.list_blobs(bucket_name):
    blob_name = blob.name
    if marker in blob_name:
        # Truncate the blob name to only include up to the marker
        idx = blob_name.find(marker)
        truncated_path = blob_name[: idx + len(marker)]

        # Extract the variable key from the path (e.g., "pr" in results/RMSE/pr/...)
        parts = truncated_path.split('/')
        if len(parts) > 3 and parts[0] == "results" and parts[1] == "RMSE":
            variable = parts[2]
            full_gs_path = f"gs://{bucket_name}/{truncated_path}"

            # Avoid duplicates
            if full_gs_path not in predicted_paths[variable]:
                predicted_paths[variable].append(full_gs_path)

predicted_paths = dict(predicted_paths)


@app.get("/variable")
def get_variable_data(variable: str = Query(...)):
    if variable not in variable_to_zarr_path:
        return {"error": f"Variable '{variable}' not supported."}

    try:
        # Load observed data
        obs_ds = xr.open_zarr(variable_to_zarr_path[variable], consolidated=True)
        obs_data = obs_ds[variable].mean(dim=["lat", "lon"])
        obs_time = obs_data["time"].values.astype(str).tolist()
        obs_values = obs_data.values.tolist()

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

        return {
            "time": obs_time,
            variable: obs_values,
            "predicted": predicted_data,
        }

    except Exception as e:
        return {"error": f"Failed to load data: {e}"}
