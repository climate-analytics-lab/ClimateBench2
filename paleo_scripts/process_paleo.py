"""
Process raw paleoclimate data into a unified dataset.

Reads from paleo_data_cache/raw/ and writes to paleo_data_cache/processed/.

CMIP6 processing (--source cmip6):
  Reads raw tas_Amon_*.nc files per model, computes time-mean annual and
  monthly climatologies, writes:
    paleo_data_cache/processed/{MODEL}/{period}_tas_annual.nc
    paleo_data_cache/processed/{MODEL}/{period}_tas_monthly.nc
  Then deletes the raw files (unless --skip-cleanup).

Observations processing (--source observations):
  Proxy data — site-level or gridded, saved per period:
    paleo_data_cache/processed/observations/proxy/lig127k_ottobliesner_tas_proxy.nc
    paleo_data_cache/processed/observations/proxy/lig127k_scussolini_pr_proxy.csv
    paleo_data_cache/processed/observations/proxy/lgm_bartlein_proxy.csv
    paleo_data_cache/processed/observations/proxy/midh_bartlein_proxy.csv
    paleo_data_cache/processed/observations/proxy/deeptime_hansen_proxy.csv
    paleo_data_cache/processed/observations/proxy/sisal_v3/

  Data assimilation — gridded, saved per period:
    paleo_data_cache/processed/observations/da/lgm_lgmda_da.nc
    paleo_data_cache/processed/observations/da/lgm_lgmr_da.nc

  Multi-period summaries:
    paleo_data_cache/processed/observations/annual_mean_global_obs.csv
    paleo_data_cache/processed/observations/annual_mean_zonal_obs.csv
    paleo_data_cache/processed/observations/monthly_mean_zonal_obs.csv

Run download_paleo.py first to populate paleo_data_cache/raw/.

Usage:
    python process_paleo.py --source all
    python process_paleo.py --source cmip6 --period lgm
    python process_paleo.py --source cmip6 --period all --skip-cleanup
    python process_paleo.py --source observations
"""

import argparse
import logging
import sys
import zipfile
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import xarray as xr

from paleo_constants import PALEO_DOWNLOADS, PALEO_MODELS, PALEO_PERIODS

RAW_DIR = Path(__file__).parent / "paleo_data_cache" / "raw"
PROCESSED_DIR = Path(__file__).parent / "paleo_data_cache" / "processed"


def setup_logging(log_level: str = "INFO", log_file: Optional[str] = None) -> None:
    handlers = [logging.StreamHandler(sys.stdout)]
    if log_file:
        handlers.append(logging.FileHandler(log_file))
    logging.basicConfig(
        level=getattr(logging, log_level.upper()),
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=handlers,
    )


# ---------------------------------------------------------------------------
# CMIP6 processing
# ---------------------------------------------------------------------------


def _load_netcdf(model_dir: Path) -> Optional[xr.Dataset]:
    nc_files = sorted(model_dir.glob("tas_Amon_*.nc"))
    if not nc_files:
        logging.warning(f"No tas_Amon_*.nc files in {model_dir}")
        return None
    logging.info(f"  Loading {len(nc_files)} file(s) from {model_dir.name}")
    drop_vars = ["time_bnds", "lat_bnds", "lon_bnds", "height"]
    try:
        return xr.open_mfdataset(nc_files, chunks={}).drop_vars(
            drop_vars, errors="ignore"
        )
    except Exception:
        try:
            return xr.open_mfdataset(nc_files, use_cftime=True, chunks={}).drop_vars(
                drop_vars, errors="ignore"
            )
        except Exception as e:
            logging.error(f"  Failed to load {model_dir.name}: {e}")
            return None


def _area_weights(ds: xr.Dataset) -> xr.DataArray:
    w = np.cos(np.deg2rad(ds.lat)).expand_dims({"lon": ds.lon})
    w.name = "areacella"
    return w


