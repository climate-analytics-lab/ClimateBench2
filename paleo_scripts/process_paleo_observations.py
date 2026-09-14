"""
Process raw paleoclimate observational data into standardized, period-sorted files.

Output structure — all under paleo_data_cache/processed/observations/
  lgm/
    Tierney2020_tos.nc          RAW LGM SST proxy anomalies, site dim (Tierney et al. 2020)
    Tierney2020_absolute_tos.nc RAW absolute LGM + late-Holocene SSTs per core
    Tierney2020_5x5_tos.nc      RAW 5x5 deg binned LGM dSST field
    Osman2021Proxies_proxy.nc   RAW uncalibrated marine geochemistry, LGM slice
    Bartlein2011_tas.nc         Pollen-based LGM MAT anomaly (Bartlein et al. 2011)
    Bartlein2011_pr.nc          Pollen-based LGM MAP anomaly (Bartlein et al. 2011)
    lgmDA_v2.1_tas.nc           DA: lgmDA LGM climatology + Holocene PI reference + anomaly
    LGMR_SAT_tas.nc             DA: LGMR LGM surface air temperature (Osman et al. 2021)
    LGMR_SST_tos.nc             DA: LGMR LGM sea surface temperature (Osman et al. 2021)
    Cleator2020_tas.nc          DA: 3D-VAR LGM MAT/MTCO/MTWA/GDD5 anomalies
    Cleator2020_pr.nc           DA: 3D-VAR LGM MAP / moisture-index anomalies
  midHolocene/
    Osman2021Proxies_proxy.nc   RAW uncalibrated marine geochemistry, 5-7 ka slice
    Bartlein2011_tas.nc         Pollen-based mid-Holocene MAT anomaly
    Bartlein2011_pr.nc          Pollen-based mid-Holocene MAP anomaly (water balance)
    Harrison2015_pr.nc          N-Africa moisture envelope by latitude (monsoon check)
    SISALv3_d18O.nc             Speleothem d18O time slice (isotope-enabled models only)
    Temp12k_tas.nc              Holocene temperature reconstruction (Kaufman et al. 2020)
  lig127k/
    OttoBliesner2021_tas.nc     LIG proxy temperature anomalies (Otto-Bliesner et al. 2021)
    Scussolini2019_pr.nc        LIG boreal precipitation proxy (Scussolini et al. 2019)
    Hoffman2017_tos.nc          LIG SST compilation (needs a manual raw download)
    SISALv3_d18O.nc             Speleothem d18O time slice (isotope-enabled models only)
  multi_period/
    ipcc_ar6_fig7_19.csv        Global mean temperature anomalies (IPCC AR6)
    tierney2020_global_tas.csv  Deep-time global mean temperature (Tierney et al. 2020)
    lgmDA_v2.1_holocene_tas.nc  DA: Holocene PI reference

Each NetCDF carries global attributes: source, doi, source_url, variable, units, period,
anomaly_ref, dataset_type, and processing_date.

`dataset_type` is one of proxy_compilation / data_assimilation / reconstruction.
Paper Appendix D (2026-09) scores Tier III against RAW proxy compilations only;
the data_assimilation outputs (lgmDA, LGMR, Cleator 2020) stay in the cache for
reference and must be excluded from scoring.

Variable naming conventions (matched to paleo_benchmark.py):
  tas, tas_std, tas_sig_val   surface air temperature, uncertainty, significance flag
  pr, pr_std, pr_sig_val      precipitation anomaly, uncertainty, significance flag
  pr_reliability              semi-quantitative reliability score (Scussolini only)
  pi_tas                      pre-industrial (Holocene) monthly tas (lgmDA only)
  tos, tos_std                sea surface temperature, uncertainty
  d18O, d18O_std              speleothem calcite d18O (SISALv3 only)
  proxy, proxy_std            uncalibrated proxy units (Osman 2021 compilation only)
  *_abs, *_ref                absolute time-slice value and its anomaly baseline

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

# Time-slice windows (calendar years BP) used to average age-resolved records.
# LGM follows the PMIP4 / LGMR convention; midHolocene is the paper's
# Appendix D "5-7 ka" slice; LIG brackets the lig127k experiment's 127 ka;
# LATE_HOLOCENE is the per-record baseline used where a compilation reports
# absolute values rather than anomalies.
LGM_AGE_MIN = 19_000
LGM_AGE_MAX = 23_000
MIDHOLOCENE_AGE_MIN = 5_000
MIDHOLOCENE_AGE_MAX = 7_000
LIG_AGE_MIN = 125_000
LIG_AGE_MAX = 129_000
LATE_HOLOCENE_AGE_MIN = 0
LATE_HOLOCENE_AGE_MAX = 2_000

# dataset_type values written to every output so the Tier III protocol can
# exclude assimilated products from scoring (paper Appendix D, 2026-09).
PROXY = "proxy_compilation"
DA = "data_assimilation"
RECON = "reconstruction"


# ---------------------------------------------------------------------------
# Metadata / IO helpers
# ---------------------------------------------------------------------------


def _write_nc(ds: xr.Dataset, path: Path, attrs: dict) -> None:
    """Write dataset to NetCDF with standardised global attributes."""
    attrs.setdefault("processing_date", PROCESSING_DATE)
    if "dataset_type" not in attrs:
        logging.warning(f"  [warn] {path.name} written without a dataset_type attribute")
    ds.attrs = attrs
    path.parent.mkdir(parents=True, exist_ok=True)
    path.unlink(missing_ok=True)
    ds.to_netcdf(path)
    logging.info(f"  Saved {path.relative_to(PALEO_DIR)}")


def _str_array(values) -> np.ndarray:
    """Object array of Python strings — pandas StringDtype cannot be encoded to NetCDF."""
    return np.array([str(v) for v in values], dtype=object)


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
            f"dataset_type: {RECON}",
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
            f"dataset_type: {RECON}",
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
            "dataset_type": DA,
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
            "dataset_type": DA,
            "anomaly_ref": "none — absolute Holocene (PI) field, itself the anomaly reference",
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
            "dataset_type": DA,
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
            "dataset_type": DA,
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
            "dataset_type": PROXY,
            "anomaly_ref": "modern (present-day climatology, Bartlein et al. 2011 baseline)",
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
            "dataset_type": RECON,
            "anomaly_ref": "pre-industrial (Kaufman et al. 2020 internal baseline)",
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
            "dataset_type": PROXY,
            "anomaly_ref": "pre-industrial / modern (as reported per site by Otto-Bliesner et al. 2021)",
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
            "dataset_type": PROXY,
            "anomaly_ref": "present (modern precipitation at the site)",
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
# Tierney et al. 2020 — raw LGM SST proxy compilation (site level)
# ---------------------------------------------------------------------------


def _process_tierney2020_proxies(raw: Path, proc: Path) -> None:
    """Tierney 2020 site-level SST proxies → lgm/Tierney2020_*.nc

    Three outputs, all `dataset_type = proxy_compilation` (these are the
    calibrated proxy SSTs the lgmDA assimilation ingests, *not* the DA field):

      Tierney2020_tos.nc           site dim; LGM − late-Holocene dSST (primary)
      Tierney2020_absolute_tos.nc  site dim; absolute LGM and LH SSTs per core
      Tierney2020_5x5_tos.nc       5x5 deg binned dSST field
    """
    tdir = raw / "tierney2020_proxies"
    common = {
        "source": "Tierney et al. (2020) — LGM SST proxy compilation",
        "doi": "10.1038/s41586-020-2617-x",
        "source_url": "https://github.com/jesstierney/lgmDA/tree/master/proxyData",
        "period": "lgm",
        "dataset_type": PROXY,
        "proxy_types": "uk (UK'37), delo (planktic d18O), mg (Mg/Ca), tex (TEX86)",
        "calibration": (
            "Bayesian forward models BAYSPLINE / BAYFOX / BAYMAG / BAYSPAR "
            "(Tierney et al. 2020 Methods) — SSTs as published, not recalibrated here"
        ),
    }

    # --- paired LGM − late-Holocene anomalies (primary target) -------------
    p_paired = tdir / "Tierney2020_ProxyDataPaired.csv"
    if p_paired.exists():
        df = pd.read_csv(p_paired).dropna(subset=["Latitude", "Longitude", "Median"])
        # Lower2s / Upper2s bracket the 95% interval, so 1 sigma = range / 4
        tos_std = ((df["Upper2s"] - df["Lower2s"]) / 4.0).values.astype(float)
        ds = xr.Dataset(
            {
                "tos": xr.DataArray(df["Median"].values.astype(float), dims=["site"]),
                "tos_std": xr.DataArray(tos_std, dims=["site"]),
                "proxy_type": xr.DataArray(_str_array(df["ProxyType"]), dims=["site"]),
            },
            coords={
                "lat": xr.DataArray(
                    df["Latitude"].values.astype(float), dims=["site"]
                ),
                "lon": xr.DataArray(
                    df["Longitude"].values.astype(float), dims=["site"]
                ),
            },
        )
        _write_nc(
            ds,
            proc / "lgm" / "Tierney2020_tos.nc",
            {
                **common,
                "variable": "tos",
                "units": "degC (anomaly)",
                "anomaly_ref": "late Holocene (0-4 ka) SST of the same core",
                "n_sites": len(df),
                "tos_description": (
                    "Paired LGM (23-19 ka) − late-Holocene (4-0 ka) SST anomaly, "
                    "posterior median; paired = same proxy type within 0.1 deg"
                ),
                "tos_std_description": (
                    "1-sigma = (Upper2s − Lower2s) / 4. Site-level error only "
                    "(analytical + observational); the global Bayesian calibration "
                    "error is NOT included, so this is smaller than the absolute-SST "
                    "uncertainty in Tierney2020_absolute_tos.nc"
                ),
                "lon_convention": "-180 to 180",
            },
        )
    else:
        logging.warning(
            "  [skip] Tierney2020_ProxyDataPaired.csv not found — no dSST sites"
        )

    # --- absolute LGM and late-Holocene SSTs per core ----------------------
    p_lgm = tdir / "Tierney2020_LGMProxyData.csv"
    p_lh = tdir / "Tierney2020_LHProxyData.csv"
    if p_lgm.exists() and p_lh.exists():
        keys = ["CoreName", "ProxyType", "Species"]
        d_lgm = pd.read_csv(p_lgm).dropna(subset=["Latitude", "Longitude", "SSTMedian"])
        d_lh = pd.read_csv(p_lh).dropna(subset=["SSTMedian"])
        for d in (d_lgm, d_lh):
            d["Species"] = d["Species"].fillna("")
        merged = d_lgm.merge(
            d_lh[keys + ["SSTMedian", "SSTLower2s", "SSTUpper2s"]],
            on=keys,
            how="left",
            suffixes=("", "_lh"),
        ).drop_duplicates(subset=keys)

        def _sigma(frame: pd.DataFrame, lo: str, hi: str) -> np.ndarray:
            return ((frame[hi] - frame[lo]) / 4.0).values.astype(float)

        ds = xr.Dataset(
            {
                "tos": xr.DataArray(
                    merged["SSTMedian"].values.astype(float), dims=["site"]
                ),
                "tos_std": xr.DataArray(
                    _sigma(merged, "SSTLower2s", "SSTUpper2s"), dims=["site"]
                ),
                "tos_ref": xr.DataArray(
                    merged["SSTMedian_lh"].values.astype(float), dims=["site"]
                ),
                "tos_ref_std": xr.DataArray(
                    _sigma(merged, "SSTLower2s_lh", "SSTUpper2s_lh"), dims=["site"]
                ),
                "proxy_type": xr.DataArray(_str_array(merged["ProxyType"]), dims=["site"]),
                "core_name": xr.DataArray(_str_array(merged["CoreName"]), dims=["site"]),
            },
            coords={
                "lat": xr.DataArray(
                    merged["Latitude"].values.astype(float), dims=["site"]
                ),
                "lon": xr.DataArray(
                    merged["Longitude"].values.astype(float), dims=["site"]
                ),
            },
        )
        n_paired = int(np.isfinite(ds["tos_ref"].values).sum())
        _write_nc(
            ds,
            proc / "lgm" / "Tierney2020_absolute_tos.nc",
            {
                **common,
                "variable": "tos",
                "units": "degC (absolute)",
                "anomaly_ref": (
                    "none — absolute SSTs. tos_ref carries the same core's "
                    "late-Holocene SST; tos − tos_ref is a per-core anomaly"
                ),
                "n_sites": len(merged),
                "n_sites_with_late_holocene_pair": n_paired,
                "tos_description": "Absolute LGM SST (posterior median)",
                "tos_ref_description": "Absolute late-Holocene SST of the same core/proxy/species",
                "tos_std_description": "1-sigma = (SSTUpper2s − SSTLower2s) / 4",
                "lon_convention": "-180 to 180",
            },
        )
    else:
        logging.warning(
            "  [skip] Tierney2020 absolute SST CSVs not found — no absolute file"
        )

    # --- 5x5 degree binned dSST field --------------------------------------
    p_grid = tdir / "Tierney2020_ProxyData_5x5_deltaSST.nc"
    if p_grid.exists():
        src = xr.open_dataset(p_grid).load()
        ds = xr.Dataset({"tos": src["deltaSST"], "tos_std": src["std"]})
        _write_nc(
            ds,
            proc / "lgm" / "Tierney2020_5x5_tos.nc",
            {
                **common,
                "variable": "tos",
                "units": "degC (anomaly)",
                "anomaly_ref": "late Holocene (0-4 ka) SST of the same cores",
                "grid": "5x5 degree bins of the site-level dSST compilation",
                "tos_description": "Bin-mean LGM − late-Holocene SST anomaly",
                "tos_std_description": "Within-bin standard deviation",
                "lon_convention": "-180 to 180",
            },
        )
    else:
        logging.warning("  [skip] Tierney2020_ProxyData_5x5_deltaSST.nc not found")


# ---------------------------------------------------------------------------
# Osman et al. 2021 — raw marine proxy compilation (site level)
# ---------------------------------------------------------------------------

_OSMAN_PROXY_UNITS = {
    "uk37": "unitless (UK'37 index)",
    "tex86": "unitless (TEX86 index)",
    "mgca": "mmol/mol (Mg/Ca)",
    "d18o": "per mil VPDB",
}

_OSMAN_SLICES = {
    "lgm": (LGM_AGE_MIN, LGM_AGE_MAX),
    "midHolocene": (MIDHOLOCENE_AGE_MIN, MIDHOLOCENE_AGE_MAX),
}


def _osman_proxy_family(var_name: str) -> Optional[str]:
    """Map a proxyDatabase variable name to its measurement family."""
    for family in ("uk37", "tex86", "mgca", "d18o"):
        if var_name.startswith(family):
            return family
    return None


def _process_osman2021_proxies(raw: Path, proc: Path) -> None:
    """Osman 2021 proxyDatabase.nc → {lgm,midHolocene}/Osman2021Proxies_proxy.nc

    The compilation holds *uncalibrated* marine geochemistry (UK'37, TEX86,
    Mg/Ca, planktic d18O) on BACON age models — one netCDF group per sediment
    core. This writes per-(core, proxy) time-slice means for the LGM and the
    Appendix D 5-7 ka mid-Holocene slice, each with a late-Holocene (0-2 ka)
    baseline from the same record so an anomaly is available.

    NOTE: turning these into `tos` requires the Bayesian forward models
    (BAYSPLINE / BAYMAG / BAYFOX / BAYSPAR); this script deliberately does not
    pick a calibration. Use lgm/Tierney2020_tos.nc for calibrated LGM SSTs.
    """
    import netCDF4  # local import: only this source needs the group API

    p = raw / "osman2021" / "proxyDatabase.nc"
    if not p.exists():
        logging.warning(
            "  [skip] osman2021_proxies — proxyDatabase.nc not found. Run "
            "download_paleo_observations.py --dataset osman2021_proxies"
        )
        return

    records: dict[str, list[dict]] = {k: [] for k in _OSMAN_SLICES}

    with netCDF4.Dataset(p) as root:
        for site_key, grp in root.groups.items():
            data = grp.groups.get("data")
            if data is None or "age_median" not in data.variables:
                continue
            age = np.asarray(data.variables["age_median"][:], dtype=float)
            lat = float(grp.getncattr("latitude"))
            lon = float(grp.getncattr("longitude"))
            site_name = str(grp.getncattr("site_name"))

            lh_mask = (age >= LATE_HOLOCENE_AGE_MIN) & (age <= LATE_HOLOCENE_AGE_MAX)

            for var_name, var in data.variables.items():
                family = _osman_proxy_family(var_name)
                if family is None:
                    continue
                values = np.asarray(var[:], dtype=float)
                if values.shape != age.shape:
                    continue

                ref = (
                    float(np.nanmean(values[lh_mask]))
                    if lh_mask.any() and np.isfinite(values[lh_mask]).any()
                    else np.nan
                )

                for period, (age_min, age_max) in _OSMAN_SLICES.items():
                    mask = (age >= age_min) & (age <= age_max) & np.isfinite(values)
                    n = int(mask.sum())
                    if n == 0:
                        continue
                    slice_vals = values[mask]
                    records[period].append(
                        {
                            "site_name": site_name,
                            "lat": lat,
                            "lon": lon,
                            "proxy_type": var_name,
                            "proxy_family": family,
                            "units": _OSMAN_PROXY_UNITS[family],
                            "proxy_abs": float(np.mean(slice_vals)),
                            "proxy_ref": ref,
                            "proxy_spread": (
                                float(np.std(slice_vals, ddof=1)) if n > 1 else np.nan
                            ),
                            "n_samples": n,
                        }
                    )

    for period, rows in records.items():
        if not rows:
            logging.warning(f"  [skip] osman2021_proxies {period} — no records in slice")
            continue
        df = pd.DataFrame(rows)
        age_min, age_max = _OSMAN_SLICES[period]
        ds = xr.Dataset(
            {
                "proxy": xr.DataArray(
                    (df["proxy_abs"] - df["proxy_ref"]).values.astype(float),
                    dims=["site"],
                ),
                "proxy_std": xr.DataArray(
                    df["proxy_spread"].values.astype(float), dims=["site"]
                ),
                "proxy_abs": xr.DataArray(
                    df["proxy_abs"].values.astype(float), dims=["site"]
                ),
                "proxy_ref": xr.DataArray(
                    df["proxy_ref"].values.astype(float), dims=["site"]
                ),
                "n_samples": xr.DataArray(
                    df["n_samples"].values.astype("int32"), dims=["site"]
                ),
                "proxy_type": xr.DataArray(_str_array(df["proxy_type"]), dims=["site"]),
                "proxy_family": xr.DataArray(_str_array(df["proxy_family"]), dims=["site"]),
                "units_per_site": xr.DataArray(_str_array(df["units"]), dims=["site"]),
                "site_name": xr.DataArray(_str_array(df["site_name"]), dims=["site"]),
            },
            coords={
                "lat": xr.DataArray(df["lat"].values.astype(float), dims=["site"]),
                "lon": xr.DataArray(df["lon"].values.astype(float), dims=["site"]),
            },
        )
        n_anom = int(np.isfinite(ds["proxy"].values).sum())
        _write_nc(
            ds,
            proc / period / "Osman2021Proxies_proxy.nc",
            {
                "source": "Osman et al. (2021) — marine SST proxy compilation (LGMR input)",
                "doi": "10.1038/s41586-021-03984-4",
                "dataset_doi": "10.25921/njxd-hg08",
                "source_url": "https://www.ncei.noaa.gov/pub/data/paleo/reconstructions/osman2021/",
                "variable": "proxy",
                "units": "mixed — see the per-site units_per_site variable",
                "period": period,
                "dataset_type": PROXY,
                "anomaly_ref": (
                    f"late Holocene ({LATE_HOLOCENE_AGE_MIN}-{LATE_HOLOCENE_AGE_MAX} BP) "
                    "mean of the same record; NaN where that record has no such samples"
                ),
                "age_window_BP": f"{age_min}-{age_max}",
                "age_model": "BACON median age (age_median)",
                "n_records": len(df),
                "n_records_with_anomaly": n_anom,
                "proxy_description": "Time-slice mean minus the record's late-Holocene mean, in native proxy units",
                "proxy_abs_description": "Time-slice mean in native proxy units",
                "proxy_std_description": "Standard deviation of the samples inside the window (NaN if n=1)",
                "scoring_note": (
                    "UNCALIBRATED. Converting these to tos requires the Bayesian "
                    "forward models BAYSPLINE (UK'37), BAYMAG (Mg/Ca), BAYFOX "
                    "(planktic d18O) and BAYSPAR (TEX86). For calibrated LGM SSTs "
                    "use lgm/Tierney2020_tos.nc."
                ),
                "lon_convention": "-180 to 180",
            },
        )


# ---------------------------------------------------------------------------
# Hoffman et al. 2017 — LIG SST compilation
# ---------------------------------------------------------------------------


def _find_column(columns: list[str], *needles: str) -> Optional[str]:
    """First column whose lower-cased name contains every needle."""
    for col in columns:
        low = str(col).lower()
        if all(n in low for n in needles):
            return col
    return None


def _process_hoffman2017(raw: Path, proc: Path) -> None:
    """Hoffman 2017 LIG SST compilation → lig127k/Hoffman2017_tos.nc

    Data File S1 of the Science paper: 104 LIG SST records from 83 marine
    cores, reported as anomalies relative to 1870-1889. The file has to be
    fetched by hand (science.org blocks automated downloads), so the column
    names are discovered rather than assumed — check the log line naming the
    columns it picked before trusting the output.
    """
    p = raw / "hoffman2017_lig_sst_compilation.xlsx"
    if not p.exists():
        logging.warning(
            "  [skip] hoffman2017 — file not found. Run "
            "download_paleo_observations.py --dataset hoffman2017 and follow the "
            "manual-download instructions."
        )
        return

    sheets = pd.read_excel(p, sheet_name=None)
    best: Optional[tuple[pd.DataFrame, str, str, str]] = None
    for sheet_name, frame in sheets.items():
        cols = list(frame.columns)
        lat_col = _find_column(cols, "lat")
        lon_col = _find_column(cols, "lon")
        val_col = (
            _find_column(cols, "sst", "anom")
            or _find_column(cols, "anom")
            or _find_column(cols, "sst")
        )
        if lat_col and lon_col and val_col:
            best = (frame, lat_col, lon_col, val_col)
            logging.info(
                f"  hoffman2017: sheet '{sheet_name}' → lat='{lat_col}', "
                f"lon='{lon_col}', value='{val_col}'"
            )
            break

    if best is None:
        logging.warning(
            "  [skip] hoffman2017 — could not identify lat/lon/SST columns. "
            f"Sheets: {list(sheets)}. Adapt _process_hoffman2017 to the real layout."
        )
        return

    df, lat_col, lon_col, val_col = best
    err_col = (
        _find_column(list(df.columns), "sd")
        or _find_column(list(df.columns), "std")
        or _find_column(list(df.columns), "error")
        or _find_column(list(df.columns), "uncert")
    )
    df = df.dropna(subset=[lat_col, lon_col, val_col])

    data_vars = {
        "tos": xr.DataArray(df[val_col].values.astype(float), dims=["site"]),
    }
    if err_col is not None:
        data_vars["tos_std"] = xr.DataArray(
            pd.to_numeric(df[err_col], errors="coerce").values.astype(float),
            dims=["site"],
        )
    else:
        logging.warning(
            "  hoffman2017: no uncertainty column found — tos_std written as NaN"
        )
        data_vars["tos_std"] = xr.DataArray(
            np.full(len(df), np.nan), dims=["site"]
        )

    ds = xr.Dataset(
        data_vars,
        coords={
            "lat": xr.DataArray(df[lat_col].values.astype(float), dims=["site"]),
            "lon": xr.DataArray(df[lon_col].values.astype(float), dims=["site"]),
        },
    )
    _write_nc(
        ds,
        proc / "lig127k" / "Hoffman2017_tos.nc",
        {
            "source": "Hoffman et al. (2017) — LIG SST compilation",
            "doi": "10.1126/science.aai8464",
            "source_url": "https://www.science.org/doi/10.1126/science.aai8464",
            "variable": "tos",
            "units": "degC (anomaly)",
            "period": "lig127k",
            "dataset_type": PROXY,
            "anomaly_ref": "1870-1889 SST (as published by Hoffman et al. 2017)",
            "n_sites": len(df),
            "columns_used": f"lat='{lat_col}', lon='{lon_col}', tos='{val_col}', tos_std='{err_col}'",
            "provenance_note": (
                "Column names discovered at runtime from the manually downloaded "
                "Data File S1; verify columns_used against the spreadsheet."
            ),
        },
    )


# ---------------------------------------------------------------------------
# Cleator et al. 2020 — LGM 3D-VAR benchmark (data assimilation)
# ---------------------------------------------------------------------------

_CLEATOR_COLUMNS = [
    "lat", "lon",
    "MI", "MAP", "MAT", "MTCO", "MTWA", "GDD5",
    "MI_SD", "MAP_SD", "MAT_SD", "MTCO_SD", "MTWA_SD", "GDD5_SD",
]


def _regular_axis(values: np.ndarray) -> tuple[np.ndarray, float]:
    """Regular coordinate axis spanning `values` at their smallest spacing.

    The reconstruction only lists cells that were reconstructed, so the unique
    coordinates have gaps; filling them keeps the written axis uniform.
    """
    uniq = np.unique(values)
    if uniq.size < 2:
        return uniq, 1.0
    step = float(np.min(np.diff(uniq)))
    n = int(round((uniq[-1] - uniq[0]) / step)) + 1
    return uniq[0] + step * np.arange(n), step


def _cleator_grid(df: pd.DataFrame, columns: dict[str, str]) -> xr.Dataset:
    """Pivot the Cleator cell list onto its native regular lat/lon grid."""
    lats, lat_step = _regular_axis(df["lat"].values)
    lons, lon_step = _regular_axis(df["lon"].values)
    rows = np.rint((df["lat"].values - lats[0]) / lat_step).astype(int)
    cols = np.rint((df["lon"].values - lons[0]) / lon_step).astype(int)

    out = {}
    for out_name, src_name in columns.items():
        grid = np.full((len(lats), len(lons)), np.nan)
        grid[rows, cols] = df[src_name].values.astype(float)
        out[out_name] = xr.DataArray(grid, dims=["lat", "lon"])
    return xr.Dataset(out, coords={"lat": lats, "lon": lons})


def _process_cleator2020(raw: Path, proc: Path) -> None:
    """Cleator 2020 → lgm/Cleator2020_{tas,pr}.nc  (tagged data_assimilation).

    3D-VAR assimilation of the Bartlein et al. 2011 pollen sites with a
    PMIP3 ensemble-mean prior, so Appendix D excludes it from proxy scoring —
    it is processed for reference and tagged accordingly.
    """
    p = raw / "cleator2020" / "LGM_reconstruction.csv"
    if not p.exists():
        logging.warning(
            "  [skip] cleator2020 — LGM_reconstruction.csv not found. Run "
            "download_paleo_observations.py --dataset cleator2020"
        )
        return

    df = pd.read_csv(
        p,
        comment="#",
        header=None,
        names=_CLEATOR_COLUMNS,
        skipinitialspace=True,
    )

    common = {
        "source": "Cleator et al. (2020) — multi-variable LGM benchmark",
        "doi": "10.17864/1947.244",
        "source_url": "https://researchdata.reading.ac.uk/244/",
        "period": "lgm",
        "dataset_type": DA,
        "anomaly_ref": "modern (present-day climatology, as in Bartlein et al. 2011)",
        "method": (
            "3D-VAR data assimilation of Bartlein et al. 2011 pollen "
            "reconstructions with a PMIP3 ensemble-mean prior"
        ),
        "exclusion_note": (
            "Data-assimilation product: paper Appendix D (2026-09) excludes "
            "these from Tier III scoring; use Bartlein2011_*.nc for the raw sites"
        ),
        "grid": "2 degree regular lat/lon, NaN outside the reconstructed cells",
    }

    tas_ds = _cleator_grid(
        df,
        {
            "tas": "MAT",
            "tas_std": "MAT_SD",
            "mtco": "MTCO",
            "mtco_std": "MTCO_SD",
            "mtwa": "MTWA",
            "mtwa_std": "MTWA_SD",
            "gdd5": "GDD5",
            "gdd5_std": "GDD5_SD",
        },
    )
    _write_nc(
        tas_ds,
        proc / "lgm" / "Cleator2020_tas.nc",
        {
            **common,
            "variable": "tas",
            "units": "degC (anomaly)",
            "tas_description": "Mean annual temperature anomaly (MAT)",
            "tas_std_description": "1-sigma posterior uncertainty (MAT SD)",
            "extra_variables": "mtco/mtwa = coldest/warmest month mean T (degC); gdd5 = growing degree days above 5 degC (day degC)",
        },
    )

    pr_ds = _cleator_grid(
        df,
        {"pr": "MAP", "pr_std": "MAP_SD", "mi": "MI", "mi_std": "MI_SD"},
    )
    _write_nc(
        pr_ds,
        proc / "lgm" / "Cleator2020_pr.nc",
        {
            **common,
            "variable": "pr",
            "units": "mm/yr (anomaly)",
            "pr_description": "Mean annual precipitation anomaly (MAP)",
            "pr_std_description": "1-sigma posterior uncertainty (MAP SD)",
            "extra_variables": "mi = moisture index anomaly (P/PET, unitless)",
        },
    )


# ---------------------------------------------------------------------------
# Harrison & Prentice — mid-Holocene North Africa moisture benchmark
# ---------------------------------------------------------------------------


def _process_harrison2015(raw: Path, proc: Path) -> None:
    """Harrison N-Africa diagnostic → midHolocene/Harrison2015_pr.nc

    Latitudinal envelope (min/max) of the mid-Holocene precipitation increase
    over northern Africa needed to support the reconstructed vegetation, from
    the lake-status and biome evidence used by Harrison et al. (2015). This is
    the observational target for the Tier III Green-Sahara monsoon check.
    """
    p = raw / "harrison2015" / "precipitation.csv"
    if not p.exists():
        logging.warning(
            "  [skip] harrison2015 — precipitation.csv not found. Run "
            "download_paleo_observations.py --dataset harrison2015"
        )
        return

    df = pd.read_csv(p).dropna(subset=["Latitude"]).sort_values("Latitude")
    pr_max = df["maximum_estimate"].values.astype(float)
    pr_min = df["minimum_estimate"].values.astype(float)

    ds = xr.Dataset(
        {
            "pr": xr.DataArray((pr_min + pr_max) / 2.0, dims=["lat"]),
            "pr_std": xr.DataArray((pr_max - pr_min) / 2.0, dims=["lat"]),
            "pr_min": xr.DataArray(pr_min, dims=["lat"]),
            "pr_max": xr.DataArray(pr_max, dims=["lat"]),
        },
        coords={"lat": df["Latitude"].values.astype(float)},
    )
    _write_nc(
        ds,
        proc / "midHolocene" / "Harrison2015_pr.nc",
        {
            "source": "Harrison & Prentice — PMIP mid-Holocene North Africa precipitation diagnostic",
            "doi": "10.17864/1947.176",
            "source_url": "https://researchdata.reading.ac.uk/176/",
            "related_publication_doi": "10.1038/nclimate2649",
            "variable": "pr",
            "units": "mm/yr (anomaly)",
            "period": "midHolocene",
            "dataset_type": PROXY,
            "anomaly_ref": "present (0 ka) precipitation at the same latitude",
            "region": "northern Africa, zonal (latitude) bands",
            "pr_description": "Midpoint of the min/max required precipitation increase",
            "pr_std_description": "Half-width of the min/max envelope (not a Gaussian sigma)",
            "pr_min_description": "Minimum increase needed to support the reconstructed vegetation",
            "pr_max_description": "Maximum increase consistent with the reconstructed vegetation",
            "monsoon_gate_note": (
                "The Tier III gate's 0.5 mm/day bound equals 182.6 mm/yr; this "
                "envelope is the latitude-resolved version of the same evidence"
            ),
        },
    )


# ---------------------------------------------------------------------------
# SISAL v3 — speleothem d18O (Kaushal et al. 2024)
# ---------------------------------------------------------------------------

_SISAL_CSV_BASE = "sisalv3_database_mysql_csv/sisalv3_csv/"

_SISAL_SLICES = {
    "lig127k": (LIG_AGE_MIN, LIG_AGE_MAX),
    "midHolocene": (MIDHOLOCENE_AGE_MIN, MIDHOLOCENE_AGE_MAX),
}


def _read_sisal_table(zf: zipfile.ZipFile, name: str, **kwargs) -> pd.DataFrame:
    with zf.open(_SISAL_CSV_BASE + name) as handle:
        return pd.read_csv(handle, na_values=["NA", "nan", "unknown"], **kwargs)


def _process_sisal_v3(raw: Path, proc: Path) -> None:
    """SISAL v3 → {lig127k,midHolocene}/SISALv3_d18O.nc

    Joins site → entity → sample → original_chronology → d18O and takes
    per-entity time-slice means, with a late-Holocene (0-2 ka) baseline from
    the same entity where one exists.

    NOTE: scoring this needs isotope-enabled model output (d18O of
    precipitation / drip water); standard CMIP6 tas/pr/tos cannot be compared
    to it directly.
    """
    p = raw / "sisal_v3" / "sisalv3_database_mysql_csv.zip"
    if not p.exists():
        logging.warning(
            "  [skip] sisal_v3 — sisalv3_database_mysql_csv.zip not found. Run "
            "download_paleo_observations.py --dataset sisal_v3"
        )
        return

    with zipfile.ZipFile(p) as zf:
        site = _read_sisal_table(zf, "site.csv")
        entity = _read_sisal_table(zf, "entity.csv", usecols=["site_id", "entity_id"])
        sample = _read_sisal_table(zf, "sample.csv", usecols=["entity_id", "sample_id"])
        chron = _read_sisal_table(
            zf, "original_chronology.csv", usecols=["sample_id", "interp_age"]
        )
        d18o = _read_sisal_table(
            zf, "d18O.csv", usecols=["sample_id", "d18O_measurement"]
        )

    df = (
        d18o.merge(chron, on="sample_id", how="inner")
        .merge(sample, on="sample_id", how="inner")
        .merge(entity, on="entity_id", how="inner")
        .merge(
            site[["site_id", "site_name", "latitude", "longitude", "elevation"]],
            on="site_id",
            how="inner",
        )
        .dropna(subset=["interp_age", "d18O_measurement", "latitude", "longitude"])
    )
    logging.info(f"  SISALv3: {len(df)} dated d18O measurements after the join")

    lh = df[
        df["interp_age"].between(LATE_HOLOCENE_AGE_MIN, LATE_HOLOCENE_AGE_MAX)
    ]
    lh_mean = lh.groupby("entity_id")["d18O_measurement"].mean().rename("d18O_ref")

    for period, (age_min, age_max) in _SISAL_SLICES.items():
        window = df[df["interp_age"].between(age_min, age_max)]
        if window.empty:
            logging.warning(f"  [skip] sisal_v3 {period} — no samples in slice")
            continue

        grouped = window.groupby(
            ["entity_id", "site_id", "site_name", "latitude", "longitude"],
            as_index=False,
        ).agg(
            d18O_abs=("d18O_measurement", "mean"),
            d18O_spread=("d18O_measurement", "std"),
            n_samples=("d18O_measurement", "size"),
            mean_age=("interp_age", "mean"),
        )
        grouped = grouped.merge(lh_mean, on="entity_id", how="left")

        ds = xr.Dataset(
            {
                "d18O": xr.DataArray(
                    (grouped["d18O_abs"] - grouped["d18O_ref"]).values.astype(float),
                    dims=["site"],
                ),
                "d18O_std": xr.DataArray(
                    grouped["d18O_spread"].values.astype(float), dims=["site"]
                ),
                "d18O_abs": xr.DataArray(
                    grouped["d18O_abs"].values.astype(float), dims=["site"]
                ),
                "d18O_ref": xr.DataArray(
                    grouped["d18O_ref"].values.astype(float), dims=["site"]
                ),
                "n_samples": xr.DataArray(
                    grouped["n_samples"].values.astype("int32"), dims=["site"]
                ),
                "mean_age": xr.DataArray(
                    grouped["mean_age"].values.astype(float), dims=["site"]
                ),
                "entity_id": xr.DataArray(
                    grouped["entity_id"].values.astype("int32"), dims=["site"]
                ),
                "site_name": xr.DataArray(_str_array(grouped["site_name"]), dims=["site"]),
            },
            coords={
                "lat": xr.DataArray(
                    grouped["latitude"].values.astype(float), dims=["site"]
                ),
                "lon": xr.DataArray(
                    grouped["longitude"].values.astype(float), dims=["site"]
                ),
            },
        )
        n_anom = int(np.isfinite(ds["d18O"].values).sum())
        _write_nc(
            ds,
            proc / period / "SISALv3_d18O.nc",
            {
                "source": "SISALv3 speleothem database (Kaushal et al. 2024)",
                "doi": "10.5194/essd-16-1933-2024",
                "source_url": "https://www.ncei.noaa.gov/pub/data/paleo/speleothem/SISAL-v3/",
                "variable": "d18O",
                "units": "per mil VPDB",
                "period": period,
                "dataset_type": PROXY,
                "anomaly_ref": (
                    f"late Holocene ({LATE_HOLOCENE_AGE_MIN}-{LATE_HOLOCENE_AGE_MAX} BP) "
                    "mean of the same entity; NaN where that entity has no such samples"
                ),
                "age_window_BP": f"{age_min}-{age_max}",
                "age_model": "original_chronology.interp_age (published chronology)",
                "n_entities": len(grouped),
                "n_entities_with_anomaly": n_anom,
                "d18O_description": "Time-slice mean speleothem calcite d18O minus the entity's late-Holocene mean",
                "d18O_abs_description": "Time-slice mean speleothem calcite d18O",
                "d18O_std_description": "Standard deviation of the samples inside the window (NaN if n=1)",
                "scoring_note": (
                    "Requires isotope-enabled model output (d18O of precipitation "
                    "or drip water). Not comparable to standard CMIP6 tas/pr/tos. "
                    "No calcite-to-precipitation fractionation is applied here."
                ),
                "lon_convention": "-180 to 180",
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
    "tierney2020_proxies": (
        "Tierney et al. 2020 raw LGM SST proxy compilation (site level)",
        _process_tierney2020_proxies,
    ),
    "osman2021_proxies": (
        "Osman et al. 2021 raw marine proxy compilation (LGM + 5-7 ka slices)",
        _process_osman2021_proxies,
    ),
    "bartlein2011": (
        "Bartlein et al. 2011 pollen-based LGM/mid-Hol recon",
        _process_bartlein2011,
    ),
    "cleator2020": (
        "Cleator et al. 2020 LGM 3D-VAR benchmark (data assimilation)",
        _process_cleator2020,
    ),
    "temp12k": (
        "Temp12k — Holocene lat-band reconstruction (Kaufman 2020)",
        _process_temp12k,
    ),
    "harrison2015": (
        "Harrison N-Africa mid-Holocene moisture benchmark (monsoon check)",
        _process_harrison2015,
    ),
    "ottobliesner2021": (
        "Otto-Bliesner et al. 2021 LIG127k proxy temperatures",
        _process_ottobliesner2021,
    ),
    "hoffman2017": (
        "Hoffman et al. 2017 LIG SST compilation (manual download)",
        _process_hoffman2017,
    ),
    "scussolini2019": (
        "Scussolini et al. 2019 LIG boreal precipitation proxy",
        _process_scussolini2019,
    ),
    "sisal_v3": (
        "SISALv3 speleothem d18O time slices (lig127k + midHolocene)",
        _process_sisal_v3,
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
