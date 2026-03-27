"""Tier I: ITCZ–energy flux equator (EFE) relationship (historical).

Verifies that the seasonal cycle of the ITCZ co-varies with the energy flux
equator (EFE) — the latitude where the vertically integrated meridional
atmospheric energy transport (AMET) vanishes.

AMET is diagnosed from the energy budget residual method:

  F_TOA  = rsdt - rsut - rlut                       (TOA net downward)
  F_sfc  = (rsds - rsus) + (rlds - rlus) - hfss - hfls  (sfc net into ocean)
  div_A  = F_TOA - F_sfc                             (atmos column divergence)

  AMET(phi) = 2*pi*a^2 * integral_{-pi/2}^{phi} div_A(phi') cos(phi') dphi'

  EFE(month)  = latitude where AMET = 0 (near-equatorial zero crossing)
  ITCZ(month) = latitude of zonal-mean precipitation maximum (|lat| <= 30°)

Pass/fail criteria (from Donohoe et al., 2013 and Schneider et al., 2014):
  - Seasonal r(ITCZ, EFE)              > 0.85
  - Scaling slope (ITCZ vs F_xeq)     1.5–5.0 °/PW
  - EFE seasonal amplitude             > 5°
  - Annual-mean |EFE – ITCZ| offset    < 5°

Usage:
    python itcz_efe_benchmark.py --model CanESM5
    python itcz_efe_benchmark.py --model CanESM5 --start_year 1950 --end_year 2014

References:
    Kang et al., 2008, J. Climate
    Kang et al., 2009, J. Climate
    Schneider et al., 2014, Nature
    Donohoe et al., 2013, J. Climate
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

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, force=True)

# --- Constants ---
EARTH_RADIUS = 6.371e6  # metres

# Pass/fail thresholds
ITCZ_EFE_CORR_MIN = 0.85   # minimum seasonal Pearson r(ITCZ, EFE)
SCALING_SLOPE_MIN = 1.5    # °/PW — lower bound on ITCZ vs F_xeq regression
SCALING_SLOPE_MAX = 5.0    # °/PW — upper bound
EFE_AMP_MIN = 5.0          # ° — EFE must migrate at least this far seasonally
ITCZ_EFE_OFFSET_MAX = 5.0  # ° — annual-mean |EFE – ITCZ| must be below this

# Tropical search bands
ITCZ_LAT_BAND = 30.0   # search ±30° for precipitation maximum
EFE_SEARCH_BAND = 40.0  # search ±40° for AMET zero crossing

# Required CMIP6 variables (all Amon)
ENERGY_VARS = ["rsdt", "rsut", "rlut", "rsds", "rsus", "rlds", "rlus", "hfss", "hfls"]
PRECIP_VARS = ["pr"]
ALL_VARS = ENERGY_VARS + PRECIP_VARS


# ---------------------------------------------------------------------------
# Flux diagnostics
# ---------------------------------------------------------------------------


def compute_toa_net(data):
    """TOA net downward flux (W/m2): rsdt - rsut - rlut."""
    return data["rsdt"]["rsdt"] - data["rsut"]["rsut"] - data["rlut"]["rlut"]


def compute_sfc_net(data):
    """Surface net flux into ocean (W/m2).

    F_sfc = (rsds - rsus) + (rlds - rlus) - hfss - hfls

    Sign convention: hfss and hfls are positive upward in CMIP6, so
    subtracting them gives the net downward flux into the surface/ocean.
    """
    return (
        (data["rsds"]["rsds"] - data["rsus"]["rsus"])
        + (data["rlds"]["rlds"] - data["rlus"]["rlus"])
        - data["hfss"]["hfss"]
        - data["hfls"]["hfls"]
    )


# ---------------------------------------------------------------------------
# Meridional energy transport
# ---------------------------------------------------------------------------


def compute_meridional_transport(zonal_mean_flux, lat):
    """AMET by cumulative integration from the S pole.

    Works for any leading dimensions (time, month, etc.):

        AMET(phi) = 2*pi*a^2 * integral_{-pi/2}^{phi} F(phi') cos(phi') dphi'

    Args:
        zonal_mean_flux: xr.DataArray with at least a 'lat' dim, in W/m2.
        lat: latitude coordinate in degrees.

    Returns:
        xr.DataArray of meridional energy transport (W) with same dims as input.
    """
    lat_rad = np.deg2rad(lat)

    dlat = np.abs(np.diff(lat_rad))
    dlat = np.append(dlat, dlat[-1])
    dlat = xr.DataArray(dlat, dims=["lat"], coords={"lat": lat})

    cos_lat = np.cos(lat_rad)
    cos_lat = xr.DataArray(cos_lat, dims=["lat"], coords={"lat": lat})

    integrand = zonal_mean_flux * cos_lat * dlat * 2 * np.pi * EARTH_RADIUS**2
    return integrand.cumsum(dim="lat")


# ---------------------------------------------------------------------------
# EFE and ITCZ diagnostics
# ---------------------------------------------------------------------------


def find_efe(amet_profile_pw, lat, search_band=EFE_SEARCH_BAND):
    """Find the energy flux equator: latitude where AMET = 0.

    Searches for zero crossings of AMET within |lat| <= search_band and
    returns the crossing nearest the equator (linearly interpolated).

    Args:
        amet_profile_pw: 1-D numpy array of AMET in PW, ordered S to N.
        lat: 1-D numpy array of latitudes (degrees), ordered S to N.
        search_band: half-width of tropical search band (degrees).

    Returns:
        float: EFE latitude in degrees, or np.nan if no crossing found.
    """
    mask = np.abs(lat) <= search_band
    lat_t = lat[mask]
    amet_t = amet_profile_pw[mask]

    signs = np.sign(amet_t)
    crossings = np.where(np.diff(signs) != 0)[0]

    if len(crossings) == 0:
        return np.nan

    efe_candidates = []
    for i in crossings:
        x0, x1 = float(lat_t[i]), float(lat_t[i + 1])
        y0, y1 = float(amet_t[i]), float(amet_t[i + 1])
        efe = x0 - y0 * (x1 - x0) / (y1 - y0) if y1 != y0 else (x0 + x1) / 2.0
        efe_candidates.append(efe)

    return float(efe_candidates[int(np.argmin(np.abs(efe_candidates)))])


def find_itcz_latitude(pr_zm_profile, lat, lat_band=ITCZ_LAT_BAND):
    """Find the ITCZ latitude as the zonal-mean precipitation maximum.

    Args:
        pr_zm_profile: 1-D numpy array of zonal-mean precipitation (any units).
        lat: 1-D numpy array of latitudes (degrees).
        lat_band: search within ±lat_band degrees.

    Returns:
        float: ITCZ latitude in degrees.
    """
    mask = np.abs(lat) <= lat_band
    lat_t = lat[mask]
    pr_t = pr_zm_profile[mask]
    idx = int(np.argmax(pr_t))
    return float(lat_t[idx])


def interpolate_amet_at_equator(amet_profile_pw, lat):
    """Linearly interpolate AMET to the equator (lat = 0).

    Args:
        amet_profile_pw: 1-D numpy array of AMET in PW, ordered S to N.
        lat: 1-D numpy array of latitudes (degrees), ordered S to N.

    Returns:
        float: AMET at the equator in PW.
    """
    return float(np.interp(0.0, lat, amet_profile_pw))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main(
    model: str,
    start_year: int = 1850,
    end_year: int = 2014,
    save_to_cloud: bool = False,
    overwrite: bool = False,
):
    logger.info(
        f"Running ITCZ–EFE benchmark for {model} "
        f"(historical {start_year}–{end_year})"
    )

    # --- Load all variables from historical ---
    hist_data = {}
    ensemble_members = None

    for var in ALL_VARS:
        logger.info(f"  Loading historical {var} ...")
        df = DataFinder(
            model=model, variable=var, start_year=start_year, end_year=end_year
        )
        try:
            ds = df.load_model_ds(ensemble_mean=True)
            hist_data[var] = ds
            if ensemble_members is None:
                ensemble_members = df.ensemble_members
            logger.info(
                f"    {var}: {len(ds.time)} months "
                f"({len(ds.time) // 12} years)"
            )
        except Exception as e:
            logger.error(f"    Failed to load historical {var}: {e}")
            raise

    # Trim all datasets to common length
    n_months_common = min(len(hist_data[v].time) for v in ALL_VARS)
    n_years_available = n_months_common // 12
    n_months_common = n_years_available * 12
    for var in ALL_VARS:
        hist_data[var] = hist_data[var].isel(time=slice(0, n_months_common))

    logger.info(f"  Using {n_years_available} years of historical data")

    # --- Compute atmospheric column divergence ---
    logger.info("  Computing TOA and surface net fluxes ...")
    f_toa = compute_toa_net(hist_data)
    f_sfc = compute_sfc_net(hist_data)
    div_a = f_toa - f_sfc

    # --- Zonal means ---
    logger.info("  Computing zonal means ...")
    div_a_zm = div_a.mean(dim="lon")
    pr_zm = hist_data["pr"]["pr"].mean(dim="lon")

    lat = div_a_zm["lat"].values

    # --- Monthly climatologies ---
    logger.info("  Computing monthly climatologies ...")
    div_a_zm_clim = div_a_zm.groupby("time.month").mean("time")
    pr_zm_clim = pr_zm.groupby("time.month").mean("time")

    # --- AMET climatology ---
    logger.info("  Computing AMET seasonal climatology ...")
    amet_clim = compute_meridional_transport(div_a_zm_clim, lat)
    amet_clim_pw = amet_clim / 1e15 # convert to PW

    # --- Seasonal EFE and ITCZ latitudes ---
    logger.info("  Diagnosing EFE and ITCZ latitudes for each calendar month ...")
    efe_lats = []
    itcz_lats = []
    xeq_flux_pw = []

    for m in range(12):
        amet_m = amet_clim_pw.isel(month=m).values
        pr_m = pr_zm_clim.isel(month=m).values

        efe = find_efe(amet_m, lat)
        itcz = find_itcz_latitude(pr_m, lat)
        fxeq = interpolate_amet_at_equator(amet_m, lat)

        efe_lats.append(efe)
        itcz_lats.append(itcz)
        xeq_flux_pw.append(fxeq)

        logger.info(
            f"    Month {m + 1:02d}: EFE = {efe:+.1f}°, "
            f"ITCZ = {itcz:+.1f}°, F_xeq = {fxeq:+.3f} PW"
        )

    efe_lats = np.array(efe_lats)
    itcz_lats = np.array(itcz_lats)
    xeq_flux_pw = np.array(xeq_flux_pw)

    # Drop any months where EFE could not be determined
    valid = ~np.isnan(efe_lats)
    n_valid = int(valid.sum())
    if n_valid < 10:
        logger.warning(
            f"  Only {n_valid}/12 calendar months have a valid EFE. "
            "Results may be unreliable."
        )

    efe_v = efe_lats[valid]
    itcz_v = itcz_lats[valid]
    fxeq_v = xeq_flux_pw[valid]

    # --- Statistics ---
    # 1. Seasonal correlation: r(ITCZ, EFE)
    r_itcz_efe = float(np.corrcoef(efe_v, itcz_v)[0, 1])

    # 2. Scaling regression: ITCZ = slope * F_xeq + intercept  (°/PW)
    slope, intercept = np.polyfit(fxeq_v, itcz_v, 1)
    slope = float(slope)
    intercept = float(intercept)

    # 3. EFE seasonal amplitude
    efe_amp = float(np.max(efe_v) - np.min(efe_v))

    # 4. Annual-mean |EFE – ITCZ| offset
    itcz_efe_offset = float(np.mean(np.abs(efe_v - itcz_v)))

    logger.info(f"  Seasonal r(ITCZ, EFE):         {r_itcz_efe:.3f}")
    logger.info(f"  Scaling slope (°/PW):          {slope:.2f}")
    logger.info(f"  EFE seasonal amplitude (°):    {efe_amp:.1f}")
    logger.info(f"  Annual-mean |EFE–ITCZ| (°):   {itcz_efe_offset:.1f}")

    # --- Pass/fail checks ---
    pass_correlation = r_itcz_efe >= ITCZ_EFE_CORR_MIN
    pass_scaling = SCALING_SLOPE_MIN <= slope <= SCALING_SLOPE_MAX
    pass_efe_amplitude = efe_amp >= EFE_AMP_MIN
    pass_offset = itcz_efe_offset <= ITCZ_EFE_OFFSET_MAX

    pass_all = pass_correlation and pass_scaling and pass_efe_amplitude and pass_offset

    logger.info(
        f"  r(ITCZ, EFE) >= {ITCZ_EFE_CORR_MIN}: "
        f"{'PASS' if pass_correlation else 'FAIL'}"
    )
    logger.info(
        f"  Scaling slope [{SCALING_SLOPE_MIN}–{SCALING_SLOPE_MAX} °/PW]: "
        f"{'PASS' if pass_scaling else 'FAIL'}"
    )
    logger.info(
        f"  EFE amplitude >= {EFE_AMP_MIN}°: "
        f"{'PASS' if pass_efe_amplitude else 'FAIL'}"
    )
    logger.info(
        f"  |EFE–ITCZ| offset <= {ITCZ_EFE_OFFSET_MAX}°: "
        f"{'PASS' if pass_offset else 'FAIL'}"
    )
    logger.info(f"  Overall ITCZ–EFE benchmark: {'PASS' if pass_all else 'FAIL'}")

    # --- Save results ---
    results_dir = "../results/itcz_efe/"
    results_file = os.path.join(results_dir, "itcz_efe_results.csv")

    result_df = pd.DataFrame(
        {
            "model": [model],
            "start_year": [start_year],
            "end_year": [end_year],
            "n_years": [n_years_available],
            "n_valid_months": [n_valid],
            "r_itcz_efe": [round(r_itcz_efe, 4)],
            "scaling_slope_deg_per_PW": [round(slope, 3)],
            "scaling_intercept_deg": [round(intercept, 3)],
            "efe_seasonal_amplitude_deg": [round(efe_amp, 2)],
            "itcz_efe_offset_deg": [round(itcz_efe_offset, 2)],
            "pass_correlation": [pass_correlation],
            "pass_scaling": [pass_scaling],
            "pass_efe_amplitude": [pass_efe_amplitude],
            "pass_offset": [pass_offset],
            "pass_all": [pass_all],
            "ensemble_members": [
                "_".join(ensemble_members) if ensemble_members else ""
            ],
        }
    )

    if save_to_cloud:
        from google.cloud import storage as gcs_storage

        storage_client = gcs_storage.Client(project="JCM and Benchmarking")
        bucket = storage_client.bucket("climatebench")
        gcs_path = "results/itcz_efe/itcz_efe_results.csv"
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
        logger.info(f"  Results saved to cloud: gs://climatebench/{gcs_path}")
    else:
        if overwrite or not os.path.isfile(results_file):
            os.makedirs(results_dir, exist_ok=True)
            result_df.to_csv(results_file, index=False)
        else:
            with open(results_file, "a") as f:
                writer_object = writer(f)
                writer_object.writerow(result_df.values.flatten().tolist())
        logger.info(f"  Results saved locally: {results_file}")

    return {
        "r_itcz_efe": r_itcz_efe,
        "scaling_slope_deg_per_PW": slope,
        "scaling_intercept_deg": intercept,
        "efe_seasonal_amplitude_deg": efe_amp,
        "itcz_efe_offset_deg": itcz_efe_offset,
        "pass_correlation": pass_correlation,
        "pass_scaling": pass_scaling,
        "pass_efe_amplitude": pass_efe_amplitude,
        "pass_offset": pass_offset,
        "pass_all": pass_all,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Tier I: ITCZ–energy flux equator relationship (historical)"
    )
    parser.add_argument(
        "--model",
        required=True,
        help="CMIP6 model name (e.g., CanESM5, UKESM1-0-LL)",
    )
    parser.add_argument(
        "--start_year",
        default=1850,
        type=int,
        help="Start year of historical period (default: 1850)",
    )
    parser.add_argument(
        "--end_year",
        default=2014,
        type=int,
        help="End year of historical period (default: 2014)",
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
        start_year=args.start_year,
        end_year=args.end_year,
        save_to_cloud=args.save_to_cloud,
        overwrite=args.overwrite,
    )
