"""Tier I: ENSO variability benchmark (piControl).

Three checks on El Niño–Southern Oscillation behaviour:

1. Spectral peak  – dominant period of the Niño-3.4 SST index falls in the
                    2–7 year band.
2. Amplitude      – Niño-3.4 standard deviation is within 0.4–1.8 K
                    (factor of two around ~0.9 K observed).
3. Teleconnections – during warm ENSO events (Niño-3.4 > 0.5 K):
                    (a) tropical-mean (30S–30N) near-surface temperature
                        anomaly is positive, and
                    (b) Maritime Continent (10S–10N, 90–150E) precipitation
                        anomaly is negative.

Niño-3.4 definition follows ICONEval recipe_ocean_timeseries.yml:
  area-mean of tos anomalies in 5S–5N, 170W–120W, 3-month rolling mean.

Usage:
    python enso_benchmark.py --model CanESM5
    python enso_benchmark.py --model UKESM1-0-LL --min_years 100

References:
    ICONEval recipe_ocean_timeseries.yml (Niño-3.4 definition)
    Planton et al. (2021)
"""

import argparse
import logging
import os
import sys
from csv import writer

import numpy as np
import pandas as pd
import xarray as xr
from scipy import signal

from benchmark_utils import DataFinder

sys.path.append("..")

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, force=True)

# --- Thresholds ---
NINO34_STD_MIN = 0.4  # K  (observed ~0.9 K; factor-of-two lower bound)
NINO34_STD_MAX = 1.8  # K  (factor-of-two upper bound)
PEAK_BAND_MIN_YR = 2  # years
PEAK_BAND_MAX_YR = 7  # years
WARM_ENSO_THRESHOLD = 0.5  # K  threshold for composite

# --- Region definitions ---
NINO34_LAT = (-5, 5)
NINO34_LON = (190, 240)

TROPICAL_LAT = (-30, 30)

MARITIME_CONTINENT_LAT = (-10, 10)
MARITIME_CONTINENT_LON = (90, 150)


def _is_curvilinear(da):
    """Return True if lat/lon are 2D coordinates rather than 1D dimension coords."""
    return "lat" not in da.dims


def _spatial_dims(da):
    """Return the names of the horizontal spatial dimensions."""
    if _is_curvilinear(da):
        return list(da["lat"].dims)  # e.g. ["j", "i"]
    return ["lat", "lon"]


def _sel_region(da, lat_bounds, lon_bounds=None):
    """Subset a DataArray to a lat/lon box.

    Rectilinear grids (lat/lon are 1D dimension coords): uses .sel with slices.
    Curvilinear grids (lat/lon are 2D non-dimension coords): uses boolean masking;
    points outside the box become NaN and are excluded from subsequent averages.
    Assumes 0–360 longitude convention.
    """
    lat_min, lat_max = lat_bounds
    if _is_curvilinear(da):
        mask = (da["lat"] >= lat_min) & (da["lat"] <= lat_max)
        if lon_bounds is not None:
            lon_min, lon_max = lon_bounds
            mask = mask & (da["lon"] >= lon_min) & (da["lon"] <= lon_max)
        return da.where(mask)
    else:
        da = da.sel(lat=slice(lat_min, lat_max))
        if lon_bounds is not None:
            da = da.sel(lon=slice(*lon_bounds))
        return da


def _area_mean(da):
    """Cosine-latitude-weighted spatial mean.

    Works for both rectilinear (averages over lat/lon dims) and curvilinear
    grids (averages over j/i or equivalent dims, skipping NaN-masked points).
    """
    weights = np.cos(np.deg2rad(da["lat"]))
    return da.weighted(weights).mean(dim=_spatial_dims(da))


# ---------------------------------------------------------------------------
# Niño-3.4 index
# ---------------------------------------------------------------------------


