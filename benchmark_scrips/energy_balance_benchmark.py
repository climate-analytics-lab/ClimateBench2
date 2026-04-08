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

import numpy as np
import pandas as pd
from scipy import stats

from benchmark_utils import DataFinder

sys.path.append("..")

from constants import REFERENCE_BOUNDS
from utils import compute_weighted_annual_mean, save_results_csv

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, force=True)

# Drift threshold from issue spec
DRIFT_THRESHOLD = 0.1  # W/m2/decade


def compute_drift(annual_values):
    """Compute linear drift in W/m2/decade from annual-mean time series.

    Args:
        annual_values: numpy array of annual-mean values

    Returns:
        dict with drift_per_decade, intercept, r_squared, p_value
    """
    years = np.arange(len(annual_values))
    slope, intercept, r_value, p_value, std_err = stats.linregress(years, annual_values)

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
    bounds = REFERENCE_BOUNDS

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
    n_years_available = min(len(picontrol_data[v].time) // 12 for v in variables)
    if n_years_available < min_years:
        logger.warning(
            f"Only {n_years_available} years available, "
            f"less than requested minimum of {min_years}"
        )

    # --- Compute annual-mean global-mean fluxes ---
    lat = picontrol_data["rsdt"]["lat"]
    weights = np.cos(np.deg2rad(lat))

    rsdt_annual = compute_weighted_annual_mean(picontrol_data["rsdt"], "rsdt", weights)
    rsut_annual = compute_weighted_annual_mean(picontrol_data["rsut"], "rsut", weights)
    rlut_annual = compute_weighted_annual_mean(picontrol_data["rlut"], "rlut", weights)

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

    save_results_csv(result_df, results_file, save_to_cloud, overwrite)

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