def _process_cmip6_model(
    raw_dir: Path, processed_dir: Path, period: str, skip_cleanup: bool
) -> bool:
    ds = _load_netcdf(raw_dir)
    if ds is None:
        return False

    processed_dir.mkdir(parents=True, exist_ok=True)
    try:
        weights = _area_weights(ds)

        xr.merge(
            [
                ds.mean(dim="time"),
                ds.std(dim="time").rename({"tas": "tas_std"}),
                weights.to_dataset(name="weight"),
            ]
        ).to_netcdf(processed_dir / f"{period}_tas_annual.nc")
        logging.info(f"  Saved {period}_tas_annual.nc")

        xr.merge(
            [
                ds.groupby("time.month").mean(),
                ds.groupby("time.month").std().rename({"tas": "tas_std"}),
                weights.to_dataset(name="weight"),
            ]
        ).to_netcdf(processed_dir / f"{period}_tas_monthly.nc")
        logging.info(f"  Saved {period}_tas_monthly.nc")
    except Exception as e:
        logging.error(f"  Processing failed for {raw_dir.name}: {e}")
        return False
    finally:
        ds.close()

    if not skip_cleanup:
        for nc in raw_dir.glob("tas_Amon_*.nc"):
            nc.unlink()

    return True


def process_cmip6(periods: list[str], skip_cleanup: bool) -> None:
    for period in periods:
        models = [m for m in PALEO_MODELS if period in PALEO_DOWNLOADS.get(m, {})]
        logging.info(
            f"\n{'='*60}\n  CMIP6 period: {period}  ({len(models)} models)\n{'='*60}"
        )
        ok = failed = 0
        for model in models:
            raw_dir = RAW_DIR / model
            if not raw_dir.exists():
                logging.warning(f"  {raw_dir} not found — run download_paleo.py first")
                failed += 1
                continue
            logging.info(f"  Processing {model}")
            if _process_cmip6_model(
                raw_dir, PROCESSED_DIR / model, period, skip_cleanup
            ):
                ok += 1
            else:
                failed += 1
        logging.info(f"  {period}: {ok} succeeded, {failed} failed")


# ---------------------------------------------------------------------------
# Observations — sub-processors
# ---------------------------------------------------------------------------


def _parse_holocene(hol_ds: xr.Dataset, var: str) -> xr.Dataset:
    latband = xr.Dataset(
        {
            "tas": (["lat_bnd", "age", "ens"], hol_ds[f"{var}_latbands"].data),
            "lat_bnd_weights": (["lat_bnd"], hol_ds.latband_weights.data),
        },
        coords={
            "lat_bnd": hol_ds["latband_ranges"].data,
            "age": hol_ds.age.data,
            "ens": np.arange(500),
        },
    )
    global_ = xr.Dataset(
        {
            "tas": (
                ["lat_bnd", "age", "ens"],
                hol_ds[f"{var}_globalmean"]
                .expand_dims({"lat_bnds": ["90S_to_90N"]})
                .data,
            ),
            "lat_bnd_weights": (["lat_bnd"], [1]),
        },
        coords={
            "lat_bnd": ["90S_to_90N"],
            "age": hol_ds.age.data,
            "ens": np.arange(500),
        },
    )
    combined = xr.concat([latband, global_], dim="lat_bnd")
    midH = combined.sel(age=slice(4000, 8000)).mean(dim="age")
    return xr.merge(
        [midH.mean(dim="ens"), midH["tas"].std(dim="ens").to_dataset(name="tas_std")]
    )


def _process_lgmda(obs_raw: Path, da_dir: Path) -> xr.Dataset:
    """lgmDA monthly gridded fields → da/lgm_lgmda_da.nc. Returns the combined dataset."""
    lgm_raw = xr.open_dataset(obs_raw / "lgmDA_lgm_ATM_monthly_climo.nc")
    pi_raw = xr.open_dataset(obs_raw / "lgmDA_hol_ATM_monthly_climo.nc")
    ds = xr.Dataset(
        {
            "lgm_tas": (["month", "lat", "lon"], lgm_raw.tas.data),
            "pi_tas": (["month", "lat", "lon"], pi_raw.tas.data),
            "lgm_tas_std": (["month", "lat", "lon"], lgm_raw.tas_std.data),
            "pi_tas_std": (["month", "lat", "lon"], pi_raw.tas_std.data),
        },
        coords={
            "month": np.arange(1, 13),
            "lon": lgm_raw.lon.data,
            "lat": lgm_raw.lat.data,
        },
    )
    ds.to_netcdf(da_dir / "lgm_lgmda_da.nc")
    logging.info("  Saved da/lgm_lgmda_da.nc")
    return ds


