"""Paleo climate benchmark: spatial temperature and precipitation evaluation with CRPS scoring.

Compares PMIP4/CMIP6 model climatologies against paleoclimate proxy reconstructions and
data assimilation (DA) products for LGM, mid-Holocene, and LIG periods.

Temperature benchmarks:
  LGM:         lgmDA absolute temperatures (Tierney et al. 2020)
               lgmDA anomaly (LGM - Holocene DA)
               LGMR SAT anomaly (Osman et al. 2021)
               Bartlein et al. 2011 pollen-based MAT anomaly
  midHolocene: Bartlein et al. 2011 pollen-based MAT anomaly
  lig127k:     Otto-Bliesner et al. 2021 proxy temperature anomalies

Precipitation benchmarks:
  LGM:         Bartlein et al. 2011 pollen-based MAP anomaly
  midHolocene: Bartlein et al. 2011 pollen-based MAP anomaly
  lig127k:     Scussolini et al. 2019 semi-quantitative precipitation changes

CRPS uses proxy/DA uncertainty as the width of a Gaussian forecast distribution,
scoring the model value as the "observation". This directly penalises models
whose paleo response falls outside proxy uncertainty bounds.

For anomaly-based comparisons the model paleo temperature is differenced against
the lgmDA Holocene (PI) field as a spatially resolved modern reference. Pass
--use-picontrol to load the model's own piControl from the main ClimateBench
DataFinder pipeline instead (requires processed piControl data).

Usage:
    cd paleo_scripts
    python paleo_benchmark.py --model AWI-ESM-1-1-LR --period lgm
    python paleo_benchmark.py --model all --period all
    python paleo_benchmark.py --model MIROC-ES2L --period lgm --use-picontrol
    python paleo_benchmark.py --model all --period lgm --obs-source lgmDA
    python paleo_benchmark.py --model all --period lgm --obs-source Bartlein2011 --variable tas
    python paleo_benchmark.py --model all --period all --save-to-cloud

Results saved to:
    ../results/paleo/{period}_paleo_benchmark_results.csv

References:
    Tierney et al. (2020) Nature 584, 569–573         [lgmDA]
    Osman et al. (2021) Nature 599, 485–490           [LGMR]
    Bartlein et al. (2011) Clim Dyn 37, 775–802       [pollen reconstructions]
    Otto-Bliesner et al. (2021) Clim Past 17, 63–88   [LIG proxies]
    Scussolini et al. (2019) Science Advances          [LIG precip]
"""

import argparse
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr
from scipy.special import erf

sys.path.append("..")
from utils import save_results_csv, standardize_dims

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
PALEO_DIR = Path(__file__).parent
OBS_DIR = PALEO_DIR / "paleo_data_cache" / "processed" / "observations"
MODEL_PROC_DIR = PALEO_DIR / "paleo_data_cache" / "processed" / "models"

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    force=True,
)


# ---------------------------------------------------------------------------
# CRPS and spatial metrics
# ---------------------------------------------------------------------------


def _crps_gaussian(obs: np.ndarray, mu: np.ndarray, sigma: np.ndarray) -> np.ndarray:
    """CRPS for Gaussian N(mu, sigma) scored against point observations.

    Positive-orientated: lower CRPS = better forecast.
    Formula from Gneiting & Raftery (2007):
        CRPS = sigma * [z*(2*Phi(z)-1) + 2*phi(z) - 1/sqrt(pi)]
    where z = (obs - mu) / sigma.
    """
    sigma = np.maximum(np.abs(sigma), 1e-6)
    z = (obs - mu) / sigma
    phi = np.exp(-0.5 * z**2) / np.sqrt(2 * np.pi)
    Phi = 0.5 * (1.0 + erf(z / np.sqrt(2.0)))
    return sigma * (z * (2.0 * Phi - 1.0) + 2.0 * phi - 1.0 / np.sqrt(np.pi))


