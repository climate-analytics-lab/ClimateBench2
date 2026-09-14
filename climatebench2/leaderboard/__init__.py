"""The ClimateBench v2 leaderboard.

Turns ClimateEval result databases (``.ddb``, one per suite — accumulate
several models with ``Suite.get_database(..., append=True)``) into the
protocol's presentation:

- **Tier I gate matrix** — every pass/fail check per model, grouped by the
  ``requirement`` tag the gate carries (paper §7.1): *Required* (the entry
  ticket), *Extended* (reported alongside, additional credit, does not gate
  entry) and *extra* (code-only sanity checks). The **Entry ticket** column
  is ✓ only when every Required check either passed or was declared N/A by
  the submission, ⚠ when a Required check produced no row at all, ✗ when an
  applicable Required check failed.
- **Tier II scores** — the headline skill ``S = 1 − E/E_ref`` per model and
  variable, where E is the model's **fair CRPS** over its stacked ensemble
  members and E_ref the **median** fair CRPS across the CMIP6 reference
  models (leave-one-out); the CRPS, its bootstrap interval and the ensemble
  size are in the cell tooltip, the Climatology-baseline skill alongside.
  The scores come from :mod:`climatebench2.scoring_pass`, which
  ``climatebench2 score`` runs after the suites (and ``leaderboard
  --rescore`` re-runs), so a database that has not been through the pass
  shows no Tier II numbers.
- **Tier III** — paleo proxy-site consistency fractions and the
  mid-Holocene monsoon gate.

``build_scores`` returns plain DataFrames; ``render_html`` produces a
self-contained static page; ``build_scores_table`` keeps the simple
deterministic summary used since Phase 0.
"""

from __future__ import annotations

import html as html_module
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from climatebench2.scoring_pass import CLIMATOLOGY_DATA_ID, SCORER

if TYPE_CHECKING:
    from pathlib import Path

    import pandas as pd


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------


def _read_all(db_paths: list[Path]) -> list[tuple[str, str, str, pd.DataFrame]]:
    """Yield (suite, diagnostic, table, df) for every table in the dbs."""
    # Private-module reuse is deliberate: climateeval is pinned by commit.
    from climateeval.report._db import read_database

    out = []
    for db_path in db_paths:
        suite = db_path.stem
        for diag_name, tables in read_database(db_path).items():
            for table_name, df in tables.items():
                out.append((suite, diag_name, table_name, df))
    return out


@dataclass
class Scores:
    """Leaderboard-ready frames (any may be empty)."""

    gates: pd.DataFrame = field(default_factory=lambda: _empty())
    crps: pd.DataFrame = field(default_factory=lambda: _empty())
    consistency: pd.DataFrame = field(default_factory=lambda: _empty())
    deterministic: pd.DataFrame = field(default_factory=lambda: _empty())
    tier3: pd.DataFrame = field(default_factory=lambda: _empty())


def _empty() -> pd.DataFrame:
    import pandas as pd

    return pd.DataFrame()


def _normalise_gates(gates: pd.DataFrame) -> pd.DataFrame:
    """Fill the requirement/applicable columns (databases predating them).

    Older result databases carry only ``passes``; their rows are all
    applicable, and their requirement tag is recovered from the gate classes
    (``climatebench2.diags``), defaulting to ``required``.
    """
    if gates.empty:
        return gates
    if "applicable" not in gates.columns:
        gates["applicable"] = 1.0
    gates["applicable"] = gates["applicable"].astype(float).fillna(1.0)
    registry: dict[str, str] = {}
    try:
        from climatebench2.diags.pass_fail import gate_requirements

        registry = gate_requirements()
    except Exception:  # noqa: BLE001 - climateeval may be unavailable
        registry = {}
    if "requirement" not in gates.columns:
        gates["requirement"] = ""
    gates["requirement"] = [
        tag if isinstance(tag, str) and tag else registry.get(var_id, "required")
        for tag, var_id in zip(gates["requirement"], gates["var_id"], strict=True)
    ]
    return gates


def _label_by_model(frame: pd.DataFrame, names: dict[str, str]) -> pd.DataFrame:
    """Relabel ``data_id`` by model name, so one model has one row everywhere.

    Tier I gate rows carry the full ``DataSourceInformation.id``
    (``model_MyModel_historical_r1i1p1f1``) because they are written per data
    source, while the scoring pass groups members and writes the **model
    name**. Mapping the ids through the ``data_sources`` tables makes the two
    halves of the scorecard agree — and collapses a model's members into one
    scorecard row, which is what a Tier I gate means (every member must pass).
    """
    if frame.empty or "data_id" not in frame.columns or not names:
        return frame
    frame = frame.copy()
    frame["data_id"] = [names.get(str(i), str(i)) for i in frame["data_id"]]
    return frame


