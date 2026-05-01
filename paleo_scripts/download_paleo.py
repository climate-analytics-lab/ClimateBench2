#!/usr/bin/env python3
"""
Download raw paleoclimate data.

Downloads two categories of data into paleo_data_cache/raw/:
  cmip6        CMIP6 PMIP tas model simulations from ESGF
               → paleo_data_cache/raw/{MODEL}/tas_Amon_*.nc
  observations Proxy/reanalysis observational datasets
               → paleo_data_cache/raw/observations/

Usage:
    python download_paleo.py --source all
    python download_paleo.py --source cmip6 --model all --period all
    python download_paleo.py --source cmip6 --model CESM2 --period lgm
    python download_paleo.py --source observations
    python download_paleo.py --list
    python download_paleo.py --dry-run --source cmip6 --model CESM2 --period lig127k
"""

import argparse
import hashlib
import logging
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

import pandas as pd

from paleo_constants import PALEO_DOWNLOADS, PALEO_MODELS, PALEO_PERIODS

RAW_DIR = Path(__file__).parent / "paleo_data_cache" / "raw"
PANGEO_CATALOG_URL = "https://storage.googleapis.com/cmip6/pangeo-cmip6.csv"
PANGEO_CATALOG_PATH = Path(__file__).parent / "paleo_data_cache" / "pangeo-cmip6.csv"

