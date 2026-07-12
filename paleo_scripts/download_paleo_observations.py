#!/usr/bin/env python3
"""
Download raw paleoclimate observational datasets.

Downloads proxy/reanalysis observations into paleo_data_cache/raw/observations/.

Datasets:
  ipcc_ar6        IPCC AR6 Fig 7.19 CSV — Eocene/Pliocene global mean anomalies
  lgmda           lgmDA v2.1 (Tierney et al.) — LGM data assimilation
  bartlein2011    Bartlein et al. 2011 — pollen-based temp/precip reconstructions (LGM, mid-Holocene)
  temp12k         Temp12k (Kaufman et al. 2020) — mid-Holocene temperature reconstruction
  osman2021       Osman et al. 2021 LGMR — LGM Reanalysis (GMST/SAT/SST climo + ensemble)
  sisal_v3        SISAL v3 — Speleothem Isotopes Synthesis and Analysis
  lig127k         Otto-Bliesner et al. 2021 — Last Interglacial proxy anomaly tables
  scussolini2019  Scussolini et al. 2019 — LIG boreal precipitation proxy
                  (manual download required — Science.org blocks automated downloads)
  tierney_hansen  Tierney THansenMethod.csv — Hansen-method deep-time reconstruction

Usage:
    python download_paleo_observations.py
    python download_paleo_observations.py --dataset lgmda
    python download_paleo_observations.py --dataset lig127k osman2021
    python download_paleo_observations.py --dry-run
    python download_paleo_observations.py --list
"""

import argparse
import logging
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

RAW_DIR = Path(__file__).parent / "paleo_data_cache" / "raw"

# ---------------------------------------------------------------------------
# URL registries
# ---------------------------------------------------------------------------

LGMDA_FILES = {
    "lgmDA_lgm_ATM_monthly_climo.nc": "https://github.com/jesstierney/lgmDA/raw/refs/heads/master/version2.1/lgmDA_lgm_ATM_monthly_climo.nc",
    "lgmDA_hol_ATM_monthly_climo.nc": "https://github.com/jesstierney/lgmDA/raw/refs/heads/master/version2.0/lgmDA_hol_ATM_monthly_climo.nc",
}

TEMP12K_BASE_URL = (
    "https://www.ncei.noaa.gov/pub/data/paleo/reconstructions/kaufman2020/"
)
TEMP12K_FILES = ["temp12k_alldata.nc"]

TEMP12K_V1_BASE_URL = "https://www.ncei.noaa.gov/pub/data/paleo/reconstructions/climate12k/temperature/version1.0.0/"
TEMP12K_V1_FILES = [
    "Temp12k_v1_0_0.pkl",
    "Temp12k_v1_essential_metadata_NOAA.csv",
    "Temp12k_v1_record_list_NOAA.csv",
]

OSMAN2021_BASE_URL = (
    "https://www.ncei.noaa.gov/pub/data/paleo/reconstructions/osman2021/"
)
OSMAN2021_FILES = [
    "LGMR_GMST_climo.nc",
    "LGMR_GMST_ens.nc",
    "LGMR_SAT_climo.nc",
    "LGMR_SST_climo.nc",
]

SISAL_V3_BASE_URL = "https://www.ncei.noaa.gov/pub/data/paleo/speleothem/SISAL-v3/"
SISAL_V3_FILES = [
    "sisalv3_database_mysql_csv.zip",
    "sisalv3_codes.zip",
]

LIG127K_ZIP_URL = (
    "https://cp.copernicus.org/articles/17/63/2021/cp-17-63-2021-supplement.zip"
)
LIG127K_TABLES = [
    "Table S2. Annual - NH Oceans, Europe, and Greenland (40-90N)_CP-2019-174.xlsx",
    "Table S3. Annual - Low latitudes (40S-40N)_CP-2019-174.xlsx",
    "Table S4. Annual - SH Oceans and Antarctica (40-90S)_CP-2019-174.xlsx",
    "Table S5. JJA - NH Oceans (40-90N) JJA_CP-2019-174.xlsx",
    "Table S6. JJA - NH terrestrial (40-90N) JJA__CP-2019-174.xlsx",
]

BARTLEIN_ZIP_URL = "https://static-content.springer.com/esm/art%3A10.1007%2Fs00382-010-0904-1/MediaObjects/382_2010_904_MOESM2_ESM.zip"

TIERNEY_HANSEN_URL = "https://raw.githubusercontent.com/jesstierney/PastClimates/master/THansenMethod.csv"

IPCC_AR6_URL = "https://dap.ceda.ac.uk/badc/ar6_wg1/data/ch_07/ch7_fig19/v20230118/Figure7_19_obs.csv"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _wget_simple(url: str, dest: Path, dry_run: bool = False) -> None:
    """Download url to dest; skip if dest already exists and is non-empty."""
    if dest.exists() and dest.stat().st_size > 0:
        logging.info(f"  [skip] {dest.name}")
        return
    if dry_run:
        logging.info(f"  [dry-run] would download {dest.name}")
        return
    logging.info(f"  Downloading {dest.name} ...")
    subprocess.run(["wget", "-q", "-O", str(dest), url], check=True)


