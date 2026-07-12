# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project is

ClimateBench v2 defines the **protocol for scoring and testing climate models**
(tiered pass/fail gates + probabilistic scores + leaderboard). It is a **thin
layer on top of [ClimateEval](https://github.com/climate-federation/ClimateEval)**,
which owns all data loading, preprocessing, and generic physical diagnostics.

Two documents govern all work here:

- [docs/climateeval_delineation_plan.md](docs/climateeval_delineation_plan.md) —
  the architecture, the CB2⟷ClimateEval ownership boundary, and the phased
  migration (Phase 0 done: package scaffold).
- [docs/metrics_reference.md](docs/metrics_reference.md) — the authoritative
  spec (inputs, formula, threshold) for every Tier I/II/III check.

**Ownership test:** code that loads/regrids data or is a generic physical
diagnostic belongs in ClimateEval (upstream PR); code that encodes a threshold,
probabilistic score, baseline, tier structure, or the leaderboard belongs here.

## The package: `climatebench2/`

```
climatebench2/
├── diags/               # ClimateEval-compatible Diagnostic subclasses (the protocol)
├── suites/              # CB2 suite YAMLs; may reference climatebench2.diags.* AND climateeval.diags.*
├── thresholds.yml       # EVERY pass/fail bound lives here — never hard-code one in a diagnostic
├── scoring.py           # pure CRPS-ESS / ensemble-consistency / EOF engine (numpy only)
├── physics.py           # pure Tier I physics functions (numpy only)
├── leaderboard/         # .ddb results → scores table (→ static HTML page, Phase 6)
└── _cli.py              # `climatebench2 score` / `climatebench2 leaderboard`
```

Key integration facts (verified against ClimateEval `main`):

- ClimateEval's `Suite` loads any importable `diagnostic:` class path via
  `str_to_object` — CB2 diagnostics need only subclass
  `climateeval.diags._base.Diagnostic`.
- Multi-experiment/ensemble inputs follow the `ECS` `ComplexDiagnostic`
  precedent (`_required_data_keys` + `ComplexDataSource`). CB2 complex
  diagnostics accept a *superset* of their required keys so one experiment
  dict feeds a whole Tier I suite; `Suite.get_database` passes the same data
  object to every diagnostic, so suites are split by data shape (cubes vs
  experiment dict).
- All output goes to ClimateEval's standard DuckDB schema (`raw_output`,
  `metrics`, `variables`, `data_sources` per diagnostic); CB2 scores add
  columns to `metrics`, never a new schema.
- ClimateEval is a **third-party dependency** (DLR; `climate-federation` org),
  pinned by commit in `pyproject.toml`. Never vendor or patch it; contribute
  upstream via PR or keep the code here.

### Commands

```bash
pip install .                       # installs climateeval (pinned) + climatebench2
# dev against a local checkout: pip install -e ../ClimateEval && pip install -e . --no-deps

climatebench2 score /path/to/model/cmor/Amon --name MyModel   # → MyModel_climatebench2/*.ddb
climatebench2 leaderboard MyModel_climatebench2/*.ddb          # scores table
climateeval report MyModel_climatebench2/*.ddb                 # interactive per-model report

# Tests (ClimateEval pixi env + this repo on PYTHONPATH; see tests/README.md)
cd ../ClimateEval && PYTHONPATH=$OLDPWD pixi run --frozen python -m pytest $OLDPWD/tests -q
```

## Paleoclimate pipeline (`paleo_scripts/`)

From the merged `paleo_data` PR (#114) — note this directory is spelled
*correctly* (only `benchmark_scrips/` keeps its intentional typo). Tier III
of the protocol wraps this in Phase 5 of the delineation plan.

```bash
cd paleo_scripts
# Observations (proxy/reanalysis datasets)
python download_paleo_observations.py                        # all datasets
python download_paleo_observations.py --dataset lgmda lig127k
python download_paleo_observations.py --list                 # show all dataset keys
# CMIP6 model data (ESGF-generated wget scripts, named {period}_{variable}.sh)
cd download_model_data && bash lgm_tas.sh && bash lgm_pr.sh

# Processing
python process_paleo_observations.py                         # all observation sources
python process_paleo_models.py --model all --period all      # model monthly climatologies

# Benchmark (spatial RMSE/MAE/CRPS)
python paleo_benchmark.py --model AWI-ESM-1-1-LR --period lgm
python paleo_benchmark.py --model all --period all
python paleo_benchmark.py --model MIROC-ES2L --period lgm --use-picontrol
```

PI reference for anomaly computation: lgmDA Holocene (default) or model
piControl (`--use-picontrol`). Precipitation benchmarks (Bartlein MAP,
Scussolini LIG) require `--use-picontrol` and processed `pr` data.

## Legacy pipeline (being retired — do not extend)

The pre-ClimateEval bespoke code is deleted piecewise as each check reaches
parity (plan §6). Already retired: `model_benchmark.py`, `ecs_benchmark.py`,
`enso_benchmark.py`, `run_benchmark.sh` (Phase 1); `MetricCalculation` +
`SaveResults` (Phase 2). What remains uses a separate conda env:

```bash
conda env create -f env.yml && conda activate backend_env
```

Note: `benchmark_scrips/` uses an intentional typo (not `scripts`).

- `benchmark_scrips/` — remaining Tier I scripts
  (`energy_balance_benchmark.py`, `land_ocean_warming_benchmark.py`,
  `arctic_amplification_benchmark.py`, `bjerknes_benchmark.py`,
  `aerosol_forcing_benchmark.py`, `meridional_heat_transport_benchmark.py`,
  `covariance_benchmark.py`, `itcz_efe_benchmark.py`), all `--model <name>`,
  outputs to `results/<benchmark>/`. Data loading via `DataFinder` in
  `benchmark_utils.py` (local → Pangeo GCS `gs://cmip6/` → ESGF;
  `load_experiment_ds()` for piControl / abrupt-4xCO2 / hist-aer).
- `constants.py` / `utils.py` — variable→frequency map, obs data specs, GCS
  project; `standardize_dims()`, `create_zarr()`.
- `download_scripts/download_observations.py` — obs → zarr
  (`observations/` or `gs://climatebench/observations/`); `clt`/`od550aer` need
  `earthengine authenticate`; CERES needs a manual NetCDF download.
- `app_data_prep/` — notebooks feeding the legacy
  [ClimateBench web app](https://climate-analytics-lab.github.io/ClimateBench_app/index.html).
- `esmvaltool/recipe_pr_rmse.yml` — hand-rolled recipe prototype, superseded by
  the ClimateEval route.

Known legacy bugs (fix only by porting, per plan §6): hard-coded
`np.ones((1980,1))` in `itcz_efe_benchmark.py`; threshold/method deviations
from the paper are itemised in `docs/metrics_reference.md` §"Cross-cutting
discrepancies".
