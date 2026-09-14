"""End-to-end tests of the Tier II scoring pass on a synthetic database.

The database is built table-by-table to match what
``climateeval.suites.Suite.get_database`` writes (one DuckDB *schema* per
diagnostic, holding ``raw_output`` / ``metrics`` / ``variables`` /
``data_sources``) and what ``climateeval.report._db.read_database`` reads
back, so no climate data or ClimateEval run is needed.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

duckdb = pytest.importorskip("duckdb")

from climatebench2 import scoring_pass  # noqa: E402
from climatebench2.scoring_pass import (  # noqa: E402
    CLIMATOLOGY_DATA_ID,
    SCORER,
    group_members,
    score_database,
    score_raw_output,
    source_names,
    stack_members,
)

DIAGNOSTIC = "annual_mean_timeseries"
BASELINE_YEARS = range(1985, 2015)
TEST_YEARS = range(2015, 2045)
ALL_YEARS = list(BASELINE_YEARS) + list(TEST_YEARS)

#: Fast bootstrap settings — the protocol values live in thresholds.yml.
FAST = {
    "block_length_monthly": 12,
    "block_length_annual": 3,
    "n_boot": 60,
    "alpha": 0.05,
    "resample_members": True,
    "seed": 1,
}


def _times(years: list[int]) -> pd.DatetimeIndex:
    return pd.to_datetime([f"{y}-01-01" for y in years])


def _truth(years: list[int], rng: np.random.Generator) -> np.ndarray:
    """A warming signal plus interannual noise."""
    x = np.array(years, dtype=float) - 1985.0
    return 0.02 * x + rng.normal(0.0, 0.1, len(years))


#: (name, category, variant(s), data_type, spread) of every source.
SOURCES = [
    ("OBS", "observation", [""], "reference", 0.0),
    ("MyModel", "model", ["r1i1p1f1", "r2i1p1f1", "r3i1p1f1"], "to_benchmark", 0.10),
    ("CMIP6_A", "CMIP6", ["r1i1p1f1", "r2i1p1f1"], "other", 0.25),
    ("CMIP6_B", "CMIP6", ["r1i1p1f1", "r2i1p1f1"], "other", 0.40),
    ("CMIP6_C", "CMIP6", ["r1i1p1f1"], "other", 0.30),  # single member -> NaN
    ("MyModel", "CMIP6", ["r1i1p1f1", "r2i1p1f1"], "other", 0.01),  # leave-one-out
]


def _source_id(category: str, name: str, exp: str, variant: str) -> str:
    """Mirror ``DataSourceInformation.id``."""
    return "_".join(p for p in (category, name, exp, variant) if p)


def _tables(rng: np.random.Generator) -> tuple[pd.DataFrame, pd.DataFrame]:
    """``(raw_output, data_sources)`` for one annual-mean tas diagnostic."""
    truth_all = _truth(ALL_YEARS, rng)
    raw_rows, sources = [], []
    for name, category, variants, data_type, spread in SOURCES:
        years = ALL_YEARS if data_type == "reference" else list(TEST_YEARS)
        exp = "" if data_type == "reference" else "historical"
        base = truth_all[-len(years) :] if years != ALL_YEARS else truth_all
        for variant in variants:
            data_id = _source_id(category, name, exp, variant)
            values = base + rng.normal(0.0, spread, len(years))
            raw_rows.append(
                pd.DataFrame(
                    {
                        "data_id": data_id,
                        "data_type": data_type,
                        "time": _times(years),
                        "tas": truth_all if data_type == "reference" else values,
                    },
                ),
            )
            sources.append(
                {
                    "id": data_id,
                    "name": name,
                    "category": category,
                    "institute": "",
                    "exp": exp,
                    "variant": variant,
                    "references": "",
                },
            )
    return pd.concat(raw_rows, ignore_index=True), pd.DataFrame(sources)


@pytest.fixture
def synthetic_db(tmp_path):  # noqa: ANN201
    """A .ddb laid out like ``Suite.get_database``'s output."""
    rng = np.random.default_rng(0)
    raw_output, data_sources = _tables(rng)
    metrics = pd.DataFrame(
        {
            "data_id": [_source_id("model", "MyModel", "historical", "r1i1p1f1")],
            "reference_data_id": ["observation_OBS"],
            "var_id": ["tas"],
            "weighted_rmse": [0.12],
            "weighted_pearsonr": [0.98],
            "weighted_emd": [0.05],
        },
    )
    db_path = tmp_path / "ClimateBench2_TierII.ddb"
    con = duckdb.connect(str(db_path))
    con.execute(f'CREATE SCHEMA "{DIAGNOSTIC}"')
    for table, frame in (
        ("raw_output", raw_output),
        ("metrics", metrics),
        ("data_sources", data_sources),
    ):
        con.register("frame", frame)
        con.execute(f'CREATE TABLE "{DIAGNOSTIC}"."{table}" AS SELECT * FROM frame')
        con.unregister("frame")
    con.close()
    return db_path


