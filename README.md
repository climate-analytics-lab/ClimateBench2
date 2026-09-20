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

# Tier III: the paleo time-slices, scored against the processed proxy NetCDFs
climatebench2 score model/Amon --name MyModel --suite ClimateBench2_TierIII \
    --experiment picontrol=/path/piControl --experiment lgm=/path/lgm \
    --paleo-data-root paleo_scripts/paleo_data_cache/processed/observations

# Tier III.2 perfect model: score against a HELD-OUT ESM run instead of observations
# (every row is labelled window = perfect-model; truth members drive the
# large-ensemble spread test). No truth data is staged yet.
climatebench2 score model/Amon --name MyModel \
    --truth /data/CESM2/ssp245 --truth-member r2i1p1f1=/data/CESM2/r2i1p1f1

# Write the suite databases but defer the Tier II scoring pass
climatebench2 score model/Amon --name MyModel --no-score

# Build the leaderboard (static HTML) from one or more models' results
climatebench2 leaderboard MyModel_climatebench2/*.ddb -o leaderboard.html
# Re-run the Tier II scoring pass over existing databases (idempotent) — also how
# a thresholds.yml change reaches databases that already exist:
climatebench2 leaderboard --rescore MyModel_climatebench2/*.ddb
```

`ClimateBench2_TierI`, `_TierI_variability`, `_TierII_events` and `_TierII` are the
default suites; `_TierII_daily` and `_TierIII` need extra data (`day`-table output and
the paleo experiments respectively), so ask for them with `--suite`.

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

Every row the pass writes carries a **held-out / in-sample** label from
`tier2.window_labels` (paper §5.6): held-out entries are scored against observations
from the reserved post-2015 test period, in-sample ones against the historical record
the models were developed with. The leaderboard badges each column and puts the
held-out ones first.

The same pass also does the other regimes. **Spatial fields** are scored on the
reference's *fixed pre-2015* EOF basis: `ReferenceEOFProjection` writes one
standardised coefficient per (source, variable, mode) and the pass takes the fair CRPS
per coefficient and its equal-weight mean. The **ensemble-consistency test** (regime c)
compares the observed trend with the model's own ensemble, widened by the piControl
internal variability of `InternalVariability` (Tier I suite) and by σ_obs — the
`tier2.obs_sigma` constants plus the measured spread across observational products,
which are told apart from comparison models by `data_sources.category` and never
ranked as if they were models. Because the Tier II suites are cut to the test window,
`ReferenceBaselineRecord` carries the reference's 1985–2014 record into the database so
the Climatology baseline has something to be built from. **Aggregated scalars** — one
number per member rather than a series — are the third shape: the realized warming
level (the protocol's primary test-window statistic), the two GMST trends, the Pinatubo
cooling and the aerosol-era NH−SH trend difference, each scored with fair CRPS against
HadCRUT5 (corrected from its blended land-air/SST basis to a surface-air-temperature
one) and reported as a consistency statement alongside.

The Tier I scorecard is grouped by each gate's `requirement` tag
(`climatebench2/thresholds.yml`): **Required** checks form the entry ticket — a model is
scored only if every applicable one passes — while **Extended** checks are reported for
additional credit and **extra** checks are non-protocol sanity checks. The entry ticket
is ⚠ (incomplete) while a Required check has no result at all, so a missing experiment
can never be mistaken for a pass.

Each suite is given the data shape and time window the protocol asks for, so
there is no single global slice of the submission:

| Suite | Data shape | Window | Per member? |
|---|---|---|---|
| `ClimateBench2_TierI` | experiment dict (`historical` = the submission unless `--experiment historical=DIR`) | every experiment in **full** | no — a gate is a property of the model |
| `ClimateBench2_TierI_variability` | cubes, from the `picontrol` experiment (ENSO wants ≥ 100 yr of control) | full | no |
| `ClimateBench2_TierII` | the model's monthly cubes | the reserved post-2015 test window, `tier2.test_window_start` → last complete year | **yes** |
| `ClimateBench2_TierII_daily` | the model's daily/hourly cubes | **full record** — the paper defines the extremes, PDF and diurnal climatologies over it, so every entry is in-sample | **yes** |
| `ClimateBench2_TierII_events` | the same experiment dict, each run with its own `historical` record — its Tier II scalars are scored across the ensemble | full | **yes** |
| `ClimateBench2_TierIII` | experiment dict (`picontrol` + the paleo slices) | full | no |

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
├── thresholds.yml       # single source of truth for every bound, requirement and tier tag
├── _thresholds.py       # the only reader of the above (`get_threshold("tier1.ecs.range")`)
├── scoring.py           # fair CRPS, ESS + block bootstrap, consistency, EOF, proxy
├── scoring_pass.py      # post-suite Tier II pass: stack members → fair CRPS → skill
├── windows.py           # the protocol's time windows (test / baseline / long trend)
├── physics.py           # pure Tier I physics (numpy only)
├── baselines.py         # climatology pseudo-members, calibrated two-layer EBM
├── data/                # packaged protocol tables (the ERF series behind the EBM)
├── leaderboard/         # .ddb results → static HTML leaderboard
└── _cli.py              # `climatebench2 score` / `climatebench2 leaderboard`
docs/                    # delineation plan, metrics reference
paleo_scripts/           # Tier III data pipeline (download/process/benchmark)
analysis/                # standalone studies behind paper figures — not protocol code
tests/                   # engine + diagnostics tests (see tests/README.md)
```

`analysis/` is exploratory work that predates and informs the protocol; it makes its
own choices (for instance a 1990–2020 anomaly reference) that are **not** the
protocol's. The protocol's own windows live in `climatebench2/windows.py` and
`thresholds.yml`, and nothing under `analysis/` is imported by the package.

## Status

Phases 0–7 of the [migration plan](docs/climateeval_delineation_plan.md#6-migration--phased-retire-as-parity)
are implemented: tier suites, the probabilistic scoring engine, the Tier I
physics gates, baselines, Tier III paleo protocol, and the leaderboard, then
(Phase 7) the 2026-09-14 re-alignment of all of it against the paper draft.
**333 tests pass**, every one of them on synthetic fixtures — but the code has
now met real data: Tier I has run end to end on **CNRM-CM6-1** and Tier II on
**MPI-ESM1-2-LR** against a staged 42-model / 160-member CMIP6 comparison
ensemble, with the 64-model Tier I ensemble in flight. What that cost is the
"Real-data fix" commits of 2026-09-20 and the regression tests beside them; the
numbers, and the protocol questions the runs raised, are under "What has run on
real data" in [docs/metrics_reference.md](docs/metrics_reference.md), and every
provisional constant under "Decisions needed from Duncan" in the same file.
The implementation was re-audited against the 2026-09 paper draft on
2026-09-19 (spec) and 2026-09-20 (code): see the status tables and the
prioritized gap list in
[docs/metrics_reference.md](docs/metrics_reference.md). The scoring-engine core is now on the
2026-09 spec (gap item 3 and its second half, work package 3b): fair CRPS with
the M = 1 rule, stacked ensemble members, observational-uncertainty draws with
a real σ_obs, the moving-block bootstrap, the median-of-per-model `E_ref` with
leave-one-out, reference-EOF fair CRPS for spatial fields, piControl σ_int in
the consistency test, and one label per model across the tiers. **Gap item 6
(work package 6a)** then built the Tier II scalar diagnostics of §II.1: the
realized warming level (the protocol's primary test-window statistic) and the
two GMST trends, the Pinatubo and hemispheric-asymmetry magnitudes as scored
numbers rather than sign flags alone, all four against HadCRUT5 with the GSAT
blending correction, a generic aggregated-scalar regime in the pass,
held-out/in-sample labelling end to end, per-member runs of the Tier II events
suite, and the suite's missing variables (clear-sky TOA, `clwvi`/`clivi`, OHC
0–100 m). **Work package 6b** then added the rest of §II.1: the eight **ETCCDI
extremes** on the ~1° conservative grid (a climatological mean and a decadal
trend per land band), the **Perkins** PDF-overlap skill, the three
**seasonal-cycle** metrics (land annual temperature range; SST–low-cloud
covariance and the seasonal cloud-radiative feedback over the stratocumulus
decks), the **diurnal** first harmonic in local solar time with the phase
scored as (cos, sin), and the **pattern-scaling baseline** — a two-layer EBM
driven by a packaged annual ERF table, one parameter calibrated to the
observed GMST through 2014, given pseudo-members so fair CRPS is defined for
it. The post-2015 multi-member CMIP6 reference `E_ref` needs is no longer an
open item: `climatebench2.data.StagedCMIP6HistoricalSSP245` enumerates a staged
historical+SSP2-4.5 pool (i1p1, any forcing index, the first ten realizations
per model) and yields data sources with the same ids as upstream's generator,
so `E_ref` is a real median of per-model fair CRPS. Headline open items are a
**daily observational product** — no ClimateEval DataSource supplies
`tasmax`/`tasmin`, so the extremes are reported model-only and unscored until
HadEX3 lands upstream — the CMIP6 multi-model-mean warming pattern for the
*spatial* half of pattern scaling, and data for Tier III's perfect-model half.
Every σ_obs
value in `thresholds.yml`, the GSAT blending factor and
the packaged ERF table are provisional and need Duncan's ruling.
Required/Extended/extra tagging of the Tier I gates, declared N/A and the
Required-only entry ticket landed on 2026-09-14 (gap item 2). The same day
(gap item 5) the three re-specced Tier I checks landed: I.5c is now the paper's
pattern-correlation test against HadISST/GPCP, I.3c (precipitation–buoyancy)
exists at last, and I.7 uses the decadal window centred on 2015 with
parallel-piControl-segment drift removal — so Tier I has a diagnostic for every
row of the paper's Table 1. Two of them fetch observations (over 1979–2014,
never the reserved test window); without network access they report the model's
own statistic and write no gate row. I.3c's stored reference slope is now
deliberately left null: the reference column has to be integrated over the
*model's* level set, so no single stored constant can be right for every
submission (52d2e50). ClimateEval is pinned at `b0e941c`, which provides the
land–ocean, Arctic and meridional-heat-transport diagnostics upstream; CB2's
copies have been replaced by thin gate wrappers that add only the protocol's
thresholds. The twelve CB2 upstream PRs (#44–#55) are **merged locally** on the
ClimateEval branch `cb2-integration` (`f8c925b`), which is what the real runs
use, and are **still open upstream**, so the pin is unchanged.

**Work package 7** then finished **Tier III**. The paleo diagnostics read the
`paleo_scripts/` pipeline's own per-dataset NetCDFs — one suite stanza per
(period, dataset, variable) — and compute the protocol's primary statistic:
the **fair CRPS of a block pseudo-ensemble** (the climatological anomalies of
non-overlapping blocks of the equilibrated paleo run, minus the full piControl
climatology) against the proxy values, with the proxy σ as the observational
variance term and an equal-weight mean over sites; the site-consistency
fraction stays beside it as the complementary diagnostic. Paper Appendix D's
distinction is enforced in code: the raw compilations (Tierney 2020,
Bartlein 2011, Otto-Bliesner 2021, Scussolini 2019) are scored, the
data-assimilation products (Cleator 2020) are computed, tagged and excluded,
and a dataset that cannot be scored at all — uncalibrated proxies, speleothem
δ¹⁸O without isotope-enabled output, a superseded compilation — writes the
reason instead of a number. Every gate now also carries its protocol **tier**,
so the scorecard places a check by tier rather than by the suite it runs in.
The **perfect-model** half (III.2) exists as a code path —
`score --truth DIR [--truth-member LABEL=PATH]` swaps the cube suites'
reference for a held-out ESM run, labels the rows `perfect-model` and runs the
large-ensemble spread test — but no CESM2/MPI-ESM/GISS-E2/CESM-LE output is
staged, so it has only ever run on synthetic databases.

## No legacy remnant

As of work package 7 the repository contains no pre-ClimateEval code:
`constants.py`, `utils.py`, `benchmark_scrips/` (`DataFinder`) and `env.yml`
have been deleted. `paleo_scripts/paleo_benchmark.py` now takes a local
`--picontrol-dir DIR` instead of `DataFinder`, and the three general-purpose
helpers the paleo scripts still needed live in `paleo_scripts/paleo_utils.py`.
Everything outside `climatebench2/` is the paleo **data pipeline** — download
and processing for the Tier III proxy targets — not protocol code.
