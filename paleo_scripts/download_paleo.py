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
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

from paleo_constants import PALEO_DOWNLOADS, PALEO_MODELS, PALEO_PERIODS

RAW_DIR = Path(__file__).parent / "paleo_data_cache" / "raw"

OBS_DOWNLOADS = {
    "Figure7_19_obs.csv": "https://dap.ceda.ac.uk/badc/ar6_wg1/data/ch_07/ch7_fig19/v20230118/Figure7_19_obs.csv",
    "lgmDA_lgm_ATM_monthly_climo.nc": "https://github.com/jesstierney/lgmDA/raw/refs/heads/master/version2.1/lgmDA_lgm_ATM_monthly_climo.nc",
    "lgmDA_hol_ATM_monthly_climo.nc": "https://github.com/jesstierney/lgmDA/raw/refs/heads/master/version2.0/lgmDA_hol_ATM_monthly_climo.nc",
    "temp12k_alldata.nc": "https://www.ncei.noaa.gov/pub/data/paleo/reconstructions/kaufman2020/temp12k_alldata.nc",
}
LIG127K_ZIP_URL = (
    "https://cp.copernicus.org/articles/17/63/2021/cp-17-63-2021-supplement.zip"
)
LIG127K_TABLES = [
    "Table S2. Annual - NH Oceans, Europe, and Greenland (40-90N)_CP-2019-174.xlsx",
    "Table S3. Annual - Low latitudes (40S-40N)_CP-2019-174.xlsx",
    "Table S4. Annual - SH Oceans and Antarctica (40-90S)_CP-2019-174.xlsx",
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
    ran = skipped = failed = 0
    for model in models:
        for period in periods:
            entries = PALEO_DOWNLOADS.get(model, {}).get(period)
            if not entries:
                logging.debug(f"No CMIP6 data for {model}/{period}, skipping")
                skipped += 1
                continue
            logging.info(
                f"\n{'='*60}\n  CMIP6  {model} / {period}  ({len(entries)} files)\n{'='*60}"
            )
            dest_dir = RAW_DIR / model
            for filename, url, checksum in entries:
                if not _download_cmip6_file(
                    url, dest_dir / filename, checksum, dry_run
                ):
                    failed += 1
            ran += 1
    logging.info(
        f"CMIP6: {ran} combination(s), {skipped} skipped, {failed} file error(s)."
    )
    return failed == 0


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

    obs_dir.mkdir(parents=True, exist_ok=True)
    lig_dir.mkdir(exist_ok=True)

    for filename, url in OBS_DOWNLOADS.items():
        _wget_simple(url, obs_dir / filename)

    # LIG127k — zip containing Excel tables
    if all((lig_dir / t).exists() for t in LIG127K_TABLES):
        logging.info("  [skip] lig127k tables already exist")
    else:
        zip_dest = obs_dir / "cp-17-63-2021-supplement.zip"
        _wget_simple(LIG127K_ZIP_URL, zip_dest)
        extract_dir = obs_dir / "SI_CP-2019-174_20210105"
        try:
            subprocess.run(
                ["unzip", "-q", str(zip_dest), "-d", str(obs_dir)], timeout=30
            )
        except subprocess.TimeoutExpired:
            pass
        for table in LIG127K_TABLES:
            src = extract_dir / table
            if src.exists():
                src.rename(lig_dir / table)
        for f in extract_dir.iterdir():
            f.unlink()
        extract_dir.rmdir()
        zip_dest.unlink(missing_ok=True)
        (obs_dir / "cp-17-63-2021-supplement-title-page.pdf").unlink(missing_ok=True)

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
        "  lgmDA v2.1 Tierney et al.          (Last Glacial Maximum data assimilation)"
    )
    print(
        "  Temp12k Kaufman et al. 2020        (Mid Holocene temperature reconstruction)"
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