def _process_lgmr(obs_raw: Path, da_dir: Path) -> None:
    """Osman et al. 2021 LGMR → da/lgm_lgmr_{sat,sst,gmst}_da.nc.

    All LGMR variables are absolute temperatures (°C). Anomalies are computed
    relative to the pre-industrial reference (100–1000 BP mean).

    SAT and SST live on different grids (96×144 vs 384×320) so they are saved
    as separate files.

    GMST is saved as a full deglaciation time series (anomaly vs PI) so the
    complete 0–26 ka record is available for plotting.
    """
    osman_dir = obs_raw / "osman2021"
    required = osman_dir / "LGMR_SAT_climo.nc"
    if not required.exists():
        logging.warning("  [skip] lgm_lgmr_*_da.nc — LGMR_SAT_climo.nc not found")
        return

    # PI reference: 100–1000 BP (5 youngest 200-yr bins, pre-industrial)
    # LGM window: 19–24 ka BP
    pi_age = slice(100, 1000)
    lgm_age = slice(19000, 24000)

    # --- Gridded files: SAT and SST ---
    for fname, out_name, skip_vars in [
        ("LGMR_SAT_climo.nc", "lgm_lgmr_sat_da.nc", set()),
        ("LGMR_SST_climo.nc", "lgm_lgmr_sst_da.nc", {"tarea"}),
    ]:
        p = osman_dir / fname
        if not p.exists():
            logging.warning(f"  [skip] {out_name} — {fname} not found")
            continue
        ds = xr.open_dataset(p).load()
        pi_mean = ds.sel(age=pi_age).mean(dim="age")
        lgm_mean = ds.sel(age=lgm_age).mean(dim="age")

        out = xr.Dataset()
        for var in ds.data_vars:
            if var in skip_vars:
                out[var] = (
                    ds[var].isel(age=0, drop=True) if "age" in ds[var].dims else ds[var]
                )
            elif var.endswith("_std"):
                # Keep LGM-period ensemble spread; differencing stds is not meaningful
                out[var] = lgm_mean[var]
                out[var].attrs = {**ds[var].attrs, "note": "ensemble spread at LGM"}
            else:
                out[var] = lgm_mean[var] - pi_mean[var]
                out[var].attrs = {
                    **ds[var].attrs,
                    "note": "LGM (19–24 ka) anomaly relative to PI (100–1000 BP)",
                }
        out.to_netcdf(da_dir / out_name)
        logging.info(f"  Saved da/{out_name}")

    # --- GMST: save full time series as anomaly vs PI ---
    gmst_path = osman_dir / "LGMR_GMST_climo.nc"
    if not gmst_path.exists():
        logging.warning("  [skip] lgm_lgmr_gmst_da.nc — LGMR_GMST_climo.nc not found")
        return
    ds = xr.open_dataset(gmst_path).load()
    pi_val = float(ds["gmst"].sel(age=pi_age).mean(dim="age").values)
    out = xr.Dataset(
        {
            "gmst_anom": ds["gmst"] - pi_val,
            "gmst_anom_std": ds["gmst_std"],
            "gmst_abs": ds["gmst"],
        }
    )
    out["gmst_anom"].attrs = {
        "units": "degrees Celsius",
        "long_name": "GMST anomaly relative to PI (100–1000 BP)",
    }
    out["gmst_anom_std"].attrs = ds["gmst_std"].attrs
    out["gmst_abs"].attrs = {**ds["gmst"].attrs, "note": "absolute temperature"}
    out.to_netcdf(da_dir / "lgm_lgmr_gmst_da.nc")
    logging.info("  Saved da/lgm_lgmr_gmst_da.nc")


