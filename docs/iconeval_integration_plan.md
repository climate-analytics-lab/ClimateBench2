# ICONEval Integration Plan

How to leverage [ICONEval](https://github.com/EyringMLClimateGroup/ICONEval) to avoid
duplicating work across ClimateBench2's open Tier I/II issues.

## Executive summary

ICONEval is an orchestration layer around ESMValTool designed for rapid
single-model diagnostics (ICON). ClimateBench2 is a cross-model scoring
protocol. The two tools overlap heavily in *what* they compute but differ in
*how results are consumed*. The recommended approach is:

1. **Do not make ICONEval a dependency** — it is too tightly coupled to ICON,
   DKRZ/Slurm, and developer-feedback workflows.
2. **Adopt ICONEval's recipe templates as a starting point** — port the subset
   that maps to open issues into `esmvaltool/`, adapting them to be
   model-agnostic (CMIP6 multi-model).
3. **Extract the observational bounds data** into a shared reference file that
   both the ESMValTool recipes and the Python benchmark pipeline can use.
4. **Build a thin recipe runner** in `benchmark_scrips/` that generates and
   executes ESMValTool recipes programmatically (no Slurm requirement).

---

## 1. Recipe mapping: ICONEval recipes to ClimateBench2 issues

Each row shows an ICONEval recipe, the ClimateBench2 issue(s) it addresses,
and the adaptation work required.

### Tier I (physical consistency — entry-ticket tests)

| ICONEval recipe | CB2 issue | Adaptation |
|---|---|---|
| `recipe_sanity_checks` | #71 (energy balance closure) | Replace ICON dataset placeholder with CMIP6 multi-model list. Extract TOA net flux (`rtmt`) bounds for pass/fail scoring. Extend from global-mean timeseries to per-decade drift check (0.1 W/m²/decade threshold from issue spec). |
| `recipe_consistency_checks_timeseries` | #72 (realistic covariances: T–radiation, T–precipitation) | Air-mass conservation check maps to energy balance. Water-vapour/C-C scaling diagnostic maps directly to T–precipitation covariance. Add T–radiation scatter from CERES. |
| `recipe_consistency_checks_scatterplot` | #72 (realistic covariances) | C-C scaling scatterplot (Δprw vs ΔT) is directly usable. Add cloud-ice-fraction vs temperature from ICONEval clouds recipes. |
| `recipe_basics_timeseries` (Niño-3.4) | #74 (ENSO variability check) | ICONEval includes Niño-3.4 SST anomaly with CMIP6 envelope. Adapt to compute standard deviation and power spectrum for pass/fail against observed ENSO amplitude range (0.7–1.2 K std dev). |
| `recipe_ocean_maps` / `recipe_basics_maps` | #75 (land-ocean warming contrast) | Not directly implemented in ICONEval, but the map infrastructure can compute land vs ocean masked means. Would need a custom diagnostic script for the warming ratio. |

### Tier II (observational benchmarking)

| ICONEval recipe | CB2 issue | Adaptation |
|---|---|---|
| `recipe_basics_timeseries` | #82 (temperature mean state/trends), #85 (warming rate) | Global-mean tas timeseries with multi-obs reference (ERA5, HadCRUT5). Add trend calculation and scoring. |
| `recipe_basics_timeseries` (pr) | #83 (precipitation mean state/trends) | Global-mean pr with GPCP reference. Already similar to existing `recipe_pr_rmse.yml`. |
| `recipe_clouds_maps` | #84 (TOA radiative fluxes), #91 (clouds, IWV) | Multi-obs mean of CERES, ERA5, MERRA2 for CRE. Directly applicable. |
| `recipe_sea_ice_annual_cycles` / `_timeseries` | #86 (sea ice extent and trends) | NH/SH ice area vs OSI-450, HadISST, NSIDC. Adapt to compute trends and September minimum scoring. |
| `recipe_clouds_annual_cycles_*` | #87 (seasonal cycle emergent constraints) | Annual cycles in large-scale and stratocumulus regions. Add amplitude/phase scoring metric. |
| `recipe_basics_timeseries` (volcanic) | #89 (Pinatubo response) | Would need to isolate 1991–1993 window and compute cooling magnitude vs observed ~0.5 K drop. ICONEval doesn't do this explicitly — new diagnostic script needed. |
| `recipe_clouds_maps` (hemispheric) | #90 (aerosol hemispheric asymmetry) | Multi-obs AOD maps exist via MODIS/ESACCI. Add NH–SH asymmetry index computation. |
| `recipe_portrait_plot` | #100 (aggregated scoring) | RMSE portrait plot across 26 variable/level combinations. Directly usable for Tier II scorecard. Adapt normalisation to ClimateBench2 scoring weights. |

### Not covered by ICONEval (build from scratch)

| CB2 issue | Why ICONEval doesn't help |
|---|---|
| #73 (SST patch experiments) | Requires non-standard experiments not in CMIP6 protocol |
| #76 (Arctic amplification) | Requires abrupt-4xCO2 analysis (now partially covered by `ecs_benchmark.py`) |
| #78 (aerosol forcing hist-aer) | Requires hist-aer experiment; no ICONEval recipe |
| #79–81 (meridional heat transport, ITCZ, Bjerknes) | Ocean-atmosphere coupling diagnostics beyond ICONEval scope |
| #92–96 (Tier III paleoclimate, perfect-model) | No paleoclimate or perfect-model capability in ICONEval |
| #97 (CRPS/probabilistic scoring) | ICONEval is deterministic only |

---

## 2. Observational bounds: extract into a shared reference

ICONEval hardcodes "reasonable range" bounds in `recipe_sanity_checks.yml`.
These should be extracted into a reusable data file.

### Action

Create `observations/reference_bounds.yaml`:

```yaml
# Observational global-mean bounds from ICONEval recipe_sanity_checks.yml
# Source: min/max across ERA5, MERRA2, CERES-EBAF, ESACCI, etc.
tas:
  units: K
  global_mean: [283.9, 293.7]
  sources: [ERA5, MERRA2, HadCRUT5]
rlut:
  units: W m-2
  global_mean: [226.4, 246.3]
  sources: [CERES-EBAF, ERA5, MERRA2]
rsut:
  units: W m-2
  global_mean: [91.1, 128.8]
  sources: [CERES-EBAF, ERA5, MERRA2]
clt:
  units: "%"
  global_mean: [58.7, 74.9]
  sources: [ESACCI-CLOUD, CLARA-AVHRR, MODIS, ERA5]
pr:
  units: mm day-1
  global_mean: [2.50, 3.21]
  sources: [GPCP, ERA5, MERRA2]
lwcre:
  units: W m-2
  global_mean: [23.6, 30.5]
  sources: [CERES-EBAF]
swcre:
  units: W m-2
  global_mean: [-73.5, -40.6]
  sources: [CERES-EBAF]
# ... extend with additional variables as needed
```

This file is consumed by:
- Python benchmark scripts (Tier I pass/fail checks)
- ESMValTool recipes (as `hlines` annotations)
- The web app (for displaying acceptable ranges on scorecards)

---

## 3. Recipe template system: what to adopt

ICONEval's template system has three components worth adopting and one to skip.

### Adopt: placeholder-based recipe generation

ICONEval uses `{{dataset_list}}`, `{{timerange}}` etc. to fill recipe
templates. ClimateBench2 should adopt this pattern for multi-model recipes:

```
esmvaltool/templates/recipe_tier1_energy_balance.yml.template
esmvaltool/templates/recipe_tier2_tas_trends.yml.template
...
```

With a Python generator (`esmvaltool/generate_recipes.py`) that fills
`{{model_list}}` from the Pangeo catalogue or a user-supplied model list.
This replaces manually writing out every ensemble member (as in the current
`recipe_pr_rmse.yml` which lists 12 dataset blocks by hand).

### Adopt: tag-based recipe selection

Map ICONEval's tag system to the tier structure:

```
#TAGS tier1 energy-balance picontrol
#TAGS tier2 temperature trends historical
```

This enables `esmvaltool run --tags tier1` to run all Tier I entry-ticket
checks, or `--tags tier2,clouds` for just cloud diagnostics.

### Adopt: per-recipe resource hints

Even without Slurm, resource hints (`#ESMVALTOOL --max_parallel_tasks=1`) are
useful for controlling memory on cloud VMs or local machines. Parse these as
comments and pass through to ESMValTool's `--max_parallel_tasks` flag.

### Skip: Slurm orchestration

ClimateBench2 targets cloud execution (GCS data, Pangeo catalogue) and local
runs. The Slurm job submission layer is not needed. Instead, use a simple
sequential or `subprocess`-based parallel runner.

---

## 4. Implementation plan

### Phase 1: Foundation (addresses #98, #99)

**Goal:** Establish the ESMValTool recipe infrastructure so subsequent
Tier I/II diagnostics can be added as individual recipes.

1. Create `esmvaltool/templates/` directory for recipe templates.
2. Create `esmvaltool/generate_recipes.py` — reads a template + model list,
   fills placeholders, writes a runnable recipe.
3. Create `esmvaltool/run_recipes.py` — thin runner that executes recipes
   via `subprocess` (no Slurm), collects outputs, generates a summary.
4. Create `observations/reference_bounds.yaml` with ICONEval's observational
   bounds (properly attributed).
5. Add `esmvaltool` to `env.yml` as an optional dependency.

**ICONEval code to reference:**
- `iconeval/_templates.py` → placeholder filling logic
- `iconeval/_io_handler.py` → directory setup pattern
- `iconeval/recipe_templates/recipe_sanity_checks.yml` → bounds data

### Phase 2: Tier I entry-ticket tests (addresses #71, #72, #74)

**Goal:** Implement the highest-value Tier I checks using adapted ICONEval
recipes.

1. **Energy balance closure (#71):**
   Port `recipe_sanity_checks` — compute TOA net flux drift in piControl.
   Score pass/fail against 0.1 W/m²/decade threshold.

2. **Realistic covariances (#72):**
   Port `recipe_consistency_checks_scatterplot` — C-C scaling (Δprw vs ΔT)
   and cloud ice fraction vs temperature. Score against observed regression
   slopes.

3. **ENSO variability (#74):**
   Port the Niño-3.4 timeseries from `recipe_basics_timeseries` and
   `recipe_ocean_timeseries`. Add standard deviation and spectral peak
   scoring.

Each recipe produces both an ESMValTool HTML diagnostic *and* a numeric score
written to `results/tier1/` in the standard CSV format.

**ICONEval code to reference:**
- `recipe_sanity_checks.yml` → variable list, bounds, preprocessors
- `recipe_consistency_checks_scatterplot.yml` → C-C diagnostic
- `recipe_ocean_timeseries.yml` → Niño-3.4 setup

### Phase 3: Tier II observational benchmarks (addresses #82–87, #91)

**Goal:** Expand the recipe set to cover the core Tier II diagnostics.

1. **Temperature/precipitation mean state (#82, #83):**
   Port `recipe_basics_maps` and `recipe_basics_timeseries`. Add RMSE/MAE
   scoring against HadCRUT5 and GPCP (replaces/extends current
   `recipe_pr_rmse.yml`).

2. **TOA radiative fluxes (#84):**
   Port `recipe_clouds_maps` for CRE fields against multi-obs mean
   (CERES-EBAF, ERA5, MERRA2).

3. **Sea ice (#86):**
   Port `recipe_sea_ice_annual_cycles` and `_timeseries`. Add September
   minimum and trend scoring.

4. **Seasonal cycle (#87):**
   Port `recipe_clouds_annual_cycles_large_scale_regions`. Add
   amplitude/phase error metrics.

5. **Extended variables (#91):**
   Port cloud profiles from `recipe_clouds_profiles` and IWV/LWP from
   `recipe_clouds_maps`.

**ICONEval code to reference:**
- All `recipe_clouds_*`, `recipe_sea_ice_*`, `recipe_basics_*` templates
- `recipe_portrait_plot.yml` → aggregated scoring across variables

### Phase 4: Scorecard and reporting (addresses #100)

**Goal:** Generate an aggregated scorecard from all Tier I + II results.

1. Port `recipe_portrait_plot` as the RMSE portrait plot across all
   evaluated variables.
2. Build a summary generator (inspired by ICONEval's `_summarize.py`) that
   produces an HTML scorecard from the results CSVs, linkable from the
   existing ClimateBench web app.
3. Add provenance tracking — record which recipe version + data version
   produced each score.

---

## 5. What NOT to adopt from ICONEval

| ICONEval feature | Reason to skip |
|---|---|
| ICON/XPP-specific `SimulationInfo` | Designed for ICON directory conventions; ClimateBench2 uses Pangeo/ESGF |
| Slurm job orchestration (`_job.py`) | Not needed for cloud/local execution |
| DKRZ Swift publishing (`publish_html.py`) | ClimateBench2 uses GitHub Pages via `app_data_prep/` |
| PDF generation (`plots2pdf.py`) | Low priority; web app is the primary output |
| `fire`-based CLI | ClimateBench2 uses `argparse` consistently |
| Per-recipe Dask cluster config | Over-engineered for current scale |

---

## 6. Collaboration opportunities

- **Upstream the observational bounds** — propose to ICONEval maintainers that
  the bounds data be extracted into a standalone YAML/JSON file (benefiting
  both projects). This could become a shared community resource.
- **Shared ESMValTool diagnostic scripts** — any new diagnostic scripts
  written for ClimateBench2 (e.g., warming-rate trend calculator, ENSO
  spectral scorer) should follow ESMValTool conventions so they can be
  contributed back to ESMValTool or used by ICONEval.
- **Cross-reference in documentation** — acknowledge ICONEval as the source of
  adapted recipes and bounds data.
