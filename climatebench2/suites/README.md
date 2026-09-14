# ClimateBench2 suites

CB2-owned suite YAMLs in [ClimateEval's suite format](https://github.com/climate-federation/ClimateEval/blob/main/docs/suites.md).
They mix stock ClimateEval diagnostics (`climateeval.diags.*`) with CB2
protocol diagnostics (`climatebench2.diags.*`), which ClimateEval loads by
dotted class path. A suite here shadows a ClimateEval suite of the same name
(`_resolve_suite` in `climatebench2/_cli.py`).

`Suite.get_database` passes **one data object to every diagnostic**, so
suites are homogeneous by data shape: *complex* suites take an experiment
dict (`--experiment KEY=PATH`), *simple* suites take cubes. Which of the two a
suite gets — and over which time window — is declared in the CLI's suite
registry (`_cli.SUITE_REGISTRY`): experiments always load in full, the
variability suite takes `picontrol`, and the Tier II suites take the model's
cubes over the post-2015 test window (`tier2.test_window_start`), once per
ensemble member (`--member LABEL=PATH`, or DRS auto-discovery).
CB2 complex diagnostics accept a superset of their required keys and skip
(with a warning) when their experiments are absent
(`climatebench2.diags.SupersetExperimentMixin`) — including the thin gate
wrappers over ClimateEval's own complex diagnostics (ECS, land–ocean warming
ratio, Arctic amplification, meridional heat transport), which take their
protocol constants from `thresholds.yml`, so their suite entries keep
`additional_diagnostic_kwargs: {}`.

| Suite | Data shape | Contents |
|---|---|---|
| `ClimateBench2_TierI` | experiment dict (`picontrol`, `4xco2`, `histaer`, `historical`, `day`, `amip`, `amip4xco2`, `patch_ep`, `patch_wp`) | 16 physical-consistency gates: ECS, energy balance, closures, clear-sky β, land–ocean, Arctic, aerosol ERF, MHT, ITCZ–EFE, ENSO teleconnections, geostrophic balance, MJO, amip-4xCO2 ERF, GFMIP Δλ + the Bjerknes and C–C extras |
| `ClimateBench2_TierI_variability` | cubes (monthly `tos`) | ENSO amplitude + spectral-shape gates |
| `ClimateBench2_TierII` | cubes (monthly) | Core variables vs HadCRUT5/GPCP/CERES/ESACCI/OSI-450/EN4 with CRPS-ESS scoring, trend consistency, and the Climatology + CMIP6-MME baseline rows |
| `ClimateBench2_TierII_daily` | cubes (daily/hourly) | TXx block maxima (daily `tasmax`), pr intensity PDF, diurnal cycle |
| `ClimateBench2_TierII_events` | experiment dict (`historical`) | Pinatubo response and aerosol-era hemispheric asymmetry — Tier II aggregated diagnostics, reported but never part of the Tier I entry ticket |
| `ClimateBench2_TierIII` | experiment dict (`picontrol` + `midholocene`/`lgm`/`lig127k`) | Mid-Holocene monsoon gate + proxy-site consistency per period |

Every threshold referenced by a diagnostic comes from
[`../thresholds.yml`](../thresholds.yml) — never hard-coded, and that includes each
gate's `requirement:` tag (`required` / `extended` / `extra` / `diagnostic`), which
decides whether the check is part of the leaderboard's entry ticket, is reported for
additional credit, or is a non-protocol sanity check. A submission may declare an
individual gate inapplicable with `climatebench2 score --not-applicable NAME` (NAME is
the suite entry name, e.g. `geostrophic_balance`); the gate then computes nothing and
its rows are marked `applicable = 0` — neither a pass nor a fail — which the scorecard
distinguishes from a gate that never ran.