def _process_ottobliesner_lig(
    obs_raw: Path, proxy_dir: Path
) -> tuple[xr.Dataset, xr.DataArray]:
    """Otto-Bliesner et al. (2021), Clim. Past 17, 63–88 LIG proxy tables →
    proxy/lig127k_ottobliesner_tas_proxy.nc.
    Returns (lig_ds, lig_weights) for use in summary CSVs."""
    lig_dir = obs_raw / "lig127k"
    tables = [
        "Table S2. Annual - NH Oceans, Europe, and Greenland (40-90N)_CP-2019-174.xlsx",
        "Table S3. Annual - Low latitudes (40S-40N)_CP-2019-174.xlsx",
        "Table S4. Annual - SH Oceans and Antarctica (40-90S)_CP-2019-174.xlsx",
    ]
    lig_df = pd.concat([pd.read_excel(lig_dir / t, skiprows=2) for t in tables])
    lig_df["SD"] = lig_df["Anom+1SD"] - lig_df["Anom"]
    lig_ds = (
        lig_df[["Latitude", "Longitude", "Anom", "SD"]]
        .groupby(["Latitude", "Longitude"])
        .mean()
        .to_xarray()
        .rename({"Latitude": "lat", "Longitude": "lon", "Anom": "tas", "SD": "tas_std"})
    )
    lig_ds.to_netcdf(proxy_dir / "lig127k_ottobliesner_tas_proxy.nc")
    logging.info("  Saved proxy/lig127k_ottobliesner_tas_proxy.nc")
    lig_weights = np.cos(np.deg2rad(lig_ds.lat)).expand_dims({"lon": lig_ds.lon})
    return lig_ds, lig_weights


def _process_scussolini(obs_raw: Path, proxy_dir: Path) -> None:
    """Scussolini et al. 2019 LIG precip proxy → proxy/lig127k_scussolini_pr_proxy.csv."""
    xlsx_path = obs_raw / "scussolini2019_lig_precip_proxy.xlsx"
    if not xlsx_path.exists() or xlsx_path.stat().st_size == 0:
        logging.warning(
            "  [skip] proxy/lig127k_scussolini_pr_proxy.csv — file missing or empty"
            " (manual download required, see download_paleo.py)"
        )
        return

    # Data is in the 'Proxy_Database' sheet; 'LatºN' and 'LonºE' are the coords.
    df = pd.read_excel(
        xlsx_path, sheet_name="Proxy_Database", header=0, engine="openpyxl"
    )
    col_lower = {c.lower(): c for c in df.columns}
    lat_col = next((col_lower[k] for k in col_lower if "lat" in k), None)
    lon_col = next((col_lower[k] for k in col_lower if "lon" in k), None)
    if lat_col is None or lon_col is None:
        logging.warning(
            f"  Scussolini xlsx: could not detect lat/lon columns. Found: {list(df.columns)}"
        )
        return

    df.rename(columns={lat_col: "lat", lon_col: "lon"}, inplace=True)
    df.to_csv(proxy_dir / "lig127k_scussolini_pr_proxy.csv", index=False)
    logging.info(f"  Saved proxy/lig127k_scussolini_pr_proxy.csv ({len(df)} records)")


