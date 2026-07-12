# ClimateBench2 suites

CB2-owned suite YAMLs in [ClimateEval's suite format](https://github.com/climate-federation/ClimateEval/blob/main/docs/suites.md).
They mix stock ClimateEval diagnostics (`climateeval.diags.*`) with CB2
protocol diagnostics (`climatebench2.diags.*`), which ClimateEval loads by
dotted class path. A suite here shadows a ClimateEval suite of the same name
(`_resolve_suite` in `climatebench2/_cli.py`).

`Suite.get_database` passes **one data object to every diagnostic**, so
suites are homogeneous by data shape: *complex* suites take an experiment
dict (`--experiment KEY=PATH`), *simple* suites take the model's cubes.
CB2 complex diagnostics accept a superset of their required keys and skip
(with a warning) when their experiments are absent.

| Suite | Data shape | Contents |
|---|---|---|
| `ClimateBench2_TierI` | experiment dict (`picontrol`, `4xco2`, `histaer`, `historical`, `day`, `amip`, `amip4xco2`, `patch_ep`, `patch_wp`) | 17 physical-consistency gates: ECS, energy balance, closures, clear-sky β, land–ocean, Arctic, aerosol ERF, MHT, ITCZ–EFE, Bjerknes, C–C, ENSO teleconnections, geostrophic balance, MJO, amip-4xCO2 ERF, GFMIP Δλ, + Pinatubo & hemispheric asymmetry |
| `ClimateBench2_TierI_variability` | cubes (monthly `tos`) | ENSO amplitude + spectral-shape gates |
| `ClimateBench2_TierII` | cubes (monthly) | Core variables vs HadCRUT5/GPCP/CERES/ESACCI/OSI-450/EN4 with CRPS-ESS scoring, trend consistency, and the Climatology + CMIP6-MME baseline rows |
| `ClimateBench2_TierII_daily` | cubes (daily/hourly) | TXx-style block maxima, pr intensity PDF, diurnal cycle |
| `ClimateBench2_TierIII` | experiment dict (`picontrol` + `midholocene`/`lgm`/`lig127k`) | Mid-Holocene monsoon gate + proxy-site consistency per period |

Every threshold referenced by a diagnostic comes from
[`../thresholds.yml`](../thresholds.yml) — never hard-coded.
