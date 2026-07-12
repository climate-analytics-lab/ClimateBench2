"""Tests for the Tier II scoring diagnostics' post-processing.

Exercises the mixin logic on synthetic DiagnosticOutput tables — no data
loading, but the real ibis/DiagnosticOutput plumbing (needs climateeval).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

climateeval = pytest.importorskip("climateeval")

import ibis  # noqa: E402

from climateeval.diags._base import DiagnosticOutput  # noqa: E402

from climatebench2.diags.tier2_scores import (  # noqa: E402
    MME_DATA_ID,
    ScoredAnnualMeanTimeSeries,
    TrendConsistency,
    _aligned,
    _stack_members,
)

N_YEARS = 20
TIMES = pd.date_range("2000-01-01", periods=N_YEARS, freq="YS")


def _raw_output_df() -> pd.DataFrame:
    """Model + reference + two CMIP6 'other' sources, one variable."""
    rng = np.random.default_rng(0)
    truth = np.linspace(0.0, 1.0, N_YEARS) + rng.normal(0, 0.05, N_YEARS)
    frames = []
    sources = [
        ("MyModel", "to_benchmark", truth + rng.normal(0, 0.1, N_YEARS)),
        ("OBS", "reference", truth),
        ("CMIP6_A", "other", truth + rng.normal(0, 0.2, N_YEARS)),
        ("CMIP6_B", "other", truth + rng.normal(0, 0.2, N_YEARS)),
    ]
    for data_id, data_type, values in sources:
        frames.append(
            pd.DataFrame(
                {
                    "data_id": data_id,
                    "data_type": data_type,
                    "time": TIMES,
                    "tas": values,
                },
            ),
        )
    return pd.concat(frames, ignore_index=True)


def _output_from(raw_df: pd.DataFrame) -> DiagnosticOutput:
    placeholder = ibis.memtable(pd.DataFrame({"x": [0]}))
    return DiagnosticOutput(
        raw_output=ibis.memtable(raw_df),
        metrics=None,
        variables=placeholder,
        data_sources=placeholder,
    )


def test_scored_time_series_appends_crps_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    raw_df = _raw_output_df()
    base_output = _output_from(raw_df)
    monkeypatch.setattr(
        "climateeval.diags.simple.AnnualMeanTimeSeries.get_output",
        lambda self, data, info: base_output,
    )
    diag = ScoredAnnualMeanTimeSeries.__new__(ScoredAnnualMeanTimeSeries)
    output = diag.get_output(None, None)

    metrics = output.metrics.to_pandas()
    assert set(metrics["data_id"]) == {"MyModel", "CMIP6_A", "CMIP6_B", MME_DATA_ID}
    my = metrics.set_index("data_id").loc["MyModel"]
    assert my["var_id"] == "tas"
    assert my["crps"] > 0
    assert my["n_members"] == 1
    assert my["n_time"] == N_YEARS
    # single member: CRPS == MAE against the reference
    x, y = _aligned(
        raw_df[raw_df.data_id == "MyModel"],
        raw_df[raw_df.data_id == "OBS"],
        "tas",
    )
    assert my["crps"] == pytest.approx(np.abs(x - y).mean())

    mme = metrics.set_index("data_id").loc[MME_DATA_ID]
    assert mme["n_members"] == 2
    assert mme["data_type"] == "baseline"


def test_trend_consistency_passes_for_consistent_obs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw_df = _raw_output_df()
    base_output = _output_from(raw_df)
    monkeypatch.setattr(
        "climateeval.diags.simple.AnnualMeanTimeSeries.get_output",
        lambda self, data, info: base_output,
    )
    diag = TrendConsistency.__new__(TrendConsistency)
    diag._sigma_obs = 0.0
    output = diag.get_output(None, None)

    metrics = output.metrics.to_pandas()
    row = metrics.iloc[0]
    assert row["var_id"] == "tas_trend_consistency"
    assert row["data_id"] == "MyModel"
    assert row["n_members"] == 3  # MyModel + 2 CMIP6
    # All sources share the same underlying trend -> consistent
    assert row["passes"] == 1.0


def test_trend_consistency_fails_for_wild_obs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw_df = _raw_output_df()
    # Give the observations a wildly different trend
    obs_mask = raw_df["data_id"] == "OBS"
    raw_df.loc[obs_mask, "tas"] = np.linspace(0.0, 50.0, N_YEARS)
    base_output = _output_from(raw_df)
    monkeypatch.setattr(
        "climateeval.diags.simple.AnnualMeanTimeSeries.get_output",
        lambda self, data, info: base_output,
    )
    diag = TrendConsistency.__new__(TrendConsistency)
    diag._sigma_obs = 0.0
    output = diag.get_output(None, None)
    assert output.metrics.to_pandas().iloc[0]["passes"] == 0.0


def test_stack_members_aligns_on_common_times() -> None:
    raw_df = _raw_output_df()
    ref = raw_df[raw_df.data_id == "OBS"]
    m1 = raw_df[raw_df.data_id == "CMIP6_A"].iloc[2:]  # missing first 2 years
    m2 = raw_df[raw_df.data_id == "CMIP6_B"]
    members, obs = _stack_members([m1, m2], ref, "tas")
    assert members.shape == (2, N_YEARS - 2)
    assert obs.shape == (N_YEARS - 2,)