def _spatial_metrics(
    model_vals: np.ndarray,
    proxy_mu: np.ndarray,
    proxy_sigma: np.ndarray,
    weights: np.ndarray | None = None,
) -> dict:
    """Compute RMSE, MAE, and CRPS across valid proxy sites/grid cells.

    Args:
        model_vals:  model values interpolated/regridded to proxy locations
        proxy_mu:    proxy reconstruction mean (same units as model_vals)
        proxy_sigma: proxy reconstruction uncertainty (1-sigma)
        weights:     optional area weights (e.g. cos-lat); uniform if None

    Returns:
        dict with keys: n_sites, rmse, mae, mean_crps, crps_skill
    """
    flat_model = np.asarray(model_vals).ravel()
    flat_mu = np.asarray(proxy_mu).ravel()
    flat_sigma = np.asarray(proxy_sigma).ravel()
    flat_w = np.ones_like(flat_mu) if weights is None else np.asarray(weights).ravel()

    valid = np.isfinite(flat_model) & np.isfinite(flat_mu) & np.isfinite(flat_sigma)
    if valid.sum() == 0:
        return dict(
            n_sites=0, rmse=np.nan, mae=np.nan, mean_crps=np.nan, crps_skill=np.nan
        )

    m = flat_model[valid]
    mu = flat_mu[valid]
    sig = flat_sigma[valid]
    w = flat_w[valid]
    w = w / w.sum()

    diff = m - mu
    rmse = float(np.sqrt(np.sum(w * diff**2)))
    mae = float(np.sum(w * np.abs(diff)))

    crps_vals = _crps_gaussian(m, mu, sig)
    mean_crps = float(np.sum(w * crps_vals))

    # Skill relative to a "climatological" forecast: N(mean(proxy), std(proxy))
    clim_mu = float(np.sum(w * mu))
    clim_sig = float(np.sqrt(np.sum(w * (mu - clim_mu) ** 2)))
    if clim_sig < 1e-6:
        clim_sig = float(np.mean(sig))
    crps_ref = float(np.mean(_crps_gaussian(m, clim_mu, clim_sig)))
    crps_skill = float(1.0 - mean_crps / crps_ref) if crps_ref > 1e-9 else np.nan

    return dict(
        n_sites=int(valid.sum()),
        rmse=round(rmse, 4),
        mae=round(mae, 4),
        mean_crps=round(mean_crps, 4),
        crps_skill=round(crps_skill, 4),
    )


# ---------------------------------------------------------------------------
# Regridding helpers
# ---------------------------------------------------------------------------


def _to_celsius(da: xr.DataArray) -> xr.DataArray:
    """Convert K → °C if values look like Kelvin (mean > 100)."""
    if float(da.mean()) > 100:
        return da - 273.15
    return da


def _regrid(
    source: xr.DataArray, target_lat: np.ndarray, target_lon: np.ndarray
) -> xr.DataArray:
    """Bilinearly interpolate source DataArray to a target regular lat/lon grid.

    Handles 0–360 vs −180–180 lon convention by remapping target lons.
    """
    src_lon = source.lon.values % 360
    tgt_lon = target_lon % 360
    source = source.assign_coords(lon=src_lon).sortby("lon")
    return source.interp(
        lat=target_lat,
        lon=tgt_lon,
        method="linear",
        kwargs={"fill_value": "extrapolate"},
    )


def _interp_to_points(
    source: xr.DataArray, lats: np.ndarray, lons: np.ndarray
) -> np.ndarray:
    """Nearest-neighbour interpolation to scattered lat/lon points."""
    lons_norm = lons % 360
    src_lon = source.lon.values % 360
    source = source.assign_coords(lon=src_lon).sortby("lon")
    vals = []
    for la, lo in zip(lats, lons_norm):
        try:
            v = float(source.sel(lat=la, lon=lo, method="nearest"))
        except Exception:
            v = np.nan
        vals.append(v)
    return np.array(vals)


# ---------------------------------------------------------------------------
# Model data loaders
# ---------------------------------------------------------------------------


def _load_model_tas(model: str, period: str) -> xr.DataArray | None:
    """Load annual-mean tas from processed monthly climatology.

    Returns DataArray in °C, or None if data is unavailable.
    """
    nc = MODEL_PROC_DIR / model / f"{period}_tas_monthly_climo.nc"
    if not nc.exists():
        logger.warning(
            f"  [skip] No processed {period} tas for {model} — run process_paleo_models.py first"
        )
        return None
    ds = xr.open_dataset(nc)
    da = ds["tas"].mean("month")
    da = standardize_dims(da.to_dataset(name="tas"))["tas"]
    return _to_celsius(da)


