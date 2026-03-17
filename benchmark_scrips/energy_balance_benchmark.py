"""Tier I: Energy balance closure test (piControl).

Assesses stability of the simulated climate by checking that TOA net
radiative flux drift in piControl is within 0.1 W/m2/decade.

Also reports the long-term mean TOA imbalance and checks individual
flux components against observational bounds from ICONEval/CERES-EBAF.

Usage:
    python energy_balance_benchmark.py --model CanESM5
    python energy_balance_benchmark.py --model UKESM1-0-LL --min_years 100

References:
    ICONEval recipe_sanity_checks.yml (observational bounds)
    Protocol Tier I - Energy balance
"""

import argparse
import logging
import os
import sys
from csv import writer

import numpy as np
import pandas as pd
import yaml
from scipy import stats

from benchmark_utils import DataFinder

sys.path.append("..")

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# Drift threshold from issue spec
DRIFT_THRESHOLD = 0.1  # W/m2/decade


def load_reference_bounds():
    """Load observational reference bounds from reference_bounds.yaml.

    Returns:
        dict of variable bounds, or empty dict if file not found.
    """
    bounds_path = os.path.join(os.path.dirname(__file__), "..", "reference_bounds.yaml")
    if os.path.exists(bounds_path):
        with open(bounds_path) as f:
            return yaml.safe_load(f)
    else:
        logger.warning("reference_bounds.yaml not found, skipping bounds checks")
        return {}


def compute_global_annual_mean(ds, variable, weights):
    """Compute area-weighted global-mean annual-mean time series.

    Args:
        ds: xr.Dataset containing the variable
        variable: variable name string
        weights: cos(lat) weights

    Returns:
        numpy array of annual-mean global-mean values
    """
    da = ds[variable]
    global_mean = da.weighted(weights).mean(dim=["lat", "lon"])

    n_months = len(global_mean)
    n_years = n_months // 12
    global_mean = global_mean.isel(time=slice(0, n_years * 12))
    annual_mean = global_mean.values.reshape(n_years, 12).mean(axis=1)

    return annual_mean


def compute_drift(annual_values):
    """Compute linear drift in W/m2/decade from annual-mean time series.

    Args:
        annual_values: numpy array of annual-mean values

    Returns:
        dict with drift_per_decade, intercept, r_squared, p_value
    """
    years = np.arange(len(annual_values))
    slope, intercept, r_value, p_value, std_err = stats.linregress(
        years, annual_values
    )

    return {
        "drift_per_decade": slope * 10,  # per year -> per decade
        "intercept": intercept,
        "r_squared": r_value**2,
        "p_value": p_value,
        "std_err_per_decade": std_err * 10,
    }