def build_scores(db_paths: list[Path]) -> Scores:
    """Collect gate/CRPS/consistency/deterministic/Tier-III frames."""
    import pandas as pd

    gates, crps, consistency, deterministic, tier3 = [], [], [], [], []
    names: dict[str, str] = {}
    for suite, diag, table, df in _read_all(db_paths):
        if df.empty:
            continue
        tagged = df.assign(suite=suite, diagnostic=diag)
        if table == "data_sources":
            if {"id", "name"} <= set(df.columns):
                names.update(
                    {str(i): str(n) for i, n in zip(df["id"], df["name"], strict=True)},
                )
        elif table == "metrics":
            # A row is a gate iff it has a verdict and no p-value: the
            # scoring pass now writes consistency rows (which carry both
            # `passes` and `p_value`) into the *same* metrics tables, so the
            # test must be per row, never per column.
            if "passes" in df.columns:
                is_gate = tagged["passes"].notna()
                if "p_value" in tagged.columns:
                    is_gate = is_gate & tagged["p_value"].isna()
                # Declared-N/A rows carry no `passes` but must be kept: they
                # are how a submission says a Required test does not apply.
                if "applicable" in tagged.columns:
                    is_gate = is_gate | (tagged["applicable"] == 0.0)
                gates.append(tagged[is_gate])
            if "crps" in df.columns:
                # Rows the scoring pass wrote are kept even with a NaN score:
                # "n/a (single member)" is a result the scorecard must show.
                keep = tagged["crps"].notna()
                if "scorer" in tagged.columns:
                    keep = keep | (tagged["scorer"] == SCORER)
                if "p_value" in tagged.columns:
                    keep = keep & tagged["p_value"].isna()
                crps.append(tagged[keep])
            if "p_value" in df.columns:
                consistency.append(tagged[tagged["p_value"].notna()])
            metric_cols = [
                c
                for c in ("weighted_rmse", "weighted_pearsonr", "weighted_emd")
                if c in df.columns
            ]
            if metric_cols:
                deterministic.append(
                    tagged.dropna(subset=metric_cols, how="all"),
                )
        elif table == "raw_output":
            site_cols = [c for c in df.columns if c.endswith("_site_consistency")]
            if site_cols:
                tier3.append(tagged)

    def cat(frames: list[pd.DataFrame]) -> pd.DataFrame:
        return (
            pd.concat(frames, ignore_index=True, sort=False)
            if frames
            else pd.DataFrame()
        )

    return Scores(
        gates=_label_by_model(_normalise_gates(cat(gates)), names),
        crps=_label_by_model(cat(crps), names),
        consistency=_label_by_model(cat(consistency), names),
        deterministic=_label_by_model(cat(deterministic), names),
        tier3=_label_by_model(cat(tier3), names),
    )


def build_scores_table(db_paths: list[Path]) -> pd.DataFrame:
    """Simple per-model summary from the deterministic metrics (Phase 0)."""
    from climateeval.report._db import read_database
    from climateeval.report._leaderboard import build_leaderboard_data

    all_metrics = {}
    for db_path in db_paths:
        diags = read_database(db_path)
        all_metrics[db_path.stem] = {
            name: tables["metrics"]
            for name, tables in diags.items()
            if "metrics" in tables
        }
    summary, _detail = build_leaderboard_data(all_metrics)
    return summary


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

_CSS = """
body{font-family:-apple-system,'Segoe UI',Helvetica,Arial,sans-serif;margin:2rem auto;
     max-width:1100px;padding:0 1rem;color:#1a1a1a;background:#fafafa}
h1{border-bottom:3px solid #205493;padding-bottom:.3rem}
h2{margin-top:2.2rem;color:#205493}
h3{margin-top:1.6rem;color:#205493;font-size:1.02rem}
table{border-collapse:collapse;width:100%;margin:.8rem 0;background:#fff;
      box-shadow:0 1px 3px rgba(0,0,0,.08);font-size:.9rem}
th,td{border:1px solid #e2e2e2;padding:.4rem .6rem;text-align:left}
th{background:#f0f4f8;position:sticky;top:0}
td.num{text-align:right;font-variant-numeric:tabular-nums}
.pass{background:#e6f4ea;color:#1e7e34;font-weight:600;text-align:center}
.fail{background:#fdecea;color:#c0392b;font-weight:600;text-align:center}
.na{color:#999;text-align:center}
.gate-all{font-weight:700}
.baseline{font-style:italic;color:#555}
.beats{color:#1e7e34;font-weight:600}
.loses{color:#c0392b}
footer{margin-top:3rem;color:#777;font-size:.8rem;border-top:1px solid #ddd;
       padding-top:.6rem}
"""


