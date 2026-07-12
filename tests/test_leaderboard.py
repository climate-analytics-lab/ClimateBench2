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
