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
├── thresholds.yml       # EVERY pass/fail bound + each gate's `requirement:` tag
│                        #   (required/extended/extra/diagnostic) — never hard-code one
├── scoring.py           # pure CRPS-ESS / ensemble-consistency / EOF engine (numpy only)
├── physics.py           # pure Tier I physics functions (numpy only)
├── leaderboard/         # .ddb results → scores table (→ static HTML page, Phase 6)
└── _cli.py              # `climatebench2 score` / `climatebench2 leaderboard`
```

Key integration facts (verified against ClimateEval `main`):

- ClimateEval's `Suite` loads any importable `diagnostic:` class path via
  `str_to_object` — CB2 diagnostics need only subclass
  `climateeval.diags._base.Diagnostic`.
- Where ClimateEval already computes the quantity (ECS, land–ocean warming
  ratio, Arctic amplification, meridional heat transport), the CB2 gate is a
  **thin wrapper subclassing the upstream diagnostic** that only feeds
  `thresholds.yml` constants into its kwargs and gates its output columns —
  never a second copy of the physics.
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
climatebench2 score MODEL --name MyEmulator --not-applicable geostrophic_balance
#   declare a Tier I gate inapplicable: recorded as n/a, not a fail (paper §7.1)
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

## Legacy remnant (do not extend)

The bespoke pipeline was retired piecewise across migration Phases 1–5
(every deletion is one phase commit; see `git log`). The only survivors are
`constants.py`, `utils.py` and `benchmark_scrips/benchmark_utils.py`
(`DataFinder`: local → Pangeo GCS `gs://cmip6/` → ESGF), kept solely because
`paleo_scripts/paleo_benchmark.py --use-picontrol` imports them (they need
the legacy conda env: `conda env create -f env.yml`). Retire all three once
the paleo pipeline loads piControl via ClimateEval. Note the intentional
typo: `benchmark_scrips/`.