def _esc(value: object) -> str:
    return html_module.escape(str(value))


# -- Tier I gate matrix -----------------------------------------------------
#
# Gate rows carry a `requirement` tag (required / extended / extra /
# diagnostic — thresholds.yml) and an `applicable` flag. The scorecard shows
# the three Tier I groups separately, because only the Required group is the
# paper's entry ticket, and it must distinguish "does not apply to this
# submission" (declared N/A) from "was not run".

#: Per-cell markup: state -> (css class, glyph).
_STATE_CELLS = {
    "pass": ("pass", "✓"),
    "fail": ("fail", "✗"),
    "na": ("na", "n/a"),
    "missing": ("na", "—"),
}

#: Entry-ticket verdicts.
_TICKET_CELLS = {
    "pass": ("pass", "✓"),
    "fail": ("fail", "✗"),
    "incomplete": ("na", "⚠"),
}


def _gate_states(gates: pd.DataFrame) -> dict[str, dict[str, str]]:
    """``data_id -> check_id -> "pass" | "fail" | "na"``.

    A check with rows from several diagnostics/suites must pass everywhere;
    a check whose rows are all declared N/A (``applicable = 0``) is ``na``.
    """
    states: dict[str, dict[str, str]] = {}
    for keys, group in gates.groupby(["data_id", "var_id"], sort=False):
        data_id, var_id = keys
        applicable = float(group["applicable"].max())
        passes = group["passes"].dropna()
        if applicable < 1.0 or passes.empty:
            state = "na"
        else:
            state = "pass" if float(passes.min()) >= 1.0 else "fail"
        states.setdefault(str(data_id), {})[str(var_id)] = state
    return states


def _check_requirements(gates: pd.DataFrame) -> dict[str, str]:
    """``check_id -> requirement`` for every known gate, run or not.

    The gate classes are the authority on the *full* Required set (a gate
    that never ran writes no row, and its absence is what makes an entry
    ticket incomplete); tags found in the databases win where they differ.
    """
    requirements: dict[str, str] = {}
    try:
        from climatebench2.diags.pass_fail import gate_requirements

        requirements.update(gate_requirements())
    except Exception:  # noqa: BLE001 - climateeval may be unavailable
        pass
    if not gates.empty:
        for var_id, tag in zip(gates["var_id"], gates["requirement"], strict=True):
            if isinstance(tag, str) and tag:
                requirements[str(var_id)] = tag
    return requirements


def entry_ticket(
    states: dict[str, str],
    required_checks: list[str],
) -> str:
    """Entry-ticket verdict for one model (paper §7.1).

    ``pass`` when every Required check either passed or was declared N/A;
    ``fail`` when any applicable Required check failed (a definitive
    outcome, so it outranks missing results); ``incomplete`` when a Required
    check produced no row at all.
    """
    outcomes = [states.get(check, "missing") for check in required_checks]
    if "fail" in outcomes:
        return "fail"
    if "missing" in outcomes or not outcomes:
        return "incomplete"
    return "pass"


def _gate_group_table(
    states: dict[str, dict[str, str]],
    checks: list[str],
    models: list[str],
    *,
    tickets: dict[str, str] | None = None,
) -> str:
    """One gate table; with ``tickets`` an Entry-ticket column is prepended."""
    header = "".join(f"<th>{_esc(c)}</th>" for c in checks)
    ticket_header = "<th>Entry ticket</th>" if tickets is not None else ""
    rows = []
    for model in models:
        cells = []
        if tickets is not None:
            cls, glyph = _TICKET_CELLS[tickets[model]]
            cells.append(f"<td class='gate-all {cls}'>{glyph}</td>")
        for check in checks:
            cls, glyph = _STATE_CELLS[states.get(model, {}).get(check, "missing")]
            cells.append(f"<td class='{cls}'>{glyph}</td>")
        rows.append(
            f"<tr><td><strong>{_esc(model)}</strong></td>{''.join(cells)}</tr>",
        )
    return (
        f"<table><thead><tr><th>Model</th>{ticket_header}{header}</tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>"
    )


