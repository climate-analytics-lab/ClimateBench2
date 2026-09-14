"""Command-line interface for ClimateBench2.

Installed as the ``climatebench2`` console script (see ``[project.scripts]``
in ``pyproject.toml``); also runnable as ``python -m climatebench2._cli``.

Subcommands
-----------
``climatebench2 score MODEL``
    Run the ClimateBench2 evaluation suites on a model's CMOR output via
    ClimateEval and write one DuckDB results database per suite (default:
    the CB2 tier suites, which grow per the delineation plan §6), then run
    the Tier II scoring pass over them (``--no-score`` skips it).
``climatebench2 leaderboard DB [DB ...]``
    Build the ClimateBench2 leaderboard from result databases;
    ``--rescore`` re-runs the Tier II scoring pass over them first.

The Tier II scores are a **post-processing pass**
(:mod:`climatebench2.scoring_pass`), not a diagnostic: ensemble members are
ingested as separate data sources, so a model's fair CRPS can only be formed
once every member has run. The pass is idempotent — it replaces the rows it
wrote before — so it is safe to re-run at any time.

ClimateBench2 deliberately has no data-loading or report machinery of its
own — ``score`` delegates to ClimateEval (``load_cmor_dir`` + ``Suite``), and
per-model interactive reports remain available via ``climateeval report``.

Each suite is fed the data *shape* and time window the protocol asks for
(:data:`SUITE_REGISTRY`), not one global slice of the submission:

- the Tier I / Tier II-events / Tier III suites take an **experiment dict**,
  whose ``historical`` entry is the model's own output loaded in **full** —
  the aerosol-era and Pinatubo diagnostics live in 1950–1993 and the
  clear-sky, ITCZ–EFE and hemispheric checks want the whole record. Tier I
  and Tier III run **once per model**; ``ClimateBench2_TierII_events`` runs
  **once per ensemble member** (``SuiteSpec.per_member``), each member
  supplying its own ``historical`` record, because its Tier II scalars —
  realized warming level, Pinatubo anomaly, hemispheric asymmetry — are
  scored across the ensemble by the fair-CRPS pass;
- ``ClimateBench2_TierI_variability`` (ENSO amplitude/spectrum) takes the
  **piControl** experiment in full — the paper asks for ≥ 100 yr of control;
- the Tier II suites take the model's cubes cut to the **post-2015 test
  window** (``tier2.test_window_start`` → ``<start>0101/<last complete
  year>1231``), which ``--timerange`` overrides explicitly.
"""

from __future__ import annotations

import argparse
import datetime as dt
import re
import sys
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Any

from climatebench2 import windows

# Heavy climateeval subsystems (ESMValCore/iris/dask, ~5 s to import) are
# imported lazily inside the command functions, mirroring climateeval's CLI.

DEFAULT_SUITES = [
    "ClimateBench2_TierI",
    "ClimateBench2_TierI_variability",
    "ClimateBench2_TierII_events",
    "ClimateBench2_TierII",
]
#: In-sample historical window: the default for cube suites that are not the
#: post-2015 test window (and the range ClimateEval's CMIP6 comparison
#: generator is hard-wired to).
DEFAULT_TIMERANGE = "19790101/20141231"


@dataclass(frozen=True)
class SuiteSpec:
    """How a CB2 suite is fed by ``climatebench2 score``.

    ``shape``
        ``"experiments"`` — an experiment dict (complex diagnostics), run once
        per model; ``"cubes"`` — a CubeList (simple diagnostics).
    ``source``
        For cube suites: ``"model"`` (the submission, run once per ensemble
        member) or ``"picontrol"`` (the piControl experiment, run once).
    ``window``
        For cube suites: ``"tier2"`` (the post-2015 test window),
        ``"historical"`` (:data:`DEFAULT_TIMERANGE`) or ``"full"`` (no cut).
        ``--timerange`` overrides the first two but never ``"full"``, which
        is used where a window would destroy the statistic: a control run has
        its own calendar (``TierI_variability``), and the daily suite's
        extremes, PDFs and diurnal climatologies are defined by the paper
        over the **whole historical record** and labelled in-sample.
    ``per_member``
        Whether the suite runs **once per submitted ensemble member**. True
        for the cube suites (each member's series is its own data source, and
        the scoring pass stacks them into one fair-CRPS ensemble) and for
        ``ClimateBench2_TierII_events``, whose aggregated scalars — the
        realized warming level, the Pinatubo anomaly, the hemispheric
        asymmetry — are scored across the members exactly the same way. An
        experiment-based suite that runs per member gets **that member's own
        record** as its ``historical`` key. False for Tier I and Tier III: a
        gate is a property of the model, not of one member.
    """

    shape: str
    source: str = "model"
    window: str = "historical"
    per_member: bool = False
    note: str = ""