def _extract_zip_robust(zip_path: Path, dest_dir: Path) -> Path:
    """Extract a zip into dest_dir and return the top-level extracted directory.

    Uses the zipfile module to discover the actual top-level directory name
    rather than assuming it, which avoids brittle hardcoded path assumptions.
    """
    with zipfile.ZipFile(zip_path) as zf:
        top_dirs = {Path(name).parts[0] for name in zf.namelist() if "/" in name}
        zf.extractall(dest_dir)

    if len(top_dirs) == 1:
        return dest_dir / top_dirs.pop()
    # Multiple top-level dirs: return dest_dir and let the caller search
    return dest_dir


# ---------------------------------------------------------------------------
# Per-dataset download functions
# ---------------------------------------------------------------------------


def _download_ipcc_ar6(obs_dir: Path, dry_run: bool) -> None:
    """IPCC AR6 Figure 7.19 — global mean temperature anomalies."""
    _wget_simple(IPCC_AR6_URL, obs_dir / "Figure7_19_obs.csv", dry_run)


def _download_lgmda(obs_dir: Path, dry_run: bool) -> None:
    """lgmDA v2.1 (Tierney et al.) — LGM and Holocene monthly climatologies."""
    for filename, url in LGMDA_FILES.items():
        _wget_simple(url, obs_dir / filename, dry_run)


def _download_bartlein2011(obs_dir: Path, dry_run: bool) -> None:
    """Bartlein et al. 2011 — pollen-based temperature/precipitation reconstructions."""
    dest = obs_dir / "bartlein2011_pollen_climate_recon.zip"
    _wget_simple(BARTLEIN_ZIP_URL, dest, dry_run)
    if dry_run or not dest.exists():
        return
    # Leave the zip in place; process_paleo_observations.py handles extraction.
    logging.info(f"  bartlein2011 zip ready at {dest.name}")


def _download_temp12k(obs_dir: Path, dry_run: bool) -> None:
    """Temp12k (Kaufman et al. 2020) — Holocene temperature reconstruction."""
    temp12k_dir = obs_dir / "climate12k"
    if not dry_run:
        temp12k_dir.mkdir(exist_ok=True)
    for filename in TEMP12K_FILES:
        _wget_simple(TEMP12K_BASE_URL + filename, obs_dir / filename, dry_run)
    for filename in TEMP12K_V1_FILES:
        _wget_simple(TEMP12K_V1_BASE_URL + filename, temp12k_dir / filename, dry_run)


def _download_osman2021(obs_dir: Path, dry_run: bool) -> None:
    """Osman et al. 2021 LGMR — LGM Reanalysis (GMST/SAT/SST)."""
    osman_dir = obs_dir / "osman2021"
    if not dry_run:
        osman_dir.mkdir(exist_ok=True)
    for filename in OSMAN2021_FILES:
        _wget_simple(OSMAN2021_BASE_URL + filename, osman_dir / filename, dry_run)


def _download_sisal_v3(obs_dir: Path, dry_run: bool) -> None:
    """SISAL v3 — Speleothem Isotopes Synthesis and Analysis database."""
    sisal_dir = obs_dir / "sisal_v3"
    if not dry_run:
        sisal_dir.mkdir(exist_ok=True)
    for filename in SISAL_V3_FILES:
        _wget_simple(SISAL_V3_BASE_URL + filename, sisal_dir / filename, dry_run)


def _download_lig127k(obs_dir: Path, dry_run: bool) -> None:
    """Otto-Bliesner et al. 2021 LIG127k — Last Interglacial proxy anomaly tables."""
    lig_dir = obs_dir / "lig127k"
    if not dry_run:
        lig_dir.mkdir(exist_ok=True)

    missing_tables = [t for t in LIG127K_TABLES if not (lig_dir / t).exists()]
    if not missing_tables:
        logging.info("  [skip] lig127k tables already extracted")
        return

    zip_dest = obs_dir / "cp-17-63-2021-supplement.zip"
    _wget_simple(LIG127K_ZIP_URL, zip_dest, dry_run)
    if dry_run or not zip_dest.exists():
        return

    logging.info("  Extracting lig127k supplement zip ...")
    extract_root = _extract_zip_robust(zip_dest, obs_dir)

    # Move each expected table from wherever it landed in the extract tree
    for table in LIG127K_TABLES:
        dest = lig_dir / table
        if dest.exists():
            continue
        # Search the extracted tree for the file (handles nested dirs)
        matches = list(obs_dir.rglob(table))
        if matches:
            matches[0].rename(dest)
        else:
            logging.warning(f"  [warn] Table not found in zip: {table}")

    # Clean up extracted tree and zip
    if extract_root != obs_dir and extract_root.exists():
        shutil.rmtree(extract_root, ignore_errors=True)
    for leftover in ["cp-17-63-2021-supplement-title-page.pdf", "__MACOSX"]:
        p = obs_dir / leftover
        if p.is_dir():
            shutil.rmtree(p, ignore_errors=True)
        elif p.exists():
            p.unlink(missing_ok=True)
    zip_dest.unlink(missing_ok=True)


