from tkinter.font import names
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import pandas as pd
import xarray as xr
import json

app = FastAPI()

# Allow CORS from any origin (for testing/dev only)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  
    allow_methods=["*"],
    allow_headers=["*"],
)

# Load JSON data once when app starts
with open("assets/data/ssp245.json", "r") as file:
    data = json.load(file)

@app.get("/models")
def get_models():
    # Return unique model names
    models = list({item.get("model") for item in data if item.get("model") is not None})
    models.sort(key=str.lower)
    return models

