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

DEFAULT_SUITES = [
    "ClimateBench2_TierI",
    "ClimateBench2_TierI_variability",
    "ClimateBench2_TierII",
]
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


def _parse_experiments(specs: list[str] | None) -> dict[str, Path]:
    """Parse repeated ``--experiment KEY=PATH`` options."""
    experiments: dict[str, Path] = {}
    for spec in specs or []:
        key, sep, path = spec.partition("=")
        if not sep or not key or not path:
            msg = f"--experiment expects KEY=PATH, got '{spec}'"
            raise SystemExit(msg)
        experiments[key.strip().lower()] = Path(path)
    return experiments


def _cmd_score(args: argparse.Namespace) -> None:
    if not args.model.exists():
        msg = f"Model path not found: {args.model}"
        raise SystemExit(msg)
    experiment_paths = _parse_experiments(args.experiment)
    for key, path in experiment_paths.items():
        if not path.exists():
            msg = f"Experiment path not found: {key}={path}"
            raise SystemExit(msg)

    print("Loading ClimateEval (this can take a few seconds)…", file=sys.stderr)
    from climateeval._loader import load_cmor_dir
    from climateeval.data import DataSourceInformation
    from climateeval.diags.complex._base import ComplexDiagnostic
    from climateeval.suites import Suite

    cubes = load_cmor_dir(args.model, timerange=args.timerange)
    if not cubes:
        msg = f"No NetCDF data found in {args.model}"
        raise SystemExit(msg)

    # Experiment dict for the complex (Tier I) suites. Experiments are loaded
    # in full (no timerange cut — piControl/abrupt-4xCO2 need their length);
    # the model's own cubes serve as "historical" unless overridden.
    experiments: dict[str, Any] = {"historical": cubes}
    for key, path in experiment_paths.items():
        experiments[key] = load_cmor_dir(path)
        print(f"Loaded experiment '{key}' from {path}", file=sys.stderr)

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
        suite = Suite(
            resolved,
            diagnostic_kwargs=diagnostic_kwargs,
            variable_kwargs={"timerange": args.timerange},
        )
        # Complex (experiment-based) suites take the experiment dict; simple
        # suites take the model cubes. Suite.get_database passes one data
        # object to every diagnostic, so suites are homogeneous by design.
        needs_experiments = any(
            isinstance(diag, ComplexDiagnostic)
            for diag in suite._get_diagnostics().values()
        )
        if needs_experiments and not experiment_paths:
            print(
                f"Skipping suite '{Path(resolved).stem}': needs --experiment "
                f"KEY=PATH inputs (e.g. picontrol=DIR, 4xco2=DIR, histaer=DIR)",
                file=sys.stderr,
            )
            continue
        data = experiments if needs_experiments else cubes

        db_path = out_dir / f"{Path(resolved).stem}.ddb"
        db_path.unlink(missing_ok=True)
        Path(str(db_path) + ".wal").unlink(missing_ok=True)
        print(
            f"Running suite '{Path(resolved).stem}' (timerange {args.timerange})",
            file=sys.stderr,
        )
        suite.get_database(data, info, database_resource=f"duckdb://{db_path}")
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

    from climatebench2.leaderboard import (
        build_scores,
        build_scores_table,
        render_html,
    )

    if args.csv is not None:
        summary = build_scores_table(db_paths)
        if summary.empty:
            msg = "No metrics found in the given database(s)."
            raise SystemExit(msg)
        summary.to_csv(args.csv, index=False)
        print(f"Wrote {args.csv}", file=sys.stderr)
        return

    scores = build_scores(db_paths)
    if all(
        frame.empty
        for frame in (scores.gates, scores.crps, scores.consistency, scores.tier3)
    ):
        msg = "No ClimateBench2 scores found in the given database(s)."
        raise SystemExit(msg)
    html = render_html(scores, source_names=[p.name for p in db_paths])
    output = args.output or Path("climatebench2_leaderboard.html")
    output.write_text(html, encoding="utf-8")
    print(f"Wrote {output}", file=sys.stderr)


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
        "--experiment",
        action="append",
        metavar="KEY=PATH",
        help=(
            "CMOR output of an auxiliary experiment for the Tier I gates; "
            "repeatable. Keys: picontrol, 4xco2, histaer, day, amip, "
            "amip4xco2, patch_ep, patch_wp (historical defaults to the MODEL "
            "data). Gates whose keys are absent are skipped; suites needing "
            "experiments are skipped if none are given."
        ),
    )
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
        "-o",
        "--output",
        type=Path,
        default=None,
        metavar="FILE",
        help="HTML output path (default: climatebench2_leaderboard.html).",
    )
    leaderboard.add_argument(
        "--csv",
        type=Path,
        default=None,
        metavar="FILE",
        help="Write the simple deterministic summary as CSV instead of HTML.",
    )
    leaderboard.set_defaults(func=_cmd_leaderboard)

    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help(sys.stderr)
        raise SystemExit(2)
    args.func(args)


if __name__ == "__main__":
    main()