def _load_model_pr(model: str, period: str) -> xr.DataArray | None:
    """Load annual-mean pr from processed monthly climatology (kg m-2 s-1 → mm/yr).

    Returns DataArray in mm/yr, or None if data is unavailable.
    """
    nc = MODEL_PROC_DIR / model / f"{period}_pr_monthly_climo.nc"
    if not nc.exists():
        return None
    ds = xr.open_dataset(nc)
    da = ds["pr"].mean("month")
    da = standardize_dims(da.to_dataset(name="pr"))["pr"]
    return da * 86400 * 365.25


def _load_picontrol_tas(model: str) -> xr.DataArray | None:
    """Load piControl annual-mean tas via the main ClimateBench DataFinder."""
    try:
        sys.path.append(str(PALEO_DIR.parent / "benchmark_scrips"))
        from benchmark_utils import DataFinder

        df = DataFinder(model=model, variable="tas", start_year=1850, end_year=2000)
        pi_ds = df.load_experiment_ds(experiment="piControl", ensemble_mean=True)
        pi_da = standardize_dims(pi_ds)["tas"]
        return _to_celsius(pi_da.mean(dim="time"))
    except Exception as e:
        logger.warning(f"  Could not load piControl for {model}: {e}")
        return None


def _load_lgmda_pi_tas() -> xr.DataArray | None:
    """Load lgmDA Holocene (PI) annual-mean tas as a spatially resolved modern reference."""
    nc = OBS_DIR / "multi_period" / "lgmDA_v2.1_holocene_tas.nc"
    if not nc.exists():
        logger.warning(
            "  lgmDA_v2.1_holocene_tas.nc not found — cannot compute model anomalies"
        )
        return None
    ds = xr.open_dataset(nc)
    pi = ds["pi_tas"]
    if "month" in pi.dims:
        pi = pi.mean(dim="month")
    return _to_celsius(pi)


def _compute_model_anom(model_tas: xr.DataArray, pi_ref: xr.DataArray) -> xr.DataArray:
    """Compute model temperature anomaly (paleo − PI reference).

    Regrids pi_ref to the model grid before differencing.
    """
    pi_on_model = _regrid(pi_ref, model_tas.lat.values, model_tas.lon.values)
    return model_tas - pi_on_model


# ---------------------------------------------------------------------------
# Per-dataset benchmark functions
# ---------------------------------------------------------------------------


def _result_row(model, period, dataset, variable, metrics: dict) -> dict:
    return dict(
        model=model, period=period, dataset=dataset, variable=variable, **metrics
    )


def bench_lgmda_absolute(
    model_tas: xr.DataArray, model: str, period: str
) -> list[dict]:
    """Absolute temperature comparison: model lgm tas vs lgmDA lgm_tas."""
    nc = OBS_DIR / "lgm" / "lgmDA_v2.1_tas.nc"
    if not nc.exists():
        return []
    ds = xr.open_dataset(nc)
    lgmda_lgm = _to_celsius((ds["pi_tas"] + ds["tas"]).mean(dim="month"))
    lgmda_std = ds["tas_std"].mean(dim="month")

    model_on_lgmda = _regrid(model_tas, lgmda_lgm.lat.values, lgmda_lgm.lon.values)
    cos_w = np.cos(np.deg2rad(lgmda_lgm.lat.values))
    w2d = np.tile(cos_w[:, None], (1, len(lgmda_lgm.lon)))

    metrics = _spatial_metrics(
        model_on_lgmda.values, lgmda_lgm.values, lgmda_std.values, w2d
    )
    logger.info(
        f"  lgmDA absolute tas: n={metrics['n_sites']} RMSE={metrics['rmse']:.2f}°C CRPS={metrics['mean_crps']:.3f} skill={metrics['crps_skill']:.3f}"
    )
    return [_result_row(model, period, "lgmDA", "tas_absolute_C", metrics)]


