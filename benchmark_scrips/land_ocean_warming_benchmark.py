"""Tier I: Land-ocean warming contrast (abrupt-4xCO2).

Verifies that land warms faster than ocean under greenhouse forcing.
Diagnoses the land-ocean warming ratio from the equilibrium response
in abrupt-4xCO2 relative to piControl baseline.

Expected ratio > 1, approximately 1.2-1.6.

Usage:
    python land_ocean_warming_benchmark.py --model CanESM5
    python land_ocean_warming_benchmark.py --model UKESM1-0-LL --n_years 150

References:
    Sutton et al., 2007; Joshi et al., 2008
"""

import argparse
import logging
import os
import sys
from csv import writer

import numpy as np
import pandas as pd
import xarray as xr

from benchmark_utils import DataFinder

sys.path.append("..")
from utils import standardize_dims

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


def load_land_fraction(data_finder):
    """Load sftlf (land area fraction, 0-100%) from CMIP6 fx table.

    Uses the same cascading source logic as DataFinder (local -> GCS -> ESGF).

    Args:
        data_finder: a DataFinder instance (for model name, grid, ensemble info)

    Returns:
        xr.DataArray of land fraction (0-100), or None if unavailable.
    """
    if data_finder.ensemble_members is None:
        data_finder.find_ensemble_members(experiment="historical")
    try:
        sftlf_ds = data_finder.read_data(
            mip="CMIP",
            experiment="historical",
            ensemble=data_finder.ensemble_members[0],
            frequency_table="fx",
            variable="sftlf",
        )
        sftlf = standardize_dims(sftlf_ds)["sftlf"]
        logger.info(f"  sftlf loaded: land fraction range [{float(sftlf.min()):.1f}, {float(sftlf.max()):.1f}]")
        return sftlf
    except Exception as e:
        logger.warning(f"  Could not load sftlf: {e}")
        return None


def compute_domain_annual_mean(tas_ds, cos_weights, land_frac, domain):
    """Compute area-weighted annual-mean temperature for land or ocean.

    Args:
        tas_ds: xr.Dataset with 'tas' variable
        cos_weights: cos(lat) weights
        land_frac: sftlf DataArray (0-100)
        domain: "land" or "ocean"

    Returns:
        numpy array of annual-mean domain-mean temperature
    """
    if domain == "land":
        domain_weights = cos_weights * (land_frac / 100.0)
    else:
        domain_weights = cos_weights * (1.0 - land_frac / 100.0)

    # Mask out cells with zero weight
    domain_weights = domain_weights.where(domain_weights > 0)

    da = tas_ds["tas"]
    domain_mean = da.weighted(domain_weights.fillna(0)).mean(dim=["lat", "lon"])

    # Annual mean: group every 12 months
    n_months = len(domain_mean)
    n_years = n_months // 12
    domain_mean = domain_mean.isel(time=slice(0, n_years * 12))
    annual_mean = domain_mean.values.reshape(n_years, 12).mean(axis=1)

    return annual_mean


def main(
    model: str,
    n_years: int = 150,
    equilibrium_years: int = 50,
    save_to_cloud: bool = False,
    overwrite: bool = False,
):
    logger.info(
        f"Computing land-ocean warming contrast for {model} "
        f"(years {n_years - equilibrium_years + 1}-{n_years} of abrupt-4xCO2)"
    )

    # --- Load land fraction mask ---
    logger.info("Loading land fraction (sftlf)")
    df = DataFinder(model=model, variable="tas", start_year=1850, end_year=2000)
    land_frac = load_land_fraction(df)
    if land_frac is None:
        raise RuntimeError(
            f"sftlf not available for {model}. Cannot compute land-ocean warming ratio."
        )

    # --- Load piControl tas (baseline) ---
    logger.info("Loading piControl tas for baseline")
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

    # --- Align land fraction grid to model grid ---
    # sftlf may have slightly different coordinates; align to tas grid
    land_frac = land_frac.reindex_like(a4x_ds, method="nearest")

    # cos(lat) weights
    lat = a4x_ds["lat"]
    cos_weights = np.cos(np.deg2rad(lat))

    # --- Compute piControl baselines ---
    logger.info("Computing piControl baselines (land and ocean)")
    pi_land_annual = compute_domain_annual_mean(pi_ds, cos_weights, land_frac, "land")
    pi_ocean_annual = compute_domain_annual_mean(pi_ds, cos_weights, land_frac, "ocean")
    pi_land_mean = pi_land_annual.mean()
    pi_ocean_mean = pi_ocean_annual.mean()
    logger.info(f"  piControl land mean: {pi_land_mean:.2f} K")
    logger.info(f"  piControl ocean mean: {pi_ocean_mean:.2f} K")

    # --- Compute abrupt-4xCO2 equilibrium response ---
    # Use the last `equilibrium_years` years as the equilibrium period
    a4x_land_annual = compute_domain_annual_mean(a4x_ds, cos_weights, land_frac, "land")
    a4x_ocean_annual = compute_domain_annual_mean(
        a4x_ds, cos_weights, land_frac, "ocean"
    )

    equil_start = len(a4x_land_annual) - equilibrium_years
    if equil_start < 0:
        logger.warning(
            f"Only {len(a4x_land_annual)} years available, using all for equilibrium"
        )
        equil_start = 0

    land_warming = a4x_land_annual[equil_start:].mean() - pi_land_mean
    ocean_warming = a4x_ocean_annual[equil_start:].mean() - pi_ocean_mean

    # --- Compute ratio ---
    if ocean_warming <= 0:
        logger.error(f"Ocean warming is non-positive ({ocean_warming:.2f} K). Cannot compute ratio.")
        ratio = np.nan
    else:
        ratio = land_warming / ocean_warming

    # Pass/fail: ratio must be > 1, expected 1.2-1.6
    in_expected_range = 1.2 <= ratio <= 1.6
    passes = ratio > 1.0

    logger.info(f"  Land warming: {land_warming:.2f} K")
    logger.info(f"  Ocean warming: {ocean_warming:.2f} K")
    logger.info(f"  Land/Ocean ratio: {ratio:.3f}")
    logger.info(f"  Pass (ratio > 1): {passes}")
    logger.info(f"  In expected range [1.2, 1.6]: {in_expected_range}")

    # --- Save results ---
    results_dir = "../results/land_ocean_warming/"
    results_file = os.path.join(results_dir, "land_ocean_warming_results.csv")

    result_df = pd.DataFrame(
        {
            "model": [model],
            "land_warming_K": [round(land_warming, 3)],
            "ocean_warming_K": [round(ocean_warming, 3)],
            "ratio": [round(ratio, 4)],
            "pass": [passes],
            "in_expected_range": [in_expected_range],
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
        gcs_path = "results/land_ocean_warming/land_ocean_warming_results.csv"
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
        "land_warming": land_warming,
        "ocean_warming": ocean_warming,
        "ratio": ratio,
        "passes": passes,
        "in_expected_range": in_expected_range,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Tier I: Land-ocean warming contrast (abrupt-4xCO2)"
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
