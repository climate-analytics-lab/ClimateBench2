"""Tests for the Tier I gate machinery (climatebench2.diags.pass_fail)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from climatebench2._thresholds import get_threshold, load_thresholds
from climatebench2.diags.pass_fail import (
    GateCheck,
    band_power_ratio,
    gate_metrics,
)


def test_thresholds_load_and_get() -> None:
    thresholds = load_thresholds()
    assert "tier1" in thresholds
    assert get_threshold("tier1.ecs.range") == [1.0, 7.0]
    with pytest.raises(KeyError, match="not found"):
        get_threshold("tier1.no_such_check.bound")


def test_gate_metrics_scalar_check() -> None:
    """One scalar per data source (the ECS shape)."""
    raw = pd.DataFrame(
        {
            "data_id": ["ModelA", "ModelB", "ModelC"],
            "data_type": ["to_benchmark", "other", "other"],
            "ecs": [3.2, 0.5, 8.1],
        },
    )
    checks = (GateCheck(check_id="ecs_gate", column="ecs", lower=1.0, upper=7.0),)
    metrics = gate_metrics(raw, checks)
    result = metrics.set_index("data_id")["passes"]
    assert result["ModelA"] == 1.0  # in range
    assert result["ModelB"] == 0.0  # below
    assert result["ModelC"] == 0.0  # above
    assert (metrics["var_id"] == "ecs_gate").all()
    assert metrics.set_index("data_id").loc["ModelA", "value"] == pytest.approx(3.2)


def test_gate_metrics_series_statistic_orders_by_time() -> None:
    rng = np.random.default_rng(0)
    n = 240
    series = rng.normal(0.0, 0.9, n)
    raw = pd.DataFrame(
        {
            "data_id": "ModelA",
            "data_type": "to_benchmark",
            "time": pd.date_range("2000-01-01", periods=n, freq="MS")[::-1],  # shuffled
            "nino": series,
        },
    )
    checks = (
        GateCheck(
            check_id="amp",
            column="nino",
            statistic=lambda s: float(s.std(ddof=1)),
            lower=0.5,
            upper=1.4,
        ),
    )
    metrics = gate_metrics(raw, checks)
    assert len(metrics) == 1
    assert metrics.loc[0, "value"] == pytest.approx(np.std(series, ddof=1))
    assert metrics.loc[0, "passes"] == 1.0


def test_gate_metrics_skips_missing_column_and_empty_series() -> None:
    raw = pd.DataFrame(
        {
            "data_id": ["A", "B"],
            "data_type": ["to_benchmark", "other"],
            "x": [1.0, np.nan],
        },
    )
    checks = (
        GateCheck(check_id="x_gate", column="x", lower=0.0),
        GateCheck(check_id="missing", column="not_there", lower=0.0),
    )
    metrics = gate_metrics(raw, checks)
    # B's only value is NaN -> dropped; 'missing' column skipped entirely
    assert list(metrics["data_id"]) == ["A"]
    assert list(metrics["var_id"]) == ["x_gate"]


def test_band_power_ratio_enso_like_vs_white_noise() -> None:
    rng = np.random.default_rng(42)
    n = 600  # 50 years, monthly
    t = np.arange(n)
    # ENSO-like: dominant 4-yr oscillation + weak noise
    enso = np.sin(2 * np.pi * t / 48.0) + 0.2 * rng.normal(size=n)
    ratio_enso = band_power_ratio(pd.Series(enso))
    assert ratio_enso > 1.5

    # White noise: flat spectrum, ratio ~ 1
    noise = rng.normal(size=n)
    ratio_noise = band_power_ratio(pd.Series(noise))
    assert ratio_noise < ratio_enso
    assert ratio_noise == pytest.approx(1.0, abs=0.75)


def test_gate_check_one_sided_bounds() -> None:
    raw = pd.DataFrame(
        {"data_id": ["A"], "data_type": ["to_benchmark"], "ratio": [2.0]},
    )
    metrics = gate_metrics(
        raw,
        (GateCheck(check_id="r", column="ratio", lower=1.5),),
    )
    assert metrics.loc[0, "passes"] == 1.0
    assert np.isnan(metrics.loc[0, "bound_upper"])
