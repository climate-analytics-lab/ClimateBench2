import os
import subprocess
import csv
from aiohttp import web
import aiohttp_cors

root_dir = os.path.abspath(".")
data_folder = os.path.join(root_dir, "public")

# Serve static files
async def handle(request):
    file_path = os.path.join(root_dir, request.match_info["filename"])
    if not os.path.exists(file_path):
        return web.Response(status=404, text="File not found")
    return web.FileResponse(file_path)

# API endpoint: /api/timeseries-data
async def timeseries_data(request):
    # Get query parameters
    params = request.rel_url.query
    variable = params.get("variable", "tas")
    model = params.get("model")
    region = params.get("region", "global")
    
    # Load model data
    model_csv_path = os.path.join(data_folder, "model_zonal_mean.csv")
    obs_csv_path = os.path.join(data_folder, "observation_zonal_mean.csv")
    
    if not os.path.exists(model_csv_path) or not os.path.exists(obs_csv_path):
        return web.Response(status=404, text="Time series data files not found")

    model_data = []
    obs_data = []
    
    # Read model data
    with open(model_csv_path, newline="") as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            if row["region"] == region and (not model or model == "all" or row["model"] == model):
                try:
                    value = float(row.get(variable, 0)) if row.get(variable) else None
                    if value is not None:
                        model_data.append({
                            "time": row["time"],
                            "model": row["model"],
                            "value": value
                        })
                except (ValueError, TypeError):
                    continue
    
    # Read observation data
    with open(obs_csv_path, newline="") as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            if row["region"] == region:
                try:
                    value = float(row.get(variable, 0)) if row.get(variable) else None
                    if value is not None:
                        obs_data.append({
                            "time": row["time"],
                            "value": value
                        })
                except (ValueError, TypeError):
                    continue

    return web.json_response({
        "model_data": model_data,
        "observation_data": obs_data
    })

    variable = request.match_info.get("variable")  # Gets the variable from the URL path
    csv_path = os.path.join(data_folder, "benchmark_results_time_series.csv")

    if not os.path.exists(csv_path):
        return web.Response(status=404, text="benchmark_results_time_series.csv not found")

    # Get query parameters for region and metric
    params = request.rel_url.query
    region = params.get("region", "global")  # default to global
    metric = params.get("metric", "MAE")  # default to MAE
    model = params.get("model")  # optional model filter

    results = []

    with open(csv_path, newline="") as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            # Filter by variable, metric, and optionally model
            if (row.get("variable") == variable and 
                row.get("metric") == metric and
                (not model or row.get("model") == model)):
                
                try:
                    value = float(row.get(region, 0)) if row.get(region) else None
                    if value is not None:
                        results.append({
                            "timestamp": row.get("time"),
                            "value": str(value),
                            "model": row.get("model"),
                            "region": region,
                            "metric": metric
                        })
                except (ValueError, TypeError):
                    continue

    if not results:
        return web.Response(status=404, text=f"No data found for variable: {variable}")

    return web.json_response(results)

# API endpoint: /api/benchmark-data
async def benchmark_data(request):
    csv_path = os.path.join(data_folder, "benchmark_results.csv")
    if not os.path.exists(csv_path):
        return web.Response(status=404, text="benchmark_results.csv not found")

    # Get query parameters
    params = request.rel_url.query
    model = params.get("model")
    variable = params.get("variable")
    metric = params.get("metric")
    region = params.get("region")

    results = []
    with open(csv_path, newline="") as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            # Skip rows with missing data
            if not row.get("model") or not row.get("Historical (2005-2014)") or not row.get("SSP2-4.5"):
                continue
                
            if model and row["model"] != model:
                continue
            if variable and row["variable"] != variable:
                continue
            if metric and row["metric"] != metric:
                continue
            if region and row["region"] != region:
                continue
                
            try:
                # Validate that the values are numeric
                historical_val = float(row.get("Historical (2005-2014)", 0))
                ssp_val = float(row.get("SSP2-4.5", 0))
                
                results.append({
                    "model": row["model"],
                    "variable": row["variable"],
                    "metric": row["metric"],
                    "region": row["region"],
                    "historical": historical_val,
                    "ssp2_4_5": ssp_val,
                    "change": row.get("Change (hist 2005)"),
                    "percent_change": row.get("Percent Change (hist 2005)")
                })
            except (ValueError, TypeError):
                # Skip rows with invalid numeric data
                continue

    if not results:
        return web.Response(status=404, text="No data found for given parameters")

    return web.json_response({"data": results})

# Setup app and CORS
app = web.Application()
cors = aiohttp_cors.setup(
    app,
    defaults={
        "*": aiohttp_cors.ResourceOptions(
            allow_credentials=True,
            expose_headers="*",
            allow_headers="*",
        )
    },
)

# Static file handler
static_resource = cors.add(app.router.add_resource("/{filename:.*}"))
cors.add(static_resource.add_route("GET", handle))

# API endpoints
timeseries_resource = cors.add(app.router.add_resource("/api/timeseries-data"))
cors.add(timeseries_resource.add_route("GET", timeseries_data))

benchmark_resource = cors.add(app.router.add_resource("/api/benchmark-data"))
cors.add(benchmark_resource.add_route("GET", benchmark_data))

print("✅ Serving on http://localhost:8000")
web.run_app(app, host="localhost", port=8000)
