"""The Tier II scoring pass over a finished results database.

Why a pass and not a diagnostic
-------------------------------
Ensemble members are ingested as **separate data sources** (``--member`` /
DRS auto-discovery run every cube suite once per member, appending rows whose
``data_id``s differ only by ``variant``). A model's fair CRPS therefore can
only be formed once *all* of its members have run — which is after the suite,
not inside a diagnostic. This module is that post-processing step:
``climatebench2 score`` runs it on the databases it just wrote, and
``climatebench2 leaderboard --rescore`` re-runs it on existing ones.

What it computes (metrics_reference.md Tier II preamble, §II.0)
---------------------------------------------------------------
For every time-series diagnostic in the database (a ``raw_output`` table with
a ``time`` column and a ``reference`` data source), and every variable in it:

1. group the non-reference rows **by model name** — the ``data_sources``
   table maps each ``data_id`` to ``(name, variant)``, so the members of one
   model come back together and the CMIP6 comparison models stay apart;
2. stack a model's members on the times they share with the reference and
   score them with the **fair CRPS** per step (``M >= 2``; a single-member
   model gets a row with ``crps = NaN`` and ``reason = "single member"``,
   since fair CRPS is undefined for a deterministic forecast);
3. summarise: time-mean score, ESS-corrected standard error, and a
   moving-block-bootstrap confidence interval (``tier2.bootstrap``);
4. add the **Climatology** baseline — the distribution of the reference's
   1985-2014 values for each calendar month (:mod:`climatebench2.baselines`);
5. set ``E_ref`` = **median of the per-model fair CRPS over the CMIP6
   comparison models** with ``M >= 2``, excluding any comparison model whose
   name equals the scored model's (leave-one-out, paper §5.6), and write the
   skill ``S = 1 - E_model / E_ref`` — bounded above, unbounded below.

Rows are appended to the diagnostic's own ``metrics`` table (never a new
schema): missing columns are added with ``ALTER TABLE ADD COLUMN``, and every
row carries ``scorer = "climatebench2"`` so a re-run deletes its predecessors
first and is idempotent.

The pooled ``CMIP6-MME`` row of earlier revisions is gone: a pooled
multi-model mixture is overdispersed (its spread is structural disagreement,
not internal variability), which inflates ``E_ref`` — the doc's ⚠ rules it
out in favour of the median of per-model scores.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import numpy as np
import pandas as pd

from climatebench2 import baselines, scoring
from climatebench2._thresholds import get_threshold

if TYPE_CHECKING:
    from pathlib import Path

#: Value of the ``scorer`` column on every row this pass writes. Rows with
#: this tag are deleted before a re-run, which makes the pass idempotent.
SCORER = "climatebench2"

#: ``data_id`` of the climatology-baseline row.
CLIMATOLOGY_DATA_ID = "Climatology"

#: ``data_id`` of the pattern-scaling baseline row — the hook for the later
#: work package. ``baselines.two_layer_ebm`` + ``baselines.pattern_scaling_
#: forecast`` are the maths; what is missing is an ERF series, a calibration
#: through 2014 and a CMIP6-MMM warming pattern, none of which the results
#: database carries, so nothing writes this row yet.
PATTERN_SCALING_DATA_ID = "PatternScaling"

#: DuckDB schemas that are not diagnostics.
_SKIP_SCHEMAS = {"main", "memory", "information_schema", "temp", "system", "pg_catalog"}

#: raw_output columns that are not variables.
_META_COLUMNS = {"data_id", "data_type", "time"}

#: Minimum overlapping time steps for a score to be meaningful.
_MIN_OVERLAP = 3

#: Minimum members for a fair CRPS.
_MIN_MEMBERS = 2

#: Median monthly-step length used to tell a monthly series from an annual one.
_MONTHLY_MAX_DAYS = 200

#: The scoring columns, with their DuckDB types. Text columns stay text;
#: everything else is DOUBLE so the table remains numeric-friendly.
_SCORE_COLUMNS: dict[str, str] = {
    "data_id": "VARCHAR",
    "data_type": "VARCHAR",
    "var_id": "VARCHAR",
    "scorer": "VARCHAR",
    "reason": "VARCHAR",
    "crps": "DOUBLE",
    "crps_se": "DOUBLE",
    "crps_ci_lo": "DOUBLE",
    "crps_ci_hi": "DOUBLE",
    "t_eff": "DOUBLE",
    "r1": "DOUBLE",
    "n_members": "DOUBLE",
    "n_time": "DOUBLE",
    "block_length": "DOUBLE",
    "e_ref": "DOUBLE",
    "n_ref_models": "DOUBLE",
    "skill": "DOUBLE",
}


@dataclass
class PassReport:
    """What the pass did to one database."""

    database: str
    diagnostics: list[str] = field(default_factory=list)
    rows: int = 0
    scored_models: int = 0
    single_member: int = 0
    messages: list[str] = field(default_factory=list)

    def summary(self) -> str:
        """One-line human-readable summary."""
        if not self.diagnostics:
            return f"{self.database}: no scorable time-series diagnostics"
        return (
            f"{self.database}: {self.rows} score rows across "
            f"{len(self.diagnostics)} diagnostic(s); {self.scored_models} model(s) "
            f"with M >= {_MIN_MEMBERS}, {self.single_member} single-member"
        )


# ---------------------------------------------------------------------------
# Grouping helpers (pure pandas — unit-testable without a database)
# ---------------------------------------------------------------------------


def source_names(data_sources: pd.DataFrame | None) -> dict[str, str]:
    """``data_id -> model name`` from a ``data_sources`` table.

    The id is ``"_".join(category, name, exp, variant)`` (empty parts
    dropped), so two ensemble members of one model differ only in their
    ``variant`` and must be mapped back to the same name before scoring.
    """
    if data_sources is None or data_sources.empty:
        return {}
    if not {"id", "name"} <= set(data_sources.columns):
        return {}
    return {
        str(row_id): str(name)
        for row_id, name in zip(
            data_sources["id"],
            data_sources["name"],
            strict=True,
        )
    }


def group_members(
    raw_df: pd.DataFrame,
    names: dict[str, str],
) -> dict[tuple[str, str], list[pd.DataFrame]]:
    """``(data_type, model name) -> [member frames]`` for the scorable rows.

    Reference rows are excluded (they are the target, not a forecast). A
    ``data_id`` absent from ``data_sources`` keeps its id as its name, so a
    hand-built or older database still groups sensibly (one member each).
    """
    groups: dict[tuple[str, str], list[pd.DataFrame]] = {}
    for (data_id, data_type), frame in raw_df.groupby(
        ["data_id", "data_type"],
        sort=True,
    ):
        if str(data_type) == "reference":
            continue
        name = names.get(str(data_id), str(data_id))
        groups.setdefault((str(data_type), name), []).append(
            frame.sort_values("time"),
        )
    return groups


def stack_members(
    members: list[pd.DataFrame],
    reference: pd.DataFrame,
    column: str,
) -> tuple[np.ndarray, np.ndarray, pd.Series]:
    """Stack member series on the times every member shares with the obs.

    Returns ``(members (M, T), obs (T,), times (T,))``.
    """
    merged = reference[["time", column]].rename(columns={column: "obs"}).dropna()
    for i, member in enumerate(members):
        merged = pd.merge(
            merged,
            member[["time", column]].rename(columns={column: f"m{i}"}),
            on="time",
            how="inner",
        )
    merged = merged.dropna().sort_values("time")
    matrix = merged[[f"m{i}" for i in range(len(members))]].to_numpy(float).T
    return matrix, merged["obs"].to_numpy(float), merged["time"]


def is_monthly(times: pd.Series) -> bool:
    """Whether a time axis steps by roughly a month rather than a year."""
    stamps = pd.to_datetime(times)
    if stamps.size < 2:  # noqa: PLR2004 - a single step tells us nothing
        return False
    return bool(stamps.diff().dropna().dt.days.median() < _MONTHLY_MAX_DAYS)


# ---------------------------------------------------------------------------
# Scoring one (diagnostic, variable)
# ---------------------------------------------------------------------------


def _bootstrap_settings() -> dict[str, Any]:
    return {
        "block_length_monthly": int(get_threshold("tier2.bootstrap.block_length_monthly")),
        "block_length_annual": int(get_threshold("tier2.bootstrap.block_length_annual")),
        "n_boot": int(get_threshold("tier2.bootstrap.n_boot")),
        "alpha": float(get_threshold("tier2.bootstrap.alpha")),
        "resample_members": bool(get_threshold("tier2.bootstrap.resample_members")),
        "seed": int(get_threshold("tier2.bootstrap.seed")),
    }


def _empty_row(data_id: str, data_type: str, var_id: str, reason: str) -> dict[str, Any]:
    """A row that records *why* there is no score, keeping the model visible."""
    row: dict[str, Any] = dict.fromkeys(_SCORE_COLUMNS, np.nan)
    row.update(
        data_id=data_id,
        data_type=data_type,
        var_id=var_id,
        scorer=SCORER,
        reason=reason,
    )
    return row


def _score_row(
    *,
    data_id: str,
    data_type: str,
    var_id: str,
    members: np.ndarray,
    obs: np.ndarray,
    monthly: bool,
    settings: dict[str, Any],
    obs_sigma: float | np.ndarray = 0.0,
) -> dict[str, Any]:
    """Fair CRPS + ESS SE + block-bootstrap CI for one stacked ensemble."""
    n_draws = int(get_threshold("tier2.obs_uncertainty.n_draws"))
    crps_t = scoring.crps_fair_with_obs_draws(
        members,
        obs,
        obs_sigma=obs_sigma,
        n_draws=n_draws,
        seed=int(get_threshold("tier2.obs_uncertainty.seed")),
    )
    summary = scoring.crps_ess_from_series(crps_t, members.shape[0])
    block_length = (
        settings["block_length_monthly"] if monthly else settings["block_length_annual"]
    )
    lo, hi = scoring.moving_block_bootstrap_ci(
        crps_t,
        block_length=block_length,
        n_boot=settings["n_boot"],
        alpha=settings["alpha"],
        seed=settings["seed"],
        members=members if settings["resample_members"] else None,
        obs=obs if settings["resample_members"] else None,
    )
    row = _empty_row(data_id, data_type, var_id, "")
    row.update(
        crps=summary.score,
        crps_se=summary.standard_error,
        crps_ci_lo=lo,
        crps_ci_hi=hi,
        t_eff=summary.t_eff,
        r1=summary.r1,
        n_members=float(summary.n_members),
        n_time=float(summary.n_time),
        block_length=float(block_length),
    )
    return row


def _climatology_row(
    reference: pd.DataFrame,
    column: str,
    settings: dict[str, Any],
) -> dict[str, Any]:
    """Baseline (i) as a distribution (see :mod:`climatebench2.baselines`)."""
    ref = reference[["time", column]].dropna().sort_values("time")
    if ref.empty:
        return _empty_row(CLIMATOLOGY_DATA_ID, "baseline", column, "no reference")
    times = pd.to_datetime(ref["time"])
    year_0, year_1 = get_threshold("tier2.climatology_baseline_period")
    years = times.dt.year.to_numpy()
    in_window = (years >= int(year_0)) & (years <= int(year_1))
    monthly = is_monthly(ref["time"])
    if in_window.sum() < _MIN_OVERLAP:
        # The Tier II suites cut every variable — the reference included — to
        # the post-2015 test window, so the 1985-2014 baseline values are
        # simply not in the database. Say so instead of silently dropping the
        # no-skill floor. (Fix: load the reference over the baseline window
        # too; that is a data-path change, not a scoring one.)
        return _empty_row(
            CLIMATOLOGY_DATA_ID,
            "baseline",
            column,
            f"reference has no {int(year_0)}-{int(year_1)} baseline window",
        )
    # Score the baseline on the reserved test window — the same target steps
    # the models are scored on, never on the window it was fitted to.
    is_target = years >= int(get_threshold("tier2.test_window_start"))
    if is_target.sum() < _MIN_OVERLAP:
        is_target = ~in_window
    if is_target.sum() < _MIN_OVERLAP:
        return _empty_row(
            CLIMATOLOGY_DATA_ID,
            "baseline",
            column,
            "reference has no test-window steps to score the baseline on",
        )
    window_values = ref[column].to_numpy(float)[in_window]
    obs = ref[column].to_numpy(float)[is_target]
    try:
        if monthly:
            members = baselines.climatology_pseudo_members(
                window_values,
                window_months=times.dt.month.to_numpy()[in_window],
                target_months=times.dt.month.to_numpy()[is_target],
            )
        else:
            members = baselines.climatology_pseudo_members(
                window_values,
                n_time=int(obs.size),
            )
    except ValueError as exc:
        return _empty_row(CLIMATOLOGY_DATA_ID, "baseline", column, str(exc))
    if members.shape[0] < _MIN_MEMBERS:
        return _empty_row(
            CLIMATOLOGY_DATA_ID,
            "baseline",
            column,
            "baseline window too short for a distribution",
        )
    return _score_row(
        data_id=CLIMATOLOGY_DATA_ID,
        data_type="baseline",
        var_id=column,
        members=members,
        obs=obs,
        monthly=monthly,
        settings=settings,
    )


def score_raw_output(
    raw_df: pd.DataFrame,
    data_sources: pd.DataFrame | None,
    *,
    settings: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Score one diagnostic's ``raw_output`` table; returns metrics rows.

    Pure pandas/numpy — the database plumbing is in :func:`score_database`.
    """
    if "time" not in raw_df.columns or "data_id" not in raw_df.columns:
        return []
    settings = settings or _bootstrap_settings()
    names = source_names(data_sources)
    var_columns = [c for c in raw_df.columns if c not in _META_COLUMNS]
    references = raw_df[raw_df["data_type"] == "reference"]
    if references.empty or not var_columns:
        return []
    reference = references[references["data_id"] == references["data_id"].iloc[0]]
    groups = group_members(raw_df, names)

    rows: list[dict[str, Any]] = []
    for column in var_columns:
        ref_series = reference[["time", column]].dropna()
        if ref_series.shape[0] < _MIN_OVERLAP:
            continue
        scored: dict[tuple[str, str], dict[str, Any]] = {}
        for (data_type, name), member_frames in groups.items():
            members, obs, times = stack_members(member_frames, reference, column)
            if obs.size < _MIN_OVERLAP:
                continue
            if members.shape[0] < _MIN_MEMBERS:
                scored[data_type, name] = _empty_row(
                    name,
                    data_type,
                    column,
                    "single member",
                )
                scored[data_type, name]["n_members"] = float(members.shape[0])
                scored[data_type, name]["n_time"] = float(obs.size)
                continue
            scored[data_type, name] = _score_row(
                data_id=name,
                data_type=data_type,
                var_id=column,
                members=members,
                obs=obs,
                monthly=is_monthly(times),
                settings=settings,
            )

        clim = _climatology_row(reference, column, settings)
        scored[clim["data_type"], clim["data_id"]] = clim

        # E_ref: median of the per-model fair CRPS over the CMIP6 comparison
        # models with M >= 2, leaving out any model of the scored model's own
        # name (paper §5.6). Comparison models are scored the same way, so
        # each of them is also left out of its own reference.
        comparison = {
            name: row["crps"]
            for (data_type, name), row in scored.items()
            if data_type == "other" and np.isfinite(row["crps"])
        }
        for row in scored.values():
            others = [e for n, e in comparison.items() if n != row["data_id"]]
            row["n_ref_models"] = float(len(others))
            if others:
                e_ref = float(np.median(others))
                row["e_ref"] = e_ref
                if np.isfinite(row["crps"]) and e_ref > 0:
                    row["skill"] = 1.0 - row["crps"] / e_ref
        rows.extend(scored.values())
    return rows


