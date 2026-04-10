"""Tier I: Aerosol forcing pass/fail check (hist-aer).

Diagnoses the net aerosol effective radiative forcing (ERF) and the
global-mean surface temperature response from the DAMIP ``hist-aer``
simulation. Two ERF estimates are reported:

1. Gregory-style intercept of regressing global-mean TOA net flux
   anomaly on global-mean surface temperature anomaly across the full
   hist-aer record. Self-contained but noisy.
2. Lambda-corrected end-of-period estimate
   ``ERF = N_end - lambda_ecs * dT_end`` where ``lambda_ecs`` is read
   from ``results/ecs/ecs_results.csv`` if available. This is the
   approach used in Forster et al. (2021, AR6 Ch. 7).

Pass/fail criteria (from issue spec):
    - End-of-period mean tas response is a net cooling (dT_end < 0)
    - Reported ERF (lambda-corrected if available, else Gregory) is in
      the range [-2.0, -0.5] W/m^2

Usage:
    python aerosol_forcing_benchmark.py --model CanESM5
    python aerosol_forcing_benchmark.py --model UKESM1-0-LL --end_period_years 30

References:
    Gillett et al., 2016 (DAMIP protocol)
    Forster et al., 2021 (IPCC AR6 WG1, Chapter 7)
"""

import argparse
import logging
import os
import sys
from csv import writer

import numpy as np
import pandas as pd
from scipy import stats

from benchmark_utils import DataFinder

sys.path.append("..")

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# Pass/fail bounds on net aerosol ERF (W/m^2), from Forster et al. 2021.
ERF_MIN = -2.0
ERF_MAX = -0.5


def compute_global_annual_mean(ds, variable, weights):
    """Area-weighted global-mean annual-mean time series.

    Args:
        ds: xr.Dataset containing the variable.
        variable: variable name string.
        weights: cos(lat) weights.

    Returns:
        numpy array of annual-mean global-mean values.
    """
    da = ds[variable]
    global_mean = da.weighted(weights).mean(dim=["lat", "lon"])

    n_months = len(global_mean)
    n_years = n_months // 12
    global_mean = global_mean.isel(time=slice(0, n_years * 12))
    annual_mean = global_mean.values.reshape(n_years, 12).mean(axis=1)

    return annual_mean


def gregory_erf_estimate(delta_t, delta_n):
    """Estimate aerosol ERF as the intercept of N = ERF + lambda * T.

    Args:
        delta_t: annual-mean global-mean tas anomaly (K) vs piControl.
        delta_n: annual-mean global-mean TOA net flux anomaly (W/m^2)
            vs piControl.

    Returns:
        dict with erf, lambda_feedback, r_squared, p_value, intercept_std_err.
    """
    slope, intercept, r_value, p_value, std_err = stats.linregress(delta_t, delta_n)
    return {
        "erf": intercept,
        "lambda_feedback": slope,
        "r_squared": r_value**2,
        "p_value": p_value,
        "slope_std_err": std_err,
    }


def read_lambda_from_ecs_results(model: str):
    """Best-effort lookup of lambda for this model from ecs_results.csv.

    Returns lambda (W/m^2/K, negative for stable climate) or None if the
    file or row is not present.
    """
    ecs_path = os.path.join(
        os.path.dirname(__file__), "..", "results", "ecs", "ecs_results.csv"
    )
    if not os.path.isfile(ecs_path):
        logger.warning(
            "ecs_results.csv not found at %s; skipping lambda-corrected ERF",
            ecs_path,
        )
        return None
    try:
        df = pd.read_csv(ecs_path)
    except Exception as e:
        logger.warning("Could not read ecs_results.csv (%s); skipping", e)
        return None
    rows = df[df["model"] == model]
    if rows.empty:
        logger.warning(
            "No ECS row found for model %s; skipping lambda-corrected ERF", model
        )
        return None
    # Use the most recent row if duplicates exist
    return float(rows.iloc[-1]["lambda_Wm2K"])