def compute_nino34(ds):
    """Compute the Niño-3.4 index from a tos dataset.

    Steps (following ICONEval recipe):
      1. Extract 5S–5N, 170W–120W.
      2. Area-weighted mean → monthly time series.
      3. Remove climatological seasonal cycle (monthly anomalies).
      4. Apply 3-month centred rolling mean.

    Args:
        ds: xr.Dataset with 'tos' variable (lat, lon, time).

    Returns:
        xr.DataArray of the Niño-3.4 index (monthly, units K or °C).
    """
    tos = ds["tos"]
    # Convert K → °C if needed (threshold is unit-agnostic for anomalies, but
    # log the offset so the user can verify)
    if float(tos.mean()) > 200:
        logger.info("  tos appears to be in Kelvin; converting to °C for Niño-3.4")
        tos = tos - 273.15

    region = _sel_region(tos, NINO34_LAT, NINO34_LON)
    ts = _area_mean(region)

    # Monthly anomaly
    anomaly = ts.groupby("time.month") - ts.groupby("time.month").mean("time")

    # 3-month centred rolling mean
    nino34 = anomaly.rolling(time=3, center=True, min_periods=2).mean()

    return nino34


# ---------------------------------------------------------------------------
# Spectral check
# ---------------------------------------------------------------------------


