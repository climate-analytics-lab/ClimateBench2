"""Tier I: Aerosol forcing pass/fail check (hist-aer).

Diagnoses the net aerosol effective radiative forcing (ERF) using the
lambda-corrected end-of-period estimate (Forster et al. 2021, AR6 Ch. 7):

    ERF = delta_N_end - lambda * delta_T_end

where lambda is computed directly from an abrupt-4xCO2 Gregory regression
(N vs delta_T), and delta_N_end / delta_T_end are the end-of-period
global-mean TOA flux and temperature anomalies from hist-aer vs piControl.

Pass/fail criteria (Forster et al. 2021):
    - End-of-period mean tas response is a net cooling (dT_end < 0)
    - ERF is in the range [-2.0, -0.5] W/m^2

Usage:
    python aerosol_forcing_benchmark.py --model CanESM5
    python aerosol_forcing_benchmark.py --model UKESM1-0-LL --end_period_years 30

References:
    Gillett et al., 2016 (DAMIP protocol)
    Forster et al., 2021 (IPCC AR6 WG1, Chapter 7)
    Gregory et al., 2004, doi:10.1029/2003GL018747
"""

import argparse
import logging
import os
import sys

import numpy as np
import pandas as pd

from benchmark_utils import DataFinder

sys.path.append("..")
from utils import compute_weighted_annual_mean, gregory_regression, save_results_csv

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# Pass/fail bounds on net aerosol ERF (W/m^2), from Forster et al. 2021.
ERF_MIN = -2.0
ERF_MAX = -0.5