def _gate_matrix_html(gates: pd.DataFrame) -> str:
    """The Tier I scorecard: Required (+ entry ticket), Extended, extra."""
    if gates.empty:
        return "<p class='na'>No Tier I gate results in the given databases.</p>"

    requirements = _check_requirements(gates)
    states = _gate_states(gates)
    seen = set(gates["var_id"].astype(str))

    def group(tag: str, *, include_unrun: bool) -> list[str]:
        ids = {c for c, t in requirements.items() if t == tag}
        return sorted(ids if include_unrun else ids & seen)

    required = group("required", include_unrun=True)
    extended = group("extended", include_unrun=False)
    extra = group("extra", include_unrun=False)

    tickets = {m: entry_ticket(s, required) for m, s in states.items()}
    order = {"pass": 0, "incomplete": 1, "fail": 2}
    models = sorted(states, key=lambda m: (order[tickets[m]], m))

    html = [
        "<p>Required checks are the paper's entry ticket: a model is scored "
        "only if every applicable Required check passes. "
        "<strong>✓</strong> passed · <strong>✗</strong> failed · "
        "<strong>n/a</strong> declared not applicable by the submission "
        "(<code>score --not-applicable NAME</code>) · <strong>—</strong> not "
        "run. The entry ticket is <strong>⚠</strong> while a Required check "
        "has no result at all.</p>",
        _gate_group_table(states, required, models, tickets=tickets),
    ]
    if extended:
        html += [
            "<h3>Extended checks</h3>",
            "<p>Reported alongside the entry ticket and contributing "
            "additional credit; these do <em>not</em> gate entry (their "
            "inputs are outside the CMIP6 protocol or need daily fields).</p>",
            _gate_group_table(states, extended, models),
        ]
    if extra:
        html += [
            "<h3>Extra checks (not part of the protocol)</h3>",
            "<p>Code-only sanity checks kept from the legacy pipeline; "
            "excluded from the entry ticket pending paper reconciliation.</p>",
            _gate_group_table(states, extra, models),
        ]
    return "".join(html)


def _event_flags_html(gates: pd.DataFrame) -> str:
    """Tier II aggregated event diagnostics (Pinatubo, hemispheric asymmetry)."""
    if gates.empty:
        return ""
    requirements = _check_requirements(gates)
    states = _gate_states(gates)
    seen = set(gates["var_id"].astype(str))
    checks = sorted(
        {c for c, t in requirements.items() if t == "diagnostic"} & seen,
    )
    if not checks:
        return ""
    models = sorted(m for m, s in states.items() if s.keys() & set(checks))
    return (
        "<h2>Tier II — aggregated event diagnostics</h2>"
        "<p>Sign flags of the Pinatubo response and the aerosol-era "
        "hemispheric asymmetry (<code>ClimateBench2_TierII_events</code>). "
        "These are Tier II diagnostics, not Tier I gates: they are reported, "
        "never part of the entry ticket.</p>"
        + _gate_group_table(states, checks, models)
    )


#: The paper clips the displayed skill score at S = -1 (it is bounded above
#: by 1, unbounded below, so a hopeless model would otherwise squash the
#: whole column).
SKILL_DISPLAY_FLOOR = -1.0


def _number(value: object) -> float:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return float("nan")