def check_spectral_peak(nino34, min_years=PEAK_BAND_MIN_YR, max_years=PEAK_BAND_MAX_YR):
    """Check that the dominant spectral peak lies in the 2–7 year band.

    Uses Welch's method with a 10-year (120-month) segment length.

    Args:
        nino34: 1-D array-like of monthly Niño-3.4 values (no NaNs).
        min_years: lower bound of target period band (years).
        max_years: upper bound of target period band (years).

    Returns:
        dict with peak_period_yr, peak_power, in_band, frequencies, power.
    """
    x = np.array(nino34.dropna("time"))
    fs = 12.0  # samples per year (monthly data)

    nperseg = min(120, len(x) // 4)  # ~10 years, or shorter if record is short
    freqs, power = signal.welch(x, fs=fs, nperseg=nperseg)

    # Exclude the zero-frequency (mean) component
    mask = freqs > 0
    freqs, power = freqs[mask], power[mask]

    peak_idx = np.argmax(power)
    peak_freq = freqs[peak_idx]
    peak_period_yr = 1.0 / peak_freq
    in_band = min_years <= peak_period_yr <= max_years

    return {
        "peak_period_yr": float(peak_period_yr),
        "peak_power": float(power[peak_idx]),
        "in_band": bool(in_band),
        "frequencies": freqs,
        "power": power,
    }


# ---------------------------------------------------------------------------
# Amplitude check
# ---------------------------------------------------------------------------


def check_amplitude(nino34, std_min=NINO34_STD_MIN, std_max=NINO34_STD_MAX):
    """Check that the Niño-3.4 std dev is within [std_min, std_max] K.

    Args:
        nino34: Niño-3.4 DataArray.
        std_min: lower bound (K).
        std_max: upper bound (K).

    Returns:
        dict with std_dev, in_range.
    """
    std = float(nino34.std())
    return {
        "std_dev": std,
        "in_range": bool(std_min <= std <= std_max),
    }


# ---------------------------------------------------------------------------
# Teleconnection checks
# ---------------------------------------------------------------------------


def check_teleconnections(nino34, tas_ds, pr_ds, threshold=WARM_ENSO_THRESHOLD):
    """Check sign of canonical ENSO teleconnections via warm-event composites.

    Warm events: months where Niño-3.4 > threshold.

    Checks:
      (a) Tropical-mean (30S–30N) tas anomaly is positive.
      (b) Maritime Continent (10S–10N, 90–150E) pr anomaly is negative.

    Args:
        nino34: Niño-3.4 DataArray (monthly).
        tas_ds: xr.Dataset with 'tas' (monthly, same or overlapping time axis).
        pr_ds:  xr.Dataset with 'pr'  (monthly, same or overlapping time axis).
        threshold: Niño-3.4 threshold defining warm events (K).

    Returns:
        dict with tropical_tas_composite, maritime_pr_composite,
              tas_sign_ok, pr_sign_ok.
    """
    # Round time dims to day
    nino34['time'] = nino34.time.dt.floor("D")
    tas_ds['time'] = tas_ds.time.dt.floor("D")
    pr_ds['time'] = pr_ds.time.dt.floor("D")
    # Align time axes
    common_time = np.intersect1d(
        nino34.time.values,
        np.intersect1d(tas_ds.time.values, pr_ds.time.values),
    )
    if len(common_time) == 0:
        logger.warning("  No overlapping time steps between tos, tas, and pr datasets.")
        return {
            "tropical_tas_composite": np.nan,
            "maritime_pr_composite": np.nan,
            "tas_sign_ok": False,
            "pr_sign_ok": False,
        }

    nino34_c = nino34.sel(time=common_time,method='nearest')
    tas = tas_ds["tas"].sel(time=common_time,method='nearest')
    pr = pr_ds["pr"].sel(time=common_time,method='nearest')

    # Monthly anomalies for tas and pr
    tas_anom = tas.groupby("time.month") - tas.groupby("time.month").mean("time")
    pr_anom = pr.groupby("time.month") - pr.groupby("time.month").mean("time")

    # Warm-event mask
    warm_mask = nino34_c > threshold
    n_warm = int(warm_mask.sum())
    logger.info(f"  Warm ENSO months (Niño-3.4 > {threshold} K): {n_warm}")
    if n_warm < 6:
        logger.warning("  Too few warm ENSO months for a reliable composite.")

    # Tropical-mean tas composite
    tas_tropical = _sel_region(tas_anom, TROPICAL_LAT)
    tas_trop_ts = _area_mean(tas_tropical)
    tropical_tas_composite = float(tas_trop_ts.where(warm_mask).mean())

    # Maritime Continent pr composite
    pr_mc = _sel_region(pr_anom, MARITIME_CONTINENT_LAT, MARITIME_CONTINENT_LON)
    pr_mc_ts = _area_mean(pr_mc)
    maritime_pr_composite = float(pr_mc_ts.where(warm_mask).mean())

    return {
        "tropical_tas_composite": tropical_tas_composite,
        "maritime_pr_composite": maritime_pr_composite,
        "tas_sign_ok": bool(tropical_tas_composite > 0),
        "pr_sign_ok": bool(maritime_pr_composite < 0),
    }


def main(
    model: str,
    min_years: int = 100,
    save_to_cloud: bool = False,
    overwrite: bool = False,
):
    logger.info(f"Running ENSO benchmark for {model} (piControl)")

    # Load piControl tos
    df_tos = DataFinder(model=model, variable="tos", start_year=1850, end_year=2000)
    try:
        ds_tos = df_tos.load_experiment_ds(experiment="piControl", ensemble_mean=True)
        logger.info(f"  tos: {len(ds_tos.time)} months loaded")
    except Exception as e:
        logger.error(f"  Failed to load piControl tos: {e}")
        raise

    n_years_tos = len(ds_tos.time) // 12
    if n_years_tos < min_years:
        logger.warning(
            f"  Only {n_years_tos} years of tos available "
            f"(requested minimum: {min_years})"
        )

    # Load piControl tas and pr (for teleconnection check)
    df_tas = DataFinder(model=model, variable="tas", start_year=1850, end_year=2000)
    df_pr = DataFinder(model=model, variable="pr", start_year=1850, end_year=2000)
    try:
        ds_tas = df_tas.load_experiment_ds(experiment="piControl", ensemble_mean=True)
        logger.info(f"  tas: {len(ds_tas.time)} months loaded")
    except Exception as e:
        logger.error(f"  Failed to load piControl tas: {e}")
        raise

    try:
        ds_pr = df_pr.load_experiment_ds(experiment="piControl", ensemble_mean=True)
        logger.info(f"  pr: {len(ds_pr.time)} months loaded")
    except Exception as e:
        logger.error(f"  Failed to load piControl pr: {e}")
        raise

    # Compute Niño-3.4 index
    logger.info("  Computing Niño-3.4 index …")
    nino34 = compute_nino34(ds_tos)
    logger.info(f"  Niño-3.4 series: {len(nino34)} months")

    # Check 1: spectral peak
    logger.info("  Check 1: spectral peak …")
    spectral = check_spectral_peak(nino34)
    logger.info(
        f"  Dominant period: {spectral['peak_period_yr']:.2f} yr  "
        f"(target {PEAK_BAND_MIN_YR}–{PEAK_BAND_MAX_YR} yr)  "
        f"-> {'PASS' if spectral['in_band'] else 'FAIL'}"
    )

    # Check 2: amplitude
    logger.info("  Check 2: amplitude …")
    amplitude = check_amplitude(nino34)
    logger.info(
        f"  Niño-3.4 std dev: {amplitude['std_dev']:.3f} K  "
        f"(target {NINO34_STD_MIN}–{NINO34_STD_MAX} K)  "
        f"-> {'PASS' if amplitude['in_range'] else 'FAIL'}"
    )

    # Check 3: teleconnections
    logger.info("  Check 3: teleconnections …")
    telecon = check_teleconnections(nino34, ds_tas, ds_pr)
    logger.info(
        f"  Tropical-mean tas composite (warm ENSO): "
        f"{telecon['tropical_tas_composite']:+.4f} K  "
        f"-> {'PASS (>0)' if telecon['tas_sign_ok'] else 'FAIL (<=0)'}"
    )
    logger.info(
        f"  Maritime Continent pr composite (warm ENSO): "
        f"{telecon['maritime_pr_composite']:+.6f} kg/m2/s  "
        f"-> {'PASS (<0)' if telecon['pr_sign_ok'] else 'FAIL (>=0)'}"
    )

    all_pass = (
        spectral["in_band"]
        and amplitude["in_range"]
        and telecon["tas_sign_ok"]
        and telecon["pr_sign_ok"]
    )
    logger.info(f"  Overall ENSO benchmark: {'PASS' if all_pass else 'FAIL'}")

    # Save results
    results_dir = "../results/enso/"
    results_file = os.path.join(results_dir, "enso_results.csv")

    ensemble_members = df_tos.ensemble_members
    result_df = pd.DataFrame(
        {
            "model": [model],
            "nino34_std_K": [round(amplitude["std_dev"], 4)],
            "pass_amplitude": [amplitude["in_range"]],
            "spectral_peak_yr": [round(spectral["peak_period_yr"], 2)],
            "pass_spectral_peak": [spectral["in_band"]],
            "tropical_tas_composite_K": [round(telecon["tropical_tas_composite"], 4)],
            "pass_tas_sign": [telecon["tas_sign_ok"]],
            "maritime_pr_composite_kgm2s": [round(telecon["maritime_pr_composite"], 8)],
            "pass_pr_sign": [telecon["pr_sign_ok"]],
            "pass_all": [all_pass],
            "n_years_tos": [n_years_tos],
            "ensemble_members": [
                "_".join(ensemble_members) if ensemble_members else ""
            ],
        }
    )

    if save_to_cloud:
        from google.cloud import storage as gcs_storage

        storage_client = gcs_storage.Client(project="JCM and Benchmarking")
        bucket = storage_client.bucket("climatebench")
        gcs_path = "results/enso/enso_results.csv"
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
        "amplitude": amplitude,
        "spectral": spectral,
        "teleconnections": telecon,
        "all_pass": all_pass,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Tier I: ENSO variability benchmark (piControl)"
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
        help="Minimum years of piControl required (default: 100)",
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