def main(
    model: str,
    end_period_years: int = 30,
    n_years_ecs: int = 150,
    save_to_cloud: bool = False,
    overwrite: bool = False,
):
    logger.info(
        f"Running aerosol forcing pass/fail (hist-aer) for {model} "
        f"with {end_period_years}-yr end window"
    )

    variables = ["tas", "rsdt", "rsut", "rlut"]

    # --- Load piControl baselines (CMIP) ---
    logger.info("Loading piControl baseline data")
    picontrol_data = {}
    for var in variables:
        df_pi = DataFinder(model=model, variable=var, start_year=1850, end_year=2000)
        try:
            ds = df_pi.load_experiment_ds(experiment="piControl", ensemble_mean=True)
            picontrol_data[var] = ds
            logger.info(
                f"  piControl {var}: {len(ds.time)} months "
                f"({len(ds.time) // 12} years)"
            )
        except Exception as e:
            logger.error(f"  Failed to load piControl {var}: {e}")
            raise

    # --- Load abrupt-4xCO2 for lambda estimation ---
    logger.info(f"Loading abrupt-4xCO2 data ({n_years_ecs} yr) for lambda")
    abrupt4x_data = {}
    for var in variables:
        df_4x = DataFinder(model=model, variable=var, start_year=1850, end_year=2000)
        try:
            ds = df_4x.load_experiment_ds(
                experiment="abrupt-4xCO2", n_years=n_years_ecs, ensemble_mean=True
            )
            abrupt4x_data[var] = ds
            logger.info(
                f"  abrupt-4xCO2 {var}: {len(ds.time)} months "
                f"({len(ds.time) // 12} years)"
            )
        except Exception as e:
            logger.error(f"  Failed to load abrupt-4xCO2 {var}: {e}")
            raise

    # --- Load hist-aer (DAMIP) ---
    logger.info("Loading hist-aer data")
    histaer_data = {}
    ensemble_members = None
    for var in variables:
        df_ha = DataFinder(model=model, variable=var, start_year=1850, end_year=2014)
        try:
            ds = df_ha.load_experiment_ds(
                experiment="hist-aer", ensemble_mean=True, mip="DAMIP"
            )
            histaer_data[var] = ds
            if ensemble_members is None:
                ensemble_members = df_ha.ensemble_members
            logger.info(
                f"  hist-aer {var}: {len(ds.time)} months "
                f"({len(ds.time) // 12} years)"
            )
        except Exception as e:
            logger.error(f"  Failed to load hist-aer {var}: {e}")
            raise

    # --- Area weights (from hist-aer grid) ---
    lat = histaer_data["tas"]["lat"]
    weights = np.cos(np.deg2rad(lat))

    # --- piControl long-term means ---
    def _pi_mean(var):
        return float(
            picontrol_data[var][var]
            .weighted(weights)
            .mean(dim=["lat", "lon"])
            .mean(dim="time")
            .values
        )

    pi_tas_mean = _pi_mean("tas")
    pi_net_flux_mean = _pi_mean("rsdt") - _pi_mean("rsut") - _pi_mean("rlut")
    logger.info(
        f"  piControl baseline: T={pi_tas_mean:.2f} K, "
        f"N={pi_net_flux_mean:.3f} W/m2"
    )

    # --- Lambda from abrupt-4xCO2 Gregory regression ---
    tas_4x = compute_weighted_annual_mean(abrupt4x_data["tas"], "tas", weights)
    rsdt_4x = compute_weighted_annual_mean(abrupt4x_data["rsdt"], "rsdt", weights)
    rsut_4x = compute_weighted_annual_mean(abrupt4x_data["rsut"], "rsut", weights)
    rlut_4x = compute_weighted_annual_mean(abrupt4x_data["rlut"], "rlut", weights)
    n_4x = min(len(tas_4x), len(rsdt_4x), len(rsut_4x), len(rlut_4x))
    delta_t_4x = tas_4x[:n_4x] - pi_tas_mean
    delta_n_4x = (rsdt_4x[:n_4x] - rsut_4x[:n_4x] - rlut_4x[:n_4x]) - pi_net_flux_mean

    greg_4x = gregory_regression(delta_t_4x, delta_n_4x)
    lambda_ecs = greg_4x["lambda_feedback"]   # W/m²/K, negative for a stable climate
    lambda_r2 = greg_4x["r_squared"]
    logger.info(
        f"  abrupt-4xCO2 Gregory: lambda={lambda_ecs:.3f} W/m2/K "
        f"(r²={lambda_r2:.3f}, n={n_4x} yr)"
    )

    # --- hist-aer global-mean annual-mean series ---
    tas_annual = compute_weighted_annual_mean(histaer_data["tas"], "tas", weights)
    rsdt_annual = compute_weighted_annual_mean(histaer_data["rsdt"], "rsdt", weights)
    rsut_annual = compute_weighted_annual_mean(histaer_data["rsut"], "rsut", weights)
    rlut_annual = compute_weighted_annual_mean(histaer_data["rlut"], "rlut", weights)

    n_common = min(len(tas_annual), len(rsdt_annual), len(rsut_annual), len(rlut_annual))
    delta_t = tas_annual[:n_common] - pi_tas_mean
    delta_n = (rsdt_annual[:n_common] - rsut_annual[:n_common] - rlut_annual[:n_common]) - pi_net_flux_mean

    n_years_picontrol = min(len(picontrol_data[v].time) // 12 for v in variables)
    logger.info(
        f"  hist-aer years used: {n_common}; piControl years available: "
        f"{n_years_picontrol}"
    )

    # --- End-of-period mean response ---
    end_window = min(end_period_years, n_common)
    if end_window < end_period_years:
        logger.warning(
            "Requested end window (%d yr) exceeds available record (%d yr); "
            "using full record",
            end_period_years,
            n_common,
        )
    delta_t_end = float(delta_t[-end_window:].mean())
    delta_n_end = float(delta_n[-end_window:].mean())
    logger.info(
        f"  End-of-period ({end_window} yr) mean: dT={delta_t_end:.3f} K, "
        f"dN={delta_n_end:.3f} W/m2"
    )

    # --- Lambda-corrected ERF (Forster et al. 2021) ---
    erf = delta_n_end - lambda_ecs * delta_t_end
    logger.info(f"  Lambda-corrected ERF: {erf:.3f} W/m2")

    # --- Pass/fail ---
    pass_cooling = bool(delta_t_end < 0)
    pass_erf_range = bool(ERF_MIN <= erf <= ERF_MAX)
    passes = pass_cooling and pass_erf_range
    logger.info(
        f"  pass_cooling={pass_cooling}, pass_erf_range={pass_erf_range} "
        f"({ERF_MIN}..{ERF_MAX} W/m2), overall passes={passes}"
    )

    # --- Save results ---
    results_dir = "../results/aerosol_forcing/"
    results_file = os.path.join(results_dir, "aerosol_forcing_results.csv")

    result_df = pd.DataFrame(
        {
            "model": [model],
            "delta_T_end_K": [round(delta_t_end, 4)],
            "delta_N_end_Wm2": [round(delta_n_end, 4)],
            "lambda_abrupt4x_Wm2K": [round(lambda_ecs, 4)],
            "lambda_r2": [round(lambda_r2, 4)],
            "erf_lambda_corrected_Wm2": [round(erf, 4)],
            "pass_cooling": [pass_cooling],
            "pass_erf_range": [pass_erf_range],
            "passes": [passes],
            "n_years_hist_aer": [n_common],
            "end_window_years": [end_window],
            "n_years_ecs": [n_4x],
            "n_years_picontrol": [n_years_picontrol],
            "ensemble_members": [
                "_".join(ensemble_members) if ensemble_members else ""
            ],
        }
    )

    save_results_csv(result_df, results_file, save_to_cloud, overwrite)

    return {
        "delta_T_end_K": delta_t_end,
        "delta_N_end_Wm2": delta_n_end,
        "lambda_abrupt4x_Wm2K": lambda_ecs,
        "erf_lambda_corrected_Wm2": erf,
        "pass_cooling": pass_cooling,
        "pass_erf_range": pass_erf_range,
        "passes": passes,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Tier I: Aerosol forcing pass/fail check (hist-aer)"
    )
    parser.add_argument(
        "--model",
        required=True,
        help="CMIP6 model name (e.g., CanESM5, UKESM1-0-LL)",
    )
    parser.add_argument(
        "--end_period_years",
        default=30,
        type=int,
        help="Length of end-of-period averaging window in years (default: 30)",
    )
    parser.add_argument(
        "--n_years_ecs",
        default=150,
        type=int,
        help="Years of abrupt-4xCO2 to use for lambda regression (default: 150)",
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
        end_period_years=args.end_period_years,
        n_years_ecs=args.n_years_ecs,
        save_to_cloud=args.save_to_cloud,
        overwrite=args.overwrite,
    )