def bench_lgmda_anomaly(
    model_anom: xr.DataArray, model: str, period: str
) -> list[dict]:
    """Anomaly comparison: model − lgmDA_pi vs lgmDA (lgm_tas − pi_tas)."""
    nc = OBS_DIR / "lgm" / "lgmDA_v2.1_tas.nc"
    if not nc.exists():
        return []
    ds = xr.open_dataset(nc)
    proxy_anom = ds["tas"].mean(dim="month")
    proxy_sigma = ds["tas_std"].mean(dim="month")

    model_on_lgmda = _regrid(model_anom, proxy_anom.lat.values, proxy_anom.lon.values)
    cos_w = np.cos(np.deg2rad(proxy_anom.lat.values))
    w2d = np.tile(cos_w[:, None], (1, len(proxy_anom.lon)))

    metrics = _spatial_metrics(
        model_on_lgmda.values, proxy_anom.values, proxy_sigma.values, w2d
    )
    logger.info(
        f"  lgmDA anomaly tas: n={metrics['n_sites']} RMSE={metrics['rmse']:.2f}°C CRPS={metrics['mean_crps']:.3f} skill={metrics['crps_skill']:.3f}"
    )
    return [_result_row(model, period, "lgmDA", "tas_anomaly_K", metrics)]


def bench_lgmr_sat(model_anom: xr.DataArray, model: str, period: str) -> list[dict]:
    """Anomaly comparison: model vs LGMR SAT (Osman et al. 2021)."""
    nc = OBS_DIR / "lgm" / "LGMR_SAT_tas.nc"
    if not nc.exists():
        return []
    ds = xr.open_dataset(nc)
    proxy_mu = ds["tas"]
    proxy_sigma = ds["tas_std"]

    model_on_lgmr = _regrid(model_anom, proxy_mu.lat.values, proxy_mu.lon.values)
    cos_w = np.cos(np.deg2rad(proxy_mu.lat.values))
    w2d = np.tile(cos_w[:, None], (1, len(proxy_mu.lon)))

    metrics = _spatial_metrics(
        model_on_lgmr.values, proxy_mu.values, proxy_sigma.values, w2d
    )
    logger.info(
        f"  LGMR SAT anomaly: n={metrics['n_sites']} RMSE={metrics['rmse']:.2f}°C CRPS={metrics['mean_crps']:.3f} skill={metrics['crps_skill']:.3f}"
    )
    return [_result_row(model, period, "LGMR_SAT", "tas_anomaly_K", metrics)]


def bench_bartlein_tas(model_anom: xr.DataArray, period: str, model: str) -> list[dict]:
    """Pollen-based MAT anomaly comparison (Bartlein et al. 2011).

    Uses tas and tas_std. Only cells with significant signal (tas_sig_val != 0) are included.
    """
    nc = OBS_DIR / period / "Bartlein2011_tas.nc"
    if not nc.exists():
        return []
    ds = xr.open_dataset(nc)
    proxy_mu = ds["tas"]
    proxy_sigma = ds["tas_std"]
    sig_var = (
        ds["tas_sig_val"] if "tas_sig_val" in ds else ds.get("tas_sig", proxy_mu * 0)
    )
    sig_mask = np.isfinite(sig_var.values) & (sig_var.values != 0)

    proxy_mu_masked = proxy_mu.where(
        xr.DataArray(sig_mask, dims=proxy_mu.dims, coords=proxy_mu.coords)
    )
    proxy_sig_masked = proxy_sigma.where(
        xr.DataArray(sig_mask, dims=proxy_sigma.dims, coords=proxy_sigma.coords)
    )

    model_on_bart = _regrid(model_anom, proxy_mu.lat.values, proxy_mu.lon.values)
    cos_w = np.cos(np.deg2rad(proxy_mu.lat.values))
    w2d = np.tile(cos_w[:, None], (1, len(proxy_mu.lon)))

    metrics = _spatial_metrics(
        model_on_bart.values, proxy_mu_masked.values, proxy_sig_masked.values, w2d
    )
    logger.info(
        f"  Bartlein MAT anomaly ({period}): n={metrics['n_sites']} RMSE={metrics['rmse']:.2f}°C CRPS={metrics['mean_crps']:.3f} skill={metrics['crps_skill']:.3f}"
    )
    return [_result_row(model, period, "Bartlein2011", "tas_anomaly_K", metrics)]