OBS_DOWNLOADS = {
    "Figure7_19_obs.csv": "https://dap.ceda.ac.uk/badc/ar6_wg1/data/ch_07/ch7_fig19/v20230118/Figure7_19_obs.csv",
    "lgmDA_lgm_ATM_monthly_climo.nc": "https://github.com/jesstierney/lgmDA/raw/refs/heads/master/version2.1/lgmDA_lgm_ATM_monthly_climo.nc",
    "lgmDA_hol_ATM_monthly_climo.nc": "https://github.com/jesstierney/lgmDA/raw/refs/heads/master/version2.0/lgmDA_hol_ATM_monthly_climo.nc",
    "temp12k_alldata.nc": "https://www.ncei.noaa.gov/pub/data/paleo/reconstructions/kaufman2020/temp12k_alldata.nc",
    "bartlein2011_pollen_climate_recon.zip": "https://static-content.springer.com/esm/art%3A10.1007%2Fs00382-010-0904-1/MediaObjects/382_2010_904_MOESM2_ESM.zip",
    "THansenMethod.csv": "https://raw.githubusercontent.com/jesstierney/PastClimates/master/THansenMethod.csv",
}
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
# Otto-Bliesner et al. (2021), Clim. Past 17, 63–88, doi:10.5194/cp-17-63-2021
# Tables S2–S4: annual temperature anomalies by latitude band
# Tables S5–S6: JJA temperature anomalies for NH oceans and terrestrial sites
LIG127K_TABLES = [
    "Table S2. Annual - NH Oceans, Europe, and Greenland (40-90N)_CP-2019-174.xlsx",
    "Table S3. Annual - Low latitudes (40S-40N)_CP-2019-174.xlsx",
    "Table S4. Annual - SH Oceans and Antarctica (40-90S)_CP-2019-174.xlsx",
    "Table S5. JJA - NH Oceans (40-90N) JJA_CP-2019-174.xlsx",
    "Table S6. JJA - NH terrestrial (40-90N) JJA__CP-2019-174.xlsx",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _wget_simple(url: str, dest: Path) -> None:
    """Download url to dest, skip if dest already exists."""
    if dest.exists():
        logging.info(f"  [skip] {dest.name}")
        return
    logging.info(f"  Downloading {dest.name}")
    subprocess.run(["wget", "-q", "-O", str(dest), url], check=True)


# ---------------------------------------------------------------------------
# Pangeo / GCS helpers
# ---------------------------------------------------------------------------


def _get_pangeo_catalog() -> pd.DataFrame | None:
    """Return the Pangeo CMIP6 catalog, downloading it once if needed."""
    if not PANGEO_CATALOG_PATH.exists():
        PANGEO_CATALOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        logging.info("  Downloading Pangeo CMIP6 catalog...")
        try:
            urllib.request.urlretrieve(PANGEO_CATALOG_URL, PANGEO_CATALOG_PATH)
        except Exception as e:
            logging.warning(f"  Could not fetch Pangeo catalog: {e}")
            return None
    return pd.read_csv(PANGEO_CATALOG_PATH)


def _download_cmip6_from_gcs(
    model: str, period: str, dest_dir: Path, catalog: pd.DataFrame
) -> bool:
    """Fallback: stream PMIP tas from the Pangeo GCS Zarr store into a single NetCDF.

    Returns True if a file was written or already existed, False on failure.
    The output file is named  tas_Amon_{model}_{period}_{member}_{grid}_full.nc
    so that process_paleo.py's glob("tas_Amon_*.nc") picks it up correctly.
    If the GCS download succeeds, any partial ESGF .nc files for this
    model/period are removed to prevent duplicate time ranges during load.
    """
    sub = catalog[
        (catalog["source_id"] == model)
        & (catalog["experiment_id"] == period)
        & (catalog["variable_id"] == "tas")
        & (catalog["table_id"] == "Amon")
    ]
    if sub.empty:
        return False

    row = sub.sort_values("version", ascending=False).iloc[0]
    zstore = row["zstore"]
    member = row.get("member_id", "r1i1p1f1")
    grid = row.get("grid_label", "gn")
    out_name = f"tas_Amon_{model}_{period}_{member}_{grid}_full.nc"
    out_path = dest_dir / out_name

    if out_path.exists():
        logging.info(f"  [skip] {out_name} (GCS full file)")
        return True

    try:
        import gcsfs
        import xarray as xr

        fs = gcsfs.GCSFileSystem(token="anon")
        store = fs.get_mapper(zstore)
        logging.info(f"  [gcs] Streaming {model}/{period} from Pangeo → {out_name}")
        ds = xr.open_zarr(store, consolidated=True)
        dest_dir.mkdir(parents=True, exist_ok=True)
        ds[["tas"]].to_netcdf(out_path)
        logging.info(f"  [gcs] Saved {out_name}")

        # Remove any partial ESGF files to avoid mixing time ranges on load
        removed = 0
        for esgf_nc in dest_dir.glob(f"tas_Amon_{model}_{period}_*.nc"):
            if esgf_nc != out_path:
                esgf_nc.unlink()
                removed += 1
        if removed:
            logging.info(f"  [gcs] Removed {removed} partial ESGF file(s)")

        return True
    except Exception as e:
        logging.error(f"  [gcs] Failed for {model}/{period}: {e}")
        return False


# ---------------------------------------------------------------------------
# CMIP6
# ---------------------------------------------------------------------------


def _download_cmip6_file(
    url: str, dest: Path, expected_checksum: str, dry_run: bool
) -> bool:
    if dest.exists():
        if _sha256(dest) == expected_checksum.lower():
            logging.info(f"  [skip] {dest.name} (verified)")
            return True
        logging.info(f"  [redownload] {dest.name} (checksum mismatch)")

    if dry_run:
        logging.info(f"  [dry-run] {url}")
        return True

    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    logging.info(f"  Downloading {dest.name}")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "wget/1.21"})
        with urllib.request.urlopen(req, timeout=300) as resp, open(tmp, "wb") as out:
            while chunk := resp.read(1 << 20):
                out.write(chunk)
    except urllib.error.URLError as e:
        logging.error(f"  ERROR: {e}")
        tmp.unlink(missing_ok=True)
        return False

    actual = _sha256(tmp)
    if actual != expected_checksum.lower():
        logging.error(
            f"  Checksum mismatch for {dest.name}: expected {expected_checksum.lower()}, got {actual}"
        )
        tmp.unlink()
        return False

    tmp.rename(dest)
    logging.info(f"  OK {dest.name}")
    return True


