"""Tier I: Covariance consistency benchmark.

Tests five physical covariances between key climate variables using
piControl interannual variability and time-mean diagnostics.

1. Clausius-Clapeyron (C-C) scaling: delta-prw vs delta-tas (~7 %/K)
   Ported from ICONEval recipe_consistency_checks_scatterplot.yml
   (prw_anom_vs_tas_anom diagnostic).

2. Temperature–clear-sky OLR covariance: delta-rlutcs vs delta-tas (~2 W/m²/K)
   Scored against CERES-EBAF Ed4.2, the same reference dataset used in
   ICONEval recipe_clouds_maps.yml for TOA LW fluxes.

3. Water budget closure: global-mean P = E in piControl steady state.
   Inspired by ICONEval recipe_consistency_checks_timeseries.yml
   (moisture_flux / global_watervapor diagnostics).

4. Latent heat flux constraint: hfls ≈ Q_net_sfc − hfss (LP ≈ Q_rad + SHF).

5. Tropical precipitation–buoyancy relationship (Neelin et al., 2009):
   log(pr) vs column water vapor slope in 30S–30N.

Usage:
    python covariance_benchmark.py --model CanESM5
    python covariance_benchmark.py --model UKESM1-0-LL --n_years 200

References:
    ICONEval recipe_consistency_checks_scatterplot.yml
      https://github.com/EyringMLClimateGroup/ICONEval
    Held & Soden (2006), doi:10.1175/JCLI3990.1
    Allan & Soden (2002), doi:10.1175/1520-0469(2002)059
    Neelin et al. (2009), doi:10.1175/2008JAS2726.1
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

L_V = 2.5008e6  # J/kg, latent heat of vaporisation
SEC_PER_DAY = 86400.0


def _global_annual_mean(model, variable, n_years):
    df = DataFinder(model=model, variable=variable, start_year=1850, end_year=2000)
    ds = df.load_experiment_ds(experiment="piControl", n_years=n_years)
    weights = np.cos(np.deg2rad(ds["lat"]))
    return compute_weighted_annual_mean(ds, variable, weights), ds


def _regress(x, y):
    slope, intercept, r, p, se = stats.linregress(x, y)
    return slope, r**2


def main(model, n_years=150, save_to_cloud=False, overwrite=False):
    logger.info(f"Covariance consistency benchmark — {model} (piControl, {n_years} yr)")

    results = {"model": model, "n_years_requested": n_years}

    # ------------------------------------------------------------------
    # 1. Clausius-Clapeyron scaling: delta-prw (%) vs delta-tas (K)
    #    Reference ~7 %/K; pass window ±2 %/K.
    #    Ported from ICONEval prw_anom_vs_tas_anom diagnostic.
    # ------------------------------------------------------------------
    logger.info("  [1/5] Clausius-Clapeyron scaling")
    tas, _ = _global_annual_mean(model, "tas", n_years)
    prw, _ = _global_annual_mean(model, "prw", n_years)
    n = min(len(tas), len(prw))
    x = tas[:n] - tas[:n].mean()
    y = (prw[:n] - prw[:n].mean()) / prw[:n].mean() * 100.0
    cc_slope, cc_r2 = _regress(x, y)
    cc_pass = abs(cc_slope - 7.0) <= 2.0
    logger.info(f"    slope={cc_slope:.2f} %/K (ref 7.0 ± 2.0)  pass={cc_pass}")
    results.update(
        {
            "cc_slope": round(cc_slope, 4),
            "cc_r2": round(cc_r2, 4),
            "cc_n_years": n,
            "cc_pass": cc_pass,
        }
    )

    # ------------------------------------------------------------------
    # 2. Temperature–clear-sky OLR covariance: delta-rlutcs vs delta-tas
    #    Reference ~2 W/m²/K from CERES-EBAF Ed4.2; pass window ±0.5.
    # ------------------------------------------------------------------
    logger.info("  [2/5] Temperature–clear-sky OLR covariance")
    rlutcs, _ = _global_annual_mean(model, "rlutcs", n_years)
    n = min(len(tas), len(rlutcs))
    x = tas[:n] - tas[:n].mean()
    y = rlutcs[:n] - rlutcs[:n].mean()
    tolr_slope, tolr_r2 = _regress(x, y)
    tolr_pass = abs(tolr_slope - 2.0) <= 0.5
    logger.info(f"    slope={tolr_slope:.2f} W/m²/K (ref 2.0 ± 0.5)  pass={tolr_pass}")
    results.update(
        {
            "tolr_slope": round(tolr_slope, 4),
            "tolr_r2": round(tolr_r2, 4),
            "tolr_n_years": n,
            "tolr_pass": tolr_pass,
        }
    )

    # ------------------------------------------------------------------
    # 3. Water budget closure: global P = E in steady state.
    #    E derived from hfls / L_v.  Pass: |P−E|/P < 1%.
    # ------------------------------------------------------------------
    logger.info("  [3/5] Water budget closure")
    pr, _ = _global_annual_mean(model, "pr", n_years)
    hfls, _ = _global_annual_mean(model, "hfls", n_years)
    n = min(len(pr), len(hfls))
    P_mean = float(pr[:n].mean())
    E_mean = float(hfls[:n].mean()) / L_V
    wb_rel_err = abs(P_mean - E_mean) / P_mean
    wb_pass = wb_rel_err < 0.01
    logger.info(
        f"    P={P_mean * SEC_PER_DAY:.4f} mm/day  E={E_mean * SEC_PER_DAY:.4f} mm/day  "
        f"|P−E|/P={wb_rel_err * 100:.2f}%  pass={wb_pass}"
    )
    results.update(
        {
            "wb_P_mmday": round(P_mean * SEC_PER_DAY, 5),
            "wb_E_mmday": round(E_mean * SEC_PER_DAY, 5),
            "wb_rel_err_pct": round(wb_rel_err * 100, 4),
            "wb_n_years": n,
            "wb_pass": wb_pass,
        }
    )

    # ------------------------------------------------------------------
    # 4. Latent heat flux constraint: hfls / (Q_net_sfc − hfss) ≈ 1.
    #    Surface energy budget identity; pass: ratio within ±0.10 of 1.0.
    # ------------------------------------------------------------------
    logger.info("  [4/5] Latent heat flux constraint")
    rsds, _ = _global_annual_mean(model, "rsds", n_years)
    rsus, _ = _global_annual_mean(model, "rsus", n_years)
    rlds, _ = _global_annual_mean(model, "rlds", n_years)
    rlus, _ = _global_annual_mean(model, "rlus", n_years)
    hfss, _ = _global_annual_mean(model, "hfss", n_years)
    n = min(len(v) for v in [rsds, rsus, rlds, rlus, hfss, hfls])
    Q_net = (rsds[:n] - rsus[:n]) + (rlds[:n] - rlus[:n])
    rhs = Q_net - hfss[:n]
    lhf_ratio = float(hfls[:n].mean()) / float(rhs.mean())
    lhf_slope, lhf_r2 = _regress(rhs, hfls[:n])
    lhf_pass = abs(lhf_ratio - 1.0) <= 0.10
    logger.info(
        f"    hfls_mean={hfls[:n].mean():.2f} W/m²  (Q−SHF)_mean={rhs.mean():.2f} W/m²  "
        f"ratio={lhf_ratio:.3f}  pass={lhf_pass}"
    )
    results.update(
        {
            "lhf_ratio": round(lhf_ratio, 4),
            "lhf_reg_slope": round(lhf_slope, 4),
            "lhf_r2": round(lhf_r2, 4),
            "lhf_n_years": n,
            "lhf_pass": lhf_pass,
        }
    )

    # ------------------------------------------------------------------
    # 5. Neelin tropical precipitation–buoyancy (Neelin et al. 2009).
    #    Time-mean log(pr) vs prw across 30S–30N grid cells.
    #    Pass: slope > 0.01 log(mm/day)/mm and r² > 0.20.
    # ------------------------------------------------------------------
    logger.info("  [5/5] Neelin tropical precipitation–buoyancy")
    df_pr = DataFinder(model=model, variable="pr", start_year=1850, end_year=2000)
    ds_pr = df_pr.load_experiment_ds("piControl", n_years=n_years)
    df_prw = DataFinder(model=model, variable="prw", start_year=1850, end_year=2000)
    ds_prw = df_prw.load_experiment_ds("piControl", n_years=n_years)

    n_t = min(len(ds_pr.time), len(ds_prw.time))
    pr_mean = (
        ds_pr["pr"]
        .isel(time=slice(0, n_t))
        .sel(lat=slice(-30, 30))
        .mean(dim="time")
        .values.ravel()
    )
    prw_mean = (
        ds_prw["prw"]
        .isel(time=slice(0, n_t))
        .sel(lat=slice(-30, 30))
        .mean(dim="time")
        .values.ravel()
    )

    min_pr = 0.01 / SEC_PER_DAY
    mask = (pr_mean > min_pr) & np.isfinite(pr_mean) & np.isfinite(prw_mean)
    log_pr = np.log(pr_mean[mask] * SEC_PER_DAY)
    cwv = prw_mean[mask]
    neelin_slope, neelin_r2 = _regress(cwv, log_pr)
    neelin_pass = (neelin_slope > 0.01) and (neelin_r2 > 0.20)
    logger.info(
        f"    slope={neelin_slope:.4f} log(mm/day)/mm  r²={neelin_r2:.3f}  "
        f"n_pts={mask.sum()}  pass={neelin_pass}"
    )
    results.update(
        {
            "neelin_slope": round(neelin_slope, 5),
            "neelin_r2": round(neelin_r2, 4),
            "neelin_n_pts": int(mask.sum()),
            "neelin_pass": neelin_pass,
        }
    )

    # ------------------------------------------------------------------
    # Summary and save
    # ------------------------------------------------------------------
    pass_flags = [cc_pass, tolr_pass, wb_pass, lhf_pass, neelin_pass]
    n_pass = sum(pass_flags)
    results["n_pass"] = n_pass
    results["all_pass"] = n_pass == 5
    logger.info(f"Summary: {n_pass}/5 tests passed for {model}")

    results_dir = "../results/covariance_consistency"
    os.makedirs(results_dir, exist_ok=True)
    save_results_csv(
        pd.DataFrame([results]),
        os.path.join(results_dir, "covariance_results.csv"),
        save_to_cloud,
        overwrite,
    )
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Tier I: Covariance consistency benchmark"
    )
    parser.add_argument(
        "--model", required=True, help="CMIP6 model name (e.g., CanESM5, UKESM1-0-LL)"
    )
    parser.add_argument(
        "--n_years",
        default=150,
        type=int,
        help="Years of piControl to use (default: 150)",
    )
    parser.add_argument("--save_to_cloud", action="store_true", default=False)
    parser.add_argument("--overwrite", action="store_true", default=False)
    args = parser.parse_args()

    main(args.model, args.n_years, args.save_to_cloud, args.overwrite)