def _process_bartlein2011(obs_raw: Path, proxy_dir: Path) -> None:
    """Bartlein et al. 2011 pollen reconstructions → proxy/lgm_bartlein_proxy.nc
    and proxy/midh_bartlein_proxy.nc.

    The zip contains one NetCDF per variable per period
    ({var}_delta_{06|21}ka_ALL_grid_2x2.nc). Variables are merged into one
    Dataset per period (6ka = midHolocene, 21ka = LGM).
    """
    import tempfile

    zip_path = obs_raw / "bartlein2011_pollen_climate_recon.zip"
    if not zip_path.exists():
        logging.warning("  [skip] Bartlein 2011 — zip not downloaded")
        return

    with zipfile.ZipFile(zip_path) as zf, tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        zf.extractall(tmp_path)

        period_datasets: dict[str, list[xr.Dataset]] = {"06ka": [], "21ka": []}
        for nc_file in sorted(tmp_path.glob("*.nc")):
            name = nc_file.stem  # e.g. mat_delta_06ka_ALL_grid_2x2
            for period in period_datasets:
                if f"_{period}_" in name:
                    period_datasets[period].append(xr.open_dataset(nc_file).load())
                    break

        period_out = {
            "06ka": ("midh_bartlein_proxy.nc", "midH"),
            "21ka": ("lgm_bartlein_proxy.nc", "LGM"),
        }
        for period, datasets in period_datasets.items():
            out_name, label = period_out[period]
            if not datasets:
                logging.warning(f"  Bartlein 2011: no files found for {period}")
                continue
            merged = xr.merge(datasets)
            merged.to_netcdf(proxy_dir / out_name)
            logging.info(
                f"  Saved proxy/{out_name} ({label}, {len(datasets)} variables)"
            )


def _process_hansen_deeptime(obs_raw: Path, proxy_dir: Path) -> None:
    """Tierney THansenMethod.csv → proxy/deeptime_hansen_proxy.csv."""
    csv_path = obs_raw / "THansenMethod.csv"
    if not csv_path.exists():
        logging.warning(
            "  [skip] proxy/deeptime_hansen_proxy.csv — THansenMethod.csv not found"
        )
        return
    pd.read_csv(csv_path).to_csv(proxy_dir / "deeptime_hansen_proxy.csv", index=False)
    logging.info("  Saved proxy/deeptime_hansen_proxy.csv")


def _process_sisal(obs_raw: Path, proxy_dir: Path) -> None:
    """Extract SISAL v3 speleothem database zips into proxy/sisal_v3/."""
    sisal_raw = obs_raw / "sisal_v3"
    sisal_proc = proxy_dir / "sisal_v3"

    for fname in ["sisalv3_database_mysql_csv.zip", "sisalv3_codes.zip"]:
        zip_path = sisal_raw / fname
        if not zip_path.exists():
            logging.warning(f"  [skip] sisal_v3 — {fname} not found")
            continue
        dest = sisal_proc / fname.replace(".zip", "")
        if dest.exists():
            logging.info(f"  [skip] {fname} already extracted")
            continue
        dest.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(dest)
        logging.info(f"  Extracted {fname} → proxy/sisal_v3/{dest.name}/")


# ---------------------------------------------------------------------------
# Observations — top-level orchestrator
# ---------------------------------------------------------------------------


