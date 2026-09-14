"""End-to-end leaderboard test on a synthetic results database."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

climateeval = pytest.importorskip("climateeval")

import ibis  # noqa: E402

from climatebench2.leaderboard import Scores, build_scores, render_html  # noqa: E402


@pytest.fixture
def synthetic_db(tmp_path):  # noqa: ANN201
    """A .ddb mirroring Suite.get_database's layout (database-per-diagnostic)."""
    db_path = tmp_path / "ClimateBench2_TierI.ddb"
    conn = ibis.connect(f"duckdb://{db_path}")

    gates = pd.DataFrame(
        {
            "data_id": ["GoodModel", "GoodModel", "BadModel", "BadModel"],
            "data_type": ["to_benchmark"] * 4,
            "var_id": ["ecs_gate", "energy_balance_mean"] * 2,
            "value": [3.1, 0.05, 9.4, 0.4],
            "bound_lower": [1.0, np.nan, 1.0, np.nan],
            "bound_upper": [7.0, 0.1, 7.0, 0.1],
            "passes": [1.0, 1.0, 0.0, 0.0],
        },
    )
    crps = pd.DataFrame(
        {
            "data_id": ["GoodModel", "Climatology", "CMIP6-MME"],
            "data_type": ["to_benchmark", "baseline", "baseline"],
            "var_id": ["tas"] * 3,
            "crps": [0.08, 0.20, 0.12],
            "crps_se": [0.01] * 3,
            "t_eff": [25.0] * 3,
            "n_members": [1, 1, 12],
            "n_time": [30] * 3,
        },
    )
    tier3 = pd.DataFrame(
        {
            "data_id": ["GoodModel"],
            "data_type": ["to_benchmark"],
            "midholocene_site_consistency": [0.85],
            "midholocene_n_sites": [120.0],
        },
    )

    conn.create_database("gates_diag")
    conn.create_table("metrics", ibis.memtable(gates), database="gates_diag")
    conn.create_database("scored_ts")
    conn.create_table("metrics", ibis.memtable(crps), database="scored_ts")
    conn.create_database("paleo")
    conn.create_table("raw_output", ibis.memtable(tier3), database="paleo")
    conn.disconnect()
    return db_path


def test_build_scores_collects_all_sections(synthetic_db) -> None:  # noqa: ANN001
    scores = build_scores([synthetic_db])
    assert set(scores.gates["data_id"]) == {"GoodModel", "BadModel"}
    assert set(scores.crps["data_id"]) == {"GoodModel", "Climatology", "CMIP6-MME"}
    assert not scores.tier3.empty
    assert scores.consistency.empty


def test_render_html_gate_matrix_and_skill(synthetic_db) -> None:  # noqa: ANN001
    scores = build_scores([synthetic_db])
    html = render_html(scores, source_names=[synthetic_db.name])

    assert "<!doctype html>" in html
    assert "GoodModel" in html
    assert "BadModel" in html
    # Gate matrix: GoodModel all-pass, BadModel all-fail
    assert "✓" in html
    assert "✗" in html
    # CRPS skill vs climatology: 1 - 0.08/0.20 = +60%
    assert "+60%" in html
    # Tier III fraction
    assert "85%" in html
    # Baselines present and styled
    assert "Climatology" in html
    assert "CMIP6-MME" in html
    # Self-contained: no external resources
    assert "http" not in html.split("</style>")[1]


def test_render_html_empty_sections() -> None:
    html = render_html(Scores(), source_names=[])
    assert "No Tier I gate results" in html
    assert "No Tier II CRPS scores" in html


# ---------------------------------------------------------------------------
# Entry-ticket semantics (paper §7.1)
# ---------------------------------------------------------------------------


def _gate_rows(model: str, states: dict[str, str]) -> pd.DataFrame:
    """Gate metrics rows for one model: check_id -> pass|fail|na."""
    from climatebench2.diags.pass_fail import gate_requirements

    requirements = gate_requirements()
    rows = []
    for check, state in states.items():
        rows.append(
            {
                "data_id": model,
                "data_type": "to_benchmark",
                "var_id": check,
                "value": np.nan if state == "na" else 1.0,
                "bound_lower": np.nan,
                "bound_upper": np.nan,
                "passes": {"pass": 1.0, "fail": 0.0, "na": np.nan}[state],
                "requirement": requirements.get(check, "required"),
                "applicable": 0.0 if state == "na" else 1.0,
                "suite": "ClimateBench2_TierI",
                "diagnostic": check,
            },
        )
    return pd.DataFrame(rows)


