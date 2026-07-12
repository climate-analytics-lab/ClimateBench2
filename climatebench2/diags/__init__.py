"""ClimateBench2 diagnostics — ClimateEval-compatible ``Diagnostic`` subclasses.

These plug into ClimateEval suites by dotted class path, e.g.::

    - name: ecs_gate
      diagnostic: climatebench2.diags.ECSGate

Modules (docs/climateeval_delineation_plan.md §4):

- ``pass_fail``      — Tier I gate machinery + gates over ClimateEval diagnostics
- ``_scoring``       — CRPS-with-ESS + ensemble-consistency primitives (Phase 2)
- ``tier1_physics``  — land-ocean, Arctic, aerosol ERF, MHT, ITCZ, ... (Phase 3)
- ``tier2_scores``   — probabilistic scoring diagnostics, regimes (a)/(b) (Phase 2)
- ``baselines``      — climatology persistence / EBM pattern scaling / MME (Phase 4)
- ``tier3_paleo``    — proxy-aware scoring + mid-Holocene monsoon check (Phase 5)

Every diagnostic subclasses ``climateeval.diags._base.Diagnostic`` (usually via
``SimpleDiagnostic`` or ``ComplexDiagnostic``) and takes its thresholds from
``climatebench2/thresholds.yml`` — never hard-code a bound.
"""

from __future__ import annotations

from climatebench2.diags.pass_fail import ENSOGate, GateCheck, GateMixin
from climatebench2.diags.tier1_physics import (
    AerosolForcingGate,
    ArcticAmplificationGate,
    BjerknesGate,
    CB2ComplexDiagnostic,
    CCScalingGate,
    ClearSkyFeedbackGate,
    ClosureGate,
    ECSGate,
    EnergyBalanceGate,
    ITCZEFEGate,
    LandOceanWarmingGate,
    MeridionalHeatTransportGate,
)
from climatebench2.diags.tier1_extended import (
    Amip4xCO2ERFGate,
    ENSOTeleconnectionsGate,
    GeostrophicBalanceGate,
    GFMIPPatchGate,
    MJOGate,
)
from climatebench2.diags.tier2_diagnostics import (
    HemisphericAsymmetryGate,
    PinatuboResponseGate,
)
from climatebench2.diags.tier3_paleo import (
    MidHoloceneMonsoonGate,
    PaleoProxyConsistencyGate,
)
from climatebench2.diags.tier2_scores import (
    ScoredAnnualMaxTimeSeries,
    ScoredAnnualMeanTimeSeries,
    ScoredMonthlyMeanTimeSeries,
    TrendConsistency,
)

__all__ = [
    "AerosolForcingGate",
    "Amip4xCO2ERFGate",
    "ArcticAmplificationGate",
    "BjerknesGate",
    "CB2ComplexDiagnostic",
    "CCScalingGate",
    "ClearSkyFeedbackGate",
    "ClosureGate",
    "ECSGate",
    "ENSOGate",
    "ENSOTeleconnectionsGate",
    "EnergyBalanceGate",
    "GFMIPPatchGate",
    "GateCheck",
    "GateMixin",
    "GeostrophicBalanceGate",
    "HemisphericAsymmetryGate",
    "ITCZEFEGate",
    "LandOceanWarmingGate",
    "MJOGate",
    "MeridionalHeatTransportGate",
    "MidHoloceneMonsoonGate",
    "PaleoProxyConsistencyGate",
    "PinatuboResponseGate",
    "ScoredAnnualMaxTimeSeries",
    "ScoredAnnualMeanTimeSeries",
    "ScoredMonthlyMeanTimeSeries",
    "TrendConsistency",
]
