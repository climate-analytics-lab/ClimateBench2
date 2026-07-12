# ClimateBench2 ⟷ ClimateEval — Delineation Plan

**Purpose.** Turn ClimateBench2 (CB2) into a *thin protocol layer* that runs on top of
[ClimateEval](https://github.com/climate-federation/ClimateEval), so CB2 owns only the
scientific protocol (which tests, which thresholds, how to score) and a leaderboard —
not the data-loading / preprocessing / diagnostic-computation machinery. The goal is to
**minimise the code CB2 must maintain into the future**.

This supersedes the ICONEval integration plan (`iconeval_integration_plan.md`, removed
2026-07-12 — see git history): the old plan was to port ICONEval *recipes* into a
hand-rolled ESMValTool runner inside CB2.
ClimateEval (built by the same DLR/Eyring group, derived from ICONEval) is now a
nearly-complete, pip-installable framework that already does that job, so CB2 depends on
it rather than re-implementing it.

**Authoritative protocol reference.** [`metrics_reference.md`](metrics_reference.md) —
the exact spec (inputs, preprocessing, formula, threshold/score) for every Tier I/II/III
diagnostic. That doc defines *what* CB2 must produce; this doc defines *where each piece
lives* and *how CB2 calls ClimateEval* to produce it.

---

## 1. Decisions taken (2026-07-12)

| Decision | Choice | Consequence |
|---|---|---|
| Where the scoring layer lives (pass/fail thresholds, CRPS-ESS, ensemble-consistency, baselines) | **CB2 custom diagnostics (plug-in)** | CB2 ships `Diagnostic` subclasses that plug into ClimateEval's suite/DataSource/report framework by class-path reference. CB2 owns the protocol; ClimateEval does all I/O + preprocessing. |
| Leaderboard presentation | **New thin CB2 leaderboard** | A minimal standalone page generated from the scores table — not ClimateEval's report, not the legacy `ClimateBench_app`. |
| Fate of bespoke `benchmark_scrips/` | **Retire as ClimateEval reaches parity** | Each bespoke script is deleted only once a CB2-diagnostic-on-ClimateEval covers it. No coverage gap. |
| Relationship to ClimateEval | **Third-party dependency** (authors: M. Schlund, A. Paçal; `climate-federation` org — not us) | CB2 consumes it via pixi/pip and contributes via PRs. CB2 must **not** assume it can refactor ClimateEval internals; anything CB2-specific stays in CB2 unless upstream accepts it. |

---

## 2. Ownership boundary

**ClimateEval owns (CB2 never re-implements):**
- Data sources & auto-download — `ERA5*`, `GPCP`, `CERESEBAF`, `HadCRUT5`, `HadISST`,
  `ESACCISST`, `NOAAERSSTv5`, `ORAS5`, `EN4`, `WOA`, `IAP`, `OSI450NH/SH`, `NSIDC…`,
  `CMIP6Historical/Abrupt4xCO2/PiControl…`, plus generic ESMValTool intake/CMORizer.
- Preprocessing — unit conversion, regridding, longitude normalisation, time-range
  extraction, level extraction, land/sea + AR6-region masking (ESMValCore).
- The `Suite` runner, DuckDB/Ibis output schema, and the base `Diagnostic` framework
  (`SimpleDiagnostic`, `ComplexDiagnostic`, `ComplexDataSource`, `DiagnosticOutput`).
- Deterministic metrics (`weighted_rmse`, `weighted_pearsonr`, `weighted_emd`) and the
  library of physical diagnostics (`Map`, `AnnualCycle`, `Nino34`, `ECS`,
  `OceanHeatContentTimeSeries`, `SeaIceArea*`, `AMOCTimeSeries`, `Hovmoller`, `QBO`,
  `DiurnalCycle`, `Histogram`, `TEMDiagnostic`, …).

**CB2 owns (the protocol):**
- **The protocol definition** — which diagnostics constitute Tier I/II/III, in what
  configuration, against which references, with which thresholds. Encoded as CB2 suite
  YAMLs + a thresholds/config file.
- **The scoring semantics ClimateEval lacks**, implemented as ClimateEval-compatible
  `Diagnostic` subclasses (§4):
  - Tier I **pass/fail** wrappers (turn a computed scalar into a binary against a paper
    threshold).
  - Tier II **CRPS with effective-sample-size (autocorrelation) correction** (regime a).
  - Tier II **ensemble-consistency test** (regime b): piControl-chunk internal variance +
    obs-error quadrature + EOF projection + two-sided *p*<0.05.
  - The three **baselines** (1990–2020 climatology persistence; 2-layer-EBM × CMIP6-MMM
    pattern scaling; CMIP6 MME) as pseudo-"model" submissions run through the same suites.
  - Physics ClimateEval has no diagnostic for but which are computable from its
    DataSources (land–ocean warming ratio, Arctic amplification, aerosol hist-aer ERF,
    meridional heat transport partitioning, ITCZ–EFE, geostrophic balance, MJO WK ratio,
    amip-4xCO2 ERF, GFMIP Δλ).
  - Tier III paleo proxy-aware scoring + mid-Holocene monsoon check, and the
    perfect-model / large-ensemble-spread suite.
- **The leaderboard** and the CB2 web presentation.
- **The paper / protocol governance.**

**One-line test for "does this belong in CB2?":** if it loads or regrids data, or is a
generic physical diagnostic → ClimateEval. If it encodes a threshold, a probabilistic
score, a baseline, a tier structure, or the leaderboard → CB2.

---

## 3. Integration mechanism (verified)

CB2 becomes an installable package `climatebench2` that **depends on** `climateeval` in
the same environment. The wiring, all confirmed against ClimateEval `main`:

1. **Custom diagnostics load by class path.** `Suite._get_diagnostics`
   (`suites/_base.py`) resolves the YAML `diagnostic:` string via
   `str_to_object` → `importlib.import_module` (`_utils.py:152`). It accepts **any**
   importable dotted path, requiring only `issubclass(cls, Diagnostic)`. So a CB2 suite
   can say `diagnostic: climatebench2.diags.EnsembleConsistency` and ClimateEval runs it.
2. **Auxiliary experiments / ensembles are a supported pattern.** The `ECS`
   `ComplexDiagnostic` declares `_required_data_keys = ("4xco2", "picontrol")` and pulls
   `CMIP6Abrupt4xCO2R1I1P1F1` + `CMIP6PiControlR1I1P1F1` via `ComplexDataSource`, emitting
   scalar `fx` outputs (`ecs`, `lambda`, `p_value`, …). This is exactly the shape CB2's
   pass/fail and ensemble-consistency diagnostics need (piControl chunks, multiple
   members, a4x/hist-aer). CB2 subclasses the same bases — **no bespoke data loading.**
3. **Output is uniform.** Every CB2 diagnostic writes to the standard DuckDB schema
   (`raw_output`, `metrics`, `variables`, `data_sources`). CB2's leaderboard reads that
   one schema regardless of which diagnostic produced a score.
4. **Run path.** CB2 exposes `climatebench2 score <model_dir>` (thin CLI) →
   `Suite("ClimateBench2_TierI", …).get_database(...)` for each tier → one `.ddb` →
   CB2 leaderboard renderer. No ClimateEval source is modified.

---

## 4. Target CB2 repository layout

```
climatebench2/                 # NEW: the installable package (was loose scripts)
├── diags/                     # CB2 Diagnostic subclasses (plug into ClimateEval)
│   ├── _scoring.py            #   CRPS-ESS + ensemble-consistency primitives (the crux)
│   ├── pass_fail.py           #   Tier-I threshold wrappers
│   ├── tier1_physics.py       #   land-ocean, arctic, aerosol ERF, MHT, ITCZ, geostrophic, MJO, ERF
│   ├── tier2_scores.py        #   probabilistic scoring diagnostics (regime a/b)
│   ├── baselines.py           #   climatology / EBM-pattern-scaling / MME
│   └── tier3_paleo.py         #   proxy-aware scoring + mid-Holocene monsoon
├── suites/                    # CB2-owned suite YAMLs (reference climatebench2.diags.* + climateeval.diags.*)
│   ├── ClimateBench2_TierI.yml
│   ├── ClimateBench2_TierII.yml
│   └── ClimateBench2_TierIII.yml
├── thresholds.yml             # single source of truth for every pass/fail bound (from metrics_reference.md)
├── leaderboard/               # thin renderer: .ddb -> scores table -> static HTML page
└── _cli.py                    # `climatebench2 score <model>`  /  `climatebench2 leaderboard <ddb...>`
pyproject.toml                 # depends on climateeval; entry point climatebench2 = climatebench2._cli:main
docs/                          # this plan, metrics_reference.md, paper
archive/                       # legacy bespoke code, retired per §6 (git-tracked until deleted)
```

Everything under `benchmark_scrips/`, `download_scripts/`, `constants.py`, `utils.py`,
`esmvaltool/` is legacy and shrinks to zero as §6 proceeds.

---

## 5. Protocol → provider map

From [`metrics_reference.md`](metrics_reference.md). "CE" = ClimateEval already provides
the physical diagnostic (CB2 adds only scoring config/threshold); "CB2-diag" = new CB2
`Diagnostic` subclass built on ClimateEval DataSources; "CB2-engine" = needs the §4
scoring primitives.

### Tier I (pass/fail entry ticket)
| Check | ClimateEval has | CB2 builds |
|---|---|---|
| I.1 Energy balance (piControl) | `Tier1_sanity_checks` (flux ranges) | pass/fail wrapper: \|μ(N)\|<0.1, drift of 10-yr mean <0.02 |
| I.2 Closure (water / atm energy) | `Tier1_consistency_checks` | absolute-bound pass/fail wrappers |
| I.3a Clear-sky LW β | — (has CERES + tas) | CB2-diag: gridpoint ∂rlutcs/∂Ts, ±25% of 2.2 |
| I.3b Geostrophic balance | — (needs daily ua/zg) | CB2-diag (daily data path) |
| I.3c Precip–buoyancy | — | CB2-diag: P′ vs ⟨MSE⟩′, ±30% of obs |
| I.4a GFMIP patch Δλ | — (non-CMIP exp) | CB2-diag + submission data path |
| I.4b amip-4xCO2 ERF | — | CB2-diag |
| I.5a–c ENSO | `Nino34` diagnostic | CB2-diag: σ, band-power ratio, teleconnection regressions |
| I.5d MJO WK ratio | `Tier3_dynamics` (Hovmöller/MJO, daily pr) | CB2-diag: east/west power ratio |
| I.6a Land–ocean ratio | — (a4x data path via ECS exists) | CB2-diag |
| I.6b Arctic amplification | — (a4x) | CB2-diag |
| I.6c ECS ∈ [1,7] | **`Tier3_ecs` / `ECS`** (emits ecs, p_value) | pass/fail wrapper only (near-free) |
| I.7 Aerosol hist-aer ERF | — (hist-aer) | CB2-diag |
| I.8a MHT partitioning | — | CB2-diag |
| I.8b ITCZ–EFE | — | CB2-diag |

### Tier II (probabilistic scoring vs post-2015 obs)
| Family | ClimateEval has | CB2 builds |
|---|---|---|
| Mean-state tas/pr/TOA/clouds | `Tier2_atmosphere_monthly` (Map/AnnualCycle/ZonalLine + ERA5/GPCP/CERES) | **CB2-engine** scoring on top (regime a CRPS-ESS / regime b consistency) |
| SST/salinity/OHC/AMOC/Niño | `Tier2_ocean_monthly`, `OceanHeatContentTimeSeries` | CB2-engine scoring |
| Sea ice extent/min/trend | `Tier2_sea_ice_monthly` | CB2-engine (regime b) |
| Diurnal cycle, pr intensity PDF | `Tier3_atmosphere_subdaily` (`DiurnalCycle`, `Histogram`) | CB2-engine scoring |
| tas daily extremes | — (needs daily tasmax/tasmin) | CB2-diag + engine |
| GMST trend, Pinatubo, hemispheric asymmetry, seasonal-cycle triplet | partial (timeseries) | CB2-diag + engine (regime b) |
| Baselines (climatology / EBM×MMM / MME) | — | CB2 baselines (run through the same suites) |
| CRPS-ESS + ensemble-consistency + EOF | — (deterministic only) | **CB2-engine — the blocking core build** |

### Tier III (paleo + perfect-model)
| Item | ClimateEval has | CB2 builds |
|---|---|---|
| lig127k / lgm / midHolocene vs proxies | — | CB2-diag (proxy-aware, reuses CB2-engine regime b) |
| mid-Holocene N-Africa JJAS monsoon | — | small CB2-diag |
| Perfect-model (CESM2 train→SSP245) | — | CB2 suite reusing Tier II engine |
| Large-ensemble spread vs CESM-LE | — | CB2-diag (variance ratio + pattern corr) |

**Blocking dependency:** the CB2-engine (CRPS-ESS + ensemble-consistency) gates every
Tier II/III aggregated score. Build it first (§6 Phase 2).

---

## 6. Migration — phased, retire-as-parity

Each phase ends with an explicit **delete** so the legacy surface only shrinks.

**Phase 0 — Scaffold (no science).** Create the `climatebench2` package + `pyproject.toml`
depending on `climateeval`; stand up an empty `diags/`, `suites/`, `thresholds.yml`,
`_cli.py`. Get `climatebench2 score` to run a *stock* ClimateEval `Tier2_atmosphere_monthly`
end-to-end on one model and emit a `.ddb`. *Deletes: nothing yet.*

**Phase 1 — Wrap the overlap (cheap wins).** CB2 suites reference existing ClimateEval
diagnostics for everything already covered: ECS (+[1,7] pass wrapper), Niño-3.4, mean-state
Tier II families, sea ice, diurnal/histogram. Populate `thresholds.yml` from
`metrics_reference.md`. *Deletes: `ecs_benchmark.py`, `enso_benchmark.py`, and the
`model_benchmark.py` deterministic path once the Tier II suite reproduces them.*

**Phase 2 — Build the scoring engine (blocking core).** Implement `diags/_scoring.py`:
CRPS-with-ESS and the ensemble-consistency test (piControl-chunk σ + obs-error quadrature +
EOF projection, two-sided p<0.05) as `ComplexDiagnostic`s. Wire them over the Phase-1
mean-state suites. This is the single most valuable new build; nothing in CB2 or ClimateEval
provides it. *Deletes: raw-CRPS paths in `benchmark_utils.py`.*

**Phase 3 — Port bespoke Tier I physics to CB2-diags.** Reimplement land–ocean, Arctic,
aerosol ERF, MHT, ITCZ–EFE (fixing the hard-coded `np.ones((1980,1))` bug), Bjerknes as
`ComplexDiagnostic`s on ClimateEval's a4x/piControl/hist-aer DataSources — align thresholds
to the paper as you port. *Deletes each `*_benchmark.py` as its CB2-diag lands and matches.*

**Phase 4 — New Tier I/II diagnostics (daily + causal).** Geostrophic balance, MJO WK,
amip-4xCO2 ERF, GFMIP Δλ, tas extremes, pr PDF, GMST trends, Pinatubo, hemispheric
asymmetry, seasonal-cycle triplet, and the three baselines. Requires daily-data variables
(ClimateEval's subdaily suite shows the path). *Deletes: `constants.py`/`utils.py`/
`download_scripts/` once nothing imports them.*

**Phase 5 — Tier III.** Proxy-aware paleo scoring + mid-Holocene monsoon check
(coordinate with the open `paleo_data` branch — don't duplicate its tas-only work); then
the perfect-model + large-ensemble-spread suite. *Deletes: `paleo_scrips/` bespoke loaders
once ClimateEval CMORizer DataSources cover the paleo experiments; retire
`app_data_prep/` + `esmvaltool/recipe_pr_rmse.yml` + `_to_delete_git_litter/`.*

**Phase 6 — Leaderboard + docs.** `leaderboard/` renderer (`.ddb` → tiered scores table →
static HTML: Tier I gate pass/fail, Tier II/III scores vs the three baselines). Rewrite
`README.md`/`CLAUDE.md` to the thin-wrapper reality. *Deletes: anything left in the repo
root that predates the package.*

---

## 7. Upstream-contribution track (optional, further shrinks CB2)

Offer to ClimateEval as PRs (they built ICONEval and welcome ESMValTool-idiomatic
diagnostics). If accepted, CB2 drops the code and just references the class path:
- Generic physical diagnostics with no CB2-specific threshold — MHT partitioning,
  ITCZ–EFE, geostrophic balance, MJO WK ratio, land–ocean & Arctic ratios. These are
  reusable evaluation diagnostics, not protocol.
- **Keep in CB2 regardless** (protocol/opinion, unlikely to be upstream-appropriate):
  the pass/fail thresholds, the CRPS-ESS + ensemble-consistency *scoring* semantics, the
  baselines, the tier structure, the leaderboard. `metrics_reference.md` §"ICONEval is
  deterministic only" already flags that probabilistic scoring stays bespoke.

Decouple this track from the migration: CB2 works whether or not any PR merges.

---

## 8. Risks & open items

1. **Ensemble access in ClimateEval's data model.** CB2-engine regime (b) needs *many*
   members + piControl chunks in one diagnostic. `ComplexDataSource` + `_required_data_keys`
   supports auxiliary experiments (ECS precedent), but confirm it can deliver an
   *N-member ensemble* as a single input before committing Phase 2's design. *First
   spike.*
2. **DuckDB schema for probabilistic scores.** The current schema is metric-per-row
   (rmse/pearson/emd). CB2 scores add *score + p-value + pass-flag + baseline-relative +
   provenance*. Extend via extra columns in CB2 diagnostics' `metrics` table (no
   ClimateEval change) and teach the CB2 leaderboard to read them.
3. **Daily / non-CMIP data paths.** Geostrophic balance, MJO, extremes, pr PDF need
   `day`-table data; GFMIP/perfect-model need submission-provided non-archive output.
   ClimateEval's subdaily suite + CMORizer DataSource are the templates; validate early.
4. **Version pinning.** Pin `climateeval` (it's `0.0.1`, pre-1.0, API may move). Track a
   known-good commit in `pyproject.toml`; CI runs CB2 suites against the pinned version.
5. **`metrics_reference.md` unresolved specs** (energy-balance ≥100 vs ≥500 yr; Bjerknes
   & C-C not in the paper's Tier I list) are paper decisions, not code — resolve in the
   protocol, then encode in `thresholds.yml`.

---

## 9. Definition of done

- `pip install climatebench2` (with `climateeval`) → `climatebench2 score <model>` runs
  all three tiers and writes one `.ddb`; `climatebench2 leaderboard *.ddb` renders the
  page.
- No data-loading, regridding, or generic-diagnostic code remains in CB2 — only
  `diags/` (thresholds + scoring), `suites/`, `thresholds.yml`, `leaderboard/`, docs.
- `benchmark_scrips/`, `download_scripts/`, `constants.py`, `utils.py`, `esmvaltool/`,
  `_to_delete_git_litter/` are gone.
- Every Tier I/II/III row in `metrics_reference.md` is either a CB2 diagnostic or an
  explicitly-tracked gap — nothing silently dropped.