def _metrics(db_path) -> pd.DataFrame:  # noqa: ANN001
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        return con.execute(f'SELECT * FROM "{DIAGNOSTIC}"."metrics"').df()
    finally:
        con.close()


# ---------------------------------------------------------------------------
# Grouping
# ---------------------------------------------------------------------------


def test_source_names_maps_ids_to_model_names() -> None:
    _raw, sources = _tables(np.random.default_rng(1))
    names = source_names(sources)
    assert names["model_MyModel_historical_r1i1p1f1"] == "MyModel"
    assert names["model_MyModel_historical_r3i1p1f1"] == "MyModel"
    assert names["CMIP6_CMIP6_A_historical_r1i1p1f1"] == "CMIP6_A"


def test_group_members_stacks_variants_of_one_model() -> None:
    raw, sources = _tables(np.random.default_rng(2))
    groups = group_members(raw, source_names(sources))
    assert len(groups[("to_benchmark", "MyModel")]) == 3
    assert len(groups[("other", "CMIP6_A")]) == 2
    assert len(groups[("other", "CMIP6_C")]) == 1
    # the reference is the target, never a forecast
    assert not any(key[0] == "reference" for key in groups)


def test_group_members_without_a_data_sources_table() -> None:
    """An older database still groups (one member per data id)."""
    raw, _sources = _tables(np.random.default_rng(3))
    groups = group_members(raw, {})
    assert all(len(frames) == 1 for frames in groups.values())


def test_stack_members_aligns_on_common_times() -> None:
    raw, sources = _tables(np.random.default_rng(4))
    reference = raw[raw.data_type == "reference"]
    groups = group_members(raw, source_names(sources))
    frames = groups[("to_benchmark", "MyModel")]
    frames = [frames[0].iloc[2:], *frames[1:]]  # first member misses 2 years
    members, obs, times = stack_members(frames, reference, "tas")
    assert members.shape == (3, len(TEST_YEARS) - 2)
    assert obs.shape == (len(TEST_YEARS) - 2,)
    assert times.size == len(TEST_YEARS) - 2


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------


def test_score_raw_output_stacks_members_and_scores_baselines() -> None:
    raw, sources = _tables(np.random.default_rng(5))
    rows = pd.DataFrame(score_raw_output(raw, sources, settings=FAST))
    by_id = rows.set_index("data_id")

    assert set(rows["data_id"]) == {
        "MyModel",
        "CMIP6_A",
        "CMIP6_B",
        "CMIP6_C",
        CLIMATOLOGY_DATA_ID,
    }
    submission = by_id.loc[
        (by_id.index == "MyModel") & (by_id["data_type"] == "to_benchmark")
    ].iloc[0]
    assert submission["n_members"] == 3  # the three variants, one ensemble
    assert submission["n_time"] == len(TEST_YEARS)
    assert submission["crps"] > 0
    assert submission["crps_se"] > 0
    assert submission["crps_ci_lo"] < submission["crps"] < submission["crps_ci_hi"]
    assert submission["reason"] == ""
    assert rows["scorer"].eq(SCORER).all()

    # The tighter ensemble scores better than the looser one
    assert (
        by_id.loc[by_id.index == "CMIP6_A", "crps"].iloc[0]
        < by_id.loc[by_id.index == "CMIP6_B", "crps"].iloc[0]
    )
    # ... and the climatology baseline, which ignores the warming, worst of all
    assert by_id.loc[CLIMATOLOGY_DATA_ID, "crps"] > submission["crps"]
    assert by_id.loc[CLIMATOLOGY_DATA_ID, "n_members"] == len(BASELINE_YEARS)


