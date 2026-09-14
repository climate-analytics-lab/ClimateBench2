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


# ---------------------------------------------------------------------------
# The reference's baseline-window record (ReferenceBaselineRecord's rows)
# ---------------------------------------------------------------------------


def _baseline_rows(years: list[int], rng: np.random.Generator) -> pd.DataFrame:
    """What ``ReferenceBaselineRecord`` writes for an annual series."""
    return pd.DataFrame(
        {
            "data_id": "observation_OBS",
            "data_type": scoring_pass.BASELINE_ANNUAL_DATA_TYPE,
            "time": _times(years),
            "tas": _truth(years, rng),
        },
    )


def test_climatology_uses_the_recorded_baseline_window() -> None:
    """The Tier II cut removes 1985-2014; the baseline record puts it back."""
    rng = np.random.default_rng(20)
    raw, sources = _tables(rng)
    cut = raw[pd.to_datetime(raw["time"]).dt.year >= min(TEST_YEARS)]
    baseline = scoring_pass.baseline_records(
        _baseline_rows(list(BASELINE_YEARS), rng),
    )
    assert set(baseline) == {("tas", "annual")}

    rows = pd.DataFrame(
        score_raw_output(cut, sources, settings=FAST, baseline=baseline),
    )
    clim = rows[rows["data_id"] == CLIMATOLOGY_DATA_ID].iloc[0]
    assert clim["reason"] == ""
    assert np.isfinite(clim["crps"])
    assert clim["n_members"] == len(BASELINE_YEARS)
    assert clim["n_time"] == len(TEST_YEARS)
    # The no-skill floor is worse than the submission, which tracks the truth
    submission = rows[
        (rows["data_id"] == "MyModel") & (rows["data_type"] == "to_benchmark")
    ].iloc[0]
    assert clim["crps"] > submission["crps"]


def test_baseline_rows_are_never_scored_as_a_forecast() -> None:
    """A pre-2015 sample is not a model: it must not appear as a scored row."""
    rng = np.random.default_rng(21)
    raw, sources = _tables(rng)
    combined = pd.concat(
        [raw, _baseline_rows(list(BASELINE_YEARS), rng)],
        ignore_index=True,
    )
    groups = group_members(combined, source_names(sources))
    assert not [
        key for key in groups if "baseline" in key[0]
    ]
    rows = pd.DataFrame(score_raw_output(combined, sources, settings=FAST))
    assert "observation_OBS" not in set(rows["data_id"])


# ---------------------------------------------------------------------------
# Observational uncertainty
# ---------------------------------------------------------------------------


def test_obs_sigma_floor_resolves_by_variable_then_prefix() -> None:
    assert scoring_pass.obs_sigma_floor("tas") == pytest.approx(0.05)
    # `tos_nino34` inherits the `tos` entry through its leading token
    assert scoring_pass.obs_sigma_floor("tos_nino34") == scoring_pass.obs_sigma_floor(
        "tos",
    )
    # An unknown sigma is 0 (the draws become a no-op), never invented
    assert scoring_pass.obs_sigma_floor("pr") == 0.0
    assert scoring_pass.obs_sigma_floor("no_such_variable") == 0.0


def test_observational_spread_adds_to_the_sigma_floor() -> None:
    times = _times(list(TEST_YEARS))
    reference = pd.DataFrame({"time": times, "tas": np.zeros(len(times))})
    product = pd.DataFrame({"time": times, "tas": np.full(len(times), 0.2)})
    sigma = scoring_pass.observational_sigma(reference, [product], "tas", 0.05)
    # std of {0, 0.2} with ddof=1 is 0.1414; in quadrature with the 0.05 floor
    expected = np.sqrt(0.05**2 + (0.2 / np.sqrt(2)) ** 2)
    assert sigma.iloc[0] == pytest.approx(expected)

    # With a single product only the floor is left
    flat = scoring_pass.observational_sigma(reference, [], "tas", 0.05)
    assert flat.unique().tolist() == [0.05]
    assert scoring_pass.observational_sigma(reference, [], "tas", 0.0) is None