def _skill_cell(row: pd.Series, clim_crps: float) -> str:
    """One Tier II cell: headline skill, climatology skill, CRPS tooltip."""
    import numpy as np

    crps = _number(row.get("crps"))
    reason = row.get("reason")
    if not np.isfinite(crps):
        note = str(reason) if isinstance(reason, str) and reason else "not scored"
        return f"<td class='na' title='{_esc(note)}'>n/a<br><small>{_esc(note)}</small></td>"

    skill = _number(row.get("skill"))
    e_ref = _number(row.get("e_ref"))
    n_ref = _number(row.get("n_ref_models"))
    lo, hi = _number(row.get("crps_ci_lo")), _number(row.get("crps_ci_hi"))

    tip = [f"fair CRPS {crps:.4g}"]
    if np.isfinite(lo) and np.isfinite(hi):
        tip.append(f"95% CI [{lo:.4g}, {hi:.4g}]")
    se = _number(row.get("crps_se"))
    if np.isfinite(se):
        tip.append(f"SE {se:.3g}")
    members = _number(row.get("n_members"))
    if np.isfinite(members):
        tip.append(f"M = {members:.0f}")
    if np.isfinite(e_ref):
        tip.append(f"E_ref {e_ref:.4g} (median of {n_ref:.0f} CMIP6 models)")

    if np.isfinite(skill):
        shown = max(skill, SKILL_DISPLAY_FLOOR)
        text = f"{shown:+.2f}" + ("" if shown == skill else "▼")
        cls = "num " + ("beats" if skill > 0 else "loses")
    else:
        # No CMIP6 comparison ensemble in this database (the post-2015
        # generator is an upstream gap) — show the raw score instead.
        text = f"{crps:.4g}"
        cls = "num"
        tip.append("no CMIP6 reference ensemble: showing the raw CRPS")

    small = ""
    if np.isfinite(clim_crps) and clim_crps > 0 and row.get("data_type") != "baseline":
        small = f"<br><small>clim {1.0 - crps / clim_crps:+.2f}</small>"
    return f"<td class='{cls}' title='{_esc('; '.join(tip))}'>{text}{small}</td>"


def _crps_table_html(crps: pd.DataFrame) -> str:
    import numpy as np

    if crps.empty:
        return "<p class='na'>No Tier II CRPS scores in the given databases.</p>"

    # One record per (model, variable); a variable scored by several
    # diagnostics keeps the first row rather than averaging incomparable
    # scores together. A submission that is *also* in the CMIP6 comparison
    # ensemble (the leave-one-out case) is shown as the submission.
    #: Which row wins a (model, variable) collision, and the row order of the
    #: table: the submission first, then the comparison models, baselines last.
    rank = {"to_benchmark": 0, "other": 1, "baseline": 2}
    records: dict[tuple[str, str], pd.Series] = {}
    for _, row in crps.iterrows():
        key = (str(row["data_id"]), str(row["var_id"]))
        kept = records.get(key)
        if kept is None or rank.get(str(row.get("data_type")), 3) < rank.get(
            str(kept.get("data_type")),
            3,
        ):
            records[key] = row
    variables = sorted({var for (_, var) in records})

    def data_type(model: str) -> str:
        return min(
            (str(r.get("data_type")) for (m, _), r in records.items() if m == model),
            key=lambda t: rank.get(t, 3),
        )

    models = sorted(
        {model for (model, _) in records},
        key=lambda m: (rank.get(data_type(m), 3), m),
    )
    clim = {
        var: _number(records[CLIMATOLOGY_DATA_ID, var].get("crps"))
        for var in variables
        if (CLIMATOLOGY_DATA_ID, var) in records
    }

    header = "".join(f"<th>{_esc(v)}</th>" for v in variables)
    body = []
    for model in models:
        cells = []
        for var in variables:
            row = records.get((model, var))
            if row is None:
                cells.append("<td class='na'>—</td>")
                continue
            cells.append(_skill_cell(row, clim.get(var, float("nan"))))
        tr_cls = " class='baseline'" if data_type(model) == "baseline" else ""
        body.append(
            f"<tr{tr_cls}><td><strong>{_esc(model)}</strong></td>"
            f"{''.join(cells)}</tr>",
        )

    # How many CMIP6 models stand behind each E_ref (leave-one-out, so the
    # largest value over the column is the size of the reference ensemble).
    counts = []
    for var in variables:
        values = [
            _number(r.get("n_ref_models"))
            for (_, v), r in records.items()
            if v == var
        ]
        finite = [v for v in values if np.isfinite(v)]
        counts.append(
            f"<td class='num'>{max(finite):.0f}</td>" if finite else "<td class='na'>0</td>",
        )
    body.append(
        "<tr><td><em>CMIP6 models behind E_ref</em></td>" + "".join(counts) + "</tr>",
    )

    return (
        "<p>Headline skill <strong>S = 1 − E/E_ref</strong> per variable, "
        "where E is the <strong>fair CRPS</strong> of the model's ensemble and "
        "E_ref the <strong>median</strong> fair CRPS across the CMIP6 "
        "reference models (leave-one-out). S = 0 is median-CMIP6 performance, "
        "S = 1 a perfect match; the score is bounded above but not below and "
        f"the display is clipped at {SKILL_DISPLAY_FLOOR:+.0f} (▼). The small "
        "figure is the same skill against the <em>Climatology</em> baseline. "
        "Hover a cell for the CRPS, its bootstrap interval and the ensemble "
        "size. <strong>n/a</strong> marks a model the protocol cannot score — "
        "most often a single-member submission, for which fair CRPS is "
        "undefined.</p>"
        f"<table><thead><tr><th>Model</th>{header}</tr></thead>"
        f"<tbody>{''.join(body)}</tbody></table>"
    )