def main(
    model: str,
    end_period_years: int = 30,
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

    # --- Area weights ---
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
    pi_rsdt_mean = _pi_mean("rsdt")
    pi_rsut_mean = _pi_mean("rsut")
    pi_rlut_mean = _pi_mean("rlut")
    pi_net_flux_mean = pi_rsdt_mean - pi_rsut_mean - pi_rlut_mean
    logger.info(
        f"  piControl baseline: T={pi_tas_mean:.2f} K, "
        f"N={pi_net_flux_mean:.3f} W/m2"
    )

    # --- hist-aer global-mean annual-mean series ---
    tas_annual = compute_global_annual_mean(histaer_data["tas"], "tas", weights)
    rsdt_annual = compute_global_annual_mean(histaer_data["rsdt"], "rsdt", weights)
    rsut_annual = compute_global_annual_mean(histaer_data["rsut"], "rsut", weights)
    rlut_annual = compute_global_annual_mean(histaer_data["rlut"], "rlut", weights)

    n_common = min(
        len(tas_annual), len(rsdt_annual), len(rsut_annual), len(rlut_annual)
    )
    tas_annual = tas_annual[:n_common]
    rsdt_annual = rsdt_annual[:n_common]
    rsut_annual = rsut_annual[:n_common]
    rlut_annual = rlut_annual[:n_common]

    delta_t = tas_annual - pi_tas_mean
    delta_n = (rsdt_annual - rsut_annual - rlut_annual) - pi_net_flux_mean

    n_years_picontrol = min(len(picontrol_data[v].time) // 12 for v in variables)
    logger.info(
        f"  hist-aer years used: {n_common}; piControl years available: "
        f"{n_years_picontrol}"
    )

    # --- End-of-period mean response ---
    if end_period_years > n_common:
        logger.warning(
            "Requested end window (%d yr) exceeds available record (%d yr); "
            "using full record",
            end_period_years,
            n_common,
        )
        end_window = n_common
    else:
        end_window = end_period_years
    delta_t_end = float(delta_t[-end_window:].mean())
    delta_n_end = float(delta_n[-end_window:].mean())
    logger.info(
        f"  End-of-period ({end_window} yr) mean: dT={delta_t_end:.3f} K, "
        f"dN={delta_n_end:.3f} W/m2"
    )

    # --- Gregory-style ERF from full hist-aer record ---
    gregory = gregory_erf_estimate(delta_t, delta_n)
    erf_gregory = gregory["erf"]
    lambda_gregory = gregory["lambda_feedback"]
    logger.info(
        f"  Gregory ERF intercept: {erf_gregory:.3f} W/m2 "
        f"(lambda={lambda_gregory:.3f} W/m2/K, R^2={gregory['r_squared']:.3f})"
    )

    # --- Lambda-corrected ERF from end-of-period mean ---
    lambda_ecs = read_lambda_from_ecs_results(model)
    if lambda_ecs is not None:
        erf_lambda_corrected = delta_n_end - lambda_ecs * delta_t_end
        logger.info(
            f"  Lambda-corrected ERF: {erf_lambda_corrected:.3f} W/m2 "
            f"(lambda_ecs={lambda_ecs:.3f} W/m2/K)"
        )
    else:
        erf_lambda_corrected = float("nan")

    # Reported ERF: prefer lambda-corrected if available
    if lambda_ecs is not None and np.isfinite(erf_lambda_corrected):
        erf_reported = erf_lambda_corrected
        erf_source = "lambda_corrected"
    else:
        erf_reported = erf_gregory
        erf_source = "gregory"
    logger.info(f"  Reported ERF ({erf_source}): {erf_reported:.3f} W/m2")

    # --- Pass/fail ---
    pass_cooling = bool(delta_t_end < 0)
    pass_erf_range = bool(ERF_MIN <= erf_reported <= ERF_MAX)
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
            "erf_gregory_Wm2": [round(erf_gregory, 4)],
            "lambda_gregory_Wm2K": [round(lambda_gregory, 4)],
            "erf_gregory_r2": [round(gregory["r_squared"], 4)],
            "lambda_ecs_used_Wm2K": [
                round(lambda_ecs, 4) if lambda_ecs is not None else ""
            ],
            "erf_lambda_corrected_Wm2": [
                round(erf_lambda_corrected, 4)
                if np.isfinite(erf_lambda_corrected)
                else ""
            ],
            "erf_reported_Wm2": [round(erf_reported, 4)],
            "erf_source": [erf_source],
            "pass_cooling": [pass_cooling],
            "pass_erf_range": [pass_erf_range],
            "passes": [passes],
            "n_years_hist_aer": [n_common],
            "end_window_years": [end_window],
            "n_years_picontrol": [n_years_picontrol],
            "ensemble_members": [
                "_".join(ensemble_members) if ensemble_members else ""
            ],
        }
    )

    if save_to_cloud:
        from google.cloud import storage as gcs_storage

        storage_client = gcs_storage.Client(project="JCM and Benchmarking")
        bucket = storage_client.bucket("climatebench")
        gcs_path = "results/aerosol_forcing/aerosol_forcing_results.csv"
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
        "delta_T_end_K": delta_t_end,
        "delta_N_end_Wm2": delta_n_end,
        "erf_gregory_Wm2": erf_gregory,
        "erf_lambda_corrected_Wm2": erf_lambda_corrected,
        "erf_reported_Wm2": erf_reported,
        "erf_source": erf_source,
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
        save_to_cloud=args.save_to_cloud,
        overwrite=args.overwrite,
    )