def test_observational_products_are_not_scored_as_comparison_models() -> None:
    """HadISST next to an SST reference is a second truth, not a forecast."""
    rng = np.random.default_rng(22)
    raw, sources = _tables(rng)
    # Re-label CMIP6_B as an observational product of the same variable
    sources = sources.copy()
    is_b = sources["name"] == "CMIP6_B"
    sources.loc[is_b, "category"] = "observation"

    rows = pd.DataFrame(score_raw_output(raw, sources, settings=FAST))
    product = rows[rows["data_id"] == "CMIP6_B"].iloc[0]
    assert np.isnan(product["crps"])
    assert "observational product" in product["reason"]

    # ... and it is out of E_ref, which now rests on CMIP6_A alone
    submission = rows[
        (rows["data_id"] == "MyModel") & (rows["data_type"] == "to_benchmark")
    ].iloc[0]
    assert submission["n_ref_models"] == 1
    cmip6_a = rows[
        (rows["data_id"] == "CMIP6_A") & (rows["data_type"] == "other")
    ].iloc[0]
    assert submission["e_ref"] == pytest.approx(cmip6_a["crps"])


def test_sigma_obs_is_recorded_on_every_scored_row() -> None:
    rng = np.random.default_rng(23)
    raw, sources = _tables(rng)
    rows = pd.DataFrame(score_raw_output(raw, sources, settings=FAST))
    scored = rows[rows["crps"].notna() & (rows["var_id"] == "tas")]
    assert (scored["sigma_obs"] > 0).all()  # tas has a protocol floor


# ---------------------------------------------------------------------------
# Regime (c): trend consistency in the pass
# ---------------------------------------------------------------------------


def _sigma_internal_rows(sigma_trend: float, sigma_mean: float = 0.1) -> pd.DataFrame:
    """What ``InternalVariability`` writes into the Tier I database."""
    return pd.DataFrame(
        {
            "data_id": ["model_MyModel_historical_r1i1p1f1"],
            "data_type": ["to_benchmark"],
            "window_years_test": [float(len(TEST_YEARS))],
            "window_years_long": [76.0],
            "tas_sigma_int_mean_test": [sigma_mean],
            "tas_sigma_int_trend_test": [sigma_trend],
            "tas_sigma_int_trend_long": [sigma_trend / 4.0],
        },
    )


def test_internal_variability_rows_are_read_back_by_window() -> None:
    table = scoring_pass.internal_variability_from_raw(_sigma_internal_rows(0.004))
    assert set(table) == {("tas", "mean"), ("tas", "trend")}
    assert dict(table["tas", "trend"]) == {len(TEST_YEARS): 0.004, 76: 0.001}
    # The nearest window length wins
    assert scoring_pass.sigma_internal_for(
        table,
        "tas",
        "trend",
        len(TEST_YEARS),
    ) == pytest.approx(0.004)
    assert scoring_pass.sigma_internal_for(table, "tas", "trend", 70) == pytest.approx(
        0.001,
    )
    # No table, no variable, or no statistic -> 0, never a crash
    assert scoring_pass.sigma_internal_for(None, "tas", "trend", 30) == 0.0
    assert scoring_pass.sigma_internal_for(table, "clt", "trend", 30) == 0.0


def test_trend_consistency_rows_carry_sigma_internal_and_sigma_obs() -> None:
    rng = np.random.default_rng(24)
    raw, sources = _tables(rng)
    sigma_internal = scoring_pass.internal_variability_from_raw(
        _sigma_internal_rows(0.004),
    )
    rows = pd.DataFrame(
        score_raw_output(raw, sources, settings=FAST, sigma_internal=sigma_internal),
    )
    trend = rows[rows["var_id"] == "tas_trend_consistency"]
    assert not trend.empty
    submission = trend[trend["data_type"] == "to_benchmark"].iloc[0]
    assert submission["data_id"] == "MyModel"
    assert submission["sigma_internal"] == pytest.approx(0.004)
    assert submission["sigma_obs"] > 0  # from tier2.obs_sigma tas = 0.05 K
    assert submission["total_sigma"] > submission["sigma_internal"]
    assert submission["value"] == pytest.approx(0.02, abs=0.01)  # the 0.02 K/yr truth
    assert submission["passes"] == 1.0
    assert 0.0 <= submission["p_value"] <= 1.0
    # A consistency row is not a CRPS row
    assert np.isnan(submission["crps"])


