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
  migration (**Phases 0–7 done**; Phase 7 is the 2026-09-14 protocol
  re-alignment). §7 lists the twelve open upstream PRs (#44–#55, none merged).
  Read its §9 "definition of done" before claiming anything is finished.
- [docs/metrics_reference.md](docs/metrics_reference.md) — the authoritative
  spec (inputs, formula, threshold) for every Tier I/II/III check. **The paper
  is the truth**: fix a disagreement there, never by diverging in code. Its
  "Decisions needed from Duncan" section is where every ⚠ / `TODO(Duncan)`
  lives — add to it rather than inventing a value.

**Current state (2026-09-14): 314 tests pass, and nothing has been
run on real model or observational data.** Every test fixture is synthetic. Do
not describe a diagnostic as "working" on that evidence.

**Ownership test:** code that loads/regrids data or is a generic physical
diagnostic belongs in ClimateEval (upstream PR); code that encodes a threshold,
probabilistic score, baseline, tier structure, or the leaderboard belongs here.

## The package: `climatebench2/`

```
climatebench2/
├── diags/               # ClimateEval-compatible Diagnostic subclasses (the protocol)
├── suites/              # CB2 suite YAMLs; may reference climatebench2.diags.* AND climateeval.diags.*
├── thresholds.yml       # EVERY pass/fail bound + each gate's `requirement:` tag
│                        #   (required/extended/extra/diagnostic) and `tier:` — never hard-code one
├── _thresholds.py       # get_threshold("tier1.ecs.range") — the only reader of the above
├── scoring.py           # pure fair-CRPS / bootstrap / consistency / EOF engine (numpy only)
├── scoring_pass.py      # post-suite Tier II pass: stack members → fair CRPS → skill
├── windows.py           # the protocol's time windows (test / 1985-2014 baseline / 1950-)
├── physics.py           # pure Tier I physics + the ETCCDI indices (numpy only)
├── baselines.py         # climatology pseudo-members, the calibrated two-layer EBM
├── data/                # packaged protocol tables (the ERF series behind the EBM)
├── leaderboard/         # .ddb results → scores table → static HTML page
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
- `_cli.SuiteSpec` says, per suite, which data shape and window it gets and
  whether it runs **once per ensemble member** (`per_member`): the cube
  suites and `ClimateBench2_TierII_events` do, Tier I and Tier III do not.
  A per-member experiment suite gets that member's own record as
  `historical`, which is what the Tier II aggregated scalars need.
- All output goes to ClimateEval's standard DuckDB schema (`raw_output`,
  `metrics`, `variables`, `data_sources` per diagnostic); CB2 scores add
  columns to `metrics`, never a new schema. `scoring_pass` recognises three
  `raw_output` shapes — a **time series** (regime a), an **EOF-coefficient**
  table (regime b) and **aggregated scalars** with no time axis (§II.1) —
  and every row it writes carries a `held-out` / `in-sample` / `perfect-model`
  `window` label (`tier2.window_labels`; `perfect-model` whenever the
  reference's `data_sources.category` is `truth`). Tier III's paleo rows are
  written by the diagnostic itself in the same column vocabulary, tagged
  `scorer = climatebench2.tier3` so `--rescore` does not delete them, and
  every **gate** row carries its protocol `tier` (I/II/III) as well as its
  `requirement`, which is what the leaderboard groups by. A CB2 **`ScalarTableDiagnostic`**
  (`diags/tier2_daily.py`) is how a *simple* diagnostic writes that third
  shape, so the suite's own `reference_data:` supplies the observed value.
  A **skill** score that is not an error — the Perkins PDF overlap — is
  written as a metric instead and never enters `E_ref`.
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
climatebench2 score MODEL --experiment picontrol=DIR --member r1i1p1f1=DIR --member r2i1p1f1=DIR
#   per-suite data paths (_cli.SUITE_REGISTRY): experiments load in FULL for the
#   complex suites, the variability suite takes piControl, the monthly Tier II suite
#   takes the post-2015 test window (tier2.test_window_start) once per ensemble
#   member, and TierII_daily takes the FULL record (its extremes/PDF/diurnal
#   climatologies are defined over it, so every entry there is in-sample)
climatebench2 score MODEL --experiment lgm=DIR --experiment picontrol=DIR \
    --paleo-data-root paleo_scripts/paleo_data_cache/processed/observations
#   Tier III: the paleo slices vs the pipeline's processed proxy NetCDFs
climatebench2 score MODEL --truth /data/CESM2/ssp245 --truth-member r2i1p1f1=DIR
#   Tier III.2 perfect model: the cube suites score against a HELD-OUT ESM run
#   instead of observations (window = perfect-model); truth members drive the
#   large-ensemble spread test. No truth data is staged yet.
climatebench2 score MODEL --no-score      # suites only; run the Tier II pass later
climatebench2 leaderboard MyModel_climatebench2/*.ddb          # scorecard (HTML)
climatebench2 leaderboard --rescore MyModel_climatebench2/*.ddb  # re-run the Tier II pass
#   --rescore is also how a thresholds.yml change reaches existing databases; the
#   pass is idempotent (it deletes its own `scorer` rows before rewriting them)
climateeval report MyModel_climatebench2/*.ddb                 # interactive per-model report

# Tests (ClimateEval pixi env + this repo on PYTHONPATH; see tests/README.md)
cd ../ClimateEval && PYTHONPATH=$OLDPWD pixi run --frozen python -m pytest $OLDPWD/tests -q
```

## Paleoclimate pipeline (`paleo_scripts/`)

From the merged `paleo_data` PR (#114). This pipeline is **data preparation,
not protocol**: it downloads and processes the proxy compilations of paper
Appendix D, and `climatebench2/diags/tier3_paleo.py::PaleoProxyScore` scores
the model against its output (one suite stanza per period/dataset/variable,
reading `paleo_data_cache/processed/observations/<period>/<dataset>.nc`).

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
python paleo_benchmark.py --model MIROC-ES2L --period lgm \
    --picontrol-dir /data/MIROC-ES2L/piControl
```

PI reference for anomaly computation: lgmDA Holocene (default) or the model's
own piControl (`--picontrol-dir DIR`, a local directory or CMOR/DRS tree read
with plain xarray). Precipitation benchmarks (Bartlein MAP, Scussolini LIG)
require `--picontrol-dir` and processed `pr` data.

## No legacy remnant (WP7, 2026-09-14)

The bespoke pipeline was retired piecewise across migration Phases 1–5 (every
deletion is one phase commit; see `git log`), and work package 7 removed the
last of it: `constants.py`, `utils.py`, `benchmark_scrips/` (`DataFinder`:
local → Pangeo GCS → ESGF) and `env.yml` are **deleted**, because
`paleo_benchmark.py` takes `--picontrol-dir DIR` instead of `DataFinder` and
the three helpers the paleo scripts still used moved to
`paleo_scripts/paleo_utils.py`. There is no legacy conda environment any
more; everything runs in the ClimateEval pixi env (see `tests/README.md`).
Nothing outside `climatebench2/` and `paleo_scripts/` should reappear.
