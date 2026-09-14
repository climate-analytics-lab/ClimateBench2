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

# Several ensemble members (auto-discovered from a DRS tree, or named explicitly):
climatebench2 score model/Amon --name MyModel \
    --member r1i1p1f1=/path/r1i1p1f1 --member r2i1p1f1=/path/r2i1p1f1

# A test the submission cannot meet by construction (e.g. an emulator with no
# dynamics) is declared, not silently skipped — it is recorded as n/a:
climatebench2 score emulator_output --name MyEmulator \
    --not-applicable geostrophic_balance

# Build the leaderboard (static HTML) from one or more models' results
climatebench2 leaderboard MyModel_climatebench2/*.ddb -o leaderboard.html
# Re-run the Tier II scoring pass over existing databases (idempotent):
climatebench2 leaderboard --rescore MyModel_climatebench2/*.ddb
```

**Tier II scoring is a pass over the finished databases, not a diagnostic.**
Ensemble members are ingested as separate data sources, so a model's fair CRPS
can only be formed once every member has run: `score` therefore runs
`climatebench2.scoring_pass` after the suites (`--no-score` skips it,
`leaderboard --rescore` re-runs it). The pass groups the raw series by model
*name* — stripping the variant via the `data_sources` table — scores each
model's stacked ensemble with the **fair (Ferro) CRPS**, adds an
ESS-corrected standard error and a moving-block-bootstrap interval, and writes
the headline skill `S = 1 − E/E_ref` with `E_ref` the **median** fair CRPS
across the CMIP6 reference models, leaving out any comparison model of the
submission's own name. A single-member submission is reported as
`n/a (single member)`: fair CRPS is undefined for a deterministic forecast.
Rows are appended to each diagnostic's own `metrics` table with
`scorer = 'climatebench2'`, and re-running replaces them.

The same pass also does the other two regimes. **Spatial fields** are scored on the
reference's *fixed pre-2015* EOF basis: `ReferenceEOFProjection` writes one
standardised coefficient per (source, variable, mode) and the pass takes the fair CRPS
per coefficient and its equal-weight mean. The **ensemble-consistency test** (regime c)
compares the observed trend with the model's own ensemble, widened by the piControl
internal variability of `InternalVariability` (Tier I suite) and by σ_obs — the
`tier2.obs_sigma` constants plus the measured spread across observational products,
which are told apart from comparison models by `data_sources.category` and never
ranked as if they were models. Because the Tier II suites are cut to the test window,
`ReferenceBaselineRecord` carries the reference's 1985–2014 record into the database so
the Climatology baseline has something to be built from.

The Tier I scorecard is grouped by each gate's `requirement` tag
(`climatebench2/thresholds.yml`): **Required** checks form the entry ticket — a model is
scored only if every applicable one passes — while **Extended** checks are reported for
additional credit and **extra** checks are non-protocol sanity checks. The entry ticket
is ⚠ (incomplete) while a Required check has no result at all, so a missing experiment
can never be mistaken for a pass.

Each suite is given the data shape and time window the protocol asks for, so
there is no single global slice of the submission:

| Suite | Gets | Window |
|---|---|---|
| `ClimateBench2_TierI`, `_TierII_events`, `_TierIII` | an experiment dict (`historical` = the submission unless `--experiment historical=DIR`) | every experiment in **full** |
| `ClimateBench2_TierI_variability` | the `picontrol` experiment (ENSO wants ≥ 100 yr of control) | full |
| `ClimateBench2_TierII`, `_TierII_daily` | the model's cubes, once per ensemble member | the reserved post-2015 test window, `tier2.test_window_start` → last complete year |

`--timerange` overrides the window of the cube-based suites only. Note that
ClimateEval's CMIP6 comparison generator is still hard-wired to 1979–2014 and
`r1i1p1f1`, so the CMIP6 comparison rows stay empty over the test window until an
SSP2-4.5 generator lands upstream — `score` warns about this rather than failing.

Per-model interactive reports remain available through ClimateEval:
`climateeval report MyModel_climatebench2/*.ddb`.

## Repository layout

```
climatebench2/           # the installable package
├── diags/               # CB2 protocol diagnostics (plug into ClimateEval suites)
├── suites/              # CB2 suite YAMLs — Tier I/II/III (see suites/README.md)
├── thresholds.yml       # single source of truth for every pass/fail bound
├── scoring.py           # fair CRPS, ESS + block bootstrap, consistency, EOF, proxy
├── scoring_pass.py      # post-suite Tier II pass: stack members → fair CRPS → skill
├── windows.py           # the protocol's time windows (test / baseline / long trend)
├── physics.py           # pure Tier I physics (numpy only)
├── baselines.py         # climatology pseudo-members, two-layer EBM × pattern scaling
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
[docs/metrics_reference.md](docs/metrics_reference.md). The scoring-engine core is now on the
2026-09 spec (gap item 3 and its second half, work package 3b): fair CRPS with
the M = 1 rule, stacked ensemble members, observational-uncertainty draws with
a real σ_obs, the moving-block bootstrap, the median-of-per-model `E_ref` with
leave-one-out, reference-EOF fair CRPS for spatial fields, piControl σ_int in
the consistency test, and one label per model across the tiers. Headline open
items are a post-2015 multi-member CMIP6 reference in ClimateEval (without
which `E_ref` has nothing to average and the Tier II cells fall back to the raw
CRPS), the realized-warming-level statistic, the pattern-scaling baseline, and
wiring Tier III to the paleo pipeline's NetCDF outputs. Every σ_obs value in
`thresholds.yml` is provisional and needs Duncan's ruling.
Required/Extended/extra tagging of the Tier I gates, declared N/A and the
Required-only entry ticket landed on 2026-09-14 (gap item 2). ClimateEval is pinned at `b0e941c`, which provides the
land–ocean, Arctic and meridional-heat-transport diagnostics upstream; CB2's
copies have been replaced by thin gate wrappers that add only the protocol's
thresholds.

## Legacy remnant

`constants.py`, `utils.py` and `benchmark_scrips/benchmark_utils.py`
(`DataFinder`) remain only because `paleo_scripts/paleo_benchmark.py
--use-picontrol` imports them; they retire together once the paleo pipeline
loads piControl via ClimateEval. Do not add new functionality there.