def test_trend_consistency_fails_for_an_inconsistent_observed_trend() -> None:
    rng = np.random.default_rng(25)
    raw, sources = _tables(rng)
    raw = raw.copy()
    is_ref = raw["data_type"] == "reference"
    raw.loc[is_ref, "tas"] = np.linspace(0.0, 50.0, int(is_ref.sum()))
    rows = pd.DataFrame(score_raw_output(raw, sources, settings=FAST))
    submission = rows[
        (rows["var_id"] == "tas_trend_consistency")
        & (rows["data_type"] == "to_benchmark")
    ].iloc[0]
    assert submission["passes"] == 0.0


def test_widening_sigma_internal_makes_the_test_more_permissive() -> None:
    rng = np.random.default_rng(26)
    raw, sources = _tables(rng)
    raw = raw.copy()
    is_ref = raw["data_type"] == "reference"
    raw.loc[is_ref, "tas"] = raw.loc[is_ref, "tas"] + np.linspace(
        0.0,
        1.0,
        int(is_ref.sum()),
    )

    def z_for(sigma_trend: float) -> float:
        table = scoring_pass.internal_variability_from_raw(
            _sigma_internal_rows(sigma_trend),
        )
        rows = pd.DataFrame(
            score_raw_output(raw, sources, settings=FAST, sigma_internal=table),
        )
        return float(
            rows[
                (rows["var_id"] == "tas_trend_consistency")
                & (rows["data_type"] == "to_benchmark")
            ].iloc[0]["z"],
        )

    assert abs(z_for(1.0)) < abs(z_for(0.0001))


def test_no_trend_consistency_for_a_monthly_series() -> None:
    """sigma_int is chunked annually; a monthly trend has no counterpart."""
    rng = np.random.default_rng(27)
    times = pd.date_range("2015-01-01", periods=72, freq="MS")
    frames = [
        pd.DataFrame(
            {
                "data_id": "obs_O",
                "data_type": "reference",
                "time": times,
                "tas": rng.normal(0, 1, times.size),
            },
        ),
    ]
    for variant in ("r1i1p1f1", "r2i1p1f1"):
        frames.append(
            pd.DataFrame(
                {
                    "data_id": f"model_M_{variant}",
                    "data_type": "to_benchmark",
                    "time": times,
                    "tas": rng.normal(0, 1, times.size),
                },
            ),
        )
    sources = pd.DataFrame(
        [
            {"id": "obs_O", "name": "O", "category": "observation"},
            {"id": "model_M_r1i1p1f1", "name": "M", "category": "model"},
            {"id": "model_M_r2i1p1f1", "name": "M", "category": "model"},
        ],
    )
    rows = pd.DataFrame(score_raw_output(pd.concat(frames), sources, settings=FAST))
    assert not any(str(v).endswith("_trend_consistency") for v in rows["var_id"])


# ---------------------------------------------------------------------------
# Regime (b): EOF coefficient tables
# ---------------------------------------------------------------------------

N_MODES = 6


def _eof_tables(rng: np.random.Generator) -> tuple[pd.DataFrame, pd.DataFrame]:
    """A coefficient table shaped like ``ReferenceEOFProjection``'s output."""
    truth = rng.normal(0.0, 1.0, N_MODES)
    rows, sources = [], []
    for name, category, variants, data_type, spread in SOURCES:
        exp = "" if data_type == "reference" else "historical"
        for variant in variants:
            data_id = _source_id(category, name, exp, variant)
            values = (
                truth
                if data_type == "reference"
                else truth + rng.normal(0.0, spread, N_MODES)
            )
            rows.append(
                pd.DataFrame(
                    {
                        "data_id": data_id,
                        "data_type": data_type,
                        "var_id": "tas",
                        "mode": np.arange(1, N_MODES + 1, dtype=float),
                        "coefficient": values,
                        "explained_variance": np.full(N_MODES, 1.0 / N_MODES),
                        "sigma_pre2015": np.ones(N_MODES),
                    },
                ),
            )
            sources.append(
                {"id": data_id, "name": name, "category": category, "variant": variant},
            )
    return pd.concat(rows, ignore_index=True), pd.DataFrame(sources)


