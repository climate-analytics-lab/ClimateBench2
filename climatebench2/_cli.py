"""Command-line interface for ClimateBench2.

Installed as the ``climatebench2`` console script (see ``[project.scripts]``
in ``pyproject.toml``); also runnable as ``python -m climatebench2._cli``.

Subcommands
-----------
``climatebench2 score MODEL``
    Run the ClimateBench2 evaluation suites on a model's CMOR output via
    ClimateEval and write one DuckDB results database per suite (default:
    the CB2 tier suites, which grow per the delineation plan §6).
``climatebench2 leaderboard DB [DB ...]``
    Build the ClimateBench2 leaderboard from result databases. Phase 0 ships
    a scores table (stdout / CSV); the standalone HTML page lands in Phase 6.

ClimateBench2 deliberately has no data-loading or report machinery of its
own — ``score`` delegates to ClimateEval (``load_cmor_dir`` + ``Suite``), and
per-model interactive reports remain available via ``climateeval report``.
"""

from __future__ import annotations

import argparse
import sys
from importlib import resources
from pathlib import Path
from typing import Any

# Heavy climateeval subsystems (ESMValCore/iris/dask, ~5 s to import) are
# imported lazily inside the command functions, mirroring climateeval's CLI.

DEFAULT_SUITES = ["ClimateBench2_TierI", "ClimateBench2_TierII"]
DEFAULT_TIMERANGE = "19790101/20141231"


def _resolve_suite(name: str) -> str:
    """Resolve a suite name to a CB2-packaged YAML if one exists.

    CB2 suites shadow ClimateEval ones of the same name; anything else
    (shipped ClimateEval suite names, explicit paths) passes through for
    ClimateEval's own resolution.
    """
    if Path(name).suffix in {".yml", ".yaml"}:
        return name
    cb2_suite = resources.files("climatebench2.suites").joinpath(f"{name}.yml")
    if cb2_suite.is_file():
        return str(cb2_suite)
    return name


def _cmd_score(args: argparse.Namespace) -> None:
    if not args.model.exists():
        msg = f"Model path not found: {args.model}"
        raise SystemExit(msg)

    print("Loading ClimateEval (this can take a few seconds)…", file=sys.stderr)
    from climateeval._loader import load_cmor_dir
    from climateeval.data import DataSourceInformation
    from climateeval.suites import Suite

    cubes = load_cmor_dir(args.model, timerange=args.timerange)
    if not cubes:
        msg = f"No NetCDF data found in {args.model}"
        raise SystemExit(msg)

    info = DataSourceInformation(
        name=args.name,
        category="model",
        institute=args.institute,
        exp=args.exp,
        variant=args.variant,
    )
    diagnostic_kwargs: dict[str, Any] = {
        "fail_on_missing_data": False,
        "fail_on_metric_error": False,
        "download_missing_data": args.download,
    }
    if args.data_root is not None:
        diagnostic_kwargs["data_root_dir"] = args.data_root

    out_dir = args.out or Path(f"{args.name}_climatebench2")
    out_dir.mkdir(parents=True, exist_ok=True)

    suite_names = args.suite or DEFAULT_SUITES
    db_paths: list[Path] = []
    for suite_name in suite_names:
        resolved = _resolve_suite(suite_name)
        db_path = out_dir / f"{Path(resolved).stem}.ddb"
        db_path.unlink(missing_ok=True)
        Path(str(db_path) + ".wal").unlink(missing_ok=True)
        suite = Suite(
            resolved,
            diagnostic_kwargs=diagnostic_kwargs,
            variable_kwargs={"timerange": args.timerange},
        )
        print(
            f"Running suite '{Path(resolved).stem}' (timerange {args.timerange})",
            file=sys.stderr,
        )
        suite.get_database(cubes, info, database_resource=f"duckdb://{db_path}")
        print(f"Wrote database {db_path}", file=sys.stderr)
        db_paths.append(db_path)

    print(
        f"\nDone. Score with:  climatebench2 leaderboard "
        f"{' '.join(str(p) for p in db_paths)}",
        file=sys.stderr,
    )


