"""
Process raw paleoclimate observational data into standardized, period-sorted files.

Output structure — all under paleo_data_cache/processed/observations/
  lgm/
    lgmDA_v2.1_tas.nc          lgmDA LGM climatology + Holocene PI reference + anomaly
    LGMR_SAT_tas.nc            LGMR LGM surface air temperature anomaly (Osman et al. 2021)
    LGMR_SST_tos.nc            LGMR LGM sea surface temperature anomaly (Osman et al. 2021)
    Bartlein2011_tas.nc        Pollen-based LGM MAT anomaly (Bartlein et al. 2011)
    Bartlein2011_pr.nc         Pollen-based LGM MAP anomaly (Bartlein et al. 2011)
  midHolocene/
    Bartlein2011_tas.nc        Pollen-based mid-Holocene MAT anomaly
    Bartlein2011_pr.nc         Pollen-based mid-Holocene MAP anomaly
    Temp12k_tas.nc             Holocene temperature reconstruction (Kaufman et al. 2020)
  lig127k/
    OttoBliesner2021_tas.nc    LIG proxy temperature anomalies (Otto-Bliesner et al. 2021)
    Scussolini2019_pr.nc       LIG boreal precipitation proxy (Scussolini et al. 2019)
  multi_period/
    ipcc_ar6_fig7_19.csv       Global mean temperature anomalies (IPCC AR6)
    tierney2020_global_tas.csv Deep-time global mean temperature (Tierney et al. 2020)

Each NetCDF carries global attributes: source, doi, source_url, variable, units, period,
anomaly_ref (where applicable), and processing_date.

Variable naming conventions (matched to paleo_benchmark.py):
  tas, tas_std, tas_sig_val   surface air temperature, uncertainty, significance flag
  pr, pr_std, pr_sig_val      precipitation anomaly, uncertainty, significance flag
  pr_reliability              semi-quantitative reliability score (Scussolini only)
  pi_tas                      pre-industrial (Holocene) monthly tas (lgmDA only)
  tos, tos_std                sea surface temperature, uncertainty

Usage:
    python process_paleo_observations.py
    python process_paleo_observations.py --source lgmda bartlein2011
    python process_paleo_observations.py --source all --log-level DEBUG
    python process_paleo_observations.py --delete-raw
"""

import argparse
import logging
import shutil
import sys
import tempfile
import zipfile
from datetime import date
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import xarray as xr

PALEO_DIR = Path(__file__).parent
RAW_DIR = PALEO_DIR / "paleo_data_cache" / "raw" / "observations"
OBS_PROC = PALEO_DIR / "paleo_data_cache" / "processed" / "observations"

PROCESSING_DATE = date.today().isoformat()

# LGM age window (years BP) used to average the LGMR reanalysis
LGM_AGE_MIN = 19_000
LGM_AGE_MAX = 23_000


# ---------------------------------------------------------------------------
# Metadata / IO helpers
# ---------------------------------------------------------------------------


def _write_nc(ds: xr.Dataset, path: Path, attrs: dict) -> None:
    """Write dataset to NetCDF with standardised global attributes."""
    attrs.setdefault("processing_date", PROCESSING_DATE)
    ds.attrs = attrs
    path.parent.mkdir(parents=True, exist_ok=True)
    path.unlink(missing_ok=True)
    ds.to_netcdf(path)
    logging.info(f"  Saved {path.relative_to(PALEO_DIR)}")