def download_cmip6(models: list[str], periods: list[str], dry_run: bool) -> bool:
    catalog = _get_pangeo_catalog()
    ran = skipped = gcs_ok = esgf_failed = 0

    for model in models:
        for period in periods:
            entries = PALEO_DOWNLOADS.get(model, {}).get(period)
            if not entries:
                logging.debug(f"No CMIP6 data for {model}/{period}, skipping")
                skipped += 1
                continue

            dest_dir = RAW_DIR / model

            # If a GCS full file already exists, nothing more to do
            if list(dest_dir.glob(f"tas_Amon_{model}_{period}_*_full.nc")):
                logging.info(
                    f"\n{'='*60}\n  CMIP6  {model} / {period}  [skip — GCS file present]\n{'='*60}"
                )
                ran += 1
                continue

            logging.info(
                f"\n{'='*60}\n  CMIP6  {model} / {period}  ({len(entries)} ESGF files)\n{'='*60}"
            )

            # Attempt ESGF downloads
            failures = []
            for filename, url, checksum in entries:
                if not _download_cmip6_file(
                    url, dest_dir / filename, checksum, dry_run
                ):
                    failures.append(filename)

            if failures and not dry_run:
                logging.warning(
                    f"  {len(failures)}/{len(entries)} ESGF file(s) failed — "
                    "trying Pangeo GCS fallback"
                )
                if catalog is not None and _download_cmip6_from_gcs(
                    model, period, dest_dir, catalog
                ):
                    gcs_ok += 1
                else:
                    esgf_failed += len(failures)
                    if (
                        catalog is None
                        or catalog[
                            (catalog["source_id"] == model)
                            & (catalog["experiment_id"] == period)
                            & (catalog["variable_id"] == "tas")
                        ].empty
                    ):
                        logging.error(
                            f"  {model}/{period} is not in the Pangeo GCS catalog.\n"
                            "  To download manually:\n"
                            "    1. Visit https://esgf-node.llnl.gov/search/cmip6/\n"
                            "    2. Filter: activity=PMIP, source_id, experiment_id, variable=tas\n"
                            "    3. Download files and place them in:\n"
                            f"       {dest_dir}/"
                        )

            ran += 1

    logging.info(
        f"CMIP6: {ran} combination(s), {skipped} skipped, "
        f"{gcs_ok} via GCS fallback, {esgf_failed} file error(s)."
    )
    return esgf_failed == 0


# ---------------------------------------------------------------------------
# Observations
# ---------------------------------------------------------------------------


