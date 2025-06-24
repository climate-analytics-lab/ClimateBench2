from fastapi import FastAPI, Query
from google.cloud import storage
import pandas as pd
from io import StringIO
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # or use ["http://localhost:8001"] if you're using a local server
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# GCS bucket and file path info
BUCKET_NAME = "climatebench"
BLOB_NAME = "results/RMSE/pr/global_mean_rmse_results.csv"

def read_csv_from_gcs(bucket_name: str, blob_name: str) -> pd.DataFrame:
    client = storage.Client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(blob_name)
    data = blob.download_as_text()
    return pd.read_csv(StringIO(data))

@app.get("/rmse-zonal-mean")
def get_zonal_mean_rmse(metric: str = Query("rmse", enum=["rmse", "rmse_bias_adjusted", "rmse_anomaly"])):
    df = read_csv_from_gcs(BUCKET_NAME, BLOB_NAME)
    df_metric = df[df['metric'] == metric]
    zonal_mean = df_metric.groupby('model').agg({
        'historical': 'mean',
        'ssp245': 'mean'
    }).reset_index()
    zonal_mean_sorted = zonal_mean.sort_values('historical')
    return {"zonal_mean_rmse": zonal_mean_sorted.to_dict(orient='records')}
