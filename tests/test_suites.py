"""Integration tests: CB2 suites parse and their diagnostics instantiate.

These need ClimateEval importable (run inside its pixi env, see tests/README.md);
they build every diagnostic from the CB2 suite YAMLs without loading any data.
"""

from __future__ import annotations

import pytest

climateeval = pytest.importorskip("climateeval")

from climateeval.suites import Suite  # noqa: E402

from climatebench2._cli import DEFAULT_SUITES, _resolve_suite  # noqa: E402


@pytest.mark.parametrize("suite_name", DEFAULT_SUITES)
def test_cb2_suites_build_all_diagnostics(suite_name: str) -> None:
    resolved = _resolve_suite(suite_name)
    assert resolved != suite_name, f"CB2 suite YAML not packaged for {suite_name}"
    suite = Suite(resolved)
    diagnostics = suite._get_diagnostics()
    assert diagnostics, f"suite {suite_name} built no diagnostics"
    for diag in diagnostics.values():
        # Every diagnostic must be a real ClimateEval Diagnostic
        from climateeval.diags._base import Diagnostic

        assert isinstance(diag, Diagnostic)


def test_tier1_gates_have_thresholds_wired() -> None:
    from climatebench2.diags import ECSGate, ENSOGate

    (ecs_check,) = ECSGate._gate_checks
    assert (ecs_check.lower, ecs_check.upper) == (1.0, 7.0)

    amp, ratio = ENSOGate._gate_checks
    assert (amp.lower, amp.upper) == (0.5, 1.4)
    assert ratio.lower == 1.5
    assert ratio.upper is None


#: Entries of the Tier I suites that are inputs to Tier II rather than gates:
#: they emit numbers only and can never touch the entry ticket.
TIER1_NON_GATE_DIAGNOSTICS = {"internal_variability"}


def test_every_tier1_gate_carries_a_requirement_tag() -> None:
    """No gate may reach the scorecard without a Required/Extended/extra tag."""
    from climatebench2.diags.pass_fail import REQUIREMENT_TAGS

    for suite_name in ("ClimateBench2_TierI", "ClimateBench2_TierI_variability"):
        suite = Suite(_resolve_suite(suite_name))
        for diag_name, diag in suite._get_diagnostics().items():
            checks = diag._gate_checks
            if diag_name in TIER1_NON_GATE_DIAGNOSTICS:
                assert not checks, f"{diag_name} must emit no pass/fail row"
                continue
            assert checks, f"{diag_name} defines no gate checks"
            for check in checks:
                assert check.requirement in REQUIREMENT_TAGS, (
                    f"{diag_name}/{check.check_id} has requirement "
                    f"'{check.requirement}'"
                )
                # Tier II event diagnostics do not belong in the Tier I suites
                assert check.requirement != "diagnostic", diag_name


def test_internal_variability_rides_in_tier1_without_gating() -> None:
    """σ_int comes from the piControl experiment, so it lives in Tier I.

    It is tagged ``diagnostic`` in thresholds.yml, emits no ``_gate_checks``
    and therefore contributes nothing to the entry ticket — the scoring pass
    reads its rows to fill σ_int in the regime-(c) consistency test.
    """
    from climatebench2.diags import InternalVariability

    diagnostics = Suite(_resolve_suite("ClimateBench2_TierI"))._get_diagnostics()
    diag = diagnostics["internal_variability"]
    assert isinstance(diag, InternalVariability)
    assert diag._required_data_keys == ("picontrol",)
    assert InternalVariability.requirement == "diagnostic"
    # ... and it is invisible to the leaderboard's Required set
    from climatebench2.diags.pass_fail import gate_requirements

    assert not [c for c, t in gate_requirements().items() if t == "diagnostic" and
                c.startswith("sigma_int")]


def test_tier2_event_gates_moved_out_of_the_tier1_suite() -> None:
    """Pinatubo / hemispheric asymmetry are Tier II diagnostics, not gates."""
    tier1 = Suite(_resolve_suite("ClimateBench2_TierI"))._get_diagnostics()
    assert "pinatubo" not in tier1
    assert "hemispheric_asymmetry" not in tier1

    events = Suite(_resolve_suite("ClimateBench2_TierII_events"))._get_diagnostics()
    assert set(events) == {
        "realized_warming_level",
        "pinatubo",
        "hemispheric_asymmetry",
        # the seasonal-cycle metrics of §II.1 (work package 6b)
        "land_temperature_range",
        "sst_low_cloud_covariance",
        "seasonal_cloud_feedback",
    }
    for diag in events.values():
        assert diag._required_data_keys == ("historical",)
        for check in diag._gate_checks:
            assert check.requirement == "diagnostic"
    assert "ClimateBench2_TierII_events" in DEFAULT_SUITES


def test_realized_warming_level_emits_no_gate_row() -> None:
    """§II.1's primary scalar is scored, not gated: no pass/fail anywhere."""
    from climatebench2.diags import RealizedWarmingLevel
    from climatebench2.diags.pass_fail import gate_requirements

    assert RealizedWarmingLevel._gate_checks == ()
    assert RealizedWarmingLevel.requirement == "diagnostic"
    assert "gmst_warming_level" not in gate_requirements()


def test_tier2_suite_covers_the_protocol_variables() -> None:
    """Clear-sky TOA, condensed-water paths and both OHC layers are wired."""
    suite = Suite(_resolve_suite("ClimateBench2_TierII"))._get_diagnostics()
    core = {v.id for v in suite["annual_mean_timeseries"]._variables}
    assert {"rsutcs", "rlutcs", "clwvi", "clivi"} <= core
    # ... and every one of them carries a reference, or the pass cannot score
    referenced = {v.id for v in suite["annual_mean_timeseries"]._reference_data}
    assert core <= referenced
    ohc = {v.id for v in suite["ohc"]._variables}
    assert {"phcint_total", "phcint_2000m", "phcint_100m"} <= ohc