# ---------------------------------------------------------------------------
# Database plumbing
# ---------------------------------------------------------------------------


def _table_columns(con: Any, schema: str, table: str) -> dict[str, str]:  # noqa: ANN401
    rows = con.execute(
        "SELECT column_name, data_type FROM information_schema.columns "
        "WHERE table_schema = ? AND table_name = ?",
        [schema, table],
    ).fetchall()
    return {str(name): str(dtype) for name, dtype in rows}


def score_database(
    db_path: Path | str,
    *,
    settings: dict[str, Any] | None = None,
) -> PassReport:
    """Run the Tier II scoring pass over one results database, in place.

    Idempotent: rows tagged ``scorer = 'climatebench2'`` are deleted before
    the new ones are inserted, so re-running (``leaderboard --rescore``)
    replaces earlier scores rather than duplicating them.

    ``settings`` overrides the ``tier2.bootstrap`` block (tests and quick
    re-scores; the protocol values come from ``thresholds.yml``).
    """
    import duckdb

    path = str(db_path)
    report = PassReport(database=path)
    settings = settings or _bootstrap_settings()
    con = duckdb.connect(path)
    try:
        schemas = [
            str(row[0])
            for row in con.execute(
                "SELECT schema_name FROM information_schema.schemata",
            ).fetchall()
            if str(row[0]).lower() not in _SKIP_SCHEMAS
        ]
        for schema in schemas:
            tables = {
                str(row[0])
                for row in con.execute(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema = ?",
                    [schema],
                ).fetchall()
            }
            if "raw_output" not in tables:
                continue
            raw_df = con.execute(f'SELECT * FROM "{schema}"."raw_output"').df()
            sources = (
                con.execute(f'SELECT * FROM "{schema}"."data_sources"').df()
                if "data_sources" in tables
                else None
            )
            rows = score_raw_output(raw_df, sources, settings=settings)
            if not rows:
                continue
            frame = pd.DataFrame(rows)[list(_SCORE_COLUMNS)]
            _write_rows(con, schema, frame, has_metrics="metrics" in tables)
            report.diagnostics.append(schema)
            report.rows += len(frame)
            report.scored_models += int(frame["crps"].notna().sum())
            for reason, count in frame.loc[
                frame["reason"] != "",
                "reason",
            ].value_counts().items():
                if str(reason) == "single member":
                    report.single_member += int(count)
                report.messages.append(
                    f"  {schema}: {int(count)} row(s) unscored — {reason}",
                )
    finally:
        con.close()
    return report