def _cmd_leaderboard(args: argparse.Namespace) -> None:
    db_paths = [p.resolve() for p in args.db]
    for path in db_paths:
        if not path.exists():
            msg = f"Database not found: {path}"
            raise SystemExit(msg)

    from climatebench2.leaderboard import build_scores_table

    scores = build_scores_table(db_paths)
    if scores.empty:
        msg = "No metrics found in the given database(s)."
        raise SystemExit(msg)

    if args.csv is not None:
        scores.to_csv(args.csv, index=False)
        print(f"Wrote {args.csv}", file=sys.stderr)
    else:
        print(scores.to_string(index=False))  # noqa: T201


def main(argv: list[str] | None = None) -> None:
    """Run the climatebench2 command-line interface."""
    parser = argparse.ArgumentParser(
        prog="climatebench2",
        description=(
            "ClimateBench2: score and test climate models against the "
            "ClimateBench v2 protocol, using ClimateEval for all diagnostics."
        ),
        epilog=(
            "examples:\n"
            "  climatebench2 score /path/to/model/cmor/Amon --name MyModel\n"
            "      run the ClimateBench2 suites and write result databases\n"
            "  climatebench2 leaderboard MyModel_climatebench2/*.ddb\n"
            "      build the scores table from the results\n"
            "\n"
            "protocol spec: docs/metrics_reference.md\n"
            "architecture:  docs/climateeval_delineation_plan.md"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command")

    score = subparsers.add_parser(
        "score",
        help="Run the ClimateBench2 suites on a model via ClimateEval.",
    )
    score.add_argument(
        "model",
        type=Path,
        help=(
            "Model output: a NetCDF file, a flat directory of NetCDF files, "
            "or a CMOR DRS tree (e.g. an Amon table directory)."
        ),
    )
    score.add_argument("--name", default="model", help="Model name (provenance).")
    score.add_argument(
        "--suite",
        action="append",
        metavar="SUITE",
        help=(
            f"Suite name or YAML path; repeat for several suites. CB2 suites "
            f"shadow ClimateEval ones of the same name "
            f"(default: {', '.join(DEFAULT_SUITES)})."
        ),
    )
    score.add_argument(
        "--timerange",
        default=DEFAULT_TIMERANGE,
        help=f"ISO time range applied to every dataset (default: {DEFAULT_TIMERANGE}).",
    )
    score.add_argument(
        "--data-root",
        type=Path,
        default=None,
        metavar="DIR",
        help="Directory with staged reference datasets.",
    )
    score.add_argument(
        "--download",
        action="store_true",
        help="Download missing references (ERA5 needs ~/.cdsapirc).",
    )
    score.add_argument(
        "-o",
        "--out",
        type=Path,
        default=None,
        metavar="DIR",
        help="Output directory (default: <name>_climatebench2/).",
    )
    score.add_argument("--institute", default="", help="Institute (provenance).")
    score.add_argument("--exp", default="", help="Experiment (provenance).")
    score.add_argument("--variant", default="", help="Variant label (provenance).")
    score.set_defaults(func=_cmd_score)

    leaderboard = subparsers.add_parser(
        "leaderboard",
        help="Build the ClimateBench2 leaderboard from result databases.",
    )
    leaderboard.add_argument("db", type=Path, nargs="+", help="DuckDB .ddb file(s).")
    leaderboard.add_argument(
        "--csv",
        type=Path,
        default=None,
        metavar="FILE",
        help="Write the scores table as CSV instead of printing it.",
    )
    leaderboard.set_defaults(func=_cmd_leaderboard)

    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help(sys.stderr)
        raise SystemExit(2)
    args.func(args)


if __name__ == "__main__":
    main()