def test_is_eof_output_recognises_the_coefficient_table() -> None:
    raw, _ = _eof_tables(np.random.default_rng(30))
    assert scoring_pass.is_eof_output(raw)
    series, _ = _tables(np.random.default_rng(30))
    assert not scoring_pass.is_eof_output(series)


def test_eof_pass_scores_the_mean_over_coefficients() -> None:
    raw, sources = _eof_tables(np.random.default_rng(31))
    rows = pd.DataFrame(scoring_pass.score_eof_output(raw, sources, settings=FAST))
    submission = rows[
        (rows["data_id"] == "MyModel") & (rows["data_type"] == "to_benchmark")
    ].iloc[0]

    assert submission["n_members"] == 3
    assert submission["n_time"] == N_MODES  # the retained modes are the sample
    assert submission["t_eff"] == N_MODES  # ... and the effective sample size
    assert submission["block_length"] == 1.0  # orthogonal: no blocks
    assert np.isnan(submission["r1"])  # no ordering along the mode index
    assert submission["crps"] > 0
    assert submission["crps_ci_lo"] <= submission["crps"] <= submission["crps_ci_hi"]

    # The score really is the equal-weight mean of the per-coefficient CRPS
    from climatebench2 import scoring as engine

    members = np.vstack(
        [
            raw[(raw["data_id"] == i)].sort_values("mode")["coefficient"].to_numpy()
            for i in sorted(
                sources[
                    (sources["name"] == "MyModel") & (sources["category"] == "model")
                ]["id"],
            )
        ],
    )
    obs = (
        raw[raw["data_type"] == "reference"]
        .sort_values("mode")["coefficient"]
        .to_numpy()
    )
    assert submission["crps"] == pytest.approx(engine.crps_fair(members, obs).mean())


def test_eof_pass_reuses_the_leave_one_out_cmip6_median() -> None:
    raw, sources = _eof_tables(np.random.default_rng(32))
    rows = pd.DataFrame(scoring_pass.score_eof_output(raw, sources, settings=FAST))
    per_model = dict(
        zip(
            rows[(rows["data_type"] == "other") & rows["crps"].notna()]["data_id"],
            rows[(rows["data_type"] == "other") & rows["crps"].notna()]["crps"],
            strict=True,
        ),
    )
    submission = rows[
        (rows["data_id"] == "MyModel") & (rows["data_type"] == "to_benchmark")
    ].iloc[0]
    expected = float(np.median([per_model["CMIP6_A"], per_model["CMIP6_B"]]))
    assert submission["e_ref"] == pytest.approx(expected)
    assert submission["skill"] == pytest.approx(1.0 - submission["crps"] / expected)
    # The single-member comparison model is n/a here too
    single = rows[rows["data_id"] == "CMIP6_C"].iloc[0]
    assert np.isnan(single["crps"])
    assert single["reason"] == "single member"


def test_score_database_scores_an_eof_schema(tmp_path) -> None:  # noqa: ANN001
    raw, sources = _eof_tables(np.random.default_rng(33))
    db_path = tmp_path / "ClimateBench2_TierII.ddb"
    con = duckdb.connect(str(db_path))
    con.execute('CREATE SCHEMA "eof_projection"')
    for table, frame in (("raw_output", raw), ("data_sources", sources)):
        con.register("frame", frame)
        con.execute(f'CREATE TABLE "eof_projection"."{table}" AS SELECT * FROM frame')
        con.unregister("frame")
    con.close()

    report = score_database(db_path, settings=FAST)
    assert report.diagnostics == ["eof_projection"]
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        metrics = con.execute('SELECT * FROM "eof_projection"."metrics"').df()
    finally:
        con.close()
    assert set(metrics["scorer"]) == {SCORER}
    assert set(metrics["var_id"]) == {"tas"}