def _download_scussolini2019(obs_dir: Path, dry_run: bool) -> None:
    """Scussolini et al. 2019 — LIG boreal precipitation proxy (manual download required)."""
    scussolini_dest = obs_dir / "scussolini2019_lig_precip_proxy.xlsx"
    scussolini_orig = obs_dir / "aax7047_external_database_s1.xlsx"

    if scussolini_dest.exists() and scussolini_dest.stat().st_size > 0:
        logging.info("  [skip] scussolini2019_lig_precip_proxy.xlsx")
        return

    if scussolini_orig.exists() and scussolini_orig.stat().st_size > 0:
        if scussolini_dest.exists():
            scussolini_dest.unlink()
        scussolini_orig.rename(scussolini_dest)
        logging.info(
            "  Renamed aax7047_external_database_s1.xlsx → scussolini2019_lig_precip_proxy.xlsx"
        )
        return

    logging.warning(
        "\n"
        "  ACTION REQUIRED: scussolini2019_lig_precip_proxy.xlsx must be downloaded manually.\n"
        "  Science.org blocks automated downloads for this file.\n"
        "\n"
        "  1. Open this URL in a browser:\n"
        "     https://www.science.org/doi/suppl/10.1126/sciadv.aax7047/suppl_file/aax7047_external_database_s1.xlsx\n"
        "  2. Save the file (downloads as aax7047_external_database_s1.xlsx).\n"
        "  3. Move it to:\n"
        f"     {scussolini_dest}\n"
        "  Then re-run this script to rename it automatically.\n"
    )


def _download_tierney_hansen(obs_dir: Path, dry_run: bool) -> None:
    """Tierney THansenMethod.csv — Hansen-method deep-time temperature reconstruction."""
    _wget_simple(TIERNEY_HANSEN_URL, obs_dir / "THansenMethod.csv", dry_run)


# ---------------------------------------------------------------------------
# Dataset registry — maps CLI name → downloader function
# ---------------------------------------------------------------------------

DATASET_REGISTRY: dict[str, tuple[str, callable]] = {
    "ipcc_ar6": ("IPCC AR6 Fig 7.19 global mean anomalies", _download_ipcc_ar6),
    "lgmda": ("lgmDA v2.1 Tierney et al. — LGM data assimilation", _download_lgmda),
    "bartlein2011": (
        "Bartlein et al. 2011 pollen temp/precip recon",
        _download_bartlein2011,
    ),
    "temp12k": (
        "Temp12k Kaufman et al. 2020 — Holocene reconstruction",
        _download_temp12k,
    ),
    "osman2021": (
        "Osman et al. 2021 LGMR — SAT/SST/GMST reanalysis",
        _download_osman2021,
    ),
    "sisal_v3": ("SISAL v3 speleothem database", _download_sisal_v3),
    "lig127k": ("Otto-Bliesner et al. 2021 LIG127k proxy tables", _download_lig127k),
    "scussolini2019": (
        "Scussolini et al. 2019 LIG precipitation proxy",
        _download_scussolini2019,
    ),
    "tierney_hansen": (
        "Tierney THansenMethod deep-time reconstruction",
        _download_tierney_hansen,
    ),
}


# ---------------------------------------------------------------------------
# CLI helpers
# ---------------------------------------------------------------------------


def list_datasets() -> None:
    print("Available datasets (--dataset <name>):")
    for key, (description, _) in DATASET_REGISTRY.items():
        print(f"  {key:<18}  {description}")


def download_datasets(dataset_names: list[str], dry_run: bool) -> bool:
    obs_dir = RAW_DIR / "observations"
    if not dry_run:
        obs_dir.mkdir(parents=True, exist_ok=True)

    ok = True
    for name in dataset_names:
        if name not in DATASET_REGISTRY:
            logging.error(
                f"Unknown dataset '{name}'. Run --list to see available options."
            )
            ok = False
            continue
        description, fn = DATASET_REGISTRY[name]
        logging.info(f"\n[{name}] {description}")
        try:
            fn(obs_dir, dry_run)
        except Exception as exc:
            logging.error(f"  Failed to download {name}: {exc}")
            ok = False
    return ok


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )

    parser = argparse.ArgumentParser(
        description="Download raw paleoclimate observational datasets.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--dataset",
        nargs="+",
        default=["all"],
        metavar="NAME",
        help=(
            "One or more dataset names to download, or 'all' (default). "
            "Run --list to see available names."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would be downloaded without downloading",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List available datasets and exit",
    )
    args = parser.parse_args()

    if args.list:
        list_datasets()
        return

    # Resolve dataset names; "all" expands to every registered key (order-preserving dedup)
    seen: dict[str, None] = {}
    for token in args.dataset:
        if token == "all":
            for key in DATASET_REGISTRY:
                seen[key] = None
        else:
            seen[token] = None
    names = list(seen)

    success = download_datasets(names, args.dry_run)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