def process_observations() -> None:
    obs_raw = RAW_DIR / "observations"
    obs_proc = PROCESSED_DIR / "observations"
    proxy_dir = obs_proc / "proxy"
    da_dir = obs_proc / "da"

    for d in (obs_proc, proxy_dir, da_dir):
        d.mkdir(parents=True, exist_ok=True)

    # ---- Data assimilation ----
    logging.info("Processing LGM lgmDA (data assimilation)")
    lgmda_ds = _process_lgmda(obs_raw, da_dir)

    logging.info("Processing LGM Osman 2021 LGMR (data assimilation)")
    _process_lgmr(obs_raw, da_dir)

    # ---- Proxy ----
    logging.info("Processing LIG Otto-Bliesner et al. 2021 temperature proxy")
    lig_ds, lig_weights = _process_ottobliesner_lig(obs_raw, proxy_dir)

    logging.info("Processing LIG Scussolini et al. 2019 precipitation proxy")
    _process_scussolini(obs_raw, proxy_dir)

    logging.info("Processing Bartlein et al. 2011 pollen reconstructions (LGM + midH)")
    _process_bartlein2011(obs_raw, proxy_dir)

    logging.info("Processing deep-time Hansen reconstruction")
    _process_hansen_deeptime(obs_raw, proxy_dir)

    logging.info("Extracting SISAL v3 speleothem database")
    _process_sisal(obs_raw, proxy_dir)

    # ---- Mid Holocene (Temp12k) — needed for summary CSVs ----
    logging.info("Processing Mid Holocene Temp12k (Kaufman et al. 2020)")
    hol_ds = xr.open_dataset(obs_raw / "temp12k_alldata.nc").load()
    midH_scc = _parse_holocene(hol_ds, "scc")

    # ---- Derived LGM anomaly fields for summaries ----
    lgm_ds = (lgmda_ds["lgm_tas"] - lgmda_ds["pi_tas"]).to_dataset(name="tas")
    lgm_ds["tas_std"] = lgmda_ds["lgm_tas_std"]
    lgm_annual = lgm_ds.mean(dim="month")
    lgm_weights = np.cos(np.deg2rad(lgm_annual.lat)).expand_dims(
        {"lon": lgm_annual.lon}
    )

    # ---- Global mean annual CSV (all periods) ----
    logging.info("Building annual_mean_global_obs.csv")
    paleo_avgs = pd.read_csv(obs_raw / "Figure7_19_obs.csv", skiprows=2)
    midH_global = midH_scc.sel(lat_bnd="90S_to_90N")
    midH_mean = float(midH_global["tas"].values)
    midH_std = float(midH_global["tas_std"].values)
    lig_zmean = lig_ds.weighted(lig_weights).mean()
    lig_mean = float(lig_zmean["tas"].values)
    lig_std = float(lig_zmean["tas_std"].values)

    paleo_avgs = pd.concat(
        [
            paleo_avgs,
            pd.DataFrame(
                {
                    "Time Period": ["midHolocene"],
                    "min temperature [degreesC]": [midH_mean - midH_std],
                    "mean temperature [degreesC]": [midH_mean],
                    "max temperature [degreesC]": [midH_mean + midH_std],
                }
            ),
            pd.DataFrame(
                {
                    "Time Period": ["lig127k"],
                    "min temperature [degreesC]": [lig_mean - lig_std],
                    "mean temperature [degreesC]": [lig_mean],
                    "max temperature [degreesC]": [lig_mean + lig_std],
                }
            ),
        ]
    )
    paleo_avgs["error [degreesC]"] = (
        paleo_avgs["max temperature [degreesC]"]
        - paleo_avgs["mean temperature [degreesC]"]
    )
    paleo_avgs = paleo_avgs[
        ~paleo_avgs["Time Period"].isin(["Historical", "post 1975"])
    ]
    paleo_avgs["period_idx"] = [3, 1, 0, 4, 2]
    paleo_avgs = paleo_avgs.sort_values("period_idx")
    paleo_avgs["period"] = [
        "eocene",
        "midPliocene-eoi400",
        "lig127k",
        "lgm",
        "midHolocene",
    ]
    (
        paleo_avgs.rename(
            columns={
                "mean temperature [degreesC]": "tas_anom",
                "error [degreesC]": "error",
            }
        )[["tas_anom", "error", "period", "period_idx"]].to_csv(
            obs_proc / "annual_mean_global_obs.csv"
        )
    )
    logging.info("Saved annual_mean_global_obs.csv")

    # ---- Zonal mean annual CSV ----
    logging.info("Building annual_mean_zonal_obs.csv")
    regions = {
        "global": [-90, 90],
        "northern_hemisphere": [0, 90],
        "tropics": [-30, 30],
        "southern_hemisphere": [-90, 0],
    }
    regions_midH = {
        "global": ["90S_to_90N"],
        "northern_hemisphere": ["0N_to_30N", "30N_to_60N", "60N_to_90N"],
        "tropics": ["30S_to_0S", "0N_to_30N"],
        "southern_hemisphere": ["30S_to_0S", "60S_to_30S", "90S_to_60S"],
    }
    rows = []
    for region, (lat_min, lat_max) in regions.items():
        lig_sl = lig_ds.sel(lat=slice(lat_min, lat_max))
        lig_w = lig_weights.sel(lat=slice(lat_min, lat_max))
        lgm_sl = lgm_annual.sel(lat=slice(lat_min, lat_max))
        lgm_w = lgm_weights.sel(lat=slice(lat_min, lat_max))
        midH_sl = midH_scc.sel(lat_bnd=regions_midH[region])

        for period, tas, err in [
            (
                "lig127k",
                float(
                    lig_sl["tas"]
                    .weighted(lig_w.fillna(0))
                    .mean(dim=["lat", "lon"])
                    .values
                ),
                float(
                    lig_sl["tas_std"]
                    .weighted(lig_w.fillna(0))
                    .mean(dim=["lat", "lon"])
                    .values
                ),
            ),
            (
                "lgm",
                float(
                    lgm_sl["tas"]
                    .weighted(lgm_w.fillna(0))
                    .mean(dim=["lat", "lon"])
                    .values
                ),
                float(
                    lgm_sl["tas_std"]
                    .weighted(lgm_w.fillna(0))
                    .mean(dim=["lat", "lon"])
                    .values
                ),
            ),
            (
                "midHolocene",
                float(
                    midH_sl["tas"]
                    .weighted(midH_sl["lat_bnd_weights"].fillna(0))
                    .mean(dim=["lat_bnd"])
                    .values
                ),
                float(
                    midH_sl["tas_std"]
                    .weighted(midH_sl["lat_bnd_weights"].fillna(0))
                    .mean(dim=["lat_bnd"])
                    .values
                ),
            ),
        ]:
            rows.append(
                {"period": period, "region": region, "tas_anom": tas, "error": err}
            )

    pd.DataFrame(rows).to_csv(obs_proc / "annual_mean_zonal_obs.csv", index=False)
    logging.info("Saved annual_mean_zonal_obs.csv")

    # ---- Monthly zonal CSV (LGM lgmDA — only dataset with monthly resolution) ----
    logging.info("Building monthly_mean_zonal_obs.csv")
    rows = []
    for region, (lat_min, lat_max) in regions.items():
        lgm_sl = lgm_ds.sel(lat=slice(lat_min, lat_max))
        lgm_w = lgm_weights.sel(lat=slice(lat_min, lat_max))
        tas_df = (
            lgm_sl["tas"]
            .weighted(lgm_w.fillna(0))
            .mean(dim=["lat", "lon"])
            .to_dataframe()
            .reset_index()
        )
        std_df = (
            lgm_sl["tas_std"]
            .weighted(lgm_w.fillna(0))
            .mean(dim=["lat", "lon"])
            .to_dataframe()
            .reset_index()
        )
        df = pd.merge(tas_df, std_df, on="month").rename(
            columns={"tas": "tas_anom", "tas_std": "error"}
        )
        df["region"] = region
        df["period"] = "lgm"
        rows.append(df)
    pd.concat(rows).to_csv(obs_proc / "monthly_mean_zonal_obs.csv", index=False)
    logging.info("Saved monthly_mean_zonal_obs.csv")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Process raw paleoclimate data into a unified dataset.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--source",
        choices=["cmip6", "observations", "all"],
        required=True,
        help="Which data to process",
    )
    parser.add_argument(
        "--period",
        default="all",
        help="CMIP6 period or 'all' (only used with --source cmip6/all)",
    )
    parser.add_argument(
        "--skip-cleanup",
        action="store_true",
        help="Keep raw tas_Amon_*.nc files after CMIP6 processing",
    )
    parser.add_argument(
        "--log-level", choices=["DEBUG", "INFO", "WARNING", "ERROR"], default="INFO"
    )
    parser.add_argument("--log-file", type=str)
    args = parser.parse_args()

    setup_logging(args.log_level, args.log_file)

    if args.source in ("cmip6", "all"):
        periods = PALEO_PERIODS if args.period == "all" else [args.period]
        invalid = [p for p in periods if p not in PALEO_PERIODS]
        if invalid:
            parser.error(f"Unknown period(s): {invalid}")
        process_cmip6(periods, args.skip_cleanup)

    if args.source in ("observations", "all"):
        logging.info(f"\n{'='*60}\n  Observations\n{'='*60}")
        process_observations()


if __name__ == "__main__":
    main()