def test_single_member_model_gets_a_nan_row_with_a_reason() -> None:
    raw, sources = _tables(np.random.default_rng(6))
    rows = pd.DataFrame(score_raw_output(raw, sources, settings=FAST))
    single = rows[rows["data_id"] == "CMIP6_C"].iloc[0]
    assert np.isnan(single["crps"])
    assert single["reason"] == "single member"
    assert single["n_members"] == 1
    assert np.isnan(single["skill"])


def test_e_ref_is_the_leave_one_out_median_of_per_model_crps() -> None:
    raw, sources = _tables(np.random.default_rng(7))
    rows = pd.DataFrame(score_raw_output(raw, sources, settings=FAST))

    comparison = rows[(rows["data_type"] == "other") & rows["crps"].notna()]
    per_model = dict(zip(comparison["data_id"], comparison["crps"], strict=True))
    assert set(per_model) == {"CMIP6_A", "CMIP6_B", "MyModel"}

    submission = rows[
        (rows["data_id"] == "MyModel") & (rows["data_type"] == "to_benchmark")
    ].iloc[0]
    # Leave-one-out: the comparison model called MyModel is excluded
    expected = float(np.median([per_model["CMIP6_A"], per_model["CMIP6_B"]]))
    assert submission["e_ref"] == pytest.approx(expected)
    assert submission["n_ref_models"] == 2
    assert submission["skill"] == pytest.approx(1.0 - submission["crps"] / expected)
    # A comparison model is also left out of its own reference
    cmip6_a = rows[
        (rows["data_id"] == "CMIP6_A") & (rows["data_type"] == "other")
    ].iloc[0]
    assert cmip6_a["n_ref_models"] == 2
    assert cmip6_a["e_ref"] == pytest.approx(
        float(np.median([per_model["CMIP6_B"], per_model["MyModel"]])),
    )
    # The submission tracks the truth more closely than the median CMIP6 model
    assert submission["skill"] > 0


def test_no_pooled_cmip6_mme_row() -> None:
    """The pooled mixture is ruled out (overdispersed) — median-of-models only."""
    raw, sources = _tables(np.random.default_rng(8))
    rows = pd.DataFrame(score_raw_output(raw, sources, settings=FAST))
    assert "CMIP6-MME" not in set(rows["data_id"])


def test_climatology_row_says_why_when_the_baseline_window_is_missing() -> None:
    """A real Tier II database is cut to the test window (no 1985-2014 obs)."""
    raw, sources = _tables(np.random.default_rng(9))
    years = pd.to_datetime(raw["time"]).dt.year
    cut = raw[years >= min(TEST_YEARS)]
    rows = pd.DataFrame(score_raw_output(cut, sources, settings=FAST))
    clim = rows[rows["data_id"] == CLIMATOLOGY_DATA_ID].iloc[0]
    assert np.isnan(clim["crps"])
    assert "1985-2014" in clim["reason"]


def test_monthly_climatology_uses_calendar_month_pseudo_members() -> None:
    rng = np.random.default_rng(10)
    times = pd.date_range("2010-01-01", "2019-12-01", freq="MS")
    season = 5.0 * np.sin(2 * np.pi * (times.month - 1) / 12)
    obs = season + rng.normal(0, 0.5, times.size)
    frames = [
        pd.DataFrame(
            {"data_id": "obs_O", "data_type": "reference", "time": times, "tas": obs},
        ),
    ]
    for variant in ("r1i1p1f1", "r2i1p1f1"):
        frames.append(
            pd.DataFrame(
                {
                    "data_id": f"model_M_{variant}",
                    "data_type": "to_benchmark",
                    "time": times,
                    "tas": season + rng.normal(0, 0.5, times.size),
                },
            ),
        )
    sources = pd.DataFrame(
        [
            {"id": "obs_O", "name": "O"},
            {"id": "model_M_r1i1p1f1", "name": "M"},
            {"id": "model_M_r2i1p1f1", "name": "M"},
        ],
    )
    # 2010-2014 is inside the protocol baseline window, 2015+ is the test window
    rows = pd.DataFrame(score_raw_output(pd.concat(frames), sources, settings=FAST))
    clim = rows[rows["data_id"] == CLIMATOLOGY_DATA_ID].iloc[0]
    assert clim["n_members"] == 5  # 2010..2014, one pseudo-member per year
    assert clim["n_time"] == 60  # 2015..2019 monthly
    assert clim["block_length"] == FAST["block_length_monthly"]
    # A seasonal-cycle climatology is a decent forecast: CRPS well under the
    # 5 K amplitude it captures
    assert 0.0 < clim["crps"] < 1.5


