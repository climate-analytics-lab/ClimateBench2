"""ClimateBench2 diagnostics — ClimateEval-compatible ``Diagnostic`` subclasses.

These plug into ClimateEval suites by dotted class path, e.g.::

    - name: ensemble_consistency
      diagnostic: climatebench2.diags.EnsembleConsistency

Planned modules (docs/climateeval_delineation_plan.md §4):

- ``_scoring``       — CRPS-with-ESS + ensemble-consistency primitives (Phase 2)
- ``pass_fail``      — Tier I threshold wrappers over computed scalars (Phase 1)
- ``tier1_physics``  — land-ocean, Arctic, aerosol ERF, MHT, ITCZ, ... (Phase 3)
- ``tier2_scores``   — probabilistic scoring diagnostics, regimes (a)/(b) (Phase 2)
- ``baselines``      — climatology persistence / EBM pattern scaling / MME (Phase 4)
- ``tier3_paleo``    — proxy-aware scoring + mid-Holocene monsoon check (Phase 5)

Every diagnostic here must subclass ``climateeval.diags._base.Diagnostic``
(usually via ``SimpleDiagnostic`` or ``ComplexDiagnostic``) and take its
thresholds from ``climatebench2/thresholds.yml`` — never hard-code a bound.
"""

from __future__ import annotations
