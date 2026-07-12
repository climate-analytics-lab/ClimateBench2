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
