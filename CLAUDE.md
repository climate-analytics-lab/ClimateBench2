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
├── leaderboard/         # .ddb results → scores table (→ static HTML page, Phase 6)
└── _cli.py              # `climatebench2 score` / `climatebench2 leaderboard`
```

Key integration facts (verified against ClimateEval `main`):

- ClimateEval's `Suite` loads any importable `diagnostic:` class path via
  `str_to_object` — CB2 diagnostics need only subclass
  `climateeval.diags._base.Diagnostic`.
- Multi-experiment/ensemble inputs follow the `ECS` `ComplexDiagnostic`
  precedent (`_required_data_keys` + `ComplexDataSource`).
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
```

## Legacy pipeline (being retired — do not extend)

The pre-ClimateEval bespoke code still runs and is deleted piecewise as each
check reaches parity (plan §6). It uses a separate conda env:

```bash
conda env create -f env.yml && conda activate backend_env
```

Note: directory names use intentional typos — `benchmark_scrips/` and
`paleo_scrips/` (not `scripts`).

- `benchmark_scrips/` — Tier I scripts (`ecs_benchmark.py`,
  `energy_balance_benchmark.py`, `land_ocean_warming_benchmark.py`,
  `arctic_amplification_benchmark.py`, `bjerknes_benchmark.py`,
  `aerosol_forcing_benchmark.py`, `meridional_heat_transport_benchmark.py`,
  `covariance_benchmark.py`, `enso_benchmark.py`, `itcz_efe_benchmark.py`) and
  the Tier II deterministic runner `model_benchmark.py` (metrics:
  `zonal_mean_rmse|mae`, `spatial_rmse|mae`, `crps`; `ohc` derived from
  `thetao`+`so`). All take `--model <name>`; outputs go to `results/<benchmark>/`.
  Shared machinery in `benchmark_utils.py` (`DataFinder`, `MetricCalculation`,
  `SaveResults`).
- `constants.py` / `utils.py` — variable→frequency map, obs data specs, GCS
  project; `standardize_dims()`, `create_zarr()`.
- `download_scripts/download_observations.py` — obs → zarr
  (`observations/` or `gs://climatebench/observations/`); `clt`/`od550aer` need
  `earthengine authenticate`; CERES needs a manual NetCDF download.
- `paleo_scrips/` — paleo data cache + tas-only prototype notebook (an open
  `paleo_data` PR builds on it).
- `app_data_prep/` — notebooks feeding the legacy
  [ClimateBench web app](https://climate-analytics-lab.github.io/ClimateBench_app/index.html).
- `esmvaltool/recipe_pr_rmse.yml` — hand-rolled recipe prototype, superseded by
  the ClimateEval route.
- CMIP6 data sources, in `DataFinder` priority order: local →
  Pangeo GCS (`gs://cmip6/`, `pangeo-cmip6.csv`) → ESGF. Historical 1960–2014 +
  `ssp245` 2015–2024 (set in `constants.py`); `load_experiment_ds()` serves
  piControl / abrupt-4xCO2 / hist-aer.

Known legacy bugs (fix only by porting, per plan §6): hard-coded
`np.ones((1980,1))` in `itcz_efe_benchmark.py`; missing `raise` in the CRPS
ensemble-dim guards in `benchmark_utils.py`; threshold/method deviations from
the paper are itemised in `docs/metrics_reference.md` §"Cross-cutting
discrepancies".