#: Data shape and default window of every CB2 suite. Suites not listed (a
#: ClimateEval suite, a user's YAML) are classified by probing their
#: diagnostics and get the historical window.
SUITE_REGISTRY: dict[str, SuiteSpec] = {
    "ClimateBench2_TierI": SuiteSpec(
        shape="experiments",
        note="Tier I gates: one experiment dict, historical in full",
    ),
    "ClimateBench2_TierI_variability": SuiteSpec(
        shape="cubes",
        source="picontrol",
        window="full",
        note="ENSO amplitude/spectrum: >= 100 yr of piControl (paper I.5)",
    ),
    "ClimateBench2_TierII": SuiteSpec(
        shape="cubes",
        window="tier2",
        per_member=True,
        note="Tier II scoring over the reserved post-2015 test window",
    ),
    "ClimateBench2_TierII_daily": SuiteSpec(
        shape="cubes",
        window="full",
        per_member=True,
        note=(
            "Tier II daily/hourly statistics over the FULL historical record "
            "(the paper computes the extremes and the PDF/diurnal "
            "climatologies over it, not over the test window) — every entry "
            "is labelled in-sample"
        ),
    ),
    "ClimateBench2_TierII_events": SuiteSpec(
        shape="experiments",
        per_member=True,
        note=(
            "Warming level / Pinatubo / hemispheric asymmetry: each member's "
            "own historical record, in full"
        ),
    ),
    "ClimateBench2_TierIII": SuiteSpec(
        shape="experiments",
        note="Paleo time slices vs piControl",
    ),
}


def default_tier2_timerange(today: dt.date | None = None) -> str:
    """Default Tier II window: ``tier2.test_window_start`` → last complete year.

    The protocol scores whole years from the start of the reserved test
    window to the last year that has finished, so the window grows by one
    year every January without a code change. Resolved by
    :mod:`climatebench2.windows`, which the reference-window diagnostics and
    the scoring pass share, so no two of them can disagree about the window.
    """
    return windows.test_window_timerange(today)


def suite_timerange(spec: SuiteSpec, explicit: str | None = None) -> str | None:
    """Resolve the ISO timerange for one suite (``None`` = no cut).

    ``explicit`` (the user's ``--timerange``) overrides the cube suites'
    default windows, but never the piControl-sourced ``full`` window: a
    control run has its own calendar, so an instrumental-era range would
    only throw its data away.
    """
    if spec.shape != "cubes" or spec.window == "full":
        return None
    if explicit is not None:
        return explicit
    if spec.window == "tier2":
        return default_tier2_timerange()
    return DEFAULT_TIMERANGE


#: CMIP6 DRS ensemble-member directory, e.g. ``r1i1p1f1``.
_VARIANT_RE = re.compile(r"^r\d+i\d+p\d+f\d+$")


def discover_members(root: Path, *, max_depth: int = 3) -> dict[str, Path]:
    """Find sibling ``r*i*p*f*`` variant directories in a DRS tree.

    Returns ``{}`` unless at least two variant directories share a parent, so
    a single-member tree (or a flat directory) keeps today's behaviour. Only
    the parent with the most variants is used — variant names repeat across
    experiments in a DRS tree, and merging those would mix experiments.
    """
    if not root.is_dir():
        return {}
    by_parent: dict[Path, dict[str, Path]] = {}
    pattern = "*"
    for _depth in range(max_depth):
        for path in sorted(root.glob(pattern)):
            if path.is_dir() and _VARIANT_RE.match(path.name):
                by_parent.setdefault(path.parent, {})[path.name] = path
        pattern += "/*"
    if not by_parent:
        return {}
    _parent, members = max(
        by_parent.items(),
        key=lambda item: (len(item[1]), str(item[0])),
    )
    return dict(sorted(members.items())) if len(members) > 1 else {}


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


def _parse_members(specs: list[str] | None) -> dict[str, Path]:
    """Parse repeated ``--member LABEL=PATH`` options."""
    members: dict[str, Path] = {}
    for spec in specs or []:
        label, sep, path = spec.partition("=")
        if not sep or not label or not path:
            msg = f"--member expects LABEL=PATH, got '{spec}'"
            raise SystemExit(msg)
        members[label.strip()] = Path(path)
    return members