def bench_bartlein_pr(
    model_pr_anom: xr.DataArray | None, period: str, model: str
) -> list[dict]:
    """Pollen-based MAP anomaly comparison (Bartlein et al. 2011).

    pr in mm/yr; pr_std is standard error.
    """
    if model_pr_anom is None:
        return []
    nc = OBS_DIR / period / "Bartlein2011_pr.nc"
    if not nc.exists():
        return []
    ds = xr.open_dataset(nc)
    if "pr" not in ds:
        return []
    proxy_mu = ds["pr"]
    proxy_sigma = ds["pr_std"]
    sig_var = ds["pr_sig_val"] if "pr_sig_val" in ds else ds.get("pr_sig", proxy_mu * 0)
    sig_mask = np.isfinite(sig_var.values) & (sig_var.values != 0)

    proxy_mu_masked = proxy_mu.where(
        xr.DataArray(sig_mask, dims=proxy_mu.dims, coords=proxy_mu.coords)
    )
    proxy_sig_masked = proxy_sigma.where(
        xr.DataArray(sig_mask, dims=proxy_sigma.dims, coords=proxy_sigma.coords)
    )

    model_on_bart = _regrid(model_pr_anom, proxy_mu.lat.values, proxy_mu.lon.values)
    cos_w = np.cos(np.deg2rad(proxy_mu.lat.values))
    w2d = np.tile(cos_w[:, None], (1, len(proxy_mu.lon)))

    metrics = _spatial_metrics(
        model_on_bart.values, proxy_mu_masked.values, proxy_sig_masked.values, w2d
    )
    logger.info(
        f"  Bartlein MAP anomaly ({period}): n={metrics['n_sites']} RMSE={metrics['rmse']:.1f}mm/yr CRPS={metrics['mean_crps']:.3f} skill={metrics['crps_skill']:.3f}"
    )
    return [_result_row(model, period, "Bartlein2011", "pr_anomaly_mmyr", metrics)]


def bench_ottobliesner_lig(
    model_anom: xr.DataArray | None, model: str, period: str
) -> list[dict]:
    """LIG proxy temperature comparison (Otto-Bliesner et al. 2021)."""
    if model_anom is None:
        return []
    nc = OBS_DIR / "lig127k" / "OttoBliesner2021_tas.nc"
    if not nc.exists():
        return []
    ds = xr.open_dataset(nc)
    lats = ds["lat"].values
    lons = ds["lon"].values
    proxy_mu = ds["tas"].values
    proxy_sigma = ds["tas_std"].values
    valid = np.isfinite(proxy_mu)
    lats, lons = lats[valid], lons[valid]
    proxy_mu, proxy_sigma = proxy_mu[valid], proxy_sigma[valid]

    model_vals = _interp_to_points(model_anom, lats, lons)
    metrics = _spatial_metrics(model_vals, proxy_mu, proxy_sigma)
    logger.info(
        f"  Otto-Bliesner LIG TAS: n={metrics['n_sites']} RMSE={metrics['rmse']:.2f}°C CRPS={metrics['mean_crps']:.3f} skill={metrics['crps_skill']:.3f}"
    )
    return [_result_row(model, period, "OttoBliesner2021", "tas_anomaly_K", metrics)]


