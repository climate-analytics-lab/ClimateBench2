"""Tier III.2: the perfect-model reference and the large-ensemble spread test.

No CESM2 / MPI-ESM / GISS-E2 / CESM-LE data is staged (the paper promises it
on publication), so everything here is synthetic: a two-file CMOR directory
for the truth DataSource, and hand-built databases for the scoring pass.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

climateeval = pytest.importorskip("climateeval")

import ibis  # noqa: E402

from climatebench2.scoring_pass import (  # noqa: E402
    LE_SPREAD_DATA_ID,
    TRUTH_CATEGORY,
    WINDOW_PERFECT_MODEL,
    is_perfect_model,
    le_spread_rows,
    score_database,
)


# ---------------------------------------------------------------------------
# The truth DataSource
# ---------------------------------------------------------------------------


def test_configure_truth_returns_suite_class_paths(tmp_path) -> None:  # noqa: ANN001
    from climatebench2.diags.truth_reference import (
        LocalCMORReference,
        configure_truth,
        truth_is_configured,
    )
    from climateeval._utils import str_to_object

    reference, members = configure_truth(
        tmp_path / "ssp245",
        {"r2i1p1f1": tmp_path / "r2", "r3i1p1f1": tmp_path / "r3"},
        name="CESM2",
    )
    assert truth_is_configured()
    assert reference == "climatebench2.diags.truth_reference.LocalCMORReference"
    assert len(members) == 2

    # every path a suite YAML would name must actually resolve
    assert str_to_object(reference) is LocalCMORReference
    classes = [str_to_object(path) for path in members]
    assert all(issubclass(c, LocalCMORReference) for c in classes)

    # the reference and each member are distinct data sources, all tagged
    # `truth` so the pass never treats one as a comparison model
    sources = [LocalCMORReference(), *(c() for c in classes)]
    assert {s.information.category for s in sources} == {TRUTH_CATEGORY}
    assert {s.information.name for s in sources} == {"CESM2"}
    assert len({s.id for s in sources}) == 3


def test_an_unconfigured_truth_source_says_so(tmp_path) -> None:  # noqa: ANN001
    from climateeval import Variable

    from climatebench2.diags.truth_reference import (
        LocalCMORReference,
        TruthNotConfiguredError,
        configure_truth,
    )

    configure_truth(tmp_path / "ssp245")
    source = LocalCMORReference()
    assert source.path == tmp_path / "ssp245"
    with pytest.raises(TruthNotConfiguredError, match="nothing to download"):
        source.download(Variable("tas", "tas", "mon"), tmp_path)


# ---------------------------------------------------------------------------
# Substituting the reference in a suite YAML
# ---------------------------------------------------------------------------


def test_substitute_reference_swaps_every_variable() -> None:
    from climatebench2._cli import substitute_reference

    definition = [
        {
            "name": "annual_mean_timeseries",
            "diagnostic": "climatebench2.diags.ScoredAnnualMeanTimeSeries",
            "variables": [
                {
                    "id": "tas",
                    "reference_data": "climateeval.data.HadCRUT5",
                    "other_data": ["climateeval.data.CMIP6HistoricalR1I1P1F1"],
                },
                {"id": "pr", "reference_data": "climateeval.data.GPCP"},
            ],
        },
    ]
    swapped = substitute_reference(definition, "pkg.Truth", ["pkg.TruthMember_r2"])
    variables = swapped[0]["variables"]
    assert [v["reference_data"] for v in variables] == ["pkg.Truth"] * 2
    # the CMIP6 comparison ensemble is replaced by the truth members: an
    # E_ref against the real world is meaningless in a perfect-model run
    assert [v["other_data"] for v in variables] == [["pkg.TruthMember_r2"]] * 2
    # nothing else is touched
    assert swapped[0]["diagnostic"].endswith("ScoredAnnualMeanTimeSeries")

    # with no truth members, `other_data` disappears rather than lingering
    bare = substitute_reference(definition, "pkg.Truth", [])
    assert "other_data" not in bare[0]["variables"][0]


def test_materialise_truth_suite_keeps_the_suite_stem(tmp_path) -> None:  # noqa: ANN001
    import yaml

    from climatebench2._cli import _resolve_suite, materialise_truth_suite

    resolved = _resolve_suite("ClimateBench2_TierII")
    target = materialise_truth_suite(resolved, tmp_path, "pkg.Truth", [])
    # the stem is the suite name AND the database filename, so it must not
    # change just because the reference did
    assert target.endswith("ClimateBench2_TierII.yml")
    definition = yaml.safe_load(open(target, encoding="utf-8"))  # noqa: SIM115, PTH123
    referenced = {
        variable["reference_data"]
        for entry in definition
        for variable in entry.get("variables", [])
        if "reference_data" in variable
    }
    assert referenced == {"pkg.Truth"}
    assert not any(
        "other_data" in variable
        for entry in definition
        for variable in entry.get("variables", [])
    )


# ---------------------------------------------------------------------------
# The scoring pass: window label and the spread test
# ---------------------------------------------------------------------------


def _series(
    data_id: str,
    data_type: str,
    values: np.ndarray,
    start: str = "2015-01-01",
) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "data_id": data_id,
            "data_type": data_type,
            "time": pd.date_range(start, periods=values.size, freq="YS"),
            "tas": values,
        },
    )


def _perfect_model_db(tmp_path, *, pred_spread: float, n_truth: int = 4):  # noqa: ANN001, ANN201
    """A database with a truth reference, truth members and a submission."""
    rng = np.random.default_rng(0)
    # 1985-2034: the baseline window the anomalies are taken about, plus the
    # 20 scored test-window years. A perfect-model run loads the same
    # extended window as an observational one.
    start = "1985-01-01"
    n_time = 50
    signal = np.linspace(0.0, 1.0, n_time)
    truth_members = [
        signal + rng.normal(0, 1.0, n_time) for _ in range(n_truth)
    ]
    frames = [
        _series("truth_ref", "reference", signal + rng.normal(0, 1.0, n_time), start),
    ]
    frames += [
        _series(f"truth_CESM2_held-out_r{i}", "other", values, start)
        for i, values in enumerate(truth_members)
    ]
    frames += [
        _series(
            f"model_Emulator_ssp245_r{i}",
            "to_benchmark",
            signal + rng.normal(0, pred_spread, n_time),
            start,
        )
        for i in range(4)
    ]
    raw = pd.concat(frames, ignore_index=True)
    sources = pd.DataFrame(
        {
            "id": sorted(set(raw["data_id"])),
            "name": [
                "Emulator" if i.startswith("model_") else "CESM2"
                for i in sorted(set(raw["data_id"]))
            ],
            "category": [
                "model" if i.startswith("model_") else TRUTH_CATEGORY
                for i in sorted(set(raw["data_id"]))
            ],
        },
    )
    db_path = tmp_path / "ClimateBench2_TierII.ddb"
    conn = ibis.connect(f"duckdb://{db_path}")
    conn.create_database("annual_mean_timeseries")
    conn.create_table("raw_output", ibis.memtable(raw), database="annual_mean_timeseries")
    conn.create_table(
        "data_sources",
        ibis.memtable(sources),
        database="annual_mean_timeseries",
    )
    conn.disconnect()
    return db_path


def _metrics(db_path):  # noqa: ANN001, ANN201
    conn = ibis.connect(f"duckdb://{db_path}")
    try:
        return conn.table("metrics", database="annual_mean_timeseries").to_pandas()
    finally:
        conn.disconnect()


def test_is_perfect_model_reads_the_reference_category() -> None:
    raw = pd.concat(
        [_series("ref", "reference", np.zeros(5)), _series("m", "to_benchmark", np.zeros(5))],
        ignore_index=True,
    )
    assert is_perfect_model(raw, {"ref": TRUTH_CATEGORY})
    assert not is_perfect_model(raw, {"ref": "observation"})
    assert not is_perfect_model(raw, {})


def test_rows_scored_against_a_truth_run_are_labelled_perfect_model(tmp_path) -> None:  # noqa: ANN001
    db_path = _perfect_model_db(tmp_path, pred_spread=1.0)
    score_database(db_path)
    metrics = _metrics(db_path)

    assert set(metrics["window"].dropna()) == {WINDOW_PERFECT_MODEL}
    # the submission is scored ...
    submission = metrics[metrics["data_id"] == "Emulator"]
    assert submission["crps"].notna().any()
    # ... and sigma_obs is zero: the truth is known exactly
    assert submission["sigma_obs"].dropna().eq(0.0).all()
    # ... while the truth members are the target, not competitors
    truth_rows = metrics[(metrics["data_id"] == "CESM2") & (metrics["data_type"] == "other")]
    assert not truth_rows.empty
    assert truth_rows["crps"].isna().all()
    assert truth_rows["reason"].str.contains("truth member").all()
    # so no E_ref is formed against the real world
    assert metrics["e_ref"].isna().all()


def test_le_spread_rows_gate_the_variance_ratio(tmp_path) -> None:  # noqa: ANN001
    from climatebench2._thresholds import get_threshold

    lower, upper = get_threshold("tier3.le_spread.variance_ratio_range")

    good = _metrics_after(tmp_path / "good", pred_spread=1.0)
    ratio = good.set_index("var_id").loc["tas_le_variance_ratio"]
    assert lower <= ratio["value"] <= upper
    assert ratio["passes"] == 1.0
    assert (ratio["bound_lower"], ratio["bound_upper"]) == (lower, upper)
    # an Extended TIER III check: reported, never part of the entry ticket
    assert (ratio["tier"], ratio["requirement"]) == ("III", "extended")
    assert ratio["data_id"] == LE_SPREAD_DATA_ID
    assert "tas_le_spread_pattern_corr" in set(good["var_id"])

    # a collapsed emulator: a tenth of the truth's spread
    collapsed = _metrics_after(tmp_path / "collapsed", pred_spread=0.1)
    ratio = collapsed.set_index("var_id").loc["tas_le_variance_ratio"]
    assert ratio["value"] < lower
    assert ratio["passes"] == 0.0


def _metrics_after(directory, *, pred_spread: float):  # noqa: ANN001, ANN201
    directory.mkdir(parents=True, exist_ok=True)
    db_path = _perfect_model_db(directory, pred_spread=pred_spread)
    score_database(db_path)
    return _metrics(db_path)


def test_no_truth_members_means_no_spread_test() -> None:
    """The test is Extended and needs both ensembles; absent one, no row."""
    rng = np.random.default_rng(1)
    frames = [
        _series(f"model_M_ssp245_r{i}", "to_benchmark", rng.normal(0, 1, 10))
        for i in range(3)
    ]
    groups = {("to_benchmark", "M"): frames}
    assert le_spread_rows(groups, {("to_benchmark", "M"): False}, ["tas"]) == []


def test_a_single_truth_member_is_a_reason_not_a_ratio() -> None:
    rng = np.random.default_rng(2)
    pred = [
        _series(f"model_M_ssp245_r{i}", "to_benchmark", rng.normal(0, 1, 10))
        for i in range(3)
    ]
    truth = [_series("truth_r1", "other", rng.normal(0, 1, 10))]
    groups = {("to_benchmark", "M"): pred, ("other", "CESM2"): truth}
    flags = {("to_benchmark", "M"): False, ("other", "CESM2"): True}
    (row,) = le_spread_rows(groups, flags, ["tas"])
    assert row["var_id"] == "tas_le_variance_ratio"
    assert "members on each side" in row["reason"]
    assert np.isnan(row["value"])


def test_only_the_registered_variables_get_a_spread_test() -> None:
    """`tier3.le_spread.variables` is the protocol list, not every column."""
    rng = np.random.default_rng(3)
    pred = [
        _series(f"model_M_ssp245_r{i}", "to_benchmark", rng.normal(0, 1, 10))
        for i in range(3)
    ]
    truth = [_series(f"truth_r{i}", "other", rng.normal(0, 1, 10)) for i in range(3)]
    groups = {("to_benchmark", "M"): pred, ("other", "CESM2"): truth}
    flags = {("to_benchmark", "M"): False, ("other", "CESM2"): True}
    assert le_spread_rows(groups, flags, ["rsut"]) == []
    assert le_spread_rows(groups, flags, ["tas"])
