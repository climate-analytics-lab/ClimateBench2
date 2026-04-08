"""Tier I: ECS diagnosis via Gregory regression (metadata).

Diagnoses Equilibrium Climate Sensitivity from abrupt-4xCO2 using
Gregory regression (TOA net flux vs global-mean surface temperature).

ECS = -F_2x / lambda, where F_2x = F_4x / 2

Usage:
    python ecs_benchmark.py --model CanESM5
    python ecs_benchmark.py --model CanESM5 --n_years 150

References:
    Gregory et al., 2004: A new method for diagnosing radiative forcing
    and climate sensitivity. Geophys. Res. Lett., 31, L03205.
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

from utils import compute_weighted_annual_mean, save_results_csv

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, force=True)


def gregory_regression(delta_t, net_flux):
    """Perform Gregory regression: N = F_4x + lambda * delta_T.

    At equilibrium (N=0): ECS = -F_2x / lambda = -F_4x / (2 * lambda)

    Args:
        delta_t: annual-mean global-mean surface temperature anomaly (K)
        net_flux: annual-mean global-mean TOA net downward flux anomaly (W/m2)

    Returns:
        dict with ecs, lambda_feedback, f4x, f2x, r_squared, p_value, slope_std_err
    """
    slope, intercept, r_value, p_value, std_err = stats.linregress(delta_t, net_flux)

    f4x = intercept  # 4xCO2 forcing (W/m2)
    lambda_feedback = slope  # feedback parameter (W/m2/K), should be negative
    f2x = f4x / 2  # 2xCO2 forcing (approximate)

    # ECS for 2xCO2: at equilibrium N=0, so 0 = F_2x + lambda*ECS
    ecs = -f2x / lambda_feedback if lambda_feedback != 0 else np.nan

    return {
        "ecs": ecs,
        "lambda_feedback": lambda_feedback,
        "f4x": f4x,
        "f2x": f2x,
        "r_squared": r_value**2,
        "p_value": p_value,
        "slope_std_err": std_err,
    }


def main(
    model: str,
    n_years: int = 150,
    save_to_cloud: bool = False,
    overwrite: bool = False,
):
    logger.info(f"Computing ECS via Gregory regression for {model} ({n_years} years)")

    # Variables needed: tas, rsdt (incoming SW), rsut (outgoing SW), rlut (outgoing LW)
    # Net TOA flux N = rsdt - rsut - rlut (positive downward)
    variables = ["tas", "rsdt", "rsut", "rlut"]

    # --- Load piControl data (for baseline climatology) ---
    logger.info("Loading piControl data for baseline")
    picontrol_data = {}
    for var in variables:
        # start_year/end_year don't matter here since we use load_experiment_ds directly
        df = DataFinder(model=model, variable=var, start_year=1850, end_year=2000)
        try:
            ds = df.load_experiment_ds(experiment="piControl", ensemble_mean=True)
            picontrol_data[var] = ds
            logger.info(f"  piControl {var}: {len(ds.time)} time steps loaded")
        except Exception as e:
            logger.error(f"  Failed to load piControl {var}: {e}")
            raise

    # --- Load abrupt-4xCO2 data (first n_years) ---
    logger.info(f"Loading abrupt-4xCO2 data (first {n_years} years)")
    abrupt4x_data = {}
    ensemble_members = None
    for var in variables:
        df = DataFinder(model=model, variable=var, start_year=1850, end_year=2000)
        try:
            ds = df.load_experiment_ds(
                experiment="abrupt-4xCO2", n_years=n_years, ensemble_mean=True
            )
            abrupt4x_data[var] = ds
            if ensemble_members is None:
                ensemble_members = df.ensemble_members
            logger.info(f"  abrupt-4xCO2 {var}: {len(ds.time)} time steps loaded")
        except Exception as e:
            logger.error(f"  Failed to load abrupt-4xCO2 {var}: {e}")
            raise

    # --- Compute global-mean annual-mean values ---
    logger.info("Computing global-mean annual-mean values")

    # cos(lat) weights for area weighting
    lat = abrupt4x_data["tas"]["lat"]
    weights = np.cos(np.deg2rad(lat))

    # piControl baselines (long-term mean)
    pi_tas_mean = float(
        picontrol_data["tas"]["tas"]
        .weighted(weights)
        .mean(dim=["lat", "lon"])
        .mean(dim="time")
        .values
    )
    pi_rsdt_mean = float(
        picontrol_data["rsdt"]["rsdt"]
        .weighted(weights)
        .mean(dim=["lat", "lon"])
        .mean(dim="time")
        .values
    )
    pi_rsut_mean = float(
        picontrol_data["rsut"]["rsut"]
        .weighted(weights)
        .mean(dim=["lat", "lon"])
        .mean(dim="time")
        .values
    )
    pi_rlut_mean = float(
        picontrol_data["rlut"]["rlut"]
        .weighted(weights)
        .mean(dim=["lat", "lon"])
        .mean(dim="time")
        .values
    )
    pi_net_flux_mean = pi_rsdt_mean - pi_rsut_mean - pi_rlut_mean

    logger.info(
        f"  piControl baseline: T={pi_tas_mean:.2f} K, N={pi_net_flux_mean:.2f} W/m2"
    )

    # abrupt-4xCO2 annual means
    tas_annual = compute_weighted_annual_mean(abrupt4x_data["tas"], "tas", weights)
    rsdt_annual = compute_weighted_annual_mean(abrupt4x_data["rsdt"], "rsdt", weights)
    rsut_annual = compute_weighted_annual_mean(abrupt4x_data["rsut"], "rsut", weights)
    rlut_annual = compute_weighted_annual_mean(abrupt4x_data["rlut"], "rlut", weights)

    # Anomalies relative to piControl
    delta_t = tas_annual - pi_tas_mean
    net_flux = (rsdt_annual - rsut_annual - rlut_annual) - pi_net_flux_mean

    # --- Perform Gregory regression ---
    logger.info("Performing Gregory regression")
    results = gregory_regression(delta_t, net_flux)

    logger.info(f"  ECS = {results['ecs']:.2f} K")
    logger.info(f"  lambda = {results['lambda_feedback']:.3f} W/m2/K")
    logger.info(f"  F_4x = {results['f4x']:.2f} W/m2")
    logger.info(f"  F_2x = {results['f2x']:.2f} W/m2")
    logger.info(f"  R^2 = {results['r_squared']:.4f}")

    # --- Save results ---
    results_dir = "../results/ecs/"
    results_file = os.path.join(results_dir, "ecs_results.csv")

    result_df = pd.DataFrame(
        {
            "model": [model],
            "ecs_K": [round(results["ecs"], 3)],
            "lambda_Wm2K": [round(results["lambda_feedback"], 4)],
            "f4x_Wm2": [round(results["f4x"], 3)],
            "f2x_Wm2": [round(results["f2x"], 3)],
            "r_squared": [round(results["r_squared"], 4)],
            "n_years": [n_years],
            "ensemble_members": [
                "_".join(ensemble_members) if ensemble_members else ""
            ],
        }
    )

    save_results_csv(result_df, results_file, save_to_cloud, overwrite)

    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Tier I: ECS diagnosis via Gregory regression (abrupt-4xCO2)"
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
        help="Number of years from abrupt-4xCO2 start to use (default: 150)",
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
        save_to_cloud=args.save_to_cloud,
        overwrite=args.overwrite,
    )