def _write_rows(
    con: Any,  # noqa: ANN401
    schema: str,
    frame: pd.DataFrame,
    *,
    has_metrics: bool,
) -> None:
    """Append score rows to ``schema.metrics``, adding columns as needed."""
    con.register("cb2_score_rows", frame)
    try:
        if not has_metrics:
            con.execute(
                f'CREATE TABLE "{schema}"."metrics" AS '
                f"SELECT * FROM cb2_score_rows",
            )
            return
        existing = _table_columns(con, schema, "metrics")
        for column, dtype in _SCORE_COLUMNS.items():
            if column not in existing:
                con.execute(
                    f'ALTER TABLE "{schema}"."metrics" ADD COLUMN "{column}" {dtype}',
                )
        if "scorer" in existing:
            con.execute(
                f'DELETE FROM "{schema}"."metrics" WHERE scorer = ?',  # noqa: S608
                [SCORER],
            )
        columns = ", ".join(f'"{c}"' for c in _SCORE_COLUMNS)
        con.execute(
            f'INSERT INTO "{schema}"."metrics" ({columns}) '  # noqa: S608
            f"SELECT {columns} FROM cb2_score_rows",
        )
    finally:
        con.unregister("cb2_score_rows")


def score_databases(
    db_paths: list[Path] | list[str],
    *,
    settings: dict[str, Any] | None = None,
) -> list[PassReport]:
    """Run :func:`score_database` over several databases."""
    return [score_database(path, settings=settings) for path in db_paths]
