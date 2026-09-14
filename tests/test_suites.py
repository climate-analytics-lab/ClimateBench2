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


def test_every_tier1_gate_carries_a_requirement_tag() -> None:
    """No gate may reach the scorecard without a Required/Extended/extra tag."""
    from climatebench2.diags.pass_fail import REQUIREMENT_TAGS

    for suite_name in ("ClimateBench2_TierI", "ClimateBench2_TierI_variability"):
        suite = Suite(_resolve_suite(suite_name))
        for diag_name, diag in suite._get_diagnostics().items():
            checks = diag._gate_checks
            assert checks, f"{diag_name} defines no gate checks"
            for check in checks:
                assert check.requirement in REQUIREMENT_TAGS, (
                    f"{diag_name}/{check.check_id} has requirement "
                    f"'{check.requirement}'"
                )
                # Tier II event diagnostics do not belong in the Tier I suites
                assert check.requirement != "diagnostic", diag_name


def test_tier2_event_gates_moved_out_of_the_tier1_suite() -> None:
    """Pinatubo / hemispheric asymmetry are Tier II diagnostics, not gates."""
    tier1 = Suite(_resolve_suite("ClimateBench2_TierI"))._get_diagnostics()
    assert "pinatubo" not in tier1
    assert "hemispheric_asymmetry" not in tier1

    events = Suite(_resolve_suite("ClimateBench2_TierII_events"))._get_diagnostics()
    assert set(events) == {"pinatubo", "hemispheric_asymmetry"}
    for diag in events.values():
        assert diag._required_data_keys == ("historical",)
        for check in diag._gate_checks:
            assert check.requirement == "diagnostic"
    assert "ClimateBench2_TierII_events" in DEFAULT_SUITES


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
