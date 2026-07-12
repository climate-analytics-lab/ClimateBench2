# ClimateBench2

ClimateBench v2 defines the **protocol for scoring and testing climate models**:
a tiered set of physical-consistency gates (Tier I, pass/fail), probabilistic
scores against post-2015 observations (Tier II), and out-of-sample paleo /
perfect-model tests (Tier III), presented as a leaderboard.

ClimateBench2 is a **thin protocol layer on top of
[ClimateEval](https://github.com/climate-federation/ClimateEval)**. ClimateEval
does all data loading, preprocessing and generic physical diagnostics;
ClimateBench2 owns only what makes it a benchmark — the tier structure, the
thresholds, the probabilistic scoring semantics, the baselines, and the
leaderboard.

- **Architecture & migration plan:** [docs/climateeval_delineation_plan.md](docs/climateeval_delineation_plan.md)
- **Exact spec of every metric/check:** [docs/metrics_reference.md](docs/metrics_reference.md)

## Install

Requires Python ≥ 3.12. ClimateEval is pulled in automatically (pinned by
commit; it is pre-1.0 and not on PyPI):

```bash
pip install .
# or, developing against a local ClimateEval checkout:
pip install -e ../ClimateEval && pip install -e . --no-deps
```

## Usage

```bash
# Score a model: point at CMOR-compliant NetCDF output (file, flat dir, or DRS tree)
climatebench2 score /path/to/model/cmor/Amon --name MyModel
# → MyModel_climatebench2/: one DuckDB results database per suite

# Build the leaderboard from one or more models' results
climatebench2 leaderboard MyModel_climatebench2/*.ddb
```

Per-model interactive reports remain available through ClimateEval:
`climateeval report MyModel_climatebench2/*.ddb`.

## Repository layout

```
climatebench2/           # the installable package
├── diags/               # CB2 protocol diagnostics (plug into ClimateEval suites)
├── suites/              # CB2 suite YAMLs (ClimateEval suite format)
├── thresholds.yml       # single source of truth for every pass/fail bound
├── leaderboard/         # scores table / leaderboard renderer
└── _cli.py              # `climatebench2 score` / `climatebench2 leaderboard`
docs/                    # delineation plan, metrics reference
```

## Status

Phase 0 of the [migration plan](docs/climateeval_delineation_plan.md#6-migration--phased-retire-as-parity):
the package scaffold is in place and `climatebench2 score` runs stock
ClimateEval suites. The CB2 tier suites, the probabilistic scoring engine
(CRPS-with-ESS, ensemble-consistency), and the baselines land in Phases 1–6.

## Legacy code (being retired)

The original bespoke pipeline — `benchmark_scrips/`, `download_scripts/`,
`constants.py`, `utils.py`, `esmvaltool/`, `paleo_scrips/`, `app_data_prep/` —
still works (see `CLAUDE.md` for commands) and is deleted piecewise as each
check reaches parity on the ClimateEval-backed path. Do not add new
functionality there.

```bash
# legacy environment, only needed for the legacy scripts
conda env create -f env.yml
conda activate backend_env
```
