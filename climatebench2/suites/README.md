# ClimateBench2 suites

CB2-owned suite YAMLs in [ClimateEval's suite format](https://github.com/climate-federation/ClimateEval/blob/main/docs/suites.md).
They mix stock ClimateEval diagnostics (`climateeval.diags.*`) with CB2
protocol diagnostics (`climatebench2.diags.*`), which ClimateEval loads by
dotted class path.

Planned (delineation plan §4/§6):

- `ClimateBench2_TierI.yml` — physical-consistency pass/fail gate (Phases 1/3/4)
- `ClimateBench2_TierII.yml` — probabilistic scoring vs post-2015 obs (Phases 1/2)
- `ClimateBench2_TierIII.yml` — paleo + perfect-model (Phase 5)

Until these land, `climatebench2 score` defaults to ClimateEval's stock
`Tier2_atmosphere_monthly`. A CB2 suite placed here shadows a ClimateEval
suite of the same name (see `_resolve_suite` in `climatebench2/_cli.py`).

Every threshold referenced by a suite must come from
[`../thresholds.yml`](../thresholds.yml), never be hard-coded in a diagnostic.
