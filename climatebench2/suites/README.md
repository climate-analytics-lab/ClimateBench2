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
`SuiteSpec.per_member` is what decides that, and it is set for
`ClimateBench2_TierII_events` too: its aggregated scalars are scored *across*
the ensemble, so the suite runs once per member with **that member's own
record** under the `historical` key (an explicit `--experiment historical=DIR`
pins one record for every member instead, collapsing the runs to one). Tier I
and Tier III stay once-per-model — a gate is a property of the model.
CB2 complex diagnostics accept a superset of their required keys and skip
(with a warning) when their experiments are absent
(`climatebench2.diags.SupersetExperimentMixin`) — including the thin gate
wrappers over ClimateEval's own complex diagnostics (ECS, land–ocean warming
ratio, Arctic amplification, meridional heat transport), which take their
protocol constants from `thresholds.yml`, so their suite entries keep
`additional_diagnostic_kwargs: {}`.

| Suite | Data shape | Contents |
|---|---|---|
| `ClimateBench2_TierI` | experiment dict (`picontrol`, `4xco2`, `histaer`, `historical`, `day`, `amip`, `amip4xco2`, `patch_ep`, `patch_wp`) | 17 physical-consistency gates: ECS, energy balance, closures, clear-sky β, precip–buoyancy, land–ocean, Arctic, aerosol ERF, MHT, ITCZ–EFE, ENSO teleconnections, geostrophic balance, MJO, amip-4xCO2 ERF, GFMIP Δλ + the Bjerknes and C–C extras — **plus** `internal_variability`, which is not a gate: it reports the piControl σ_int the Tier II consistency test needs, and rides here because this is where the control is loaded in full |
| `ClimateBench2_TierI_variability` | cubes (monthly `tos`) | ENSO amplitude + spectral-shape gates |
| `ClimateBench2_TierII` | cubes (monthly) | Core variables vs HadCRUT5/GPCP/CERES/ESACCI/OSI-450/EN4 — `tas`, `pr`, all-sky **and clear-sky** TOA (`rsut`/`rlut`/`rtnt`/`rsutcs`/`rlutcs`), `prw`, clouds (`clt`/`clwvi`/`clivi`), SST, sea ice, OHC (total, 0–2000 m **and 0–100 m**) — plus `reference_baseline` / `sst_baseline` (the reference's pre-test 1985–2014 record) and `eof_projection` / `sst_eof_projection` (the regime-(b) coefficients on the reference's fixed pre-2015 EOF basis) |
| `ClimateBench2_TierII_daily` | cubes (daily/hourly) | TXx block maxima (daily `tasmax`), pr intensity PDF, diurnal cycle |
| `ClimateBench2_TierII_events` | experiment dict (`historical`), **once per ensemble member** | The Tier II aggregated scalars of §II.1 — realized warming level (the protocol's primary test-window statistic) and the two GMST trends, the Pinatubo response, the aerosol-era hemispheric asymmetry. Reported and *scored*, never part of the Tier I entry ticket |
| `ClimateBench2_TierIII` | experiment dict (`picontrol` + `midholocene`/`lgm`/`lig127k`) | Mid-Holocene monsoon gate + proxy-site consistency per period |

The `Scored*` diagnostics named by the Tier II suites (and `TrendConsistency`,
kept only so older YAMLs stay valid) are **thin subclasses of the ClimateEval
time-series diagnostics**: they emit the raw series and ClimateEval's
deterministic metrics only. The probabilistic score is added
afterwards by `climatebench2.scoring_pass`, which `climatebench2 score` runs
over the finished databases (and `climatebench2 leaderboard --rescore`
re-runs) — members arrive as separate data sources, so a model's fair CRPS
can only be formed once every member has run, and the regime-(c) consistency
test additionally needs the σ_int rows from the Tier I database.

Two Tier I gates fetch **observations** through ClimateEval DataSources rather
than working from the submission alone: `precip_buoyancy` (I.3c — the GPCP/ERA5
reference slope over `tier1.precip_buoyancy.obs_window`) and
`enso_teleconnections` (I.5c — the HadISST/GPCP regression patterns over
`tier1.enso.teleconnection_obs_window`). Both windows end in 2014, so neither
touches the reserved post-2015 test period. When the products cannot be fetched
(no network, no CDS key) and `fail_on_missing_data` is False, each emits the
model's own statistic, logs the reason and writes **no gate row** — the
scorecard's "not run" hole rather than a spurious pass or fail.

Two Tier II entries deliberately reach **back past the suite's test-window cut**,
by loading their reference through a copy of the `Variable` carrying a different
`timerange` (`diags/tier2_reference.py`): `reference_baseline` records the
1985–2014 series the Climatology baseline is built from, and `eof_projection`
builds the regime-(b) basis from the reference's pre-2015 monthly anomalies. Both
skip a reference that does not cover the window, with a logged reason.

The **Tier II events** suite also fetches observations, and unlike the Tier I
gates it emits them as `reference` rows so the scoring pass can score against
them (`diags/tier2_diagnostics.py::ObservedScalarMixin`): HadCRUT5 `tas`,
corrected from its blended land-air/SST basis to a surface-air-temperature one
with `tier2.gsat_blending_factor` and carrying
`tier2.gsat_blending_relative_uncertainty` of the change as the scalar's
`_sigma_obs`. Two of its scalars have **no** observational counterpart and stay
model-only sign flags, with the reason recorded: the Pinatubo `rsds` dimming
(no BSRN or CERES-SYN DataSource) and the ITCZ shift (GPCP starts in 1979,
after the 1950–1985 aerosol era). GISTEMP, Berkeley Earth and NOAAGlobalTemp —
the paper's other three GMST products — have no ClimateEval DataSource either,
so `tas` has no inter-product observational spread yet; the pass picks them up
automatically once they land upstream.

Sea ice is scored as **area** (Σ siconc·A), which is what ClimateEval's
`SeaIceArea*` diagnostics compute; the protocol asks for **extent** (Σ A where
siconc > 15 %). `ClimateBench2_TierII.yml` carries a commented-out
`SeaIceExtentTimeSeries` stanza against ClimateEval PR #47 rather than
mislabelling area as extent.

Every threshold referenced by a diagnostic comes from
[`../thresholds.yml`](../thresholds.yml) — never hard-coded, and that includes each
gate's `requirement:` tag (`required` / `extended` / `extra` / `diagnostic`), which
decides whether the check is part of the leaderboard's entry ticket, is reported for
additional credit, or is a non-protocol sanity check. A submission may declare an
individual gate inapplicable with `climatebench2 score --not-applicable NAME` (NAME is
the suite entry name, e.g. `geostrophic_balance`); the gate then computes nothing and
its rows are marked `applicable = 0` — neither a pass nor a fail — which the scorecard
distinguishes from a gate that never ran.