def bench_scussolini_lig(
    model_pr_anom: xr.DataArray | None, model: str, period: str
) -> list[dict]:
    """LIG precipitation comparison (Scussolini et al. 2019).

    Uses only sites with quantitative ΔP (mm) estimates and reliability ≥ 1.
    Reliability 1 → proxy_sigma = 300 mm/yr; reliability ≥ 2 → 150 mm/yr.
    """
    if model_pr_anom is None:
        return []
    nc = OBS_DIR / "lig127k" / "Scussolini2019_pr.nc"
    if not nc.exists():
        return []
    ds = xr.open_dataset(nc)
    if "pr" not in ds:
        logger.warning("  Scussolini: no pr variable in NetCDF")
        return []

    lats = ds["lat"].values
    lons = ds["lon"].values
    proxy_mu_all = ds["pr"].values
    reliability = (
        ds["pr_reliability"].values if "pr_reliability" in ds else np.ones(len(lats))
    )

    has_quant = np.isfinite(proxy_mu_all)
    reliable = reliability >= 1
    mask = has_quant & reliable
    if not mask.any():
        logger.warning("  Scussolini: no quantitative precipitation sites available")
        return []

    lats, lons = lats[mask], lons[mask]
    proxy_mu = proxy_mu_all[mask]
    proxy_sigma = np.where(reliability[mask] >= 2, 150.0, 300.0)

    model_vals = _interp_to_points(model_pr_anom, lats, lons)
    metrics = _spatial_metrics(model_vals, proxy_mu, proxy_sigma)
    logger.info(
        f"  Scussolini LIG precip: n={metrics['n_sites']} RMSE={metrics['rmse']:.1f}mm/yr CRPS={metrics['mean_crps']:.3f} skill={metrics['crps_skill']:.3f}"
    )
    return [_result_row(model, period, "Scussolini2019", "pr_anomaly_mmyr", metrics)]


def bench_temp12k(
    model_anom: xr.DataArray | None, model: str, period: str
) -> list[dict]:
    """Holocene temperature reconstruction (Kaufman et al. 2020 / Temp12k). Stub — not yet implemented."""
    logger.warning("  bench_temp12k: not yet implemented")
    return []


# ---------------------------------------------------------------------------
# Obs source registry — maps period → source → {variable → benchmark functions}
# Used for --obs-source filtering
# ---------------------------------------------------------------------------

OBS_SOURCE_REGISTRY: dict[str, dict[str, dict[str, tuple]]] = {
    "lgm": {
        "lgmDA": {"tas": (bench_lgmda_absolute, bench_lgmda_anomaly)},
        "LGMR_SAT": {"tas": (bench_lgmr_sat,)},
        "Bartlein2011": {"tas": (bench_bartlein_tas,), "pr": (bench_bartlein_pr,)},
    },
    "midHolocene": {
        "Bartlein2011": {"tas": (bench_bartlein_tas,), "pr": (bench_bartlein_pr,)},
        "Temp12k": {"tas": (bench_temp12k,)},
    },
    "lig127k": {
        "OttoBliesner2021": {"tas": (bench_ottobliesner_lig,)},
        "Scussolini2019": {"pr": (bench_scussolini_lig,)},
    },
}


# ---------------------------------------------------------------------------
# Per-period orchestration
# ---------------------------------------------------------------------------


def _run_lgm(
    model: str,
    use_picontrol: bool,
    obs_sources: list[str] | None,
    variables: list[str],
) -> list[dict]:
    rows = []
    run_tas = "tas" in variables
    run_pr = "pr" in variables

    model_tas = _load_model_tas(model, "lgm") if run_tas else None
    if run_tas and model_tas is None:
        return rows

    if use_picontrol:
        pi_ref = _load_picontrol_tas(model)
        if pi_ref is None:
            logger.warning("  Falling back to lgmDA PI reference")
            pi_ref = _load_lgmda_pi_tas()
    else:
        pi_ref = _load_lgmda_pi_tas()

    sources = obs_sources or list(OBS_SOURCE_REGISTRY["lgm"])

    if run_tas and "lgmDA" in sources and model_tas is not None:
        rows += bench_lgmda_absolute(model_tas, model, "lgm")

    if pi_ref is not None:
        model_anom = (
            _compute_model_anom(model_tas, pi_ref) if model_tas is not None else None
        )

        if run_tas and model_anom is not None:
            if "lgmDA" in sources:
                rows += bench_lgmda_anomaly(model_anom, model, "lgm")
            if "LGMR_SAT" in sources:
                rows += bench_lgmr_sat(model_anom, model, "lgm")
            if "Bartlein2011" in sources:
                rows += bench_bartlein_tas(model_anom, "lgm", model)

        if run_pr and "Bartlein2011" in sources:
            model_pr = _load_model_pr(model, "lgm")
            model_pr_anom = (
                _compute_pr_anom(model_pr, model, "lgm", use_picontrol)
                if model_pr is not None
                else None
            )
            rows += bench_bartlein_pr(model_pr_anom, "lgm", model)
    else:
        logger.warning("  No PI reference — skipping anomaly benchmarks for LGM")

    return rows