# ---------------------------------------------------------------------------
# Database round trip
# ---------------------------------------------------------------------------


def test_score_database_appends_to_the_metrics_table(synthetic_db) -> None:  # noqa: ANN001
    report = score_database(synthetic_db, settings=FAST)
    assert report.diagnostics == [DIAGNOSTIC]
    assert report.single_member == 1

    metrics = _metrics(synthetic_db)
    # ClimateEval's deterministic row survives, untouched
    deterministic = metrics[metrics["scorer"].isna()]
    assert len(deterministic) == 1
    assert deterministic.iloc[0]["weighted_rmse"] == pytest.approx(0.12)
    # ... alongside the new score rows, in the same table
    scored = metrics[metrics["scorer"] == SCORER]
    assert len(scored) == report.rows
    assert set(scored["data_id"]) == {
        "MyModel",
        "CMIP6_A",
        "CMIP6_B",
        "CMIP6_C",
        CLIMATOLOGY_DATA_ID,
    }
    for column in ("crps_ci_lo", "crps_ci_hi", "e_ref", "n_ref_models", "skill"):
        assert column in metrics.columns


def test_score_database_is_idempotent(synthetic_db) -> None:  # noqa: ANN001
    first = score_database(synthetic_db, settings=FAST)
    before = _metrics(synthetic_db)
    second = score_database(synthetic_db, settings=FAST)
    after = _metrics(synthetic_db)
    assert first.rows == second.rows
    assert len(before) == len(after)  # replaced, not duplicated
    np.testing.assert_allclose(
        before[before["scorer"] == SCORER].sort_values("data_id")["crps"].to_numpy(),
        after[after["scorer"] == SCORER].sort_values("data_id")["crps"].to_numpy(),
        equal_nan=True,
    )


def test_score_database_reads_back_through_climateeval(synthetic_db) -> None:  # noqa: ANN001
    """The rows must be visible to the leaderboard's reader."""
    pytest.importorskip("climateeval")
    from climateeval.report._db import read_database

    score_database(synthetic_db, settings=FAST)
    tables = read_database(synthetic_db)
    metrics = tables[DIAGNOSTIC]["metrics"]
    assert (metrics["scorer"] == SCORER).sum() > 0


def test_score_database_without_a_metrics_table(tmp_path) -> None:  # noqa: ANN001
    raw, sources = _tables(np.random.default_rng(11))
    db_path = tmp_path / "no_metrics.ddb"
    con = duckdb.connect(str(db_path))
    con.execute('CREATE SCHEMA "ts"')
    for table, frame in (("raw_output", raw), ("data_sources", sources)):
        con.register("frame", frame)
        con.execute(f'CREATE TABLE "ts"."{table}" AS SELECT * FROM frame')
        con.unregister("frame")
    con.close()

    report = score_database(db_path, settings=FAST)
    assert report.rows > 0
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        created = con.execute('SELECT * FROM "ts"."metrics"').df()
    finally:
        con.close()
    assert set(created["scorer"]) == {SCORER}


def test_score_database_ignores_non_timeseries_diagnostics(tmp_path) -> None:  # noqa: ANN001
    db_path = tmp_path / "spatial.ddb"
    con = duckdb.connect(str(db_path))
    con.execute('CREATE SCHEMA "map_diag"')
    frame = pd.DataFrame(
        {
            "data_id": ["m"],
            "data_type": ["to_benchmark"],
            "latitude": [0.0],
            "longitude": [0.0],
            "tas": [1.0],
        },
    )
    con.register("frame", frame)
    con.execute('CREATE TABLE "map_diag"."raw_output" AS SELECT * FROM frame')
    con.close()
    report = score_database(db_path, settings=FAST)
    assert report.rows == 0
    assert "no scorable" in report.summary()


def test_pattern_scaling_hook_is_declared_but_unwired() -> None:
    """The third baseline is a later work package; only its id exists."""
    raw, sources = _tables(np.random.default_rng(12))
    rows = pd.DataFrame(score_raw_output(raw, sources, settings=FAST))
    assert scoring_pass.PATTERN_SCALING_DATA_ID not in set(rows["data_id"])
