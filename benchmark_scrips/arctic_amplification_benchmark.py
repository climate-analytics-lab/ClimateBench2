"""Tier I: Arctic amplification (abrupt-4xCO2).

Verifies enhanced Arctic warming under greenhouse forcing.
Arctic (north of 66.5N) must warm at least 1.5x the global mean
in abrupt-4xCO2, driven by sea-ice albedo feedback, lapse-rate
feedback, and increased poleward energy transport.

Usage:
    python arctic_amplification_benchmark.py --model CanESM5
    python arctic_amplification_benchmark.py --model UKESM1-0-LL --n_years 150

References:
    Pithan and Mauritsen, 2014: Arctic amplification dominated by
    temperature feedbacks in contemporary climate models.
    Nature Geoscience, 7, 181-184.
"""

import argparse
import logging
import os
import sys
from csv import writer

import numpy as np
import pandas as pd

from benchmark_utils import DataFinder

sys.path.append("..")

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, force=True)

# Issue spec: Arctic must warm at least 1.5x the global mean
ARCTIC_AMPLIFICATION_THRESHOLD = 1.5
ARCTIC_LAT_MIN = 66.5  # degrees N


def compute_regional_annual_mean(ds, variable, weights, lat_min=None, lat_max=None):
    """Compute area-weighted regional-mean annual-mean time series.

    Args:
        ds: xr.Dataset containing the variable
        variable: variable name string
        weights: cos(lat) weights (full grid)
        lat_min: southern latitude bound (None for global)
        lat_max: northern latitude bound (None for global)

    Returns:
        numpy array of annual-mean regional-mean values
    """
    da = ds[variable]

    # Apply latitude bounds if specified
    if lat_min is not None or lat_max is not None:
        lat = ds["lat"]
        mask = True
        if lat_min is not None:
            mask = mask & (lat >= lat_min)
        if lat_max is not None:
            mask = mask & (lat <= lat_max)
        da = da.where(mask, drop=True)
        w = weights.where(mask, drop=True)
    else:
        w = weights

    regional_mean = da.weighted(w).mean(dim=["lat", "lon"])

    # Annual mean: group every 12 months (robust to non-standard calendars)
    n_months = len(regional_mean)
    n_years = n_months // 12
    regional_mean = regional_mean.isel(time=slice(0, n_years * 12))
    annual_mean = regional_mean.values.reshape(n_years, 12).mean(axis=1)

    return annual_mean