def _run_midholocene(
    model: str,
    use_picontrol: bool,
    obs_sources: list[str] | None,
    variables: list[str],
) -> list[dict]:
    rows = []
    run_tas = "tas" in variables
    run_pr = "pr" in variables

    model_tas = _load_model_tas(model, "midHolocene") if run_tas else None
    if run_tas and model_tas is None:
        return rows

    pi_ref = _load_picontrol_tas(model) if use_picontrol else _load_lgmda_pi_tas()
    if pi_ref is None:
        logger.warning(
            "  No PI reference — skipping anomaly benchmarks for midHolocene"
        )
        return rows

    sources = obs_sources or list(OBS_SOURCE_REGISTRY["midHolocene"])

    if run_tas and model_tas is not None:
        model_anom = _compute_model_anom(model_tas, pi_ref)
        if "Bartlein2011" in sources:
            rows += bench_bartlein_tas(model_anom, "midHolocene", model)
        if "Temp12k" in sources:
            rows += bench_temp12k(model_anom, model, "midHolocene")

    if run_pr and "Bartlein2011" in sources:
        model_pr = _load_model_pr(model, "midHolocene")
        model_pr_anom = (
            _compute_pr_anom(model_pr, model, "midHolocene", use_picontrol)
            if model_pr is not None
            else None
        )
        rows += bench_bartlein_pr(model_pr_anom, "midHolocene", model)

    return rows


def _run_lig127k(
    model: str,
    use_picontrol: bool,
    obs_sources: list[str] | None,
    variables: list[str],
) -> list[dict]:
    rows = []
    run_tas = "tas" in variables
    run_pr = "pr" in variables

    model_tas = _load_model_tas(model, "lig127k") if run_tas else None

    pi_ref = _load_picontrol_tas(model) if use_picontrol else _load_lgmda_pi_tas()
    if pi_ref is None:
        logger.warning("  No PI reference — skipping anomaly benchmarks for lig127k")
        return rows

    sources = obs_sources or list(OBS_SOURCE_REGISTRY["lig127k"])

    if run_tas and model_tas is not None:
        model_anom = _compute_model_anom(model_tas, pi_ref)
        if "OttoBliesner2021" in sources:
            rows += bench_ottobliesner_lig(model_anom, model, "lig127k")

    if run_pr and "Scussolini2019" in sources:
        model_pr = _load_model_pr(model, "lig127k")
        model_pr_anom = (
            _compute_pr_anom(model_pr, model, "lig127k", use_picontrol)
            if model_pr is not None
            else None
        )
        rows += bench_scussolini_lig(model_pr_anom, model, "lig127k")

    return rows


def _compute_pr_anom(
    model_pr: xr.DataArray | None,
    model: str,
    period: str,
    use_picontrol: bool,
) -> xr.DataArray | None:
    """Compute model precipitation anomaly (mm/yr) relative to PI reference."""
    if model_pr is None:
        return None
    if use_picontrol:
        try:
            sys.path.append(str(PALEO_DIR.parent / "benchmark_scrips"))
            from benchmark_utils import DataFinder

            df = DataFinder(model=model, variable="pr", start_year=1850, end_year=2000)
            pi_ds = df.load_experiment_ds(experiment="piControl", ensemble_mean=True)
            pi_pr = standardize_dims(pi_ds)["pr"].mean(dim="time") * 86400 * 365.25
            pi_pr_on_model = _regrid(pi_pr, model_pr.lat.values, model_pr.lon.values)
            return model_pr - pi_pr_on_model
        except Exception as e:
            logger.warning(f"  Could not load piControl pr: {e}")
    logger.warning(
        f"  No precipitation PI reference for {period} — skipping pr anomaly benchmarks. "
        "Pass --use-picontrol to enable."
    )
    return None


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

PERIOD_RUNNERS = {
    "lgm": _run_lgm,
    "midHolocene": _run_midholocene,
    "lig127k": _run_lig127k,
}


