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
- **Tier II scores** — CRPS (with ESS-corrected uncertainty) per variable,
  reported as skill relative to the protocol baselines (climatology
  persistence and the CMIP6 multi-model ensemble), plus the regime-(b)
  consistency outcomes.
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


def build_scores(db_paths: list[Path]) -> Scores:
    """Collect gate/CRPS/consistency/deterministic/Tier-III frames."""
    import pandas as pd

    gates, crps, consistency, deterministic, tier3 = [], [], [], [], []
    for suite, diag, table, df in _read_all(db_paths):
        if df.empty:
            continue
        tagged = df.assign(suite=suite, diagnostic=diag)
        if table == "metrics":
            if "passes" in df.columns and "p_value" not in df.columns:
                # Declared-N/A rows carry no `passes` but must be kept: they
                # are how a submission says a Required test does not apply.
                is_gate = tagged["passes"].notna()
                if "applicable" in tagged.columns:
                    is_gate = is_gate | (tagged["applicable"] == 0.0)
                gates.append(tagged[is_gate])
            if "crps" in df.columns:
                crps.append(tagged[tagged["crps"].notna()])
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
        gates=_normalise_gates(cat(gates)),
        crps=cat(crps),
        consistency=cat(consistency),
        deterministic=cat(deterministic),
        tier3=cat(tier3),
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


def _crps_table_html(crps: pd.DataFrame) -> str:
    import numpy as np
    import pandas as pd

    if crps.empty:
        return "<p class='na'>No Tier II CRPS scores in the given databases.</p>"
    pivot = crps.pivot_table(
        index="data_id",
        columns="var_id",
        values="crps",
        aggfunc="mean",
    )
    baseline_ids = [
        i
        for i in pivot.index
        if i in ("Climatology", "CMIP6-MME")
        or (crps.loc[crps.data_id == i, "data_type"] == "baseline").any()
    ]
    model_ids = [i for i in pivot.index if i not in baseline_ids]

    header = "".join(f"<th>{_esc(c)}</th>" for c in pivot.columns)
    rows = []
    clim = pivot.loc["Climatology"] if "Climatology" in pivot.index else None
    for data_id in [*model_ids, *baseline_ids]:
        row = pivot.loc[data_id]
        is_baseline = data_id in baseline_ids
        cells = []
        for col, val in row.items():
            if pd.isna(val):
                cells.append("<td class='na'>—</td>")
                continue
            skill = ""
            cls = "num"
            if clim is not None and not is_baseline and np.isfinite(clim.get(col, np.nan)):
                rel = 1.0 - val / clim[col]
                mark = "beats" if rel > 0 else "loses"
                cls = f"num {mark}"
                skill = f" <small>({rel:+.0%})</small>"
            cells.append(f"<td class='{cls}'>{val:.4g}{skill}</td>")
        tr_cls = " class='baseline'" if is_baseline else ""
        rows.append(
            f"<tr{tr_cls}><td><strong>{_esc(data_id)}</strong></td>{''.join(cells)}</tr>",
        )
    return (
        "<p>CRPS per variable (lower is better); the percentage is skill "
        "relative to the climatology-persistence baseline.</p>"
        f"<table><thead><tr><th>Model</th>{header}</tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>"
    )


def _consistency_table_html(consistency: pd.DataFrame) -> str:
    import pandas as pd

    if consistency.empty:
        return ""
    cols = ["data_id", "var_id", "value", "z", "p_value", "n_members", "passes"]
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