def main(
    model: str,
    n_years: int = 150,
    equilibrium_years: int = 50,
    save_to_cloud: bool = False,
    overwrite: bool = False,
):
    logger.info(
        f"Computing Arctic amplification for {model} "
        f"(years {n_years - equilibrium_years + 1}-{n_years} of abrupt-4xCO2)"
    )

    # --- Load piControl tas (baseline) ---
    logger.info("Loading piControl tas for baseline")
    df = DataFinder(model=model, variable="tas", start_year=1850, end_year=2000)
    pi_ds = df.load_experiment_ds(experiment="piControl", ensemble_mean=True)
    logger.info(f"  piControl tas: {len(pi_ds.time)} time steps loaded")

    # --- Load abrupt-4xCO2 tas ---
    logger.info(f"Loading abrupt-4xCO2 tas (first {n_years} years)")
    a4x_df = DataFinder(model=model, variable="tas", start_year=1850, end_year=2000)
    a4x_ds = a4x_df.load_experiment_ds(
        experiment="abrupt-4xCO2", n_years=n_years, ensemble_mean=True
    )
    ensemble_members = a4x_df.ensemble_members
    logger.info(f"  abrupt-4xCO2 tas: {len(a4x_ds.time)} time steps loaded")

    # cos(lat) weights
    lat = a4x_ds["lat"]
    weights = np.cos(np.deg2rad(lat))

    # --- Compute piControl baselines (global and Arctic) ---
    logger.info("Computing piControl baselines")
    pi_global_annual = compute_regional_annual_mean(pi_ds, "tas", weights)
    pi_arctic_annual = compute_regional_annual_mean(
        pi_ds, "tas", weights, lat_min=ARCTIC_LAT_MIN
    )
    pi_global_mean = pi_global_annual.mean()
    pi_arctic_mean = pi_arctic_annual.mean()
    logger.info(f"  piControl global mean: {pi_global_mean:.2f} K")
    logger.info(f"  piControl Arctic mean: {pi_arctic_mean:.2f} K")

    # --- Compute abrupt-4xCO2 equilibrium response ---
    a4x_global_annual = compute_regional_annual_mean(a4x_ds, "tas", weights)
    a4x_arctic_annual = compute_regional_annual_mean(
        a4x_ds, "tas", weights, lat_min=ARCTIC_LAT_MIN
    )

    equil_start = len(a4x_global_annual) - equilibrium_years
    if equil_start < 0:
        logger.warning(
            f"Only {len(a4x_global_annual)} years available, using all for equilibrium"
        )
        equil_start = 0

    global_warming = a4x_global_annual[equil_start:].mean() - pi_global_mean
    arctic_warming = a4x_arctic_annual[equil_start:].mean() - pi_arctic_mean

    # --- Compute amplification ratio ---
    if global_warming <= 0:
        logger.error(
            f"Global warming is non-positive ({global_warming:.2f} K). "
            "Cannot compute amplification ratio."
        )
        ratio = np.nan
    else:
        ratio = arctic_warming / global_warming

    passes = ratio >= ARCTIC_AMPLIFICATION_THRESHOLD

    logger.info(f"  Global warming: {global_warming:.2f} K")
    logger.info(f"  Arctic warming (>{ARCTIC_LAT_MIN}N): {arctic_warming:.2f} K")
    logger.info(f"  Arctic amplification ratio: {ratio:.3f}")
    logger.info(f"  Pass (ratio >= {ARCTIC_AMPLIFICATION_THRESHOLD}): {passes}")

    # --- Save results ---
    results_dir = "../results/arctic_amplification/"
    results_file = os.path.join(results_dir, "arctic_amplification_results.csv")

    result_df = pd.DataFrame(
        {
            "model": [model],
            "global_warming_K": [round(global_warming, 3)],
            "arctic_warming_K": [round(arctic_warming, 3)],
            "amplification_ratio": [round(ratio, 4)],
            "pass": [passes],
            "n_years": [n_years],
            "equilibrium_years": [equilibrium_years],
            "ensemble_members": [
                "_".join(ensemble_members) if ensemble_members else ""
            ],
        }
    )

    if save_to_cloud:
        from google.cloud import storage as gcs_storage

        storage_client = gcs_storage.Client(project="JCM and Benchmarking")
        bucket = storage_client.bucket("climatebench")
        gcs_path = "results/arctic_amplification/arctic_amplification_results.csv"
        blob = gcs_storage.Blob(bucket=bucket, name=gcs_path)

        if blob.exists(storage_client):
            import io

            existing_data = blob.download_as_text()
            output = io.StringIO(existing_data)
            output.seek(0, io.SEEK_END)
            writer_object = writer(output)
            writer_object.writerow(result_df.values.flatten().tolist())
            output.seek(0)
            blob.upload_from_string(output.getvalue(), content_type="text/csv")
        else:
            result_df.to_csv(f"gs://climatebench/{gcs_path}", index=False)
        logger.info(f"Results saved to cloud: gs://climatebench/{gcs_path}")
    else:
        if overwrite or not os.path.isfile(results_file):
            os.makedirs(results_dir, exist_ok=True)
            result_df.to_csv(results_file, index=False)
        else:
            with open(results_file, "a") as f:
                writer_object = writer(f)
                writer_object.writerow(result_df.values.flatten().tolist())
        logger.info(f"Results saved locally: {results_file}")

    return {
        "global_warming": global_warming,
        "arctic_warming": arctic_warming,
        "ratio": ratio,
        "passes": passes,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Tier I: Arctic amplification (abrupt-4xCO2)"
    )
    parser.add_argument(
        "--model",
        required=True,
        help="CMIP6 model name (e.g., CanESM5, UKESM1-0-LL)",
    )
    parser.add_argument(
        "--n_years",
        default=150,
        type=int,
        help="Total years of abrupt-4xCO2 to load (default: 150)",
    )
    parser.add_argument(
        "--equilibrium_years",
        default=50,
        type=int,
        help="Number of final years to average for equilibrium response (default: 50)",
    )
    parser.add_argument(
        "--save_to_cloud",
        action="store_true",
        default=False,
        help="Save results to Google Cloud Storage",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        default=False,
        help="Overwrite existing results file",
    )
    args = parser.parse_args()

    main(
        model=args.model,
        n_years=args.n_years,
        equilibrium_years=args.equilibrium_years,
        save_to_cloud=args.save_to_cloud,
        overwrite=args.overwrite,
    )