def main(
    models: list[str],
    periods: list[str],
    use_picontrol: bool = False,
    save_to_cloud: bool = False,
    overwrite: bool = False,
    obs_sources: list[str] | None = None,
    variables: list[str] | None = None,
) -> pd.DataFrame:
    if variables is None:
        variables = ["tas", "pr"]

    rows_by_period: dict[str, list[dict]] = {p: [] for p in periods}

    for model in models:
        for period in periods:
            if period not in PERIOD_RUNNERS:
                logger.info(
                    f"  No benchmark configured for period '{period}' — skipping"
                )
                continue
            logger.info(f"\n{'='*60}\n  {model} / {period}\n{'='*60}")
            rows = PERIOD_RUNNERS[period](model, use_picontrol, obs_sources, variables)
            rows_by_period[period].extend(rows)
            if not rows:
                logger.warning(f"  No benchmark results for {model}/{period}")

    all_dfs = []
    for period, rows in rows_by_period.items():
        if not rows:
            continue
        period_df = pd.DataFrame(rows)
        results_file = f"../results/paleo/{period}_paleo_benchmark_results.csv"
        save_results_csv(period_df, results_file, save_to_cloud, overwrite)
        print(period_df.to_string(index=False))
        all_dfs.append(period_df)

    if not all_dfs:
        logger.warning("No results collected.")
        return pd.DataFrame()

    return pd.concat(all_dfs, ignore_index=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Paleo benchmark: spatial RMSE/MAE/CRPS against proxy and DA observations"
    )
    parser.add_argument(
        "--model",
        default="all",
        help="Model name or 'all' for all models with processed data (default: all)",
    )
    parser.add_argument(
        "--period",
        default="all",
        choices=["lgm", "midHolocene", "lig127k", "all"],
        help="Paleo period to benchmark (default: all)",
    )
    parser.add_argument(
        "--obs-source",
        nargs="+",
        default=None,
        metavar="SOURCE",
        help=(
            "Observation source(s) to benchmark against. "
            "LGM: lgmDA, LGMR_SAT, Bartlein2011. "
            "midHolocene: Bartlein2011, Temp12k. "
            "lig127k: OttoBliesner2021, Scussolini2019. "
            "Default: all sources for the selected period."
        ),
    )
    parser.add_argument(
        "--variable",
        nargs="+",
        default=["all"],
        choices=["tas", "pr", "all"],
        help="Variable(s) to benchmark: tas, pr, or all (default: all)",
    )
    parser.add_argument(
        "--use-picontrol",
        action="store_true",
        default=False,
        help="Load model piControl from main ClimateBench DataFinder for anomaly computation",
    )
    parser.add_argument(
        "--save-to-cloud",
        action="store_true",
        default=False,
        help="Save results to GCS bucket 'climatebench'",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        default=False,
        help="Overwrite existing results CSV instead of appending",
    )
    args = parser.parse_args()

    # Resolve model list
    if args.model == "all":
        available = [
            p.name
            for p in MODEL_PROC_DIR.iterdir()
            if p.is_dir() and any(p.glob("*_tas_monthly_climo.nc"))
        ]
        if not available:
            logger.error(
                "No processed model data found in paleo_data_cache/processed/models/. "
                "Run process_paleo_models.py first."
            )
            sys.exit(1)
        model_list = sorted(available)
    else:
        model_list = [args.model]

    # Resolve period list
    period_list = list(PERIOD_RUNNERS) if args.period == "all" else [args.period]

    # Resolve variable list
    variable_list = ["tas", "pr"] if "all" in args.variable else args.variable

    logger.info(f"Models:    {model_list}")
    logger.info(f"Periods:   {period_list}")
    logger.info(f"Variables: {variable_list}")
    logger.info(f"Sources:   {args.obs_source or 'all'}")
    logger.info(
        f"PI reference: {'piControl (DataFinder)' if args.use_picontrol else 'lgmDA Holocene'}"
    )

    main(
        models=model_list,
        periods=period_list,
        use_picontrol=args.use_picontrol,
        save_to_cloud=args.save_to_cloud,
        overwrite=args.overwrite,
        obs_sources=args.obs_source,
        variables=variable_list,
    )