def _resolve_members(args: argparse.Namespace) -> dict[str, Path]:
    """Ensemble members of the submission: explicit, discovered or single."""
    members = _parse_members(args.member)
    for label, path in members.items():
        if not path.exists():
            msg = f"Member path not found: {label}={path}"
            raise SystemExit(msg)
    if members:
        return members
    discovered = discover_members(args.model)
    if discovered:
        print(
            f"Discovered {len(discovered)} ensemble members under {args.model}: "
            f"{', '.join(discovered)}",
            file=sys.stderr,
        )
        return discovered
    return {args.variant: args.model}


def _suite_spec(
    stem: str,
    diagnostics: dict[str, Any],
    complex_type: type,
) -> SuiteSpec:
    """Registry entry for a suite, or one inferred from its diagnostics."""
    if stem in SUITE_REGISTRY:
        return SUITE_REGISTRY[stem]
    shape = (
        "experiments"
        if any(isinstance(diag, complex_type) for diag in diagnostics.values())
        else "cubes"
    )
    # An unregistered cube suite keeps the old behaviour (one run per member);
    # an unregistered experiment suite is assumed to be a gate suite.
    return SuiteSpec(
        shape=shape,
        per_member=shape == "cubes",
        note="not in the CB2 suite registry",
    )


def _cmd_score(args: argparse.Namespace) -> None:  # noqa: C901, PLR0912, PLR0915
    if not args.model.exists():
        msg = f"Model path not found: {args.model}"
        raise SystemExit(msg)
    experiment_paths = _parse_experiments(args.experiment)
    for key, path in experiment_paths.items():
        if not path.exists():
            msg = f"Experiment path not found: {key}={path}"
            raise SystemExit(msg)
    members = _resolve_members(args)

    print("Loading ClimateEval (this can take a few seconds)…", file=sys.stderr)
    from climateeval._loader import load_cmor_dir
    from climateeval.data import DataSourceInformation
    from climateeval.diags.complex._base import ComplexDiagnostic
    from climateeval.suites import Suite

    cache: dict[tuple[str, str | None], Any] = {}

    def load(path: Path, timerange: str | None) -> Any:  # noqa: ANN401
        """Load a CMOR directory once per (path, window)."""
        key = (str(path), timerange)
        if key not in cache:
            cubes = load_cmor_dir(path, timerange=timerange)
            if not cubes:
                window = f" within {timerange}" if timerange else ""
                msg = f"No NetCDF data found in {path}{window}"
                raise SystemExit(msg)
            cache[key] = cubes
        return cache[key]

    # Experiment dict for the complex suites. Every experiment is loaded in
    # FULL (no timerange cut): piControl/abrupt-4xCO2 need their length, and
    # the historical gates run outside the Tier II test window (the aerosol
    # era, Pinatubo, the clear-sky and ITCZ-EFE records). The first member's
    # own output serves as "historical" unless --experiment historical=DIR
    # overrides it — Tier I is evaluated once per model, not per member.
    first_label, first_path = next(iter(members.items()))
    experiments: dict[str, Any] = {"historical": load(first_path, None)}
    explicit_historical = "historical" in experiment_paths
    for key, path in experiment_paths.items():
        experiments[key] = load(path, None)
        print(f"Loaded experiment '{key}' from {path} (full record)", file=sys.stderr)

    def info_for(label: str) -> DataSourceInformation:
        """Provenance for one member (the variant separates their data ids)."""
        return DataSourceInformation(
            name=args.name,
            category="model",
            institute=args.institute,
            exp=args.exp,
            variant=label or args.variant,
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

    not_applicable = [name.strip() for name in (args.not_applicable or [])]

    def build_suite(
        resolved: str,
        extra: dict[str, Any],
        timerange: str | None,
    ) -> Any:  # noqa: ANN401
        """A Suite with the CLI's kwargs and this suite's own time window."""
        return Suite(
            resolved,
            diagnostic_kwargs={**diagnostic_kwargs, **extra},
            variable_kwargs={} if timerange is None else {"timerange": timerange},
        )

    suite_names = args.suite or DEFAULT_SUITES
    db_paths: list[Path] = []
    declared_seen: set[str] = set()
    for suite_name in suite_names:
        resolved = _resolve_suite(suite_name)
        stem = Path(resolved).stem

        diagnostics = build_suite(resolved, {}, None)._get_diagnostics()
        spec = _suite_spec(stem, diagnostics, ComplexDiagnostic)
        timerange = suite_timerange(spec, args.timerange)

        # `not_applicable` is a complex-diagnostic kwarg (declared N/A gates);
        # ClimateEval's simple diagnostics take no **kwargs, so it is only
        # handed to the experiment-based suites.
        extra_kwargs: dict[str, Any] = {}
        if spec.shape == "experiments" and not_applicable:
            declared_seen |= set(diagnostics) & set(not_applicable)
            extra_kwargs["not_applicable"] = not_applicable
        suite = build_suite(resolved, extra_kwargs, timerange)

        # (data, information) pairs to run, in order; the first writes the
        # database and the rest append into it.
        runs: list[tuple[Any, DataSourceInformation]] = []
        if spec.shape == "experiments":
            available = set(experiments)
            if not any(
                set(getattr(diag, "_required_data_keys", ())) <= available
                for diag in diagnostics.values()
            ):
                print(
                    f"Skipping suite '{stem}': none of its diagnostics can run "
                    f"from the experiments given ({', '.join(sorted(available))}); "
                    f"add --experiment KEY=PATH (e.g. picontrol=DIR, 4xco2=DIR)",
                    file=sys.stderr,
                )
                continue
            if spec.per_member and not explicit_historical:
                # Tier II aggregated scalars (§II.1) are scored across the
                # submission's ensemble, so each member contributes its OWN
                # historical record under the `historical` key, with its own
                # variant in the data id; every other experiment is shared.
                runs = [
                    ({**experiments, "historical": load(path, None)}, info_for(label))
                    for label, path in members.items()
                ]
            else:
                if spec.per_member and len(members) > 1:
                    print(
                        f"Note: suite '{stem}' runs per member, but "
                        f"--experiment historical=DIR pins one record for "
                        f"every member; running it once instead",
                        file=sys.stderr,
                    )
                runs = [(experiments, info_for(first_label))]
        elif spec.source == "picontrol":
            if "picontrol" in experiments:
                runs = [(experiments["picontrol"], info_for(first_label))]
            else:
                print(
                    f"Warning: suite '{stem}' wants the piControl experiment "
                    f"(the paper asks for >= 100 yr of control) but none was "
                    f"given; falling back to the submission's own output — pass "
                    f"--experiment picontrol=DIR for a protocol-conforming run",
                    file=sys.stderr,
                )
                runs = [(load(first_path, None), info_for(first_label))]
        else:
            # `per_member` is authoritative for every shape, so a cube suite
            # that is *not* per-member scores the first member only.
            chosen = (
                list(members.items())
                if spec.per_member
                else [(first_label, first_path)]
            )
            runs = [(load(path, timerange), info_for(label)) for label, path in chosen]

        if spec.window == "tier2":
            print(
                "Note: ClimateEval's CMIP6HistoricalR1I1P1F1 comparison generator "
                "is hard-wired to 19790101/20141231 and r1i1p1f1, so the CMIP6 "
                "comparison rows stay empty for the post-2015 test window until "
                "an SSP2-4.5 generator lands upstream (metrics_reference.md #13). "
                "Model variables that do not cover the window are skipped, not "
                "fatal.",
                file=sys.stderr,
            )

        db_path = out_dir / f"{stem}.ddb"
        db_path.unlink(missing_ok=True)
        Path(str(db_path) + ".wal").unlink(missing_ok=True)
        window = timerange or "full record"
        print(
            f"Running suite '{stem}' ({spec.shape}, {window})"
            + (f" for {len(runs)} members" if len(runs) > 1 else ""),
            file=sys.stderr,
        )
        for index, (data, info) in enumerate(runs):
            suite.get_database(
                data,
                info,
                database_resource=f"duckdb://{db_path}",
                append=index > 0,
            )
        print(f"Wrote database {db_path}", file=sys.stderr)
        db_paths.append(db_path)

    for name in sorted(set(not_applicable) - declared_seen):
        print(
            f"Warning: --not-applicable '{name}' matched no gate diagnostic in "
            f"the suites that ran; the scorecard will show it as 'not run', "
            f"not 'n/a'",
            file=sys.stderr,
        )

    if len(members) > 1:
        print(
            f"\nIngested {len(members)} members ({', '.join(members)}) into the "
            f"per-member suites (the cube suites and the Tier II events), each "
            f"with its own data id; Tier I and Tier III ran once on "
            f"'{first_label or args.variant or args.name}'. The scoring pass "
            f"below stacks them into one fair-CRPS ensemble per model.",
            file=sys.stderr,
        )

    if db_paths and not args.no_score:
        run_scoring_pass(db_paths)

    print(
        f"\nDone. Score with:  climatebench2 leaderboard "
        f"{' '.join(str(p) for p in db_paths)}",
        file=sys.stderr,
    )


def run_scoring_pass(db_paths: list[Path]) -> None:
    """Run the Tier II scoring pass over the given databases, reporting to stderr.

    Members are ingested as separate data sources, so the fair CRPS of a
    model's ensemble can only be formed once every member has run — this is
    that step (``climatebench2.scoring_pass``). It is idempotent: re-running
    it replaces the scores it wrote before.
    """
    from climatebench2.scoring_pass import score_databases

    print("\nScoring Tier II (fair CRPS over stacked members)…", file=sys.stderr)
    for report in score_databases(db_paths):
        print(f"  {report.summary()}", file=sys.stderr)
        for message in report.messages:
            print(f"  {message}", file=sys.stderr)


def _cmd_leaderboard(args: argparse.Namespace) -> None:
    db_paths = [p.resolve() for p in args.db]
    for path in db_paths:
        if not path.exists():
            msg = f"Database not found: {path}"
            raise SystemExit(msg)

    if args.rescore:
        run_scoring_pass(db_paths)

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


def build_parser() -> argparse.ArgumentParser:
    """Build the ``climatebench2`` argument parser."""
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
            "  climatebench2 score MODEL --name Emulator "
            "--not-applicable geostrophic_balance\n"
            "      declare a Tier I gate inapplicable (recorded as n/a, not a fail)\n"
            "  climatebench2 score MODEL --name MyModel "
            "--member r1i1p1f1=DIR --member r2i1p1f1=DIR\n"
            "      score several ensemble members into the same databases\n"
            "  climatebench2 leaderboard MyModel_climatebench2/*.ddb\n"
            "      build the scorecard from the results\n"
            "  climatebench2 leaderboard --rescore MyModel_climatebench2/*.ddb\n"
            "      re-run the Tier II scoring pass first (idempotent)\n"
            "\n"
            "each suite gets the data shape and window the protocol asks for:\n"
            "  Tier I / TierII_events / TierIII  experiment dict, every "
            "experiment in full\n"
            "  TierI_variability                 the piControl experiment, in "
            "full (>= 100 yr)\n"
            f"  TierII                            model cubes over "
            f"{default_tier2_timerange()} (--timerange overrides)\n"
            "  TierII_daily                      model cubes over the full "
            "record (extremes/PDFs/diurnal are in-sample)\n"
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
        "--not-applicable",
        action="append",
        metavar="NAME",
        help=(
            "Declare a Tier I gate inapplicable to this submission "
            "(repeatable; NAME is the gate's suite entry name, e.g. "
            "geostrophic_balance for a model with no dynamical "
            "representation). The gate computes nothing and is recorded as "
            "n/a — neither a pass nor a fail — on the scorecard, which is "
            "different from a gate that simply did not run."
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
        "--member",
        action="append",
        metavar="LABEL=PATH",
        help=(
            "An ensemble member of the submission (repeatable); LABEL becomes "
            "the variant of its data id, e.g. r1i1p1f1=/path/r1i1p1f1. If not "
            "given and MODEL is a DRS tree with several r*i*p*f* directories, "
            "they are discovered automatically. The per-member suites — the "
            "cube suites and ClimateBench2_TierII_events, whose Tier II "
            "aggregated scalars are scored across the ensemble — run once per "
            "member into one database per suite (an event run takes that "
            "member's own record as its `historical` experiment); the Tier I "
            "and paleo suites run once per model, on the first member."
        ),
    )
    score.add_argument(
        "--timerange",
        default=None,
        help=(
            "ISO time range for the cube-based suites, overriding their "
            "protocol defaults: the Tier II suites score the reserved test "
            f"window (currently {default_tier2_timerange()}, from "
            f"tier2.test_window_start) and other cube suites use "
            f"{DEFAULT_TIMERANGE}. The experiment-based suites (Tier I, "
            "events, paleo) always load their experiments in full and ignore "
            "this, as does the piControl-fed variability suite."
        ),
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
    score.add_argument(
        "--no-score",
        action="store_true",
        help=(
            "Write the suite databases but skip the Tier II scoring pass "
            "(fair CRPS over the stacked ensemble members, its bootstrap "
            "interval and the skill against the CMIP6 median). Run it later "
            "with `climatebench2 leaderboard --rescore DB ...`."
        ),
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
    leaderboard.add_argument(
        "--rescore",
        action="store_true",
        help=(
            "Re-run the Tier II scoring pass over the databases first, "
            "replacing the scores in them. `climatebench2 score` already runs "
            "the pass; use this on databases written with --no-score, on ones "
            "written before the pass existed, or after changing "
            "thresholds.yml. The pass is idempotent."
        ),
    )
    leaderboard.set_defaults(func=_cmd_leaderboard)

    return parser


def main(argv: list[str] | None = None) -> None:
    """Run the climatebench2 command-line interface."""
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help(sys.stderr)
        raise SystemExit(2)
    args.func(args)


if __name__ == "__main__":
    main()