def download_observations(dry_run: bool) -> bool:
    obs_dir = RAW_DIR / "observations"
    lig_dir = obs_dir / "lig127k"

    if dry_run:
        logging.info(
            "[dry-run] would download observational datasets to paleo_data_cache/raw/observations/"
        )
        return True

    osman_dir = obs_dir / "osman2021"
    temp12k_dir = obs_dir / "climate12k"
    sisal_dir = obs_dir / "sisal_v3"

    obs_dir.mkdir(parents=True, exist_ok=True)
    lig_dir.mkdir(exist_ok=True)
    osman_dir.mkdir(exist_ok=True)
    temp12k_dir.mkdir(exist_ok=True)
    sisal_dir.mkdir(exist_ok=True)

    for filename, url in OBS_DOWNLOADS.items():
        _wget_simple(url, obs_dir / filename)

    # Scussolini et al. 2019 — Science.org blocks automated downloads.
    # wget produces a 0-byte file; the real download lands as the original
    # Science.org filename (aax7047_external_database_s1.xlsx) when done via
    # a browser. Rename it to the canonical name if found.
    scussolini_dest = obs_dir / "scussolini2019_lig_precip_proxy.xlsx"
    scussolini_orig = obs_dir / "aax7047_external_database_s1.xlsx"
    if scussolini_dest.exists() and scussolini_dest.stat().st_size > 0:
        logging.info(f"  [skip] {scussolini_dest.name}")
    elif scussolini_orig.exists() and scussolini_orig.stat().st_size > 0:
        if scussolini_dest.exists():
            scussolini_dest.unlink()  # remove 0-byte placeholder
        scussolini_orig.rename(scussolini_dest)
        logging.info(
            "  Renamed aax7047_external_database_s1.xlsx → scussolini2019_lig_precip_proxy.xlsx"
        )
    else:
        logging.warning(
            "\n"
            "  ACTION REQUIRED: scussolini2019_lig_precip_proxy.xlsx must be downloaded manually.\n"
            "  Science.org blocks automated downloads for this file.\n"
            "\n"
            "  1. Copy and paste this URL into your browser:\n"
            "     https://www.science.org/doi/suppl/10.1126/sciadv.aax7047/suppl_file/aax7047_external_database_s1.xlsx\n"
            "  2. Save the file (it will download as aax7047_external_database_s1.xlsx).\n"
            "  3. Move it to:\n"
            f"     {scussolini_dest}\n"
        )

    # Kaufman et al. 2020 Temp12k v1.0.0 full database (NCEI study 27330)
    for filename in TEMP12K_V1_FILES:
        _wget_simple(TEMP12K_V1_BASE_URL + filename, temp12k_dir / filename)

    # Osman et al. 2021 Last Glacial Maximum Reanalysis (LGMR)
    for filename in OSMAN2021_FILES:
        _wget_simple(OSMAN2021_BASE_URL + filename, osman_dir / filename)

    # SISAL v3 — Speleothem Isotopes Synthesis and Analysis database
    for filename in SISAL_V3_FILES:
        _wget_simple(SISAL_V3_BASE_URL + filename, sisal_dir / filename)

    # LIG127k — Otto-Bliesner et al. (2021), Clim. Past 17, 63–88
    # Zip contains Tables S2–S6; extract any that are not already in lig_dir.
    missing_tables = [t for t in LIG127K_TABLES if not (lig_dir / t).exists()]
    if not missing_tables:
        logging.info("  [skip] lig127k tables already exist")
    else:
        zip_dest = obs_dir / "cp-17-63-2021-supplement.zip"
        _wget_simple(LIG127K_ZIP_URL, zip_dest)
        extract_dir = obs_dir / "SI_CP-2019-174_20210105"
        try:
            subprocess.run(
                ["unzip", "-q", "-o", str(zip_dest), "-d", str(obs_dir)], timeout=30
            )
        except subprocess.TimeoutExpired:
            pass
        for table in LIG127K_TABLES:
            src = extract_dir / table
            dest = lig_dir / table
            if src.exists() and not dest.exists():
                src.rename(dest)
        # Clean up extracted directory and zip
        shutil.rmtree(extract_dir, ignore_errors=True)
        zip_dest.unlink(missing_ok=True)
        (obs_dir / "cp-17-63-2021-supplement-title-page.pdf").unlink(missing_ok=True)
        # Remove macOS resource-fork junk left by unzip
        macos_junk = obs_dir / "__MACOSX"
        shutil.rmtree(macos_junk, ignore_errors=True)

    return True


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def list_available() -> None:
    print("CMIP6 model/period combinations:")
    for model in PALEO_MODELS:
        for period in PALEO_PERIODS:
            if model in PALEO_DOWNLOADS and period in PALEO_DOWNLOADS[model]:
                n = len(PALEO_DOWNLOADS[model][period])
                print(
                    f"  {model:25s} / {period:25s}  ({n} file{'s' if n != 1 else ''})"
                )
    print("\nObservational datasets:")
    print("  IPCC AR6 Fig 7.19 CSV              (Eocene, Pliocene global mean)")
    print("  Capron et al. 2021 (xlsx tables)   (Last Interglacial proxy anomalies)")
    print(
        "  Scussolini et al. 2019 (xlsx)      (Last Interglacial boreal precipitation proxy database)"
    )
    print(
        "  Bartlein et al. 2011 (zip)         (Pollen-based temperature/precip reconstructions at 6 ka and 21 ka)"
    )
    print(
        "  Tierney THansenMethod.csv          (Hansen-method deep-time temperature reconstruction)"
    )
    print(
        "  lgmDA v2.1 Tierney et al.          (Last Glacial Maximum data assimilation)"
    )
    print(
        "  Temp12k Kaufman et al. 2020        (Mid Holocene temperature reconstruction)"
    )
    print(
        "  Temp12k v1.0.0 Kaufman et al. 2020 (Full proxy database: pkl + metadata CSVs, NCEI study 27330)"
    )
    print(
        "  Osman et al. 2021 LGMR             (Last Glacial Maximum Reanalysis: GMST/SAT/SST climo + GMST ensemble)"
    )
    print(
        "  SISAL v3                           (Speleothem Isotopes Synthesis and Analysis: MySQL/CSV database + codes)"
    )


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )

    parser = argparse.ArgumentParser(
        description="Download raw paleoclimate data.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--source",
        choices=["cmip6", "observations", "all"],
        help="Which data to download",
    )
    parser.add_argument(
        "--model",
        default="all",
        help="CMIP6 model name or 'all' (only used with --source cmip6/all)",
    )
    parser.add_argument(
        "--period",
        default="all",
        help="Paleo period or 'all' (only used with --source cmip6/all)",
    )
    parser.add_argument(
        "--list", action="store_true", help="List available data and exit"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would be downloaded without downloading",
    )
    args = parser.parse_args()

    if args.list:
        list_available()
        return

    if not args.source:
        parser.error("--source is required")

    success = True

    if args.source in ("cmip6", "all"):
        models = PALEO_MODELS if args.model == "all" else [args.model]
        periods = PALEO_PERIODS if args.period == "all" else [args.period]
        invalid_m = [m for m in models if m not in PALEO_DOWNLOADS]
        invalid_p = [p for p in periods if p not in PALEO_PERIODS]
        if invalid_m:
            parser.error(f"Unknown model(s): {invalid_m}. Run --list to see options.")
        if invalid_p:
            parser.error(f"Unknown period(s): {invalid_p}. Run --list to see options.")
        success &= download_cmip6(models, periods, args.dry_run)

    if args.source in ("observations", "all"):
        success &= download_observations(args.dry_run)

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