def _consistency_table_html(consistency: pd.DataFrame) -> str:
    import pandas as pd

    if consistency.empty:
        return ""
    cols = [
        "data_id",
        "var_id",
        "value",
        "z",
        "p_value",
        "sigma_internal",
        "sigma_obs",
        "n_members",
        "passes",
    ]
    cols = [c for c in cols if c in consistency.columns]
    sub = consistency[cols]
    header = "".join(f"<th>{_esc(c)}</th>" for c in cols)
    rows = []
    for _, row in sub.iterrows():
        cells = []
        for c in cols:
            val = row[c]
            if c == "passes":
                cls = "pass" if val >= 1.0 else "fail"
                cells.append(f"<td class='{cls}'>{'✓' if val >= 1.0 else '✗'}</td>")
            elif isinstance(val, float) and not pd.isna(val):
                cells.append(f"<td class='num'>{val:.4g}</td>")
            else:
                cells.append(f"<td>{_esc(val)}</td>")
        rows.append(f"<tr>{''.join(cells)}</tr>")
    return (
        "<h2>Tier II — ensemble-consistency tests</h2>"
        "<p>Regime (c), a reported diagnostic and falsification check — never "
        "part of the entry ticket or of the headline skill. The observed "
        "statistic is tested against the model's own ensemble, with "
        "σ_total² = var(members) + σ_int² + σ_obs²: σ_int from the piControl "
        "chunks of the <code>internal_variability</code> diagnostic (0 when "
        "no piControl was supplied), σ_obs from <code>tier2.obs_sigma</code> "
        "and the spread across observational products.</p>"
        f"<table><thead><tr>{header}</tr></thead><tbody>{''.join(rows)}</tbody></table>"
    )


def _tier3_html(tier3: pd.DataFrame) -> str:
    if tier3.empty:
        return ""
    site_cols = sorted(
        {c for c in tier3.columns if c.endswith("_site_consistency")},
    )
    rows = []
    for _, row in tier3.iterrows():
        for col in site_cols:
            val = row.get(col)
            if val is None or (isinstance(val, float) and val != val):
                continue
            rows.append(
                f"<tr><td><strong>{_esc(row.get('data_id', '?'))}</strong></td>"
                f"<td>{_esc(col.replace('_site_consistency', ''))}</td>"
                f"<td class='num'>{float(val):.0%}</td></tr>",
            )
    if not rows:
        return ""
    return (
        "<h2>Tier III — paleo proxy-site consistency</h2>"
        "<p>Fraction of proxy sites where the model anomaly is consistent "
        "with the proxy within its uncertainty (regime-b, p ≥ 0.05).</p>"
        "<table><thead><tr><th>Model</th><th>Period</th><th>Consistent sites"
        f"</th></tr></thead><tbody>{''.join(rows)}</tbody></table>"
    )


def render_html(scores: Scores, *, source_names: list[str] | None = None) -> str:
    """Render the leaderboard as a self-contained static HTML page."""
    sources = ", ".join(_esc(s) for s in (source_names or []))
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>ClimateBench v2 Leaderboard</title><style>{_CSS}</style></head><body>
<h1>ClimateBench v2 Leaderboard</h1>
<p>Protocol: tiered physical-consistency gates (Tier I), probabilistic
scores against observations (Tier II), out-of-sample paleo tests (Tier III).
Spec: <code>docs/metrics_reference.md</code>.</p>
<h2>Tier I — physical-consistency gates (entry ticket)</h2>
{_gate_matrix_html(scores.gates)}
<h2>Tier II — probabilistic scores vs baselines</h2>
{_crps_table_html(scores.crps)}
{_event_flags_html(scores.gates)}
{_consistency_table_html(scores.consistency)}
{_tier3_html(scores.tier3)}
<footer>Generated by <code>climatebench2 leaderboard</code> from: {sources}
</footer></body></html>"""