def main(
    model: str,
    min_years: int = 100,
    save_to_cloud: bool = False,
    overwrite: bool = False,
):
    logger.info(f"Running energy balance closure test for {model} (piControl)")

    # --- Load reference bounds ---
    bounds = load_reference_bounds()

    # --- Load piControl data for rsdt, rsut, rlut ---
    variables = ["rsdt", "rsut", "rlut"]
    picontrol_data = {}

    for var in variables:
        df = DataFinder(model=model, variable=var, start_year=1850, end_year=2000)
        try:
            ds = df.load_experiment_ds(experiment="piControl", ensemble_mean=True)
            picontrol_data[var] = ds
            n_months = len(ds.time)
            logger.info(
                f"  piControl {var}: {n_months} months ({n_months // 12} years)"
            )
        except Exception as e:
            logger.error(f"  Failed to load piControl {var}: {e}")
            raise

    # Check we have enough data
    n_years_available = min(
        len(picontrol_data[v].time) // 12 for v in variables
    )
    if n_years_available < min_years:
        logger.warning(
            f"Only {n_years_available} years available, "
            f"less than requested minimum of {min_years}"
        )

    # --- Compute annual-mean global-mean fluxes ---
    lat = picontrol_data["rsdt"]["lat"]
    weights = np.cos(np.deg2rad(lat))

    rsdt_annual = compute_global_annual_mean(picontrol_data["rsdt"], "rsdt", weights)
    rsut_annual = compute_global_annual_mean(picontrol_data["rsut"], "rsut", weights)
    rlut_annual = compute_global_annual_mean(picontrol_data["rlut"], "rlut", weights)

    # Trim to common length
    n_common = min(len(rsdt_annual), len(rsut_annual), len(rlut_annual))
    rsdt_annual = rsdt_annual[:n_common]
    rsut_annual = rsut_annual[:n_common]
    rlut_annual = rlut_annual[:n_common]

    # TOA net downward flux: N = rsdt - rsut - rlut
    toa_net = rsdt_annual - rsut_annual - rlut_annual

    logger.info(f"  Using {n_common} years of piControl data")

    # --- Compute drift ---
    drift_results = compute_drift(toa_net)
    drift = drift_results["drift_per_decade"]
    passes = abs(drift) < DRIFT_THRESHOLD

    # --- Long-term mean imbalance ---
    mean_imbalance = float(toa_net.mean())
    mean_rsut = float(rsut_annual.mean())
    mean_rlut = float(rlut_annual.mean())

    logger.info(f"  TOA net flux drift: {drift:.4f} W/m2/decade")
    logger.info(f"  TOA net flux mean imbalance: {mean_imbalance:.3f} W/m2")
    logger.info(f"  Pass (|drift| < {DRIFT_THRESHOLD}): {passes}")
    logger.info(f"  Mean rsut: {mean_rsut:.2f} W/m2")
    logger.info(f"  Mean rlut: {mean_rlut:.2f} W/m2")

    # --- Check against ICONEval observational bounds ---
    bounds_checks = {}
    for var, mean_val in [("rsut", mean_rsut), ("rlut", mean_rlut)]:
        if var in bounds and "global_mean" in bounds[var]:
            lo, hi = bounds[var]["global_mean"]
            in_range = lo <= mean_val <= hi
            bounds_checks[var] = in_range
            status = "OK" if in_range else "OUTSIDE"
            logger.info(
                f"  {var} bounds check [{lo}, {hi}] W/m2: "
                f"{mean_val:.2f} -> {status}"
            )

    # --- Save results ---
    results_dir = "../results/energy_balance/"
    results_file = os.path.join(results_dir, "energy_balance_results.csv")

    ensemble_members = df.ensemble_members
    result_df = pd.DataFrame(
        {
            "model": [model],
            "toa_drift_Wm2_decade": [round(drift, 6)],
            "toa_drift_std_err": [round(drift_results["std_err_per_decade"], 6)],
            "toa_mean_imbalance_Wm2": [round(mean_imbalance, 4)],
            "mean_rsut_Wm2": [round(mean_rsut, 2)],
            "mean_rlut_Wm2": [round(mean_rlut, 2)],
            "pass_drift": [passes],
            "rsut_in_bounds": [bounds_checks.get("rsut", "")],
            "rlut_in_bounds": [bounds_checks.get("rlut", "")],
            "n_years": [n_common],
            "r_squared": [round(drift_results["r_squared"], 6)],
            "ensemble_members": [
                "_".join(ensemble_members) if ensemble_members else ""
            ],
        }
    )

    if save_to_cloud:
        from google.cloud import storage as gcs_storage

        storage_client = gcs_storage.Client(project="JCM and Benchmarking")
        bucket = storage_client.bucket("climatebench")
        gcs_path = "results/energy_balance/energy_balance_results.csv"
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
        "drift_per_decade": drift,
        "mean_imbalance": mean_imbalance,
        "passes": passes,
        "bounds_checks": bounds_checks,
        "n_years": n_common,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Tier I: Energy balance closure test (piControl)"
    )
    parser.add_argument(
        "--model",
        required=True,
        help="CMIP6 model name (e.g., CanESM5, UKESM1-0-LL)",
    )
    parser.add_argument(
        "--min_years",
        default=100,
        type=int,
        help="Minimum years of piControl required (default: 100, spec: 500)",
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
        min_years=args.min_years,
        save_to_cloud=args.save_to_cloud,
        overwrite=args.overwrite,
    )
