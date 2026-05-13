"""
Process raw CMIP6 paleoclimate model data into monthly climatologies.

For each model/period/variable combination, all raw Amon NetCDF chunks are
concatenated, a 12-month climatology is computed, and the result is written to:

  paleo_data_cache/processed/models/{MODEL}/{period}_{variable}_monthly_climo.nc

Annual mean is computed on the fly by callers (mean over the month dimension).

Usage:
    python process_paleo_models.py
    python process_paleo_models.py --model AWI-ESM-1-1-LR --period lgm
    python process_paleo_models.py --model AWI-ESM-1-1-LR --period lgm --variable pr
    python process_paleo_models.py --model all --period all --variable all --overwrite
    python process_paleo_models.py --model all --period lgm --delete-raw
    python process_paleo_models.py --log-level DEBUG
"""

import argparse
import logging
import sys
from datetime import date
from pathlib import Path

import xarray as xr

sys.path.insert(0, str(Path(__file__).parent.parent))
from utils import standardize_dims

PALEO_DIR = Path(__file__).parent
RAW_MODELS = PALEO_DIR / "paleo_data_cache" / "raw" / "models"
PROC_MODELS = PALEO_DIR / "paleo_data_cache" / "processed" / "models"

PROCESSING_DATE = date.today().isoformat()

KNOWN_PERIODS = ["lgm", "lig127k", "midHolocene", "midPliocene-eoi400"]
KNOWN_VARIABLES = ["tas", "pr"]


# ---------------------------------------------------------------------------
# Core processing
# ---------------------------------------------------------------------------


def _discover_periods(model_dir: Path) -> list[str]:
    """Return periods that have at least one raw file in model_dir."""
    periods = set()
    for f in model_dir.glob("*.nc"):
        parts = f.name.split("_")
        # filename pattern: {var}_Amon_{model}_{period}_...
        if len(parts) >= 4:
            periods.add(parts[3])
    return sorted(periods)


def _process_one(
    model: str, period: str, variable: str, overwrite: bool, delete_raw: bool = False
) -> bool:
    """Process a single model/period/variable. Returns True if output was written."""
    model_raw = RAW_MODELS / model
    pattern = f"{variable}_Amon_*_{period}_*.nc"
    files = sorted(model_raw.glob(pattern))

    if not files:
        logging.warning(
            f"  [skip] {model} / {period} / {variable} — no raw files found"
        )
        return False

    out_dir = PROC_MODELS / model
    out_path = out_dir / f"{period}_{variable}_monthly_climo.nc"

    if out_path.exists() and not overwrite:
        logging.info(
            f"  [skip] {out_path.relative_to(PALEO_DIR)} already exists (use --overwrite)"
        )
        return False

    logging.info(
        f"  Processing {model} / {period} / {variable}  ({len(files)} file(s))"
    )

    ds = xr.open_mfdataset(
        files,
        combine="by_coords",
        use_cftime=True,
        data_vars="minimal",
        coords="minimal",
        compat="override",
    )
    ds = standardize_dims(ds)

    climo = ds[[variable]].groupby("time.month").mean("time")
    n_years = len(ds.time) // 12

    climo.attrs = ds[variable].attrs
    climo[variable].attrs = ds[variable].attrs
    climo.attrs.update(
        {
            "model": model,
            "period": period,
            "variable": variable,
            "n_years_averaged": n_years,
            "source_files": ", ".join(f.name for f in files),
            "processing_date": PROCESSING_DATE,
        }
    )

    out_dir.mkdir(parents=True, exist_ok=True)
    out_path.unlink(missing_ok=True)
    climo.to_netcdf(out_path)
    logging.info(f"    Saved {out_path.relative_to(PALEO_DIR)}")
    ds.close()

    if delete_raw:
        for f in files:
            f.unlink()
            logging.debug(f"    Deleted {f.relative_to(PALEO_DIR)}")
        logging.info(f"    Deleted {len(files)} raw file(s)")

    return True


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Process CMIP6 paleo model data into monthly climatologies."
    )
    parser.add_argument(
        "--model",
        nargs="+",
        default=["all"],
        help="Model name(s) or 'all' to discover from raw/models/ subdirectories",
    )
    parser.add_argument(
        "--period",
        nargs="+",
        default=["all"],
        choices=KNOWN_PERIODS + ["all"],
        help="Period(s) or 'all'",
    )
    parser.add_argument(
        "--variable",
        nargs="+",
        default=["all"],
        choices=KNOWN_VARIABLES + ["all"],
        help="Variable(s) or 'all'",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Reprocess even if output already exists",
    )
    parser.add_argument(
        "--delete-raw",
        action="store_true",
        help="Delete raw source files after successful processing",
    )
    parser.add_argument(
        "--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"]
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level), format="%(levelname)s %(message)s"
    )

    # Resolve models
    if "all" in args.model:
        if not RAW_MODELS.exists():
            logging.error(f"Raw models directory not found: {RAW_MODELS}")
            sys.exit(1)
        models = sorted(d.name for d in RAW_MODELS.iterdir() if d.is_dir())
    else:
        models = args.model

    # Resolve variables
    variables = KNOWN_VARIABLES if "all" in args.variable else args.variable

    written = 0
    skipped = 0

    for model in models:
        model_dir = RAW_MODELS / model
        if not model_dir.exists():
            logging.warning(f"[skip] {model} — directory not found in raw/models/")
            continue

        # Resolve periods: either explicit list or discover from filenames
        if "all" in args.period:
            periods = _discover_periods(model_dir)
            if not periods:
                logging.warning(f"[skip] {model} — no raw NetCDF files found")
                continue
        else:
            periods = args.period

        for period in periods:
            for variable in variables:
                ok = _process_one(
                    model, period, variable, args.overwrite, args.delete_raw
                )
                if ok:
                    written += 1
                else:
                    skipped += 1

    logging.info(f"Done — {written} file(s) written, {skipped} skipped.")


if __name__ == "__main__":
    main()
