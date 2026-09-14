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
# Tier I gates need the auxiliary experiments:
climatebench2 score model/Amon --name MyModel \
    --experiment picontrol=/path/piControl --experiment 4xco2=/path/abrupt-4xCO2 \
    --experiment histaer=/path/hist-aer
# → MyModel_climatebench2/: one DuckDB results database per suite

# Build the leaderboard (static HTML) from one or more models' results
climatebench2 leaderboard MyModel_climatebench2/*.ddb -o leaderboard.html
```

Per-model interactive reports remain available through ClimateEval:
`climateeval report MyModel_climatebench2/*.ddb`.

## Repository layout

```
climatebench2/           # the installable package
├── diags/               # CB2 protocol diagnostics (plug into ClimateEval suites)
├── suites/              # CB2 suite YAMLs — Tier I/II/III (see suites/README.md)
├── thresholds.yml       # single source of truth for every pass/fail bound
├── scoring.py           # CRPS-ESS, ensemble-consistency, EOF, proxy, LE-spread engine
├── physics.py           # pure Tier I physics (numpy only)
├── baselines.py         # climatology persistence, two-layer EBM × pattern scaling
├── leaderboard/         # .ddb results → static HTML leaderboard
└── _cli.py              # `climatebench2 score` / `climatebench2 leaderboard`
docs/                    # delineation plan, metrics reference
paleo_scripts/           # Tier III data pipeline (download/process/benchmark)
tests/                   # engine + diagnostics tests (see tests/README.md)
```

## Status

Phases 0–6 of the [migration plan](docs/climateeval_delineation_plan.md#6-migration--phased-retire-as-parity)
are implemented: tier suites, the probabilistic scoring engine, the Tier I
physics gates, baselines, Tier III paleo protocol, and the leaderboard.
The implementation was re-audited against the 2026-09 paper draft on
2026-09-14: see the status tables and the prioritized gap list in
[docs/metrics_reference.md](docs/metrics_reference.md). Headline open items
are re-aligning the scoring engine to fair CRPS, multi-member ingestion, a
post-2015 multi-member CMIP6 reference in ClimateEval, Required/Extended/N-A
tagging of the Tier I gates, and wiring Tier III to the paleo pipeline's
NetCDF outputs. ClimateEval is pinned at `b0e941c`, which provides the
land–ocean, Arctic and meridional-heat-transport diagnostics upstream; CB2's
copies have been replaced by thin gate wrappers that add only the protocol's
thresholds.

## Legacy remnant

`constants.py`, `utils.py` and `benchmark_scrips/benchmark_utils.py`
(`DataFinder`) remain only because `paleo_scripts/paleo_benchmark.py
--use-picontrol` imports them; they retire together once the paleo pipeline
loads piControl via ClimateEval. Do not add new functionality there.