def test_entry_ticket_four_outcomes() -> None:
    from climatebench2.leaderboard import entry_ticket

    required = ["a", "b", "c"]
    assert entry_ticket({"a": "pass", "b": "pass", "c": "pass"}, required) == "pass"
    # a declared N/A Required check does not block the ticket
    assert entry_ticket({"a": "pass", "b": "na", "c": "pass"}, required) == "pass"
    # a missing Required check makes the scorecard incomplete
    assert entry_ticket({"a": "pass", "b": "pass"}, required) == "incomplete"
    # an applicable Required failure is definitive, even with results missing
    assert entry_ticket({"a": "fail"}, required) == "fail"
    assert entry_ticket({"a": "pass", "b": "fail", "c": "na"}, required) == "fail"


def test_gate_matrix_groups_and_entry_ticket_column() -> None:
    from climatebench2.diags.pass_fail import gate_requirements
    from climatebench2.leaderboard import Scores, render_html

    requirements = gate_requirements()
    required = sorted(c for c, t in requirements.items() if t == "required")

    complete = dict.fromkeys(required, "pass")
    passing = {**complete, "geostrophic_balance": "na"}  # declared N/A
    failing = {**complete, "ecs_gate": "fail"}
    partial = {c: "pass" for c in required if c != "ecs_gate"}

    gates = pd.concat(
        [
            _gate_rows("Emulator", {**passing, "mjo_east_west": "pass"}),
            _gate_rows("BadModel", failing),
            _gate_rows("PartialModel", partial),
            _gate_rows("ExtraModel", {**complete, "bjerknes_compensation": "fail"}),
        ],
        ignore_index=True,
    )
    html = render_html(Scores(gates=gates))

    def ticket(model: str) -> str:
        row = html.split(f"<strong>{model}</strong></td>", 1)[1]
        cell = row.split("</td>", 1)[0]
        assert "gate-all" in cell, cell
        return cell.split(">")[-1]

    assert ticket("Emulator") == "✓"  # N/A does not block entry
    assert ticket("BadModel") == "✗"
    assert ticket("PartialModel") == "⚠"
    assert ticket("ExtraModel") == "✓"  # an extra check never gates entry

    # Declared N/A renders as n/a, not as a pass or a fail
    assert "n/a" in html
    # The three groups are rendered separately
    assert "Extended checks" in html
    assert "Extra checks" in html


def test_gate_matrix_distinguishes_not_run_from_not_applicable() -> None:
    from climatebench2.leaderboard import Scores, render_html

    gates = _gate_rows("M", {"ecs_gate": "na", "water_budget": "pass"})
    html = render_html(Scores(gates=gates))
    assert "n/a" in html  # declared N/A
    assert "—" in html  # every other Required check: no row at all


def test_tier2_event_flags_are_not_in_the_entry_ticket() -> None:
    from climatebench2.diags.pass_fail import gate_requirements
    from climatebench2.leaderboard import Scores, entry_ticket, render_html

    requirements = gate_requirements()
    required = sorted(c for c, t in requirements.items() if t == "required")
    states = {**dict.fromkeys(required, "pass"), "pinatubo_dimming": "fail"}
    gates = _gate_rows("M", states)

    assert entry_ticket(states, required) == "pass"
    html = render_html(Scores(gates=gates))
    assert "Tier II — aggregated event diagnostics" in html
    assert "pinatubo_dimming" in html


def test_build_scores_keeps_declared_na_rows_and_fills_old_columns(
    tmp_path,  # noqa: ANN001
) -> None:
    """Databases written before the tags still render (backward compatible)."""
    from climatebench2.leaderboard import build_scores

    db_path = tmp_path / "ClimateBench2_TierI.ddb"
    conn = ibis.connect(f"duckdb://{db_path}")
    gates = pd.DataFrame(
        {
            "data_id": ["M", "M"],
            "data_type": ["to_benchmark"] * 2,
            "var_id": ["ecs_gate", "geostrophic_balance"],
            "value": [3.1, np.nan],
            "bound_lower": [1.0, 0.9],
            "bound_upper": [7.0, np.nan],
            "passes": [1.0, np.nan],
            "applicable": [1.0, 0.0],
        },
    )
    conn.create_database("gates_diag")
    conn.create_table("metrics", ibis.memtable(gates), database="gates_diag")
    conn.disconnect()

    scores = build_scores([db_path])
    assert len(scores.gates) == 2  # the declared-N/A row survives the filter
    by_check = scores.gates.set_index("var_id")
    assert by_check.loc["geostrophic_balance", "applicable"] == 0.0
    # requirement recovered from the gate classes
    assert by_check.loc["ecs_gate", "requirement"] == "required"
    assert by_check.loc["geostrophic_balance", "requirement"] == "required"