def _write_csv(df: pd.DataFrame, path: Path, comment_lines: list[str]) -> None:
    """Write CSV with comment-header lines documenting provenance."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        for line in comment_lines:
            f.write(f"# {line}\n")
        df.to_csv(f, index=False)
    logging.info(f"  Saved {path.relative_to(PALEO_DIR)}  ({len(df)} rows)")


# ---------------------------------------------------------------------------
# IPCC AR6 Figure 7.19
# ---------------------------------------------------------------------------


def _process_ipcc_ar6(raw: Path, proc: Path) -> None:
    """Multi-period global mean temperature anomalies → multi_period/ipcc_ar6_fig7_19.csv"""
    p = raw / "Figure7_19_obs.csv"
    if not p.exists():
        logging.warning("  [skip] ipcc_ar6 — Figure7_19_obs.csv not found")
        return

    df = pd.read_csv(p, header=2)
    df.columns = ["time_period", "tas_min_anom", "tas_anom", "tas_max_anom"]
    df["units"] = "K"

    _write_csv(
        df,
        proc / "multi_period" / "ipcc_ar6_fig7_19.csv",
        [
            "source: IPCC AR6 Figure 7.19",
            "source_url: https://dap.ceda.ac.uk/badc/ar6_wg1/data/ch_07/ch7_fig19/",
            "variable: tas anomaly relative to pre-industrial",
            "units: K",
            "periods: Eocene, Pliocene, LGM, and others",
            f"processing_date: {PROCESSING_DATE}",
        ],
    )


# ---------------------------------------------------------------------------
# Tierney 2020 deep-time reconstruction
# ---------------------------------------------------------------------------


def _process_tierney2020(raw: Path, proc: Path) -> None:
    """Deep-time global mean TAS timeseries → multi_period/tierney2020_global_tas.csv"""
    p = raw / "THansenMethod.csv"
    if not p.exists():
        logging.warning("  [skip] tierney2020 — THansenMethod.csv not found")
        return

    df = pd.read_csv(p)
    df.columns = ["age_Ma", "tas_degC"]
    df["units"] = "degC"

    _write_csv(
        df,
        proc / "multi_period" / "tierney2020_global_tas.csv",
        [
            "source: Tierney et al. (2020) Hansen-method deep-time reconstruction",
            "source_url: https://github.com/jesstierney/PastClimates",
            "variable: global mean surface temperature",
            "units: degC (relative to pre-industrial)",
            "age_Ma: millions of years before present",
            f"processing_date: {PROCESSING_DATE}",
        ],
    )


# ---------------------------------------------------------------------------
# lgmDA — LGM data assimilation (Tierney et al. 2020)
# ---------------------------------------------------------------------------


def _process_lgmda(raw: Path, proc: Path) -> None:
    """lgmDA → lgm/lgmDA_v2.1_tas.nc with pi_tas, tas (anomaly), tas_std.

    Also writes multi_period/lgmDA_v2.1_holocene_tas.nc as a standalone
    Holocene PI reference for use in anomaly computation across all periods.
    """
    path_hol = raw / "lgmDA_hol_ATM_monthly_climo.nc"
    path_lgm = raw / "lgmDA_lgm_ATM_monthly_climo.nc"
    if not path_hol.exists() or not path_lgm.exists():
        logging.warning("  [skip] lgmda — raw files not found")
        return

    def _load_lgmda(path: Path) -> xr.Dataset:
        ds = xr.open_dataset(path).load()
        return (
            ds.swap_dims({"nmonth": "nMonth"})
            .set_index({"nLat": "lat", "nLon": "lon", "nMonth": "month"})
            .rename({"nLat": "lat", "nLon": "lon", "nMonth": "month"})
        )

    ds_hol = _load_lgmda(path_hol)
    ds_lgm = _load_lgmda(path_lgm)

    # --- lgm/lgmDA_v2.1_tas.nc ---
    # pi_tas: Holocene monthly climatology (absolute)
    # tas:    LGM − Holocene monthly anomaly
    # tas_std: LGM posterior standard deviation
    lgm_ds = xr.Dataset(
        {
            "pi_tas": ds_hol["tas"],  # Holocene monthly clim
            "tas": ds_lgm["tas"] - ds_hol["tas"],  # LGM anomaly
            "tas_std": ds_lgm["tas_std"],  # LGM uncertainty
        }
    )
    _write_nc(
        lgm_ds,
        proc / "lgm" / "lgmDA_v2.1_tas.nc",
        {
            "source": "Tierney et al. (2020)",
            "doi": "10.1038/s41586-020-2617-x",
            "source_url": "https://github.com/jesstierney/lgmDA",
            "variable": "tas",
            "units": "K",
            "period": "lgm",
            "anomaly_ref": "Holocene (lgmDA v2.0)",
            "pi_tas_description": "Holocene (PI) monthly mean surface air temperature (absolute)",
            "tas_description": "LGM − Holocene monthly surface air temperature anomaly",
            "tas_std_description": "LGM posterior 1-sigma uncertainty",
        },
    )

    # --- multi_period/lgmDA_v2.1_holocene_tas.nc ---
    # Standalone Holocene reference file used as PI baseline for all periods
    hol_ds = ds_hol[["tas", "tas_std"]].rename(
        {"tas": "pi_tas", "tas_std": "pi_tas_std"}
    )
    _write_nc(
        hol_ds,
        proc / "multi_period" / "lgmDA_v2.1_holocene_tas.nc",
        {
            "source": "Tierney et al. (2020)",
            "doi": "10.1038/s41586-020-2617-x",
            "source_url": "https://github.com/jesstierney/lgmDA",
            "variable": "tas",
            "units": "K",
            "period": "Holocene (PI reference)",
            "description": "Holocene monthly mean surface air temperature — PI reference for anomaly computation",
        },
    )


# ---------------------------------------------------------------------------
# LGMR SAT (Osman et al. 2021)
# ---------------------------------------------------------------------------


def _process_lgmr_sat(raw: Path, proc: Path) -> None:
    """LGMR SAT → lgm/LGMR_SAT_tas.nc (LGM-window mean, lat/lon grid)."""
    p = raw / "osman2021" / "LGMR_SAT_climo.nc"
    if not p.exists():
        logging.warning("  [skip] lgmr_sat — LGMR_SAT_climo.nc not found")
        return

    ds = xr.open_dataset(p).load()

    # Average over the LGM age window
    lgm_mask = (ds.age >= LGM_AGE_MIN) & (ds.age <= LGM_AGE_MAX)
    ds_lgm = ds.sel(age=lgm_mask).mean(dim="age")
    n_ages = int(lgm_mask.sum())
    logging.info(
        f"  LGMR SAT: averaged over {n_ages} age slices ({LGM_AGE_MIN}–{LGM_AGE_MAX} BP)"
    )

    out_ds = xr.Dataset({"tas": ds_lgm["sat"], "tas_std": ds_lgm["sat_std"]})
    _write_nc(
        out_ds,
        proc / "lgm" / "LGMR_SAT_tas.nc",
        {
            "source": "Osman et al. (2021)",
            "doi": "10.1038/s41586-021-03984-4",
            "source_url": "https://www.ncei.noaa.gov/pub/data/paleo/reconstructions/osman2021/",
            "variable": "tas",
            "units": "degC",
            "period": "lgm",
            "anomaly_ref": "modern (LGMR reanalysis internal reference)",
            "lgm_age_window_BP": f"{LGM_AGE_MIN}–{LGM_AGE_MAX}",
        },
    )


# ---------------------------------------------------------------------------
# LGMR SST (Osman et al. 2021)
# ---------------------------------------------------------------------------


def _process_lgmr_sst(raw: Path, proc: Path) -> None:
    """LGMR SST → lgm/LGMR_SST_tos.nc (2D curvilinear lat/lon grid)."""
    p = raw / "osman2021" / "LGMR_SST_climo.nc"
    if not p.exists():
        logging.warning("  [skip] lgmr_sst — LGMR_SST_climo.nc not found")
        return

    ds = xr.open_dataset(p).load()

    # Average over the LGM age window
    lgm_mask = (ds.age >= LGM_AGE_MIN) & (ds.age <= LGM_AGE_MAX)
    ds_lgm = ds.sel(age=lgm_mask).mean(dim="age")

    # The SST grid has 2D lat/lon; promote them to proper coordinates
    lat_2d = ds_lgm["lat"].values
    lon_2d = ds_lgm["lon"].values
    ds_lgm = ds_lgm.drop_vars(["lat", "lon"])
    ds_lgm = ds_lgm.rename({"lat": "y", "lon": "x"})
    ny, nx = lat_2d.shape
    ds_lgm = ds_lgm.assign_coords(y=np.arange(ny), x=np.arange(nx))
    ds_lgm = ds_lgm.assign_coords(
        lat=xr.DataArray(lat_2d, dims=["y", "x"]),
        lon=xr.DataArray(lon_2d, dims=["y", "x"]),
    )
    if "nEns" in ds_lgm:
        ds_lgm = ds_lgm.drop_vars("nEns")

    # Roll x so longitude starts near 0° (raw grid starts at ~320°)
    roll_by = int(np.argmin(ds_lgm["lon"].values[ny // 2, :]))
    ds_lgm = ds_lgm.roll(x=-roll_by, roll_coords=False)
    ds_lgm = ds_lgm.assign_coords(x=np.arange(nx))

    out_ds = xr.Dataset({"tos": ds_lgm["sst"], "tos_std": ds_lgm["sst_std"]})
    _write_nc(
        out_ds,
        proc / "lgm" / "LGMR_SST_tos.nc",
        {
            "source": "Osman et al. (2021)",
            "doi": "10.1038/s41586-021-03984-4",
            "source_url": "https://www.ncei.noaa.gov/pub/data/paleo/reconstructions/osman2021/",
            "variable": "tos",
            "units": "degC",
            "period": "lgm",
            "anomaly_ref": "modern (LGMR reanalysis internal reference)",
            "grid": "curvilinear 2D lat/lon (y, x dimensions)",
            "lgm_age_window_BP": f"{LGM_AGE_MIN}–{LGM_AGE_MAX}",
        },
    )


# ---------------------------------------------------------------------------
# Bartlein et al. 2011
# ---------------------------------------------------------------------------

_BARTLEIN_PERIOD_MAP = {
    "06ka": ("midHolocene", "MIDH"),
    "21ka": ("lgm", "LGM"),
}


def _extract_bartlein_zip(raw: Path) -> Optional[Path]:
    """Extract the Bartlein zip to a temp-like subdirectory; return path or None."""
    zp = raw / "bartlein2011_pollen_climate_recon.zip"
    if not zp.exists():
        logging.warning("  [skip] bartlein2011 — zip not found")
        return None
    dest = raw / "bartlein2011"
    if dest.exists():
        # Already extracted
        return dest
    dest.mkdir()
    with zipfile.ZipFile(zp) as zf:
        zf.extractall(dest)
    return dest


def _process_bartlein2011(raw: Path, proc: Path) -> None:
    """Bartlein → lgm/Bartlein2011_{tas,pr}.nc and midHolocene/Bartlein2011_{tas,pr}.nc"""
    bart_dir = _extract_bartlein_zip(raw)
    if bart_dir is None:
        return

    per_period: dict[str, dict[str, xr.Dataset]] = {}

    for ka, (period_dir, period_label) in _BARTLEIN_PERIOD_MAP.items():
        mat_file = bart_dir / f"mat_delta_{ka}_ALL_grid_2x2.nc"
        map_file = bart_dir / f"map_delta_{ka}_ALL_grid_2x2.nc"

        if not mat_file.exists() or not map_file.exists():
            logging.warning(f"  [skip] bartlein2011 {ka} — NC files not found in zip")
            continue

        ds_mat = xr.open_dataset(mat_file)
        ds_map = xr.open_dataset(map_file)

        tas_ds = xr.Dataset(
            {
                "tas": ds_mat["mat_anm_mean"],
                "tas_std": ds_mat["mat_se_mean"],
                "tas_sig_val": ds_mat["mat_sig"],
            }
        )
        pr_ds = xr.Dataset(
            {
                "pr": ds_map["map_anm_mean"],
                "pr_std": ds_map["map_se_mean"],
                "pr_sig_val": ds_map["map_sig"],
            }
        )

        common_attrs = {
            "source": "Bartlein et al. (2011)",
            "doi": "10.1007/s00382-010-0904-1",
            "source_url": "https://static-content.springer.com/esm/art%3A10.1007%2Fs00382-010-0904-1/",
            "period": period_dir,
            "processing_date": PROCESSING_DATE,
        }

        _write_nc(
            tas_ds,
            proc / period_dir / "Bartlein2011_tas.nc",
            {
                **common_attrs,
                "variable": "tas",
                "units": "K (anomaly relative to pre-industrial)",
                "tas_description": "Mean Annual Temperature anomaly (mat_anm_mean)",
                "tas_std_description": "Standard error of MAT anomaly (mat_se_mean)",
                "tas_sig_val_description": "Significance flag: non-zero = significant",
            },
        )
        _write_nc(
            pr_ds,
            proc / period_dir / "Bartlein2011_pr.nc",
            {
                **common_attrs,
                "variable": "pr",
                "units": "mm/yr (anomaly relative to pre-industrial)",
                "pr_description": "Mean Annual Precipitation anomaly (map_anm_mean)",
                "pr_std_description": "Standard error of MAP anomaly (map_se_mean)",
                "pr_sig_val_description": "Significance flag: non-zero = significant",
            },
        )


# ---------------------------------------------------------------------------
# Temp12k (Kaufman et al. 2020)
# ---------------------------------------------------------------------------


def _process_temp12k(raw: Path, proc: Path) -> None:
    """Temp12k → midHolocene/Temp12k_tas.nc (latitudinal band reconstructions)."""
    p = raw / "temp12k_alldata.nc"
    if not p.exists():
        logging.warning("  [skip] temp12k — temp12k_alldata.nc not found")
        return

    ds = xr.open_dataset(p).load()

    ds_all = ds.set_coords(["age", "latband_ranges"]).swap_dims(
        {"latbands": "latband_ranges"}
    )
    ds_latbnds = ds_all.drop_vars(
        [
            "scc_globalmean",
            "dcc_globalmean",
            "gam_globalmean",
            "cps_globalmean",
            "pai_globalmean",
        ]
    )
    ds_glob = ds_all[
        [
            "scc_globalmean",
            "dcc_globalmean",
            "gam_globalmean",
            "cps_globalmean",
            "pai_globalmean",
        ]
    ]
    ds_glob = ds_glob.expand_dims({"latband_ranges": ["90S_to_90N"]}).rename(
        {
            "scc_globalmean": "scc_latbands",
            "dcc_globalmean": "dcc_latbands",
            "gam_globalmean": "gam_latbands",
            "cps_globalmean": "cps_latbands",
            "pai_globalmean": "pai_latbands",
        }
    )
    ds_all = xr.concat([ds_latbnds, ds_glob], dim="latband_ranges")

    dataset_list = []
    for var in ds_all.data_vars:
        if var != "latband_weights":
            ds_temp = ds_all[var].expand_dims(
                {"reconstruct_method": [var.split("_")[0]]}
            )
            dataset_list.append(ds_temp.to_dataset(name="tas_anom"))

    ds_new = xr.concat(dataset_list, dim="reconstruct_method")
    ds_new = xr.merge([ds_new, ds_all[["latband_weights"]]])

    _write_nc(
        ds_new,
        proc / "midHolocene" / "Temp12k_tas.nc",
        {
            "source": "Kaufman et al. (2020)",
            "doi": "10.1038/s41597-020-0530-7",
            "source_url": "https://www.ncei.noaa.gov/pub/data/paleo/reconstructions/kaufman2020/",
            "variable": "tas",
            "units": "K (anomaly relative to pre-industrial)",
            "period": "midHolocene",
            "description": "Holocene latitudinal band surface temperature reconstructions (5 methods)",
            "methods": "scc, dcc, gam, cps, pai",
        },
    )


# ---------------------------------------------------------------------------
# Otto-Bliesner et al. 2021 (LIG127k)
# ---------------------------------------------------------------------------


def _process_ottobliesner2021(raw: Path, proc: Path) -> None:
    """Otto-Bliesner → lig127k/OttoBliesner2021_tas.nc (site-dimension NetCDF)."""
    lig_dir = raw / "lig127k"
    tables = [
        "Table S2. Annual - NH Oceans, Europe, and Greenland (40-90N)_CP-2019-174.xlsx",
        "Table S3. Annual - Low latitudes (40S-40N)_CP-2019-174.xlsx",
        "Table S4. Annual - SH Oceans and Antarctica (40-90S)_CP-2019-174.xlsx",
    ]
    columns_needed = ["Latitude", "Longitude", "Anom-1SD", "Anom", "Anom+1SD"]

    frames = []
    for t in tables:
        p = lig_dir / t
        if p.exists():
            df = pd.read_excel(p, header=2)[columns_needed]
            frames.append(df)
        else:
            logging.warning(f"  Otto-Bliesner: {t} not found")

    if not frames:
        logging.warning("  [skip] ottobliesner2021 — no table files found")
        return

    df = pd.concat(frames, ignore_index=True).dropna(subset=["Anom"])
    n = len(df)

    # 1-sigma = average of upper and lower 1SD bounds
    tas = df["Anom"].values.astype(float)
    tas_std = ((df["Anom+1SD"] - df["Anom-1SD"]) / 2.0).values.astype(float)

    ds = xr.Dataset(
        {
            "tas": xr.DataArray(tas, dims=["site"]),
            "tas_std": xr.DataArray(tas_std, dims=["site"]),
        },
        coords={
            "lat": xr.DataArray(df["Latitude"].values.astype(float), dims=["site"]),
            "lon": xr.DataArray(df["Longitude"].values.astype(float), dims=["site"]),
        },
    )
    _write_nc(
        ds,
        proc / "lig127k" / "OttoBliesner2021_tas.nc",
        {
            "source": "Otto-Bliesner et al. (2021)",
            "doi": "10.5194/cp-17-63-2021",
            "source_url": "https://cp.copernicus.org/articles/17/63/2021/",
            "variable": "tas",
            "units": "K (anomaly relative to pre-industrial)",
            "period": "lig127k",
            "n_sites": n,
            "tas_description": "Annual mean temperature anomaly (Anom column)",
            "tas_std_description": "1-sigma = (Anom+1SD − Anom−1SD) / 2",
            "tables_used": "S2 (NH), S3 (Tropics), S4 (SH)",
        },
    )


# ---------------------------------------------------------------------------
# Scussolini et al. 2019 (LIG precipitation)
# ---------------------------------------------------------------------------


def _process_scussolini2019(raw: Path, proc: Path) -> None:
    """Scussolini → lig127k/Scussolini2019_pr.nc (site-dimension NetCDF)."""
    p = raw / "scussolini2019_lig_precip_proxy.xlsx"
    if not p.exists():
        logging.warning(
            "  [skip] scussolini2019 — file not found. "
            "Run download_paleo_observations.py --dataset scussolini2019 and follow instructions."
        )
        return

    df = pd.read_excel(p, sheet_name="Proxy_Database", header=0)

    lat_col = "LatºN"
    lon_col = "LonºE"
    pr_col = "Quantitative signal of ΔP (mm)"
    rel_col = "Reliability score"

    # Keep only rows with valid lat/lon
    df = df.dropna(subset=[lat_col, lon_col])
    n_total = len(df)

    # pr_col may be missing/NaN for sites without quantitative estimates
    if pr_col not in df.columns:
        logging.warning("  [skip] scussolini2019 — quantitative ΔP column not found")
        return

    pr = df[pr_col].values.astype(float)
    reliability = (
        df[rel_col].values.astype(float) if rel_col in df.columns else np.ones(n_total)
    )

    ds = xr.Dataset(
        {
            "pr": xr.DataArray(pr, dims=["site"]),
            "pr_reliability": xr.DataArray(reliability, dims=["site"]),
        },
        coords={
            "lat": xr.DataArray(df[lat_col].values.astype(float), dims=["site"]),
            "lon": xr.DataArray(df[lon_col].values.astype(float), dims=["site"]),
        },
    )
    n_quant = int(np.isfinite(pr).sum())
    _write_nc(
        ds,
        proc / "lig127k" / "Scussolini2019_pr.nc",
        {
            "source": "Scussolini et al. (2019)",
            "doi": "10.1126/sciadv.aax7047",
            "source_url": "https://www.science.org/doi/10.1126/sciadv.aax7047",
            "variable": "pr",
            "units": "mm (annual precipitation anomaly relative to present)",
            "period": "lig127k",
            "n_sites_total": n_total,
            "n_sites_quantitative": n_quant,
            "pr_description": "Quantitative annual precipitation anomaly (ΔP mm); NaN = qualitative only",
            "pr_reliability_description": (
                "Reliability score (0–2): 0=low, 1=moderate, 2=high. "
                "Benchmark uses σ=300 mm/yr for score 1, σ=150 mm/yr for score ≥2"
            ),
        },
    )


# ---------------------------------------------------------------------------
# Source registry
# ---------------------------------------------------------------------------

SOURCE_REGISTRY: dict[str, tuple[str, callable]] = {
    "ipcc_ar6": (
        "IPCC AR6 Fig 7.19 multi-period global mean anomalies",
        _process_ipcc_ar6,
    ),
    "tierney2020": (
        "Tierney et al. 2020 deep-time global mean TAS",
        _process_tierney2020,
    ),
    "lgmda": (
        "lgmDA v2.1 — LGM data assimilation (Tierney et al. 2020)",
        _process_lgmda,
    ),
    "lgmr_sat": (
        "LGMR SAT — LGM surface air temp (Osman et al. 2021)",
        _process_lgmr_sat,
    ),
    "lgmr_sst": (
        "LGMR SST — LGM sea surface temp (Osman et al. 2021)",
        _process_lgmr_sst,
    ),
    "bartlein2011": (
        "Bartlein et al. 2011 pollen-based LGM/mid-Hol recon",
        _process_bartlein2011,
    ),
    "temp12k": (
        "Temp12k — Holocene lat-band reconstruction (Kaufman 2020)",
        _process_temp12k,
    ),
    "ottobliesner2021": (
        "Otto-Bliesner et al. 2021 LIG127k proxy temperatures",
        _process_ottobliesner2021,
    ),
    "scussolini2019": (
        "Scussolini et al. 2019 LIG boreal precipitation proxy",
        _process_scussolini2019,
    ),
}


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def process_observations(
    source_names: list[str],
    delete_raw: bool = False,
) -> None:
    OBS_PROC.mkdir(parents=True, exist_ok=True)
    for period_dir in ("lgm", "midHolocene", "lig127k", "multi_period"):
        (OBS_PROC / period_dir).mkdir(exist_ok=True)

    for name in source_names:
        description, fn = SOURCE_REGISTRY[name]
        logging.info(f"\n[{name}] {description}")
        try:
            fn(RAW_DIR, OBS_PROC)
        except Exception as exc:
            logging.error(f"  Error processing {name}: {exc}", exc_info=True)

    if delete_raw:
        shutil.rmtree(RAW_DIR)
        logging.info(f"  Deleted {RAW_DIR}")


def setup_logging(log_level: str = "INFO", log_file: Optional[str] = None) -> None:
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    if log_file:
        handlers.append(logging.FileHandler(log_file))
    logging.basicConfig(
        level=getattr(logging, log_level.upper()),
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=handlers,
        force=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Process raw paleoclimate observational data into standardized period-sorted files.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--source",
        nargs="+",
        default=["all"],
        metavar="NAME",
        help=(
            "One or more source names to process, or 'all' (default). "
            "Choices: " + ", ".join(SOURCE_REGISTRY)
        ),
    )
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
    )
    parser.add_argument("--log-file", type=str)
    parser.add_argument(
        "--delete-raw",
        action="store_true",
        help="Delete the raw/observations directory after processing.",
    )
    args = parser.parse_args()
    setup_logging(args.log_level, args.log_file)

    # Resolve source list
    seen: dict[str, None] = {}
    for token in args.source:
        if token == "all":
            for key in SOURCE_REGISTRY:
                seen[key] = None
        elif token in SOURCE_REGISTRY:
            seen[token] = None
        else:
            logging.error(
                f"Unknown source '{token}'. Choices: {', '.join(SOURCE_REGISTRY)}"
            )
            sys.exit(1)
    source_names = list(seen)

    logging.info(f"\n{'='*60}\n  Processing paleoclimate observations\n{'='*60}")
    logging.info(f"  Sources: {source_names}")
    process_observations(source_names, delete_raw=args.delete_raw)


if __name__ == "__main__":
    main()
