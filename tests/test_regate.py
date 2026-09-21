"""Tests for `climatebench2.regate` — `climatebench2 leaderboard --regate`.

Mirrors the layout ``tests/test_scoring_pass.py`` uses for ``--rescore``: a
``.ddb`` built table-by-table to match what ``Suite.get_database`` writes, so
no climate data or ClimateEval run is needed. The gate bound is monkeypatched
on the real ``ITCZEFEGate`` rather than by editing ``thresholds.yml`` on
disk, because a ``GateCheck``'s bound is a literal baked in at class-body
(module-import) time (see ``climatebench2/diags/tier1_physics.py``) — exactly
what a real ``thresholds.yml`` edit followed by a fresh ``climatebench2``
invocation would produce, without depending on this test suite's process
having imported the module before or after any particular edit.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

duckdb = pytest.importorskip("duckdb")

from climatebench2 import regate  # noqa: E402
from climatebench2.diags import tier1_physics  # noqa: E402
from climatebench2.diags.pass_fail import GateCheck  # noqa: E402

ITCZ_SCHEMA = "itcz_efe"
DATA_ID = "model_MyModel_historical_r1i1p1f1"


def _write_db(tmp_path, schema: str, tables: dict[str, pd.DataFrame]):  # noqa: ANN001, ANN201
    db_path = tmp_path / "ClimateBench2_TierI.ddb"
    con = duckdb.connect(str(db_path))
    con.execute(f'CREATE SCHEMA "{schema}"')
    for table, frame in tables.items():
        con.register("frame", frame)
        con.execute(f'CREATE TABLE "{schema}"."{table}" AS SELECT * FROM frame')
        con.unregister("frame")
    con.close()
    return db_path


def _read_metrics(db_path, schema: str) -> pd.DataFrame:  # noqa: ANN001
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        return con.execute(f'SELECT * FROM "{schema}"."metrics"').df()
    finally:
        con.close()


@pytest.fixture
def tightened_corr_check(monkeypatch):  # noqa: ANN001, ANN201
    """Patch ``ITCZEFEGate`` to one correlation check with ``lower = 0.90``.

    Simulates ``thresholds.yml``'s ``tier1.itcz_efe.corr_min`` having been
    raised since the database was written (the database below was written
    with ``bound_lower = 0.5``, an arbitrary looser value).
    """
    check = GateCheck(
        check_id="itcz_efe_correlation",
        column="itcz_efe_r_abs",
        lower=0.90,
        requirement="required",
        tier="I",
    )
    monkeypatch.setattr(tier1_physics.ITCZEFEGate, "_gate_checks", (check,))
    return check


def _raw_output(r_abs: float) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "data_id": [DATA_ID],
            "data_type": ["to_benchmark"],
            "itcz_efe_r_abs": [r_abs],
            "itcz_efe_slope_abs": [3.0],
        },
    )


def _gate_row(*, passes: float, bound_lower: float, var_id: str = "itcz_efe_correlation") -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "data_id": DATA_ID,
                "data_type": "to_benchmark",
                "var_id": var_id,
                "value": np.nan,
                "bound_lower": bound_lower,
                "bound_upper": np.nan,
                "passes": passes,
                "requirement": "required",
                "tier": "I",
                "applicable": 1.0,
            },
        ],
    )


# ---------------------------------------------------------------------------
# Schema -> diagnostic resolution
# ---------------------------------------------------------------------------


def test_schema_diagnostic_paths_maps_itcz_efe() -> None:
    mapping = regate.schema_diagnostic_paths()
    assert mapping["itcz_efe"] == "climatebench2.diags.ITCZEFEGate"
    assert mapping["ecs_gate"] == "climatebench2.diags.ECSGate"


def test_gate_checks_for_schema_distinguishes_unknown_from_non_gate() -> None:
    assert regate.gate_checks_for_schema("not_a_real_schema") is None
    # A schema this repo's suites do define, with no gates of its own.
    checks = regate.gate_checks_for_schema("internal_variability")
    assert checks == ()


# ---------------------------------------------------------------------------
# 1. A tightened bound flips `passes`
# ---------------------------------------------------------------------------


def test_regate_flips_passes_when_a_bound_tightens(
    tmp_path,  # noqa: ANN001
    tightened_corr_check,  # noqa: ANN001
) -> None:
    raw = _raw_output(r_abs=0.87)  # below the new 0.90 bound
    metrics = _gate_row(passes=1.0, bound_lower=0.5)  # was passing the old, looser bound
    db_path = _write_db(tmp_path, ITCZ_SCHEMA, {"raw_output": raw, "metrics": metrics})

    report = regate.regate_database(db_path)

    assert report.rows_evaluated == 1
    assert report.rows_changed == 1
    result = _read_metrics(db_path, ITCZ_SCHEMA).iloc[0]
    assert result["passes"] == 0.0
    assert result["bound_lower"] == pytest.approx(0.90)
    assert result["requirement"] == tightened_corr_check.requirement
    assert result["tier"] == tightened_corr_check.tier
    # `value` is never rewritten by a regate.
    assert pd.isna(result["value"])


def test_regate_leaves_a_still_passing_row_unflipped(
    tmp_path,  # noqa: ANN001
    tightened_corr_check,  # noqa: ANN001
) -> None:
    raw = _raw_output(r_abs=0.95)  # still above the new 0.90 bound
    metrics = _gate_row(passes=1.0, bound_lower=0.5)
    db_path = _write_db(tmp_path, ITCZ_SCHEMA, {"raw_output": raw, "metrics": metrics})

    report = regate.regate_database(db_path)

    assert report.rows_evaluated == 1
    assert report.rows_changed == 0  # bound moved, but the verdict did not
    result = _read_metrics(db_path, ITCZ_SCHEMA).iloc[0]
    assert result["passes"] == 1.0
    assert result["bound_lower"] == pytest.approx(0.90)


# ---------------------------------------------------------------------------
# 2. Idempotence
# ---------------------------------------------------------------------------


def test_regate_is_idempotent(tmp_path, tightened_corr_check) -> None:  # noqa: ANN001
    raw = _raw_output(r_abs=0.87)
    metrics = _gate_row(passes=1.0, bound_lower=0.5)
    db_path = _write_db(tmp_path, ITCZ_SCHEMA, {"raw_output": raw, "metrics": metrics})

    first = regate.regate_database(db_path)
    after_first = _read_metrics(db_path, ITCZ_SCHEMA)

    second = regate.regate_database(db_path)
    after_second = _read_metrics(db_path, ITCZ_SCHEMA)

    assert first.rows_changed == 1
    assert second.rows_changed == 0  # nothing left to flip
    assert second.rows_evaluated == 1  # still re-evaluated, just unchanged
    pd.testing.assert_frame_equal(
        after_first.sort_index(axis=1),
        after_second.sort_index(axis=1),
    )


# ---------------------------------------------------------------------------
# 3. A missing raw column leaves the row untouched
# ---------------------------------------------------------------------------


def test_regate_leaves_a_row_untouched_when_its_raw_column_is_missing(
    tmp_path,  # noqa: ANN001
    tightened_corr_check,  # noqa: ANN001
) -> None:
    raw = pd.DataFrame(
        {
            "data_id": [DATA_ID],
            "data_type": ["to_benchmark"],
            # No 'itcz_efe_r_abs' column at all -- as if the diagnostic never
            # wrote it (a schema/diagnostic mismatch, or a stale database).
            "itcz_efe_slope_abs": [3.0],
        },
    )
    metrics = _gate_row(passes=1.0, bound_lower=0.5)
    db_path = _write_db(tmp_path, ITCZ_SCHEMA, {"raw_output": raw, "metrics": metrics})

    report = regate.regate_database(db_path)

    assert report.rows_evaluated == 0
    assert report.rows_changed == 0
    assert any("itcz_efe_r_abs" in message for message in report.messages)
    assert any("left untouched" in message for message in report.messages)
    result = _read_metrics(db_path, ITCZ_SCHEMA).iloc[0]
    assert result["passes"] == 1.0  # unchanged
    assert result["bound_lower"] == pytest.approx(0.5)  # unchanged


# ---------------------------------------------------------------------------
# 4. Tier II/III scorer rows are never touched
# ---------------------------------------------------------------------------


def test_regate_never_touches_a_tier2_scorer_row(
    tmp_path,  # noqa: ANN001
    tightened_corr_check,  # noqa: ANN001
) -> None:
    raw = _raw_output(r_abs=0.87)
    gate_row = _gate_row(passes=1.0, bound_lower=0.5)
    # A Tier II/III scorer row that happens to reuse the same var_id and
    # carry gate-shaped columns (the III.2 large-ensemble spread row is
    # written exactly like this by climatebench2.scoring_pass) -- it must
    # never be mistaken for a pass_fail gate row because it carries `scorer`.
    scorer_row = pd.DataFrame(
        [
            {
                "data_id": DATA_ID,
                "data_type": "to_benchmark",
                "var_id": "itcz_efe_correlation",
                "value": 0.87,
                "bound_lower": 0.5,
                "bound_upper": np.nan,
                "passes": 1.0,
                "requirement": "required",
                "tier": "III",
                "applicable": 1.0,
                "scorer": "climatebench2",
            },
        ],
    )
    metrics = pd.concat([gate_row.assign(scorer=None), scorer_row], ignore_index=True)
    db_path = _write_db(tmp_path, ITCZ_SCHEMA, {"raw_output": raw, "metrics": metrics})

    report = regate.regate_database(db_path)

    result = _read_metrics(db_path, ITCZ_SCHEMA)
    scored = result[result["scorer"] == "climatebench2"].iloc[0]
    gated = result[result["scorer"].isna()].iloc[0]

    assert report.rows_evaluated == 1  # only the true gate row
    assert gated["passes"] == 0.0  # the real gate row still flips
    assert gated["bound_lower"] == pytest.approx(0.90)
    # The scorer row is untouched: still the OLD bound and OLD verdict.
    assert scored["passes"] == 1.0
    assert scored["bound_lower"] == pytest.approx(0.5)
    assert scored["tier"] == "III"


# ---------------------------------------------------------------------------
# Not-applicable rows have no raw_output row to match, so they are untouched
# ---------------------------------------------------------------------------


def test_regate_leaves_a_declared_not_applicable_row_untouched(
    tmp_path,  # noqa: ANN001
    tightened_corr_check,  # noqa: ANN001
) -> None:
    # not_applicable_metrics writes value/passes = NaN, applicable = 0.0, and
    # `data_id` is the DIAGNOSTIC's own name -- never a row in raw_output.
    metrics = pd.DataFrame(
        [
            {
                "data_id": ITCZ_SCHEMA,
                "data_type": "to_benchmark",
                "var_id": "itcz_efe_correlation",
                "value": np.nan,
                "bound_lower": 0.5,
                "bound_upper": np.nan,
                "passes": np.nan,
                "requirement": "required",
                "tier": "I",
                "applicable": 0.0,
            },
        ],
    )
    raw = _raw_output(r_abs=0.87).assign(data_id=DATA_ID)
    db_path = _write_db(tmp_path, ITCZ_SCHEMA, {"raw_output": raw, "metrics": metrics})

    report = regate.regate_database(db_path)

    assert report.rows_changed == 0
    result = _read_metrics(db_path, ITCZ_SCHEMA).iloc[0]
    assert pd.isna(result["passes"])
    assert result["applicable"] == 0.0
    assert result["bound_lower"] == pytest.approx(0.5)  # untouched, old bound kept