def test_complex_gates_accept_the_not_applicable_kwarg() -> None:
    """Every experiment-based gate can be declared N/A by a submission."""
    for suite_name in ("ClimateBench2_TierI", "ClimateBench2_TierII_events"):
        suite = Suite(
            _resolve_suite(suite_name),
            diagnostic_kwargs={"not_applicable": ["geostrophic_balance"]},
        )
        diagnostics = suite._get_diagnostics()
        assert diagnostics
        for name, diag in diagnostics.items():
            assert diag.declared_not_applicable == (name == "geostrophic_balance")


def test_suite_registry_matches_the_actual_diagnostics() -> None:
    """The CLI's data-shape registry must agree with what each suite holds."""
    from climateeval.diags.complex._base import ComplexDiagnostic

    from climatebench2._cli import SUITE_REGISTRY

    for suite_name, spec in SUITE_REGISTRY.items():
        diagnostics = Suite(_resolve_suite(suite_name))._get_diagnostics()
        is_complex = [
            isinstance(diag, ComplexDiagnostic) for diag in diagnostics.values()
        ]
        assert any(is_complex) == (spec.shape == "experiments"), suite_name
        # Suites are homogeneous by data shape (Suite.get_database passes one
        # data object to every diagnostic).
        assert all(is_complex) == any(is_complex), suite_name


def test_unregistered_suites_are_classified_by_probing() -> None:
    from climateeval.diags.complex._base import ComplexDiagnostic

    from climatebench2._cli import _suite_spec

    tier1 = Suite(_resolve_suite("ClimateBench2_TierI"))._get_diagnostics()
    spec = _suite_spec("SomeOtherSuite", tier1, ComplexDiagnostic)
    assert spec.shape == "experiments"
    assert "not in the CB2 suite registry" in spec.note

    variability = Suite(
        _resolve_suite("ClimateBench2_TierI_variability"),
    )._get_diagnostics()
    spec = _suite_spec("SomeOtherSuite", variability, ComplexDiagnostic)
    assert (spec.shape, spec.window) == ("cubes", "historical")


def test_the_daily_suite_runs_over_the_full_record_per_member() -> None:
    """The extremes/PDF/diurnal statistics are in-sample, not test-window.

    The paper computes them "over the full historical record", so the daily
    suite is the one cube suite the CLI does not cut — and every entry in it
    is labelled in-sample in `tier2.window_labels`.
    """
    from climatebench2._cli import SUITE_REGISTRY, suite_timerange
    from climatebench2._thresholds import get_threshold

    spec = SUITE_REGISTRY["ClimateBench2_TierII_daily"]
    assert (spec.shape, spec.window, spec.per_member) == ("cubes", "full", True)
    # ... and not even an explicit --timerange re-cuts it
    assert suite_timerange(spec) is None
    assert suite_timerange(spec, "19790101/20141231") is None

    labels = get_threshold("tier2.window_labels")["diagnostics"]
    suite = Suite(_resolve_suite("ClimateBench2_TierII_daily"))._get_diagnostics()
    for name in suite:
        assert labels.get(name, "held-out") == "in-sample", name


def test_the_daily_extremes_are_model_only_but_scorable_in_shape() -> None:
    """No daily obs product exists upstream, so the extremes carry no reference.

    The shape is still the scored one (aggregated scalars), so the day a
    HadEX3 DataSource lands the suite only needs a `reference_data:` line.
    """
    from climatebench2.diags import ETCCDIExtremes, ScalarTableDiagnostic

    suite = Suite(_resolve_suite("ClimateBench2_TierII_daily"))._get_diagnostics()
    extremes = suite["extremes"]
    assert isinstance(extremes, ETCCDIExtremes)
    assert isinstance(extremes, ScalarTableDiagnostic)
    assert not extremes._reference_data, "extremes must stay unscored for now"
    assert {v.var_name for v in extremes._variables} == {"tasmax", "tasmin", "pr"}
    # ETCCDI indices are land indices: the mask is ClimateEval's, per variable
    assert all(v.landsea_mask == "land_only" for v in extremes._variables)

    # ... whereas the diurnal harmonic and the Perkins score do have one
    assert suite["diurnal_harmonic"]._reference_data
    assert suite["perkins"]._reference_data


def test_the_seasonal_metrics_read_their_boxes_from_thresholds() -> None:
    from climatebench2._thresholds import get_threshold
    from climatebench2.diags import (
        LandAnnualTemperatureRange,
        SeasonalCloudRadiativeFeedback,
        SSTLowCloudCovariance,
    )

    decks = get_threshold("tier2.seasonal.stratocumulus_regions")
    assert len(decks) == 5  # the five conventional stratocumulus decks
    for box in decks.values():
        assert len(box["lat"]) == 2 and len(box["lon"]) == 2

    suite = Suite(_resolve_suite("ClimateBench2_TierII_events"))._get_diagnostics()
    assert isinstance(suite["land_temperature_range"], LandAnnualTemperatureRange)
    assert isinstance(suite["sst_low_cloud_covariance"], SSTLowCloudCovariance)
    assert isinstance(
        suite["seasonal_cloud_feedback"],
        SeasonalCloudRadiativeFeedback,
    )
    # reported numbers, never gates
    for name in (
        "land_temperature_range",
        "sst_low_cloud_covariance",
        "seasonal_cloud_feedback",
    ):
        assert suite[name]._gate_checks == ()
        assert suite[name].requirement == "diagnostic"
