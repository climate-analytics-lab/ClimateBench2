# ClimateBench v2 — Metrics Reference

**Purpose.** Single authoritative reference for every metric/diagnostic required by the
ClimateBench v2 protocol (JAMES draft), with (a) scientific rationale, (b) exact
calculation spec (inputs, preprocessing, formula, threshold/score), (c) implementation
status in this repository, and (d) pseudocode. Definitions are tool-agnostic; a note on
each Tier II entry states whether it is expected to be provided by **ClimateEval**
(YAML-suite diagnostic framework on ESMValCore, derived from ICONEval — see
`docs/climateeval_delineation_plan.md`) or by **bespoke** code.

**Paper synchronisation.** Specs below were last reconciled against the JAMES
manuscript on **2026-09-14** (`main` draft, Tier I Table 1 + Appendix B, Tier II §5,
Tier III Table 3). Where the paper and this document disagree, **the paper is the
truth**; open a PR against this file rather than diverging in code.

**Implementation synchronisation.** Status entries were re-audited on **2026-09-14**
against the `climatebench2/` package at commit **`d21be52`** (migration **Phase 7**,
"protocol re-alignment", of `docs/climateeval_delineation_plan.md`), where
**314 tests pass** (`pytest tests -q` in ClimateEval's pixi env with this repo on
`PYTHONPATH`), and against **ClimateEval `main` @ `b0e941c`** — **still the pin in
`pyproject.toml`**, because none of the twelve PRs tabulated below has merged.
`b0e941c` (2026-09) contains the merged CB2 upstream PR #35 (`LandOceanWarmingRatio`,
`ArcticAmplification`, `MeridionalHeatTransport` complex diagnostics; the
`rsds`/`rsus`/`rlds`/`rlus`/`tasmax`/`tasmin` variables), the ocean-transport
diagnostics of #34, and the relative-score leaderboard of #37. **The pin was bumped to
`b0e941c`** (gap item 0, `b7e8593`): the three duplicated Tier I diagnostics are
thin `GateMixin` wrappers over the upstream classes, the CB2-side registry stopgap
(`RegistryFreeVariable`) is gone and the daily suite scores `tasmax`. **Gap item 1**
(the same day) then corrected the gates that were wrong as written — the I.2b identity,
the I.1 evaluation window, the I.3a monthly anomalies, the I.5a unsmoothed index, the
I.5b integrated band power and the 1985–2014 Tier II baseline window — so the status
entries for I.1, I.2b, I.3a, I.5a/b and the Pinatubo/Climatology rows below describe
the corrected code. **Gap item 2** then gave the protocol its entry-ticket semantics:
every gate block in `thresholds.yml` carries a `requirement:` tag
(required / extended / extra / diagnostic), gate rows carry `requirement` and
`applicable` columns, a submission can *declare* a test inapplicable
(`score --not-applicable NAME`), the Pinatubo and hemispheric-asymmetry diagnostics
moved out of the Tier I suite into `ClimateBench2_TierII_events`, and the leaderboard
computes the entry ticket over the Required group alone. **Gap item 3** then brought the
**scoring-engine core** to the 2026-09 spec (`a4c5948`, `732e860`): fair (Ferro) CRPS
with a hard M ≥ 2 rule, observational-uncertainty draws, a moving-block bootstrap, and
a new post-suite pass (`climatebench2/scoring_pass.py`) that stacks a model's ensemble
members into one forecast and writes the skill against the **median** per-model CMIP6
fair CRPS with leave-one-out; **gap item 3b (work package 3b)** then finished it
(`519ef72`, `a3ff255`): the reference's **pre-2015 record** is carried into the database
by two new diagnostics (`ReferenceBaselineRecord`, `ReferenceEOFProjection`) that reach
back past the test-window cut, **regime (b) is scored with fair CRPS on the reference's
fixed pre-2015 EOF basis**, σ_int comes from piControl chunks (`InternalVariability`)
and the regime-(c) consistency test moved out of a diagnostic into the pass, σ_obs is a
protocol constant plus the measured spread across observational products (which are no
longer scored as comparison models), and the leaderboard labels every row by model
name. **Gap item 4 (CB2 side)** had earlier
fixed the data paths for a real CMIP6 run: a per-suite registry in `_cli.py` loads the
`historical` experiment in full for the complex suites, feeds the variability suite the
`picontrol` experiment, scores the Tier II suites over the reserved post-2015 test
window derived from `tier2.test_window_start`, and ingests several ensemble members
(`--member`, DRS auto-discovery) into one database per suite. **Gap item 5 (work
package 5)** then brought the three **re-specced Tier I physics** checks to the
2026-09 paper (`bbf7d43`, `8f8a36a`): I.5c is the pattern-correlation test against
HadISST/GPCP, I.3c exists at last as `PrecipBuoyancyGate`, and I.7 uses the decadal
window centred on 2015 with parallel-segment drift removal — so the Tier I suite now
carries a diagnostic for **every** row of the paper's Table 1, and two of them
(I.3c, I.5c) fetch observations through ClimateEval DataSources. **Gap item 6
(work package 6a)** then built the **Tier II scalar diagnostics** (`5185c72`, `9d4b7a9`):
the realized warming level and the two GMST trends of §II.1 exist at last
(`RealizedWarmingLevel`), the Pinatubo and hemispheric-asymmetry magnitudes are
scored rather than only sign-flagged, all four take their observed counterpart
from HadCRUT5 corrected to a surface-air-temperature basis, the pass grew a
generic **aggregated-scalar** regime and a **held-out / in-sample** label on every
row, `ClimateBench2_TierII_events` runs **once per ensemble member**, and the
Tier II suite gained clear-sky TOA, the condensed-water paths and OHC 0–100 m.
**Work package 6b** (`ce509c3`, `d8df85b`, `74a4841`) then finished §II.1: the
eight **ETCCDI extremes** on the ~1° conservative grid as a climatological mean
and a decadal trend per land band (computed, but **unscored** — no ClimateEval
DataSource supplies daily `tasmax`/`tasmin`), the **Perkins** PDF-overlap skill
as a metric in its own leaderboard table, the three **seasonal-cycle** metrics
(land annual temperature range; SST–low-cloud covariance and the seasonal
cloud-radiative feedback over the stratocumulus decks), the **diurnal** first
harmonic in local solar time with the phase scored as (cos, sin), and the
**pattern-scaling baseline** for GMST-type series — a two-layer EBM driven by a
packaged annual ERF table, one parameter calibrated on the observations through
2014 and given pseudo-members so fair CRPS is defined for it. The daily suite
now runs over the **full historical record** and is in-sample throughout.
**Gap item 7 (work package 7)** then finished **Tier III**: `PaleoProxyScore`
reads the paleo pipeline's own per-dataset NetCDFs (discrepancy #18) and
scores the paper's primary statistic — the **fair CRPS of a block
pseudo-ensemble** against each proxy compilation, with σ_proxy as the
observational variance term — keeping the site-consistency fraction as the
complementary diagnostic; every gate now carries a protocol `tier` so the
scorecard places a check by tier rather than by the suite it runs in; the
perfect-model path of §III.2 exists (`score --truth DIR`, a
`LocalCMORReference` DataSource, the `perfect-model` window label and the
large-ensemble spread test) but has no data to run on; and the legacy
`constants.py`/`utils.py`/`benchmark_scrips/` island is **deleted**.

**Open ClimateEval PRs (2026-09-14) — twelve, none merged.** Every one was opened by
this effort; the pin therefore stays at `b0e941c` and **nothing below has been run
against real model or observational data**. URLs are
`https://github.com/climate-federation/ClimateEval/pull/N`. Two ordering constraints:
**#44 must merge before #45** (they add generators to the same module — an additive
conflict) and **#49 before #53**. GitHub Actions did not trigger on any of them, so
each carries only local `pixi` test + `ruff`/pre-commit evidence.

| PR | What it adds upstream | What it unblocks in CB2 | What CB2 changes when it merges |
|---|---|---|---|
| **#44** | `CMIP6HistoricalSSP245` multi-member generator (+ `CMIP6HistoricalAllMembers`) | **The binding constraint on every Tier II number**: comparison models with M ≥ 2 over the test window (#10, #13), and the CMIP6 multi-model-mean warming pattern | `E_ref` becomes non-empty and the skill column shows `S` instead of raw CRPS; `_eof_pattern_scaling_row` stops writing a `reason` and scores the **spatial** half of the pattern-scaling baseline; bump the pin |
| **#45** | hist-aer / amip / amip-4xCO2 / lgm / midHolocene / lig127k generators | Running I.4a/b, I.7 and Tier III against archived data instead of submission-supplied `--experiment` directories | PMIP4 and DAMIP **comparison ensembles** become available, so Tier III gets an `E_ref` of its own; the CLI's experiment flags become optional rather than required |
| **#46** | `Nino34` accepting `window_length = 1` | I.5a's unsmoothed monthly index without a CB2 override | **Delete `ENSOGate._preprocess`** — the gate becomes a pure threshold wrapper |
| **#47** | `SeaIceExtent*` diagnostics (Σ A where siconc > 15 %) | The protocol's sea-ice definition (#15) | Uncomment the `SeaIceExtentTimeSeries` stanza in `ClimateBench2_TierII.yml` and **switch the sea-ice rows from area to extent** |
| **#48** | ERA5 `zg` / `ts` | I.3c's geopotential reference, I.5c's temperature reference | I.3c drops the `physics.hydrostatic_height` fallback; I.5c's `ts` pattern uses ERA5 rather than HadISST `tos` alone (no more pairwise land masking) |
| **#49** | GISTEMP / BerkeleyEarth / NOAAGlobalTemp / CRU sources (+ the `tasa` variable) | The paper's four GMST products, hence a **measured inter-product σ_obs** for `tas`; a land-only reference for the seasonal temperature range | Add three suite entries and `tas` gains a real observational spread term instead of the provisional 0.05 K constant; `LandAnnualTemperatureRange` switches ERA5 → CRU TS |
| **#50** | Tier I energy budget / covariance — `EnergyBalance`, `BudgetClosure`, `ClearSkyLongwaveFeedback`, `PrecipitationBuoyancy`, `ClausiusClapeyronScaling` | Nothing new scientifically — this is the **upstream track** (gap item 8) | **Delete the CB2 copies in `diags/tier1_physics.py` / `tier1_extended.py`** and keep only `GateMixin` wrappers, exactly as `ECSGate` already is |
| **#51** | dynamics / variability — `GeostrophicBalance`, `MJOEastWestPowerRatio`, `ITCZEnergyFluxEquator`, `BjerknesCompensation`, `ENSOTeleconnectionPatterns` | Same | Same: CB2 keeps the thresholds, upstream keeps the physics |
| **#52** | forcing — `Amip4xCO2ERF`, `GFMIPPatchFeedback`, `AerosolERF` + a branch-time helper | Same, plus the parallel-segment selector moves next to `ECS` where it belongs | Same; and see decision D.3 — adopting the helper in `ECS` would move ClimateEval's published ECS numbers |
| **#53** | HadEX3 + `ESACCISeaIceNH/SH` (depends on #49) | **A daily observational product** — the one thing standing between the eight ETCCDI extremes and a score (#16) | Add one `reference_data:` line to the `extremes` entry; nothing else changes, the shape is already the scored one |
| **#54** | `ERA5Daily` | A daily reference that is not `ERA5Hourly`'s single hard-wired year | The commented-out daily-`pr` stanza can be uncommented; Perkins and the diurnal harmonic stop depending on one staged year |
| **#55** | `LocalCMORDataSource` | The perfect-model path's reference (§III.2) | **Replace `climatebench2/diags/truth_reference.py`** with the upstream class — CB2's last piece of data-loading code |

Beyond the twelve, three references named in this document have no upstream PR at all
and no CB2 workaround: **warming-level multi-product spread** beyond #49's four,
sub-daily CRE (CERES-SYN, IMERG), and a **`PMIP4Proxies` CMORizer** for the paleo
compilations — which is where `PaleoProxyScore`'s NetCDF reading ultimately belongs.

The legacy
`benchmark_scrips/*.py` scripts that earlier revisions of this document audited were
deleted in migration Phases 1–5; **every status entry below refers to
`climatebench2/`**, and as of **work package 7** there are no legacy survivors at all:
`constants.py`, `utils.py`, `benchmark_scrips/` and `env.yml` are gone, because
`paleo_scripts/paleo_benchmark.py` now takes `--picontrol-dir DIR` instead of
`benchmark_utils.DataFinder` and the three helpers it still needed moved to
`paleo_scripts/paleo_utils.py` (delineation plan §9).

**Conventions.**
- TOA net downward flux: `N = rsdt − rsut − rlut`
  (`diags.tier1_physics.CB2ComplexDiagnostic._toa_net_annual_global`).
- Surface net downward flux: `F_sfc = (rsds − rsus) + (rlds − rlus) − hfss − hfls`
  (`CB2ComplexDiagnostic._SFC_FLUXES`; hfss/hfls positive upward in CMIP6).
- Every field is first regridded to ClimateEval's common 2°×2° grid
  (`climateeval.diags._utils.DEFAULT_GRID`, linear); global and regional means use
  ESMValCore `area_statistics` (true cell areas from coordinate bounds). The few
  pure-numpy helpers that weight by `cos(lat)` (`physics.area_weighted_mean`, the
  pattern correlations) operate on that regular 2° grid.
- Data enter only through ClimateEval: `climateeval._loader.load_cmor_dir` for the
  submission and its auxiliary experiments (`climatebench2 score MODEL --experiment
  KEY=PATH`), ClimateEval DataSources for references and the CMIP6 comparison
  ensemble. CB2 complex diagnostics read an experiment dict keyed `picontrol`,
  `4xco2`, `histaer`, `historical`, `day`, `amip`, `amip4xco2`, `patch_ep`,
  `patch_wp`, `midholocene`, `lgm`, `lig127k` and accept a superset of their
  required keys, so one dict feeds a whole suite.
- Every bound is read from `climatebench2/thresholds.yml` through
  `climatebench2._thresholds.get_threshold("tier1.ecs.range")`; gate outcomes are
  `metrics` rows
  `var_id | value | bound_lower | bound_upper | passes | requirement | applicable`
  (`diags/pass_fail.py`), so the leaderboard reads one schema for every check.
  `requirement` (`required` / `extended` / `extra` / `diagnostic`) is read from the
  gate's own `thresholds.yml` block by `pass_fail.gate_requirement`, never hard-coded;
  `applicable` is 0.0 with NaN `value`/`passes` for a check the submission declared
  N/A (`climatebench2 score --not-applicable NAME`), which is distinct from a check
  that did not run and wrote no row at all.
- Status legend: ✅ implemented per the (2026-09) spec · 🟡 implemented but deviates
  from spec · ❌ missing · ⬆ generic physics now provided by ClimateEval `main`
  (CB2 should keep only the threshold wrapper).

---

# Decisions needed from Duncan (2026-09-14)

Every ⚠ and `TODO(Duncan)` the implementation raised, in one list. Nothing here blocks
the code from running — each item is a **choice already made provisionally**, recorded
so it can be ratified or overruled rather than discovered later. Each line says what
was decided and where it lives; the detail is in the section named. (Sources: the ⚠
marks throughout this document and the `TODO(Duncan)` comments in
`climatebench2/thresholds.yml` and `climatebench2/data/erf_ar6_ssp245.csv`.)

### A. Paper text — manuscript edits, no code change (5)

1. **§5.4 mixture vs Fig. 4 median.** §5.4 defines the reference score as an "unweighted
   **mixture**" of the CMIP6 models; the Fig. 4 caption says the **median** `E`. The
   code follows Fig. 4. One of the two must change. → discrepancy #10, §II.0.
2. **App. B.8 aerosol-ERF sign.** App. B.8 writes `F = ΔN + λΔT` while the same sentence
   defines λ as the (negative) Gregory slope; the correct form, and what the code does,
   is `F = ΔN − λΔT`. → I.7, discrepancy #8.
3. **App. E hosting claim.** "The Tier I–III diagnostics are hosted in the ClimateEval
   repository" is not true today: 3 of 18 Tier I sub-checks are upstream and none of the
   Tier II/III scoring is. Either land PRs #50–#52 before submission or soften the
   sentence. → discrepancy #21, gap item 8.
4. **Open Research org name.** The section places ClimateBench under `climate-federation`;
   the repository is `climate-analytics-lab/ClimateBench2` (`climate-federation` is
   ClimateEval's org). → discrepancy #21.
5. **§4.3 cross-reference.** The ENSO paragraph cites `app:implementation` where
   `app:tier1` is meant. → discrepancy #21.

### B. Protocol interpretations made in code — ratify or overrule (23)

Each of these is a reading CB2 had to commit to in order to compute anything. All are
implemented and unit-tested; none is claimed to be the paper's own words.

1. **Climatology baseline as a distribution.** A deterministic monthly mean is M = 1, for
   which fair CRPS is undefined, so the baseline is scored as the **distribution** of the
   1985–2014 values per calendar month (30 pseudo-members). → §II.0 "Baselines",
   `baselines.climatology_pseudo_members`.
2. **EBM pattern-scaling pseudo-members.** Same problem, same fix: the calibrated EBM
   trajectory is displaced by the detrended observed residuals of the baseline window.
   → §II.0, `baselines.ebm_pseudo_members`.
3. **`E_ref` = median with leave-one-out.** Median of the per-model fair CRPS over
   comparison models with M ≥ 2, excluding any model of the submission's own name.
   → item A.1 above; `scoring_pass.score_raw_output`.
4. **Regime-(b) bootstrap axis.** CB2 resamples the orthogonal EOF **coefficients** with
   `T_eff = K` rather than bootstrapping spatial blocks, on the reading that the retained
   modes *are* the discounted effective sample. → Tier II preamble, discrepancy #12.
5. **Model test-window anomaly.** Defined as the test-window mean minus the **reference's**
   baseline climatology (not the model's own), so a mean bias is penalised.
   → Tier II preamble, discrepancy #12.
6. **Aerosol window `[2010, 2019]`, clipped.** A hist-aer record ending in 2014 has the
   decade slid back keeping its length, and the window actually used is emitted as
   `window_first/last_year`. → I.7, `tier1.aerosol_forcing.window`.
7. **TX90p / WSDI thresholds are per calendar month**, not per calendar day: the ETCCDI
   calendar-day form needs a 5-day window and Zhang et al.'s bootstrap, which a monthly
   threshold sidesteps at the cost of a smoother annual cycle. → §II.1 extremes,
   `physics.calendar_percentile`.
8. **R95pTOT denominator.** The fraction of the **annual total** precipitation above the
   base-period wet-day 95th percentile (the other common convention is the wet-day total).
   → §II.1, `physics.heavy_precipitation_fraction`.
9. **`clt` as the low-cloud proxy.** Total cloud fraction stands in for low cloud in the
   stratocumulus metrics; a genuine low-cloud fraction needs `cl` on levels.
   → §II.1 seasonal cycle, `tier2.seasonal`.
10. **The five stratocumulus boxes** (Californian, Peruvian, Namibian, Canarian,
    Australian) are the conventional decks, not the paper's own list.
    → `tier2.seasonal.stratocumulus_regions`.
11. **Perkins baseline is fixed, not moving.** The paper says "a moving climatological
    baseline"; CB2 uses the fixed 1985–2014 monthly climatology. → §II.1 Perkins,
    `tier2.perkins`.
12. **Extremes regions are land latitude bands** (`global_land`, `tropical_land`, the two
    extratropical land bands), not AR6 reference regions. → `tier2.extremes.regions`.
13. **Diurnal phase as (cos, sin).** The phase is emitted as two components and never as
    an hour, because fair CRPS on an angle is ill-defined (23 h and 1 h are not 22 h
    apart). → §II.1 diurnal, `physics.phase_components`.
14. **`block_years` = 30, `spinup_years` = 100.** CB2 defaults, not paper values: 30 yr is
    the conventional PMIP4 climatology, 100 yr the usual equilibration allowance.
    → §III.1, `tier3.block_years` / `tier3.spinup_years`.
15. **Equal site weighting** for the Tier III variable-level score — proxy networks are
    point measurements, so cos-latitude weighting would weight grid cells, not cores.
    → `tier3.site_weighting`.
16. **DA products reported, not scored.** Only `dataset_type: proxy_compilation` enters the
    protocol score; Cleator 2020 is computed, tagged and excluded (App. D).
    → `tier3.scored_dataset_types`, §III.1.
17. **Scussolini 2019 σ refusal.** Its uncertainty column is a semi-quantitative
    reliability flag, not a σ, so the stanza reports that rather than inventing an
    observational variance term. → `suites/ClimateBench2_TierIII.yml`.
18. **Entry-ticket precedence: ✗ beats ⚠.** A submission with one failed Required check
    *and* one missing Required check reads ✗, not ⚠ incomplete. → Tier I wiring note,
    `leaderboard.entry_ticket`.
19. **GSAT blending factor 1.09 and its 10 % uncertainty.** 1.09 is the ~9 % more warming
    SAT shows than a blended product (Cowtan 2015; Richardson 2016); the paper's "at most
    10 % of the long-term change" is read as 10 % of the corrected statistic's own
    magnitude, added in quadrature to σ_obs. → §II.1,
    `tier2.gsat_blending_factor` / `_relative_uncertainty`.
20. **Every `tier2.obs_sigma` value.** tas/ts 0.05 K, tos 0.05 K, TOA fluxes
    0.20 W m⁻², `pr` and `default` `null`. All provisional; `null` means "unknown" and
    scores at zero — an honest no-op, not a claim of zero error. → `tier2.obs_sigma`.
21. **`scalar_consistency` mapping for Pinatubo.** The Jul 1991–Dec 1993 anomaly (~2.5 yr)
    is matched to the `test`-window mean σ_int, the nearer of the two reported lengths —
    an *under*-estimate of a 2.5-yr mean's spread, so a conservative (stricter) test.
    → `tier2.scalar_consistency`.
22. **Trend σ_obs by conversion, not quadrature.** σ_obs on a *trend* is obtained from the
    per-step σ through `scoring.ols_trend_sigma`; the paper states the quadrature sum.
    Unit-tested against Monte Carlo. → §II.0.
23. **Tier III site standard error ignores spatial correlation.** `std / sqrt(n_sites)`
    treats nearby cores as independent and is therefore optimistic. → §III.1.

### C. Placeholder data — must be replaced before publication (3)

1. **`climatebench2/data/erf_ar6_ssp245.csv`** is a piecewise-linear interpolation between
   published AR6 anchor values of *total anthropogenic* ERF, with **natural (volcanic and
   solar) forcing omitted** — not the AR6 annual series. Its own header carries the
   anchors and the consequences. Needs the digitised AR6 Ch. 7 / Annex III series.
   → §II.0 baselines.
2. **`tier1.precip_buoyancy.reference_slope: null`.** Until it is pinned, I.3c computes
   the GPCP/ERA5 slope at run time where the data are reachable and otherwise reports the
   model slope with **no gate row** at all. → I.3c.
3. **`tier3.le_spread.variance_ratio_range: [0.5, 2.0]`** is provisional and has never
   been exercised against CESM-LE. → §III.2.

### D. Upstream and process (5)

1. **PR merge order.** #44 before #45 (both add generators to the same module — an
   additive conflict), and #49 before #53. → "Implementation synchronisation" table below.
2. **GitHub Actions did not trigger on any of the twelve PRs.** Each was validated only by
   local `pixi` tests plus `ruff`/pre-commit; worth saying so when asking for review.
3. **Adopting the parallel-segment helper upstream would move published ECS numbers.**
   `physics.parallel_control_window` is the natural companion to ClimateEval's `ECS`,
   which has the same branch-time need — but switching `ECS` from a long-term-mean to a
   parallel-segment control baseline changes every ECS value ClimateEval has published.
   Duncan's call whether to propose it. → I.7, gap item 5.
4. **Osman 2021 needs a proxy calibration.** Its site file is uncalibrated geochemistry
   (δ¹⁸O, Mg/Ca), so both the LGM and mid-Holocene stanzas are `NOT_SCOREABLE`. Scoring it
   means adopting a calibration, which is a protocol choice. → §III.1.
5. **Otto-Bliesner 2021 marine/terrestrial split.** The paper calls it "terrestrial T", but
   the pipeline pools annual Tables S2–S4, which include NH and SH **ocean** sites, and the
   suite stanza then applies a `land_only` mask. Confirm whether the target is the
   terrestrial subset (Table S6) or all 92 sites. → §III.1,
   `paleo_scripts/process_paleo_observations.py`.

---

# Tier I — Physical consistency (entry ticket, pass/fail)

Every check is binary pass/fail. A model must pass Tier I to be scored in Tier II/III.

## Tier I status summary

| # | Diagnostic | Paper requirement (short) | Req. | Status (2026-09-14) | Code |
|---|---|---|---|---|---|
| I.1 | Energy balance (piControl) | \|μ(N)\| < 0.1 W/m²; 10-yr-running-mean drift \|δ\| < 0.02 W/m²/decade; **evaluated over the last 100 yr of piControl** | Req. | ✅ both criteria over the last `tier1.energy_balance.evaluation_years` = 100 annual values; a shorter control is used whole with a logged warning and the length reported as `n_years` | `diags.tier1_physics.EnergyBalanceGate`, `physics.running_mean_drift` |
| I.2a | Water budget closure | \|⟨P⟩−⟨E⟩\| < 0.05 mm/day | Req. | ✅ | `ClosureGate`, `physics.water_budget_residual` |
| I.2b | Atmospheric energy budget | \|⟨Q_rad⟩ − (⟨L·P⟩+⟨SHF⟩)\| < 2 W/m² | Req. | ✅ the paper's arrangement, `Q_rad = sfc_net_rad − TOA_net`; an Earth-like column (LP ≈ 80, SHF ≈ 20, Q_rad ≈ 100 W/m²) now closes to ≈ 0 | `ClosureGate`, `physics.atmospheric_energy_residual` |
| I.3a | Clear-sky LW feedback β = ∂rlutcs/∂Ts | global-mean gridpoint slope within ±25% of 2.2 W/m²/K, historical | Req. | ✅ gridpoint regression of **deseasonalised monthly anomalies** (`anomalies(period="month")`) of `rlutcs` on `ts`, ±25% of 2.2 | `ClearSkyFeedbackGate`, `physics.gridpoint_regression_slope` |
| I.3b | Midlatitude geostrophic balance | spatial ρ(u, u_g) at 850 hPa daily, 30–60°, > 0.9. **Skipped (N/A) for models with no dynamical representation** | Req. (N/A allowed) | ✅ per spec (daily `ua`/`zg` at 850 hPa, optional `ps` orography mask, pooled 30–60° both hemispheres); N/A now **declarable** (`score --not-applicable geostrophic_balance` → `applicable = 0`); untested on real daily data | `diags.tier1_extended.GeostrophicBalanceGate` |
| I.3c | Tropical precipitation–buoyancy | monthly P′ vs column-MSE′ slope, 20S–20N, ±30% of GPCP/ERA5 | Req. | ✅ new gate: ∫(c_p·ta + g·zg + L_v·hus) dp/g over the available `plev`, monthly anomalies over 20S–20N, pooled slope, gated at ±30% of the GPCP/ERA5 slope (computed at run time, else the stored `reference_slope` — **null until Duncan pins it**, in which case the model slope is reported without a gate row) | `diags.tier1_extended.PrecipBuoyancyGate`, `physics.moist_static_energy` / `mass_weighted_column_integral` / `pooled_regression_slope` |
| I.4a | GFMIP SST patch experiments | Δλ = ΔR_EP/ΔTs_EP − ΔR_WP/ΔTs_WP > 0.5 W/m²/K — **Extended** | Ext. | ✅ per spec; needs submission-provided `amip`/`patch_ep`/`patch_wp`; tagged `requirement: extended`, so it is reported for credit but outside the entry ticket | `GFMIPPatchGate` |
| I.4b | amip-4xCO2 ERF | 6.5–9.0 W/m² | Req. | ✅ (TOA-net difference amip-4xCO2 − amip; no land-warming correction, none asked) | `Amip4xCO2ERFGate` |
| I.5a | ENSO amplitude | σ(Niño-3.4) ∈ [0.5, 1.4] K | Req. | ✅ σ of the **unsmoothed** deseasonalised monthly index (`ENSOGate._rolling_window_length = 1`), computed on the **piControl experiment in full** (confirmed 2026-09-14: `_cli.SUITE_REGISTRY` gives `ClimateBench2_TierI_variability` `source="picontrol"`, `window="full"`; the CLI warns loudly and falls back to the submission's own output if none is given). Remaining note: the unsmoothed index relies on CB2's `_preprocess` override until **ClimateEval PR #46** merges | `diags.pass_fail.ENSOGate` |
| I.5b | ENSO spectrum | power(2–7 yr)/power(1–2 yr) > 1.5 | Req. | ✅ Welch PSD **integrated** over each band (`np.trapezoid`), so 1.5 means what the paper says (white noise now scores ≈ 0.71, not ≈ 1.0) | `pass_fail.band_power_ratio` |
| I.5c | ENSO teleconnections | gridpoint regression of `ts` and `pr` on standardized Niño-3.4, 30S–30N; centred spatial correlation of modelled vs observed regression patterns > 0.7 (R² > 0.5), vs HadISST/ERA5 and GPCP | Req. | ✅ the paper's pattern test: standardised unsmoothed piControl index, per-gridpoint regression of monthly `ts`/`pr` anomalies over 30S–30N, the same for HadISST `tos` + GPCP `pr` over 1979–2014, centred cos-weighted pattern correlation gated at 0.7 — rows `enso_teleconnection_ts`, `enso_teleconnection_pr`. No observations reachable → model pattern summary, logged reason, no gate row | `diags.tier1_extended.ENSOTeleconnectionsGate`, `physics.banded_pattern_correlation` |
| I.5d | MJO Wheeler–Kiladis | east/west power ratio (k=1–3, 30–90 d) > 1.5 — **Extended** | Ext. | ✅ (2-D FFT east/west ratio, k = 1–3, 30–90 d, ±15°, daily `pr`); tagged `requirement: extended` — reported, outside the entry ticket | `MJOGate`, `physics.mjo_east_west_ratio` |
| I.6a | Land–ocean warming ratio | ratio ∈ [1.2, 1.6] (**strict** — resolved 2026-09); a4x last 50 yr | Req. | ✅ one strict-range gate row `land_ocean_warming`; thin wrapper over `climateeval.diags.complex.LandOceanWarmingRatio` (⬆ done) | `LandOceanWarmingGate` |
| I.6b | Arctic amplification | (ΔT>66.5N)/(ΔT global) ≥ 1.5; a4x last 50 yr | Req. | ✅ thin wrapper over `climateeval.diags.complex.ArcticAmplification` (⬆ done) | `ArcticAmplificationGate` |
| I.6c | ECS (Gregory, 150 yr) | ∈ [1, 7] K | Req. | ✅ gate wrapper over ClimateEval's `ECS` (the template for the ⬆ rows) | `ECSGate` |
| I.7 | Aerosol forcing (hist-aer) | 2015 aerosol ERF ∈ [−2.0, −0.5] W/m²; ΔT(2015) < 0 — **Required** (promoted from Extended) | Req. | ✅ ERF = ΔN − λ_Gregory·ΔT, range, cooling; "2015" is now the **decadal mean** `tier1.aerosol_forcing.window` = 2010–2019, slid back (keeping its length) to the end of a hist-aer record that stops in 2014 and emitted as `window_first/last_year`; drift removed with the **parallel piControl segment** from `branch_time_in_parent`/`parent_time_units`, falling back to the long-term mean with a warning (`parallel_segment` flag) | `AerosolForcingGate`, `physics.aerosol_erf` / `clip_window_to_record` / `parallel_control_window` |
| I.8a | Meridional heat transport | OMET peak 1.5–2.0 PW near 15–20°; AMET peak 4–5 PW near ~45° | Req. | ✅ thresholds per paper (15–20°, 45 ± 5°); thin wrapper over `climateeval.diags.complex.MeridionalHeatTransport`, search bands from `thresholds.yml` (⬆ done) | `MeridionalHeatTransportGate` |
| I.8b | ITCZ–EFE relationship | 12-month climatology; slope within ±50% of ~3°/PW; r > 0.9 | Req. | ✅ 12-month climatology, slope ±50% of 3°/PW, \|r\| > 0.9; the hard-coded-1980 bug is gone | `ITCZEFEGate`, `physics.itcz_efe_regression` |
| (extra) | Bjerknes compensation 40–70N | not in paper's Tier I list as specced | extra | ✅ vs its own spec; tagged `requirement: extra` and **excluded from the entry ticket** (fixed 2026-09-14, gap item 2) | `BjerknesGate` |
| (extra) | Clausius–Clapeyron scaling | not in paper's Tier I list as specced | extra | ✅ vs its own spec; tagged `requirement: extra`, excluded from the entry ticket | `CCScalingGate` |

**Wiring (updated 2026-09-14, gap items 2 and 5).** The experiment-based gates plus the
two extras live in `climatebench2/suites/ClimateBench2_TierI.yml` (17 gate entries
since I.3c's `precip_buoyancy` joined them, plus
the non-gating `internal_variability` σ_int diagnostic of Tier II, which rides there
because that is where the piControl experiment is loaded in full) and run from
one experiment dict; ENSO amplitude/spectrum run on cubes in
`ClimateBench2_TierI_variability.yml`; the two Tier II event diagnostics
(`pinatubo`, `hemispheric_asymmetry`, §II.1) moved to
`ClimateBench2_TierII_events.yml` (`historical` key, in the CLI defaults) and are
tagged `requirement: diagnostic`, so the leaderboard lists them under Tier II.

Every gate block in `thresholds.yml` now carries a `requirement:` tag, which the gate
classes read through the single helper `pass_fail.gate_requirement`, and every gate row
carries it (plus `applicable`) into `metrics`. The leaderboard
(`leaderboard/_gate_matrix_html`) renders three groups — **Required** (with the
`Entry ticket` column), **Extended** (reported, additional credit) and **extra**
(non-protocol) — with cells ✓ / ✗ / `n/a` (declared) / — (not run). The entry ticket is
✓ only when every Required check either passed or was declared N/A, ⚠ when a Required
check has no row at all (the full Required set comes from the gate classes'
`_gate_checks` via `pass_fail.gate_requirements`, so a gate that never ran is visible as
a hole rather than silently ignored), and ✗ as soon as an applicable Required check
fails. Neither daily-data gate (I.3b, I.5d) nor the fixed-SST gates (I.4a/b) has been
exercised on real CMIP6 output yet; only the unit tests (synthetic cubes) cover them,
and the same is true of the two observation-fed gates added in work package 5 (I.3c,
I.5c), whose reference branch has never been run against real GPCP/HadISST/ERA5 files.

**Observations inside Tier I (new, gap item 5).** I.3c and I.5c are the only Tier I
checks that compare against *data* rather than a constant, and they take that data the
way the rest of CB2 does — a ClimateEval DataSource, a `Variable` carrying a
`timerange`, `download_missing_data` from the CLI. Their windows
(`tier1.precip_buoyancy.obs_window`, `tier1.enso.teleconnection_obs_window`, both
1979–2014) start where GPCP does and stop before the reserved post-2015 test period, so
Tier I never sees the Tier II target. Both degrade identically when the products cannot
be fetched and `fail_on_missing_data` is False (the CLI default): the model's own
statistic is written to `raw_output`, the reason is logged, and **no gate row** is
emitted — which the leaderboard renders as "—" and the entry ticket as ⚠ incomplete,
never as a pass.

---

## I.1 Energy balance closure (piControl)

**Measures.** Whether the coupled model conserves energy: an unforced control run must
have near-zero global-mean TOA net flux and negligible secular drift. This is the most
basic "the model is a physically closed system" test.

**Spec (paper).**
- Inputs: piControl monthly `rsdt`, `rsut`, `rlut`. A ≥500 yr control run is
  requested, but **both criteria are evaluated over the last 100 years of the
  piControl** (RESOLVED 2026-09; previously ambiguous between ≥500 and ≥100 yr).
  Shorter controls (≥100 yr) are accepted, with the record length noted on the
  scorecard and reduced power to detect slow drifts.
- Evaluating on the final segment avoids penalising a model that is still
  equilibrating early in the control, and is the segment contemporaneous with the
  historical branch point.
- Compute global annual-mean `N(t) = rsdt − rsut − rlut`.
- Pass criterion 1: long-term mean `|μ(N)| < 0.1 W/m²`.
- Pass criterion 2: drift of the **10-yr running mean** of N, `|δ| < 0.02 W/m²/decade`.

**Implementation status: ✅** — `climatebench2/diags/tier1_physics.py::EnergyBalanceGate`
(`picontrol` key).
- ✅ Global annual-mean N via ClimateEval preprocessors (regrid to 2°, `area_statistics`,
  `annual_statistics`); `|μ|` gated at `tier1.energy_balance.mean_toa_net_abs_max = 0.1`;
  drift = OLS slope of the centred 10-yr running mean × 10 (`physics.running_mean_drift`),
  gated at `drift_10yr_running_abs_max = 0.02`. Rows `energy_balance_mean`,
  `energy_balance_drift`; raw output also carries `n_years`.
- ✅ Both statistics are computed over the **last
  `tier1.energy_balance.evaluation_years` = 100** annual values (the stale
  `min_years: 500 # TODO` key is gone). A control shorter than the window is used
  whole, with a logged warning; `n_years` is the number of years actually used and is
  the record-length caveat for the scorecard.
- ➖ The legacy CERES-range sanity checks on `rsut`/`rlut` were dropped with the script;
  ClimateEval's stock `Tier1_sanity_checks` suite covers flux ranges if wanted.

**Pseudocode (per spec).**
```python
N = gmean(rsdt) - gmean(rsut) - gmean(rlut)        # annual, area-weighted, piControl
assert len(N) >= 100                                # >=500 requested; >=100 accepted
N = N[-100:]                                        # last 100 yr of the control
mu = N.mean()
N10 = N.rolling(year=10, center=True).mean()        # 10-yr running mean
delta = 10 * linregress(np.arange(N10.size), N10.dropna()).slope   # W/m2/decade
pass_mean  = abs(mu)    < 0.1
pass_drift = abs(delta) < 0.02
passes = pass_mean and pass_drift
```

---

## I.2 Closure constraints (piControl, global multidecadal means)

### I.2a Water budget: ⟨P⟩ ≈ ⟨E⟩

**Measures.** Global moisture conservation in steady state: precipitation must balance
evaporation over multidecadal means.

**Spec.** piControl global multidecadal means; `E = hfls / L_v` with
`L_v = 2.5008e6 J/kg`. **Pass: |⟨P⟩ − ⟨E⟩| < 0.05 mm/day** (absolute).

**Status: ✅** — `ClosureGate` (`physics.water_budget_residual`): full-period piControl
global means of `pr` and `hfls`, `|P − hfls/L_v|·86400`, gated at
`tier1.water_budget.p_minus_e_abs_max = 0.05` (row `water_budget`). Matches the spec.

```python
P = gmean_annual(pr, piControl).mean()             # kg m-2 s-1
E = gmean_annual(hfls, piControl).mean() / 2.5008e6
passes = abs(P - E) * 86400 < 0.05                 # mm/day
```

### I.2b Atmospheric energy budget: ⟨L·P⟩ ≈ ⟨Q_rad⟩ + ⟨SHF⟩

**Measures.** Atmospheric-column energy conservation: latent heating from precipitation
must balance net atmospheric radiative cooling plus surface sensible heat input.

**Spec.** piControl global multidecadal means. The atmosphere is heated by latent heat
release and by the surface sensible heat flux, and cooled radiatively, so in steady state
`Q_rad ≈ L_v·P + SHF` with `Q_rad` the **magnitude of net radiative cooling** of the
atmospheric column, `Q_rad = [(rsds − rsus) + (rlds − rlus)] − (rsdt − rsut − rlut)`
(positive ≈ +100 W/m²). Implementers should verify signs against one model before
hard-coding.
**Pass: |⟨Q_rad⟩ − (⟨L_v·P⟩ + ⟨hfss⟩)| < 2 W/m²** (absolute).

⚠ **Changed 2026-09.** Earlier revisions of both the paper and this document wrote the
identity as `|L_v·P − (Q_rad + SHF)|`, which implies the sensible heat flux cools the
atmosphere. The paper (Table 1 and Appendix B) now carries the physically standard
arrangement above; code written against the old form must be reordered.

**Status: ✅.** `ClosureGate` calls `physics.atmospheric_energy_residual`, which
returns `|Q_rad − (L_v·P + hfss)|` with `Q_rad = sfc_net_rad − TOA_net` — the paper's
arrangement. (Earlier revisions returned `|L_v·P − (Q_rad + SHF)|`, which is off by
2·SHF ≈ 40 W/m² against a 2 W/m² bound and failed every physically reasonable model.)
`tests/test_physics.py` covers both the balanced case and an Earth-like column
(LP ≈ 80, SHF ≈ 20, Q_rad ≈ 100 W/m² → residual 0, where the old form gave ≈ 40), and
`tests/test_tier1_physics.py` checks the gate end-to-end on synthetic cubes built to
close this identity. The absolute 2 W/m² bound and the piControl full-period means were
already right.

```python
LP    = 2.5008e6 * gmean(pr).mean()                        # W/m2
Qrad  = gmean(rsds - rsus + rlds - rlus                    # sfc net radiation
              - (rsdt - rsut - rlut)).mean()               # minus TOA net -> atm cooling (+ve)
SHF   = gmean(hfss).mean()
passes = abs(Qrad - (LP + SHF)) < 2.0                      # W/m2
```

---

## I.3 Diagnostic covariances (historical)

Emergent internal covariances that any physically plausible atmosphere must reproduce.
The paper computes these on the **historical** experiment; the CB2 gates take the
`historical` key (which the CLI defaults to the model cubes being scored).

### I.3a Clear-sky longwave feedback β = ∂rlutcs/∂Ts

**Measures.** The tight, theoretically understood link between surface temperature and
clear-sky OLR (Koll & Cronin 2018); observed value ≈ 2.2 W/m²/K (CERES).

**Spec.** For each grid point, temporally regress monthly (or annual) `rlutcs` on
surface temperature `ts` over the historical period; area-average the slope field.
**Pass: global-mean slope within ±25% of 2.2 W/m²/K → [1.65, 2.75] W/m²/K.**

**Status: ✅** — `ClearSkyFeedbackGate` (`historical` key): both `rlutcs` and `ts` are
reduced to **deseasonalised monthly anomalies**
(`esmvalcore.preprocessor.anomalies(period="month")`, paper App. B) before the
per-gridpoint OLS on the 2° grid (`physics.gridpoint_regression_slope`), then a
cos-weighted area mean, gated at `2.2 × (1 ± 0.25)` from
`tier1.clear_sky_lw_feedback` (row `clear_sky_lw_feedback`). Annual means — the
previous behaviour — suppress the seasonal covariance and shorten the sample 12-fold;
the unit test builds a field whose monthly-anomaly β is 2.5 and whose annual-mean β is
4.2, so a reversion fails the gate. The 2.2 reference is a fixed constant in
`thresholds.yml` (the paper quotes the CERES-derived value, so no live CERES regression
is needed).

```python
beta = xr.apply_ufunc(linregress_slope, ts_anom, rlutcs_anom,   # per grid point, over time
                      input_core_dims=[["time"], ["time"]], vectorize=True)
beta_gm = area_mean(beta)
passes = 0.75 * 2.2 <= beta_gm <= 1.25 * 2.2                     # W/m2/K
```

### I.3b Midlatitude geostrophic balance

**Measures.** Large-scale dynamical consistency: daily midlatitude winds must be close
to geostrophic balance with the model's own geopotential field.

**Spec.** Inputs: **daily** 850 hPa zonal wind `ua850` and geopotential `Φ850`
(historical; `Φ = g·zg`). Geostrophic wind `u_g = −f⁻¹ ∂Φ/∂y`, `f = 2Ω sin(lat)`.
For each day (or
pooled), compute the **spatial** Pearson correlation ρ(u, u_g) over 30–60° (each
hemisphere or combined; masking |lat|<30 avoids small f). **Pass: ρ > 0.9.**

**Implementation note (per Duncan, 2026-07):** the 850 hPa surface intersects orography
across much of the 30–60° band (Rockies, Andes, Tibetan Plateau, Antarctica), where
sub-surface pressure-level values are extrapolated or missing. Mask grid points where
`ps < 870 hPa` (or where the level is flagged sub-surface) before computing both u and
u_g, and compute ∂Z/∂y only from unmasked neighbours. The paper deliberately leaves this
at 850 hPa; handle the masking here in code rather than changing the spec.

**Applicability (RESOLVED 2026-09; implemented 2026-09-14).** This test is **skipped and
recorded as N/A** for submissions with no dynamical representation of the atmosphere
(e.g. emulators that map forcing directly to regional `tas`/`pr`). It is required for
any model that produces winds and geopotential. The scorecard reports which Tier I tests
were applicable to each submission rather than treating N/A as either a pass or a fail —
otherwise the inclusivity the protocol claims in §7.1 would be contradicted by a gate in
Tier I. In code: `climatebench2 score MODEL --not-applicable geostrophic_balance`
(repeatable) passes `not_applicable=[…]` into the diagnostics of the experiment-based
suites; a gate whose own name is listed computes nothing, needs no data, and emits one
row per check with `applicable = 0.0` and NaN `value`/`passes`
(`SupersetExperimentMixin` / `pass_fail.not_applicable_metrics`). The leaderboard shows
that as `n/a`, counts it as neither pass nor fail, and still lets the entry ticket be ✓.

**Status: ✅ (structurally; untested on real data)** —
`diags/tier1_extended.py::GeostrophicBalanceGate` (`day` key): `extract_levels` to
850 hPa for daily `ua` and `zg`, `physics.geostrophic_wind_u` (= −(g/f)∂Z/∂y on the
sphere, |lat| < 10° masked), optional orography mask where daily `ps < 870 hPa` when
`ps` is present in the `day` data, then `physics.midlatitude_pattern_correlation` —
cos-weighted correlation pooled over all days and both 30–60° bands — gated at
`tier1.geostrophic_balance.spatial_corr_min = 0.9` (row `geostrophic_balance`).
Applicability: ✅ a submission *declares* "no dynamics" with
`--not-applicable geostrophic_balance` (→ `applicable = 0`, rendered `n/a`); a gate
whose `day` experiment was simply not supplied still writes no row and is rendered "—",
which now makes the entry ticket **incomplete (⚠)** instead of silently dropping a
Required test. Remaining gap: (ii) loading a `day`-table DRS tree through
`load_cmor_dir` and the memory footprint of decades of daily 3-D `ua`/`zg` have not
been exercised; the unit tests use synthetic cubes.

```python
f  = 2 * 7.292e-5 * np.sin(np.deg2rad(lat))
ug = -(9.81 / f) * zg850.differentiate("lat") / (np.deg2rad(1) * R_earth)
band = dict(lat=slice(30, 60))      # repeat for -60..-30
rho = spatial_corr(ua850.sel(band), ug.sel(band), weights=coslat, dims=("lat","lon","time"))
passes = rho > 0.9
```

### I.3c Tropical precipitation–buoyancy relationship

**Measures.** Convective coupling: tropical precipitation increases with column
instability (moist static energy / buoyancy), per Neelin-type precipitation–buoyancy
relations.

**Spec.** Monthly anomalies, 20S–20N, historical. Regress precipitation anomalies P′ on
column-integrated MSE anomalies ⟨h⟩′ (MSE h = c_p·T + g·z + L_v·q, mass-weighted vertical
integral; requires `ta`, `zg`/`hus` profiles or a column proxy). Compare the slope to the
same regression computed from GPCP precipitation and ERA5 column MSE.
**Pass: model slope within ±30% of the observed slope.**

**Status: ✅ (2026-09-14, gap item 5)** —
`diags/tier1_extended.py::PrecipBuoyancyGate` (`historical` key,
`requirement: required`, suite entry `precip_buoyancy`).
- ✅ **Column MSE.** `ta`, `zg` and `hus` (all three in ClimateEval's registry with an
  `alevel` coordinate) are regridded to 2°, cut to 20S–20N, put on their *common*
  pressure levels with `esmvalcore.preprocessor.extract_levels`, combined into
  `h = c_p·ta + g·zg + L_v·hus` (`physics.moist_static_energy`; `c_p`, `R_d` and the
  virtual-temperature factor join `L_v` and `g` as module constants) and integrated
  with `physics.mass_weighted_column_integral` (`np.trapezoid` over `plev`, ÷ g). The
  integral spans only the levels the monthly Amon data carry (`plev19`), so it is a
  *partial* column — which is why the reference must be truncated the same way.
- ✅ **The statistic.** Monthly anomalies of ⟨h⟩ (`physics.deseasonalised_anomalies`,
  the numpy counterpart of `anomalies(period="month")` for a field CB2 derives itself
  and never holds as a cube) and of `pr` (the ESMValCore preprocessor, on the cube),
  then `physics.pooled_regression_slope` over time *and* space. Units: mm day⁻¹ per
  MJ m⁻², so the number is O(0.1–1) instead of O(1e-7); the gate is a ratio, so the
  scaling cancels. No cos-weighting inside the pool — over 20S–20N the weight varies
  between 0.94 and 1.
- 🟡 **The reference slope.** `_observed_slope` computes the same statistic from GPCP
  `pr` and ERA5 `ta`/`hus`/`zg` over `tier1.precip_buoyancy.obs_window` = 1979–2014
  when those data are obtainable, and falls back to the stored
  `tier1.precip_buoyancy.reference_slope` — **null, TODO(Duncan)**: pin it once the
  reference has been computed once, as was done for the 2.2 W/m²/K clear-sky constant.
  With neither available the model slope is emitted and no gate row is written.
- ⚠ **Upstream gap.** `climateeval.data.ERA5.VARIABLE_MAPPING` has `ta` and `hus` but
  **no `zg`** (no `geopotential` entry), so the reference column falls back to a
  hydrostatic geopotential integrated from ERA5 `ta`/`hus`
  (`physics.hydrostatic_height`). This is defensible for *anomalies* — the missing
  surface term is constant in time — but adding `zg` to ERA5 upstream would remove the
  approximation. The fallback is logged when it happens.
- Gate row `precip_buoyancy` on `|slope_model/slope_ref − 1| ≤
  `rel_tolerance_vs_obs` = 0.30`; `precip_buoyancy_slope`,
  `precip_buoyancy_slope_ref` and `precip_buoyancy_reference_from_obs` are emitted.
- Tested on synthetic cubes with a column whose MSE anomaly is known analytically and
  a `pr` field that responds differently outside 25S–25N, so a gate that forgot the
  tropical band would fail.

```python
h_col = column_integral(cp*ta + g*zg + Lv*hus)               # J/m2, monthly
Pp, hp = monthly_anom(pr).sel(lat=slice(-20,20)), monthly_anom(h_col).sel(lat=slice(-20,20))
slope_mod = pooled_regression(hp, Pp)                        # over time and space
slope_obs = pooled_regression(era5_mse_anom, gpcp_pr_anom)   # -> thresholds.yml
passes = abs(slope_mod/slope_obs - 1) <= 0.30
```

### (extra, code-only) Clausius–Clapeyron scaling Δprw vs Δtas

`CCScalingGate` (`picontrol`): global-annual-mean fractional `prw` anomaly (%) regressed
on Δtas (K) (`physics.cc_scaling_slope`); pass if slope ∈ `tier1.cc_scaling.slope_range`
= [5, 9] %/K (Held & Soden 2006; ported from ICONEval `prw_anom_vs_tas_anom`).
**Not in the paper's Tier I list** — kept as a supplementary sanity check tagged
`tier1.cc_scaling.requirement: extra` (2026-09-14) and excluded from the entry ticket.

---

## I.4 Causal response tests

### I.4a GFMIP-style SST patch experiments

**Measures.** The "pattern effect": the radiative feedback must depend on *where* SST
warming occurs. Warming the East Pacific (EP) patch must give a more stabilizing
(more negative λ, i.e. larger ΔR/ΔTs magnitude difference) response than the West
Pacific (WP) warm-pool patch.

**Spec.** Requires bespoke AMIP-style experiments: `amip` control plus `patch-EP+1K`
and `patch-WP+1K` (GFMIP protocol). For each patch experiment compute global-mean
ΔR (TOA net anomaly vs amip) and ΔTs (global-mean surface temperature anomaly vs amip).
**Pass: Δλ = ΔR_EP/ΔTs_EP − ΔR_WP/ΔTs_WP > 0.5 W/m²/K** (sign convention: EP more
stabilizing).

**Status designation (RESOLVED 2026-09): Extended.** Demoted from Required because the
GFMIP patch runs are not part of the CMIP6 protocol, so no archived CMIP6 model can
supply them; leaving it Required would fail the entire reference ensemble at Tier I.

**Status: ✅** — `diags/tier1_extended.py::GFMIPPatchGate`
(`_required_data_keys = ("amip", "patch_ep", "patch_wp")`): λ = ΔR/ΔTs for each patch
relative to `amip` (annual global means over the overlapping record), `delta_lambda`
gated > `tier1.gfmip_patch.delta_lambda_min = 0.5`; `lambda_ep`/`lambda_wp` emitted.
Data path: submission-provided CMOR directories via `--experiment patch_ep=DIR
--experiment patch_wp=DIR --experiment amip=DIR` (nothing on ESGF). Being Extended, it
does not count toward the entry ticket: `tier1.gfmip_patch.requirement: extended`
(2026-09-14), so the leaderboard shows it in the Extended group.

```python
def lam(exp):
    dR  = gmean(toa_net(exp)  - toa_net(amip)).mean("time")
    dTs = gmean(ts(exp) - ts(amip)).mean("time")
    return dR / dTs
passes = (lam("patch-EP") - lam("patch-WP")) > 0.5    # W/m2/K
```

### I.4b amip-4xCO2 effective radiative forcing

**Spec.** ERF from fixed-SST `amip-4xCO2` minus `amip`: global-mean TOA net flux
difference (optionally with land-warming correction). **Pass: ERF ∈ [6.5, 9.0] W/m².**

**Status: ✅** — `Amip4xCO2ERFGate` (`amip`, `amip4xco2` keys): difference of the
time-mean annual global-mean TOA net flux, gated at `tier1.amip_4xco2_erf.range`
(row `amip_4xco2_erf`). No land-surface-warming correction is applied; the paper does
not ask for one. (Distinct from the Gregory intercept `f4x` that ClimateEval's `ECS`
emits from the coupled run.)

```python
erf = gmean(toa_net(amip_4xCO2)).mean("time") - gmean(toa_net(amip)).mean("time")
passes = 6.5 <= erf <= 9.0
```

---

## I.5 Coupled variability (piControl ≥ 100 yr)

### I.5a–c ENSO — `diags/pass_fail.py::ENSOGate`, `diags/tier1_extended.py::ENSOTeleconnectionsGate`

**Measures.** Existence, amplitude, timescale and teleconnection footprint of the
model's dominant coupled mode of interannual variability.

**Index definition (as built).** `ENSOGate` subclasses ClimateEval's `Nino34`
diagnostic with `_rolling_window_length = 1`: regrid to 2°, `extract_region`
190–240°E × 5S–5N, `anomalies(period="month")`, area mean — i.e. the paper's
*unsmoothed* monthly anomalies, without the operational ONI 3-month running mean.
(iris refuses a rolling window shorter than two points, so `ENSOGate._preprocess`
reproduces the upstream chain minus that one step; **ClimateEval PR #46** makes
`window_length = 1` a no-op upstream, and once it merges the override goes and only the
ClassVar is needed — the code comment names the PR.) It runs in
`ClimateBench2_TierI_variability.yml` on
the model's monthly `tos` cubes (variable id `tos_nino34`) with ESACCI-SST as reference
and ERSSTv5/HadISST as additional data — the gate is applied to the observational series
too, which sanity-checks the thresholds. `ENSOTeleconnectionsGate` recomputes the same
unsmoothed index inside a complex diagnostic on the `picontrol` key and **standardises**
it (I.5c regresses per σ of Niño-3.4).

**(a) Amplitude.**
- Spec: **σ(Niño-3.4) ∈ [0.5, 1.4] K**.
- Code: `std(ddof=1)` of the index, gated at `tier1.enso.amplitude_range`
  = [0.5, 1.4] (row `enso_amplitude`). ✅ The index is now the unsmoothed monthly one
  (the 3-month running mean lowered σ by roughly 5–10%). ✅ The input record is right
  too since 2026-09-14 (gap item 4): the CLI's suite registry feeds
  `ClimateBench2_TierI_variability` the **`picontrol` experiment in full** rather than
  the Tier II cubes, so the ≥ 100 yr control the paper specifies is what is gated —
  with a loud warning and a fallback to the submission's own output when no
  `--experiment picontrol=DIR` is given (the observational reference series are
  unaffected: no timerange is applied to this suite). Re-confirmed 2026-09-14 with
  work package 5: `_cli.SUITE_REGISTRY["ClimateBench2_TierI_variability"]` is
  `SuiteSpec(shape="cubes", source="picontrol", window="full")`, and
  `tests/test_suites.py::test_suite_registry_matches_the_actual_diagnostics` keeps the
  registry honest about the suite's data shape.
- Status: ✅ statistic, ✅ input record. One note remains: the unsmoothed index needs
  CB2's `ENSOGate._preprocess` override until **ClimateEval PR #46**
  (https://github.com/climate-federation/ClimateEval/pull/46) merges, after which the
  `_rolling_window_length = 1` ClassVar alone suffices.

**(b) Spectral shape.**
- Spec: **ratio of spectral power in the 2–7 yr band to the 1–2 yr band > 1.5**.
- Code: `pass_fail.band_power_ratio` — Welch PSD (fs = 12/yr, 20-yr segments) and the
  ratio of the **integrated** power `np.trapezoid(psd[mask], freqs[mask])` in 2–7 yr to
  that in 1–2 yr, gated at `tier1.enso.band_power_ratio_min = 1.5` (row
  `enso_spectral_ratio`). The former mean-PSD ratio ran ≈ 1.4× high (the 1–2 yr band
  spans 0.5 cycles/yr against the 2–7 yr band's 0.357), so 1.5 then meant ≈ 1.07 in the
  paper's units; white noise now scores ≈ 0.71 instead of ≈ 1.0. A band containing
  fewer than two Welch frequencies returns NaN rather than a spurious ratio.
- Status: ✅.

```python
f, S = welch(nino34, fs=12, nperseg=240)          # cycles/yr
band = lambda lo, hi: trapezoid(S[(f >= 1/hi) & (f <= 1/lo)], f[(f >= 1/hi) & (f <= 1/lo)])
ratio = band(2, 7) / band(1, 2)                   # integrated power
passes = ratio > 1.5
```

**(c) Teleconnections.** ⚠ **Replaced 2026-09** — the previous scalar criterion
(tropical-mean 500 hPa T regression positive, Maritime Continent precipitation
regression negative, each within a factor of 2 of obs) has been superseded by a
**spatial pattern criterion**, which captures sign and approximate magnitude in a
single statistic and avoids two ad-hoc regional indices.
- Spec: regress local **monthly anomalies of surface temperature and of precipitation**
  onto the **standardized** Niño-3.4 index **at each grid point over 30°S–30°N**.
  Compute the **centred spatial correlation** between the modelled and observed
  regression patterns. **Pass: correlation > 0.7** (equivalently spatial **R² > 0.5**),
  evaluated against **HadISST/ERA5** (temperature) and **GPCP** (precipitation).
- Extratropical teleconnections (e.g. PNA) are explicitly **not** used as pass/fail
  criteria — poorly constrained even in long ensembles (Deser et al. 2017).
- Code (rewritten 2026-09-14, gap item 5): `ENSOTeleconnectionsGate` (`picontrol`)
  1. builds the **standardised** unsmoothed Niño-3.4 index from the model's `tos`
     (`physics.standardised`; same box and deseasonalisation as I.5a);
  2. regresses monthly anomalies of `ts` and of `pr` on it at every 2° grid point over
     30S–30N (`physics.gridpoint_regression_slope`, the index broadcast over the map);
  3. does the same for the observations, and scores each field with
     `physics.banded_pattern_correlation` — the centred, cos-weighted correlation of
     the two patterns, generalised from `midlatitude_pattern_correlation` to an
     arbitrary latitude band (which is now a one-line wrapper over it, so I.3b is
     unchanged) — gated at
     `tier1.enso.teleconnection_pattern_corr_min = 0.7`. Rows
     `enso_teleconnection_ts` and `enso_teleconnection_pr`; the model's own
     `ts_pattern_rms`, `pr_pattern_rms`, `nino34_std` and the obs window used
     (`teleconnection_obs_first/last_year`) are emitted alongside.
- **Observational products.** *Temperature*: **HadISST** `tos` — the paper offers
  HadISST *or* ERA5, and ClimateEval's `ERA5.VARIABLE_MAPPING` has no `ts`/skin
  temperature (an upstream gap; `tas` is available but is a different field). HadISST
  is SST-only, so its regression pattern is missing over land; the pattern correlation
  drops non-finite pairs, which masks the model's `ts` to exactly the same ocean
  points — the "mask land consistently in model and obs" the criterion needs, with no
  separate land mask. *Precipitation*: **GPCP** `pr`. The **observed index is taken
  from HadISST**, so both observed patterns are regressed on one index (GPCP carries
  no SST), and the two products are aligned on their common (year, month) steps.
  Window: `tier1.enso.teleconnection_obs_window` = 1979–2014.
- **Model window.** The model patterns come from the piControl control run, the
  observed ones from the satellite era: a pattern correlation is scale-free and ENSO
  teleconnections are an internal-variability property, so the two need not be
  contemporaneous (they cannot be — piControl has no calendar in common with 1979).
- The four stale keys (`teleconnection_obs_factor`, `teleconnection_t_min`,
  `teleconnection_pr_max`, `teleconnection_reference_t/pr`) are **gone** from
  `thresholds.yml`.
- Status: ✅.

```python
n34 = (nino34 - nino34.mean()) / nino34.std()              # standardized index
band = dict(lat=slice(-30, 30))
def regmap(field):                                          # slope per unit sigma(N3.4)
    return regress_gridpoint(field.sel(**band).monthly_anom(), n34)
for mod_f, obs_f in [(ts_model, ts_obs), (pr_model, pr_obs)]:
    r = centred_spatial_corr(regmap(mod_f), regmap(obs_f), weights=coslat)
    assert r > 0.7                                          # equivalently R^2 > 0.5
```

Output: `metrics` rows `enso_amplitude`, `enso_spectral_ratio` (variability suite) and
`enso_teleconnection_ts`, `enso_teleconnection_pr` (Tier I suite), each with
`value`/`passes`. The two teleconnection rows are absent — not failed — when the
observational products cannot be fetched and `fail_on_missing_data` is False.

### I.5d MJO (Wheeler–Kiladis)

**Measures.** Eastward-propagating intraseasonal convective variability.

**Spec.** Wheeler–Kiladis wavenumber–frequency spectrum of near-equatorial daily
precipitation (or OLR): **ratio of eastward to westward power for zonal wavenumbers
k = 1–3 and periods 30–90 days > 1.5.**

**Status designation: Extended.** Not all architectures produce daily fields suitable
for a Wheeler–Kiladis decomposition, so this does not gate entry.

**Status: ✅** — `diags/tier1_extended.py::MJOGate` (`day` key): 15S–15N meridional
mean of daily `pr`, `physics.mjo_east_west_ratio` — time-mean removed, Hann taper, 2-D
FFT, power summed over 1 ≤ |k| ≤ 3 and 30–90 d, eastward = ω·k < 0 in numpy's sign
convention (unit-tested with a synthetic eastward wave) — gated at
`tier1.mjo.east_west_power_ratio_min = 1.5` (row `mjo_east_west`). No red-noise
background removal or symmetric/antisymmetric split — the paper's R_MJO is defined on
the raw spectrum, so none is required. The pure-Python double loop over (frequency,
wavenumber) is O(N_t·N_lon); fine for decades of daily data. Being Extended, it does
not count toward the entry ticket (`tier1.mjo.requirement: extended`, 2026-09-14).

```python
pr_eq = pr_daily.sel(lat=slice(-15, 15)).mean("lat")           # detrended, tapered
P = abs(np.fft.fft2(pr_eq)) ** 2                               # (freq, wavenumber)
east = P[(1/90 <= f) & (f <= 1/30), (k >= 1) & (k <= 3)].sum() # eastward: k>0,f>0
west = P[(1/90 <= f) & (f <= 1/30), (k <= -1) & (k >= -3)].sum()
passes = east / west > 1.5
```

---

## I.6 Basic forced responses (abrupt-4xCO2)

RESOLVED 2026-07: paper updated to **last 50 yr**. Both the CB2 gates
(`tier1.*.equilibrium_years = 50` in `thresholds.yml`) and the upstream ClimateEval
diagnostics (`equilibrium_years` kwarg, default 50) use that window for I.6a/b.

### I.6a Land–ocean warming ratio — `LandOceanWarmingGate` ⬆ `climateeval.diags.complex.LandOceanWarmingRatio`

**Measures.** Land must warm faster than ocean under GHG forcing (thermal inertia +
lapse-rate/moisture constraints; Sutton 2007, Joshi 2008).

**Spec.** Ratio = ΔT_land / ΔT_ocean, where Δ is equilibrium-period abrupt-4xCO2 mean
minus the piControl long-term mean, per domain. Domains defined by `sftlf` (fx land
fraction, 0–100). **Pass: ratio ∈ [1.2, 1.6]** — the strict range is the pass criterion
(RESOLVED 2026-09; the earlier "ratio > 1 required, [1.2, 1.6] expected" formulation is
superseded).

**Status: ✅ (upstream computation + CB2 gate).**
- ✅ `diags/tier1_physics.py::LandOceanWarmingGate` is a thin
  `_UpstreamGate` wrapper over `climateeval.diags.complex.LandOceanWarmingRatio`:
  `tas` regridded to 2°, `mask_landsea("sea")`/`("land")` domains (ESMValCore's
  land-sea mask on the common grid rather than the model's own `sftlf` — equivalent at
  2°), last-`equilibrium_years` a4x mean minus full piControl mean per domain,
  emitting `land_ocean_warming_ratio`, `delta_t_land`, `delta_t_ocean` and the CMIP6
  r1i1p1f1 piControl/abrupt-4xCO2 comparison ensemble. CB2 keeps only the protocol
  layer: `equilibrium_years` is fed from
  `tier1.land_ocean_warming.equilibrium_years = 50` into the upstream kwargs (the
  suite YAML keeps `additional_diagnostic_kwargs: {}`).
- ✅ **One** gate row, `land_ocean_warming`, against
  `tier1.land_ocean_warming.range = [1.2, 1.6]` — the strict range is the criterion
  (2026-09). The former `land_ocean_warming_required` / `_expected` pair and the
  `required_min`/`expected_range` keys are gone.
- Behavioural note: the upstream class *raises* if the a4x run is shorter than the
  equilibrium window, where CB2's deleted copy silently averaged what it had — a
  short a4x submission now fails loudly.

```python
w_land, w_ocean = coslat * sftlf/100, coslat * (1 - sftlf/100)
dT_land  = wmean(a4x_tas[-N_eq:], w_land)  - wmean(pi_tas, w_land)     # annual means
dT_ocean = wmean(a4x_tas[-N_eq:], w_ocean) - wmean(pi_tas, w_ocean)
ratio = dT_land / dT_ocean
passes = 1.2 <= ratio <= 1.6                                           # strict
```

### I.6b Arctic amplification — `ArcticAmplificationGate` ⬆ `climateeval.diags.complex.ArcticAmplification`

**Measures.** Polar amplification from ice-albedo and lapse-rate feedbacks and
poleward transport (Pithan & Mauritsen 2014).

**Spec.** ΔT(lat > 66.5N) / ΔT(global) ≥ **1.5**, anomalies as in I.6a.

**Status: ✅.** `ArcticAmplificationGate` is a thin `_UpstreamGate` wrapper over
`climateeval.diags.complex.ArcticAmplification`: `extract_region` (66.5–90N) vs global,
last-`equilibrium_years` a4x minus piControl mean, plus the CMIP6 comparison ensemble;
`arctic_amplification`, `delta_t_arctic`, `delta_t_global` emitted. CB2 feeds
`arctic_latitude` = `tier1.arctic_amplification.lat_min` and `equilibrium_years`
= `tier1.arctic_amplification.equilibrium_years` into the upstream kwargs and gates the
`arctic_amplification` column at `ratio_min = 1.5` (row `arctic_amplification`).

```python
dT_arc = wmean(a4x_tas[-N_eq:], coslat, lat_min=66.5) - wmean(pi_tas, coslat, lat_min=66.5)
dT_glo = wmean(a4x_tas[-N_eq:], coslat)               - wmean(pi_tas, coslat)
passes = (dT_arc / dT_glo) >= 1.5
```

### I.6c ECS via Gregory regression — `ECSGate` over `climateeval.diags.complex.ECS`

**Measures.** Equilibrium climate sensitivity diagnosed from the transient
abrupt-4xCO2 response (Gregory et al. 2004).

**Spec.** 150 yr of abrupt-4xCO2. Annual global means of ΔT (tas anomaly vs piControl
long-term mean) and ΔN (TOA net anomaly vs piControl mean). OLS: `N = F_4x + λ·ΔT`;
`F_2x = F_4x/2`; `ECS = −F_2x/λ`. **Pass: ECS ∈ [1, 7] K.**

**Status: ✅** — `ECSGate(GateMixin, ECS)`: ClimateEval's `ECS` complex diagnostic
(Gregory regression over the first 150 yr, piControl long-term-mean baseline; emits
`ecs`, `lambda`, `lambda_stderr`, `f4x`, `f2x`, `p_value`, `r2`, plus the CMIP6
r1i1p1f1 comparison ensemble) with one gate row `ecs_gate` at `tier1.ecs.range`
= [1, 7] K. `SupersetExperimentMixin` lets it run from the shared Tier I experiment
dict and skip with a warning when `picontrol`/`4xco2` were not supplied. This is the
pattern I.6a/b and I.8a now follow. (No drift correction against
the parallel piControl segment — an acceptable simplification for well-balanced
controls; I.1 gates drift separately.)

```python
dT = annual_gmean(a4x.tas)  - pi_gmean_tas                      # 150 values
dN = annual_gmean(toa_net(a4x)) - pi_gmean_toa_net
lam, F4x = polyfit(dT, dN, 1)                                    # slope, intercept
ECS = -(F4x / 2) / lam
passes = 1.0 <= ECS <= 7.0
```

---

## I.7 Aerosol forcing (hist-aer, DAMIP) — `AerosolForcingGate`

**Measures.** Whether aerosols exert a net negative (cooling) forcing of realistic
magnitude — a key causal-attribution requirement.

**Spec.** From DAMIP `hist-aer` (aerosol-only historical): **2015 aerosol ERF ∈
[−2.0, −0.5] W/m²** and global-mean **ΔT(2015) < 0** (cooling), anomalies vs piControl.
**Status designation: Required** (promoted from Extended, 2026-09) — `hist-aer` is
widely available in DAMIP and is a short run.
Paper Appendix B.8 (2026-09) specifies the energy-balance inversion in detail: λ from
the model's own abrupt-4xCO2 Gregory regression (unit efficacy), ΔN and ΔT as a
**decadal mean centred on 2015**, and **control drift removed using the parallel
piControl segment** before forming anomalies. Online double-call or fixed-SST ERF
estimates are preferred where a model provides them (extended output).

**Status: ✅ (2026-09-14, gap item 5)** — `diags/tier1_physics.py::AerosolForcingGate`
(`picontrol`, `4xco2`, `histaer` keys):
- ✅ λ from a fresh 150-yr Gregory regression of the a4x run
  (`physics.gregory_regression`, `tier1.ecs.n_years`); `ERF = ΔN − λ·ΔT`
  (`physics.aerosol_erf`) — the correct form for the negative Gregory slope; gate rows
  `aerosol_erf` at `tier1.aerosol_forcing.erf_range = [−2.0, −0.5]` and
  `aerosol_cooling` (`delta_t_end < 0`); `lambda_4x`, `delta_n_end` emitted.
- ✅ **The decadal window.** `tier1.aerosol_forcing.window = [2010, 2019]` (the class
  constant `_end_period_years = 30` is gone). DAMIP `hist-aer` ends in 2014 for many
  models, so `physics.clip_window_to_record` keeps the window's *length* and slides it
  back to the end of the record supplied (1850–2014 → 2005–2014); a record shorter
  than the window is used whole. The clip is logged as a warning and the window
  actually used is emitted as `window_first_year` / `window_last_year`.
- ✅ **Parallel-segment drift removal.** The hist-aer cubes' CMIP6
  `branch_time_in_parent` / `parent_time_units` attributes give the piControl calendar
  year the run branched from (decoded with `cf_units.Unit`, on the child's own
  calendar); `physics.parallel_control_window` maps the evaluation window onto the
  concurrent control years and the anomalies are taken against *that* segment's means.
  When the branch metadata is absent, or the implied segment falls outside the control
  record, the long-term mean is used with a warning. Which one was used is emitted as
  `parallel_segment` (1/0). *Attribute survival (checked against ClimateEval `main`):*
  `load_cmor_dir` runs `equalise_attributes` over the time-split files of **one
  variable**, which drops only attributes that differ between them (`creation_date`,
  `tracking_id`) — the run-level branch attributes are identical across a run's files
  and survive, and `get_prepared_cube` copies the cube rather than rebuilding it.
- ⚠ Paper sign nit (for the manuscript, not the code): App. B.8 writes
  `F_aer = ΔN + λΔT`, which is correct only if λ denotes the positive feedback magnitude.
  With λ = the Gregory slope (negative, as the same sentence says) the correct form is
  `F = ΔN − λΔT`, which is what the code does. **Still open, paper-side.**
- Not done here: an **online double-call or fixed-SST** aerosol ERF, which App. B.8
  prefers where a model provides it (extended output). CB2 has no key for such a run.

```python
lam = gregory(a4x_dT, a4x_dN).slope                       # W/m2/K from abrupt-4xCO2 (negative)
first, last = clip_window(2010, 2019, histaer_years)      # -> 2005-2014 for a run ending 2014
pi_seg = parallel_control_window((first, last),           # branch_time_in_parent
                                 branch_year, histaer_years[0])
dT_end = histaer_gmean_tas_annual[first:last].mean() - pi_tas[pi_seg].mean()
dN_end = histaer_gmean_N_annual[first:last].mean()   - pi_N[pi_seg].mean()
ERF = dN_end - lam * dT_end
passes = (dT_end < 0) and (-2.0 <= ERF <= -0.5)
```

---

## I.8 Coupled diagnostics

### I.8a Meridional heat transport partitioning — `MeridionalHeatTransportGate` ⬆ `climateeval.diags.complex.MeridionalHeatTransport`

**Measures.** Correct partitioning of poleward energy transport: ocean dominates the
deep tropics, atmosphere the midlatitudes (Trenberth & Caron 2001; ECCO/ERA5).

**Method (residual, shared with I.8b and Bjerknes via `climatebench2.physics`).**
`F_TOA = rsdt − rsut − rlut`; `F_sfc = (rsds−rsus) + (rlds−rlus) − hfss − hfls`;
`div_A = F_TOA − F_sfc`. Zonal-mean, then
`MET(φ) = 2π a² ∫_{−π/2}^{φ} F̄(φ′) cos φ′ dφ′` (`physics.meridional_transport`,
cumulative from the S pole). AMET from `div_A`, OMET from `F_sfc`.
Inputs: piControl monthly, 9 Amon variables (all now in ClimateEval's registry).

**Spec.** **Peak OMET 1.5–2.0 PW near 15–20°N; peak AMET 4–5 PW at ~45°N**
(vs ECCO/ERA5).

**Status: ✅.**
- ✅ `MeridionalHeatTransportGate` (`picontrol`) is a thin `_UpstreamGate` wrapper over
  `climateeval.diags.complex.MeridionalHeatTransport` — the same residual computation
  on time-mean zonal-mean fluxes on the 2° grid, plus the CMIP6 piControl comparison
  ensemble. Four gate rows on the upstream output columns — `omet_peak` [1.5, 2.0] PW,
  `omet_peak_lat` [15, 20]°, `amet_peak` [4, 5] PW, `amet_peak_lat` 45 ± 5° — all from
  `tier1.meridional_heat_transport`, whose `omet_search_band` [5, 30] and
  `amet_search_band` [25, 55] are fed into the upstream kwargs. The legacy widened pass
  windows and CB2's `_transport_profiles` are gone.
  (`physics.meridional_transport` stays for I.8b and Bjerknes until ClimateEval exposes
  `implied_meridional_transport` publicly; `physics.nh_peak` was deleted with its last
  caller.)
- ⚠ No global-imbalance correction before integrating: the residual OMET inherits any
  piControl F_sfc imbalance. Small for a balanced control, and I.1 gates the imbalance
  separately; the upstream class has the same property.

```python
div_A, F_sfc = (toa_net - sfc_net), sfc_net                    # (time, lat, lon)
AMET = cumint_from_spole(div_A.mean("lon"))                    # 2*pi*a^2 * sum F cos(lat) dlat
OMET = cumint_from_spole(F_sfc.mean("lon"))
omet_pk, omet_lat = nh_peak(OMET.mean("time")/1e15, 5, 30)     # PW
amet_pk, amet_lat = nh_peak(AMET.mean("time")/1e15, 25, 55)
passes = (1.5<=omet_pk<=2.0) & (15<=omet_lat<=20) \
       & (4.0<=amet_pk<=5.0) & (abs(amet_lat-45)<=5)           # paper windows
```

### I.8b ITCZ–energy flux equator (EFE) — `ITCZEFEGate`

**Measures.** The energetic constraint on tropical rainfall: the ITCZ sits near the
energy flux equator and migrates with the cross-equatorial atmospheric energy transport
(Donohoe 2013; Schneider 2014; Kang 2008/2009).

**Spec.** Historical **climatological seasonal cycle (12 monthly means)**:
regress the latitude of the zonal-mean precipitation maximum on the EFE latitude
(AMET zero crossing) — equivalently on the cross-equatorial flux F_xeq —
**slope within ±50% of ~3°/PW** (i.e. |slope| ∈ [1.5, 4.5] °/PW, negative sign for
ITCZ-vs-southward-flux convention) and **r > 0.9**.

**Status: ✅** — `diags/tier1_physics.py::ITCZEFEGate` (`historical`):
`climate_statistics(period="month")` gives 12 zonal-mean maps of the nine flux
variables and `pr`; per month AMET via `physics.meridional_transport`, F_xeq = AMET at
0° (`np.interp`), ITCZ = argmax of zonal-mean `pr` within ±30°;
`physics.itcz_efe_regression` → slope (°/PW) and r; gate rows `itcz_efe_slope`
(|slope| within `slope_reference × (1 ± 0.5)` = [1.5, 4.5]) and `itcz_efe_correlation`
(|r| > `corr_min = 0.9`); signed slope emitted. The retired script's all-timesteps
regression, ad-hoc 2-month lag and hard-coded `np.ones((1980,1))` are gone
(`physics.zero_crossing_nearest_equator` computes the EFE latitude proper without any
time-length assumption, though the gate regresses on F_xeq, per the °/PW slope).
Minor: the ITCZ latitude is the argmax on the 2° zonal mean, i.e. quantised to 2°; a
centroid or parabolic refinement would tighten r.

```python
clim = monthly_climatology(historical)                     # 12 maps per field
AMET  = cumint_from_spole((toa_net(clim) - sfc_net(clim)).mean("lon")) / 1e15   # PW
itcz  = zonal_mean(clim.pr).sel(lat=slice(-30,30)).idxmax("lat")   # 12 values
efe   = zero_crossing_nearest_equator(AMET, band=20)                # 12 values
fxeq  = AMET.interp(lat=0)
slope, r = linfit(fxeq, itcz)                               # deg per PW
passes = (abs(r) > 0.9) and (1.5 <= abs(slope) <= 4.5)
```

### (extra, code-only) Bjerknes compensation — `BjerknesGate`

Not in the paper's Tier I list (it *is* in repo CLAUDE.md history); treat as an
optional/extended Tier I check pending paper reconciliation.
**Measures** decadal anti-correlation of AMET and OMET anomalies at 40–70N
(Bjerknes 1964; Outten 2018). **Method (as built):** monthly zonal-mean fluxes →
per-month AMET/OMET via `physics.meridional_transport`, 40–70N band mean
(`_band_transport_series`), `physics.monthly_anomalies`, 121-month centred running
means, Pearson r (`physics.bjerknes_correlation`). **Pass:** r <
`tier1.bjerknes.corr_max = −0.3` (row `bjerknes_compensation`). The legacy DJF-only
variant was not ported. piControl. Status: ✅ (vs its own spec); tagged
`tier1.bjerknes.requirement: extra` (2026-09-14), so it is reported in the leaderboard's
extra group and excluded from the entry ticket.

---

# Tier II — Probabilistic scoring against post-2015 observations

**Scope (paper).** Score model *ensembles* against observations over 2015–present.
Core variables: `tas` (incl. **daily extremes**), `ts`, `pr` (incl. **intensity PDF**),
TOA fluxes, **sea ice**. Extended: OHC, surface fluxes, cloud properties, `prw`.
**Baselines (RESTRUCTURED 2026-09).** There is now **one headline skill score per
scorecard entry**, taken relative to the **CMIP6 multi-model ensemble**. Two further
references are computed and reported *alongside* it as diagnostic context, not as
parallel headline numbers:
- **climatology baseline** — predicts the **1985–2014** monthly mean for every test year
  (note: 1985–2014, *not* 1990–2020; the old window overlapped the reserved test period);
  establishes the no-skill floor.

  ⚠ **CB2 interpretation, needs Duncan's ruling.** A deterministic monthly mean is
  M = 1, for which fair CRPS is *undefined* — so as written this baseline cannot be
  scored by the protocol's own primary score. CB2 therefore scores it as the
  **distribution** of the reference's baseline-window values for each calendar month
  (30 pseudo-members for a monthly series, the 30 annual values for an annual one;
  `baselines.climatology_pseudo_members`, 2026-09-14, `a4c5948`). This is the natural
  probabilistic reading of "predict the climatology" and puts the no-skill floor on
  the same fair-CRPS footing as every other row, but it is *not* what the manuscript
  says; either the manuscript adopts the distributional reading or the baseline needs
  a different score.

  ✅ **The window is now in the database** (`a3ff255`). The Tier II suites are cut to
  the post-2015 test window, which also cuts the *reference*, so the 1985–2014 values
  the pseudo-members are made of used to be simply absent and the pass could only
  record "the reference has no baseline window". `diags/tier2_reference.py::Reference
  BaselineRecord` (suite entries `reference_baseline` / `sst_baseline`) loads each
  variable's reference over `tier2.climatology_baseline_period` — a copy of the suite
  `Variable` carrying that `timerange`, which is exactly how ClimateEval applies a
  window — and writes the area-mean **monthly and annual** series under the data types
  `reference_baseline` / `reference_baseline_annual`. The pass builds the
  pseudo-members from those rows and keeps the "window absent" reason only for a
  database that has none. A reference that does not reach back
  `tier2.climatology_baseline_min_years` (10) into the window is skipped with a logged
  reason rather than half-sampled. *Not* added to `ClimateBench2_TierII_daily`: its
  statistic is an annual block maximum, for which an area-mean baseline series would
  be the wrong sample.
- **pattern-scaling baseline** — multi-linear: global-mean temperature trajectory from a
  two-layer EBM calibrated to observations **through 2014**, multiplied by a fixed CMIP6
  multi-model-mean response pattern; the simplest defensible emulator.

  ✅ **The GMST trajectory is wired and calibrated** (2026-09-14, work package 6b):
  a packaged annual ERF table drives the EBM and **one** parameter is fitted by
  least squares to the observed GMST through 2014. ⚠ Two things need Duncan:
  the deterministic trajectory is given **pseudo-members** (the detrended
  observed residuals of the 1985–2014 window displace it) for the same reason
  the climatology is — fair CRPS is undefined at M = 1 — and the ERF table is a
  **provisional interpolation of AR6 anchor values with no natural forcing**,
  not the AR6 annual series. ❌ the multi-model-mean **pattern** needs CMIP6
  baseline-window maps that arrive with upstream PR #44; until then the spatial
  half emits a `reason` row.
Individual CMIP6 models are also shown for context.

**Scoring (RESTRUCTURED 2026-09).** **Fair CRPS is the primary probabilistic score
throughout Tiers II and III**, complemented by distributional and ensemble-consistency
diagnostics. This supersedes the earlier "two co-equal regimes" framing in which
aggregated diagnostics were scored *only* by a pass/fail consistency test.

**Fair CRPS.** The fair (Ferro) form is used everywhere, so that submissions with 3 and
with 50 members are directly comparable; the empirical form penalises small ensembles:
```
CRPS_fair(x_{1..M}, y) = (1/M) Σ_i |x_i − y|  −  (1/(2M(M−1))) Σ_i Σ_j |x_i − x_j|
```
Note the `M(M−1)` normalisation on the spread term (the empirical/biased form uses `M²`).
**For a deterministic baseline (M = 1) fair CRPS is undefined** — deterministic
references must be handled explicitly rather than falling through to absolute error.

**(a) Time-resolved quantities** — monthly/annual anomaly series 2015–present. Fair CRPS
per timestep, averaged over time; the **effective-sample-size correction applies to the
reported uncertainty**, not to the point score:
```
score = (1/T) Σ_t CRPS_fair,t
SE    = std(CRPS_fair,t) / sqrt(T_eff),   T_eff = T·(1 − r1)/(1 + r1)
```
A **moving-block bootstrap** of the per-step series (blocks of one year — 12 steps
monthly, 3 steps annual — from `tier2.bootstrap`, optionally resampling ensemble
members too) gives the reported confidence interval. Observational uncertainty enters
as **common draws**: the fair CRPS is averaged over pseudo-observations
`y_k ~ N(obs, σ_obs)` generated from a fixed seed, so a submission and its baselines
see identical draws (`tier2.obs_uncertainty`). ✅ all three implemented 2026-09-14
(`a4c5948`); σ_obs itself is still 0 everywhere because no observational error field
is plumbed through (HadCRUT5's is the first candidate).

**(b) Aggregated diagnostics and spatial fields** — climatologies, trends, variability
amplitudes, seasonal-cycle amplitude/phase. Scored with fair CRPS in a projected basis:
- project **both model and observations** onto the leading **EOFs of the reference
  dataset**, defined over the **pre-2015 record and fixed in advance** (not recomputed
  per submission, and not derived from the test window);
- **standardize each retained coefficient by its pre-2015 observational standard
  deviation**;
- score each coefficient with fair CRPS and take the **equal-weight mean over
  coefficients** as the variable-level score;
- uncertainty by **block bootstrap** resampling spatial blocks, discounted to an
  effective sample size because the coefficients are spatially correlated.

⚠ **CB2 interpretation of the (b) bootstrap axis, needs Duncan's ruling.** The paper
asks for a bootstrap that "resamples spatial blocks and discounts them to an effective
sample size". CB2 does not resample in space at all: by the time the score exists the
field has already been reduced to K **orthogonal, standardised coefficients**, which is
what the discount is for — the retained modes *are* the effective sample. The interval
is therefore an iid bootstrap over the per-coefficient CRPS values
(`moving_block_bootstrap_ci(..., block_length=1)`, member resampling as in regime (a))
with `T_eff = K`, and no serial-correlation correction is applied because the mode
index has no ordering (`scoring.crps_independent_summary`, which reports `r1 = NaN` to
say so). Resampling spatial blocks *before* the projection would give a slightly wider
interval and a different — arguably more faithful — reading of the sentence; the two
agree on the point score.

⚠ **CB2 definition of the model's test-window anomaly** (implemented, needs
confirmation). The field projected onto the basis is the **test-window time mean minus
the reference's baseline (1985–2014) climatology**, per ensemble member, on the common
2° grid. Using the reference's climatology rather than each model's own removes the
model's mean bias from *neither* side, so a biased model is penalised — which is the
point of scoring a climatology. The alternative (each source minus its own baseline
climatology) would score only the *change*, and would need a pre-2015 record for every
comparison model.

**(c) Ensemble-consistency test — complementary diagnostic.** The two-sided
consistency test (observed value vs ensemble distribution, spread combining ensemble
spread, piControl internal variability chunked into observation-length segments, and
observational uncertainty in quadrature; p < 0.05) is retained as a **reported
diagnostic and falsification check**, not as the primary score. It is the natural
vehicle for the realized-warming-level check (§II.1), which is reported as a
pass/fail consistency statement rather than folded into a rank.

**Skill score (the scorecard entry).** Every scorecard cell reports
```
S = 1 − E_model / E_ref
```
where `E` is the fair CRPS of §(a)/(b) and **`E_ref` is the median `E` across the CMIP6
reference ensemble**. Hence `S = 0` is median-CMIP6 performance, `S = 1` a perfect
match, and `S < 0` worse than the median model. The score is **bounded above but not
below**; the leaderboard clips display at `S = −1`.

⚠ `E_ref` must be the **median of the per-model fair CRPS**, each model scored on its
own members — *not* the fair CRPS of a pooled multi-model mixture. A pooled mixture is
overdispersed (its spread is structural disagreement, not internal variability), which
inflates `E_ref` and makes almost any centred submission clear `S = 0`.

⚠ **The paper is currently internally inconsistent on this point** (2026-09-14 draft):
§5.4 "Baselines and reference scores" defines the headline reference as "an unweighted
**mixture** of the ensemble distributions from all CMIP6 models … with equal total weight
assigned to each model", i.e. the pooled form, whereas the Fig. 4 caption defines
`E_ref` as "the **median** E across the ensemble" (the form adopted here).
**The code now implements the median-of-per-model form with leave-one-out**
(2026-09-14, gap item 3, `732e860`): `scoring_pass` computes one fair CRPS per
comparison model from that model's own members and takes the median, excluding any
comparison model whose name equals the scored model's; the pooled `CMIP6-MME` row is
deleted. **§5.4's "mixture" wording still needs Duncan's fix in the manuscript** — the
code follows the Fig. 4 caption, not §5.4.

⚠ **Figure 4 of the paper** is being regenerated with fair CRPS; earlier versions of that
figure used a weighted earth mover's distance. **EMD is not part of the protocol** — do
not implement it as `E`. (ClimateEval's own `report`/leaderboard uses `weighted_emd` as
its default relative-score metric since #37; that is ClimateEval's display, not a CB2
score.)

```python
# complementary ensemble-consistency test for a scalar diagnostic D
D_members = [diag(m) for m in ensemble]                      # model ensemble values
sigma_int = std([diag(seg) for seg in chunk(piControl, len_obs)])
sigma_obs = obs_uncertainty
mu, sig = mean(D_members), sqrt(var(D_members) + sigma_int**2 + sigma_obs**2)
z = (D_obs - mu) / sig
passes = abs(z) < 1.96                                       # two-sided p < 0.05
# spatial fields: project model+obs onto leading EOFs, test each PC (Bonferroni/Hotelling)
```

**Tooling (as built).** The ClimateEval wrapper is in place:
`climatebench2/suites/ClimateBench2_TierII.yml` (monthly cubes) and
`ClimateBench2_TierII_daily.yml` (daily/hourly cubes) run ClimateEval diagnostics
(`AnnualMeanTimeSeries`, `AnnualCycle`, `Map`, `ZonalLine`,
`OceanHeatContentTimeSeries`, `SeaIceAreaAnnualCycle`/`TimeSeries`, `Histogram`,
`DiurnalCycle`) against ClimateEval DataSources (HadCRUT5, GPCP, CERES-EBAF,
ERA5Monthly/Hourly, ESACCICloud, ESACCISST, NOAAERSSTv5, HadISST, EN4, IAP, OSI450NH/SH,
NSIDCG02202SH), with `CMIP6HistoricalR1I1P1F1` as the comparison ensemble. The
**scoring layer** is CB2's — `climatebench2/scoring.py` (pure numpy),
`climatebench2/scoring_pass.py` (the post-suite pass), `climatebench2/windows.py` (the
protocol's time windows), `diags/tier2_scores.py`
(`ScoredAnnualMeanTimeSeries`, `ScoredMonthlyMeanTimeSeries`,
`ScoredAnnualMaxTimeSeries`, `TrendConsistency` — thin aliases now — and
`InternalVariability`), `diags/tier2_reference.py` (`ReferenceBaselineRecord`,
`ReferenceEOFProjection` — the two entries that reach back past the test-window cut),
`diags/tier2_diagnostics.py` (the aggregated scalars of §II.1: realized warming level,
Pinatubo, hemispheric asymmetry, the three seasonal-cycle metrics, plus the
`ObservedScalarMixin` that gives a complex diagnostic its observational `reference`
rows), `diags/tier2_daily.py` (the daily statistics — the ETCCDI extremes, the
Perkins PDF skill and the diurnal first harmonic — through `ScalarTableDiagnostic`,
which is how a *simple* diagnostic writes the aggregated-scalar shape),
`baselines.py`,
`leaderboard/`. ✅ **Re-aligned to the 2026-09 fair-CRPS protocol on 2026-09-14** —
gap item 3 for regime (a) and the skill score, gap item 3b for regime (b), σ_int and
σ_obs. Nothing probabilistic exists in
ClimateEval/ESMValTool (they are deterministic-only), so the scoring layer stays
bespoke by design. The legacy
`esmvaltool/recipe_pr_rmse.yml` prototype and `benchmark_utils.MetricCalculation` are
gone.

## Tier II status summary

| Diagnostic / component | Spec regime | Status (2026-09-14) | Code / provider |
|---|---|---|---|
| Deterministic metrics (weighted RMSE / Pearson / EMD; maps, zonal lines, annual cycles) | — | ✅ from ClimateEval for every suite variable; shown by `climateeval report` and `climatebench2 leaderboard --csv` — display only, EMD is **not** a protocol score | ClimateEval `SimpleDiagnostic` metrics |
| **Fair** CRPS of ensemble time series | (a) | ✅ (2026-09-14, gap item 3, `a4c5948`/`732e860`) `scoring.crps_fair` — spread term `1/(2M(M−1))ΣᵢΣⱼ\|xᵢ−xⱼ\|`, i.e. the average over the i ≠ j pairs; **M < 2 raises** (never \|x−y\|), and a single-member model is reported as `n/a (single member)`. The empirical `crps_ensemble` is deleted rather than left as a trap. Unit-tested for the two-member analytic case and for size-independence (M = 2 vs M = 20) | `climatebench2/scoring.py`, `scoring_pass.py` |
| ESS correction on the reported SE | (a) | ✅ `crps_ess_score` (lag-1 r → T_eff; `crps_se`, `t_eff`, `r1` emitted) | `scoring.py` |
| Fair CRPS on fixed pre-2015 **reference** EOFs, standardised coefficients, block bootstrap | (b) | ✅ (2026-09-14, gap item 3b, `a3ff255`) `ReferenceEOFProjection` loads the reference over the pre-2015 window, forms monthly anomalies against that window's monthly climatology, builds the **area-weighted** basis truncated by `tier2.eof.variance_explained` = 0.9 (cap `max_modes` = 20) and projects the test-window climatological anomaly of the model (per member), of the reference and of every comparison source onto it, standardising each coefficient by its pre-2015 PC σ; one `raw_output` row per (source, variable, mode). `scoring_pass.score_eof_output` takes the fair CRPS per coefficient, its equal-weight mean as the variable score, and the same `E_ref`/skill as (a). ⚠ two interpretations flagged in the preamble: the bootstrap axis and the definition of the model anomaly. The old model-variability `field_consistency` z-test is left in place, unwired | `diags/tier2_reference.py`, `scoring.eof_basis`/`standardised_coefficients`, `scoring_pass.score_eof_output` |
| Ensemble-consistency test — complementary | (c) | 🟡 → ✅ **wired** (2026-09-14, gap item 3b, `a3ff255`): the test moved out of `TrendConsistency` (a thin alias now, dropped from the Tier II YAML) into `scoring_pass`, the only place that has the members grouped by model, the reference and the σ_int rows. σ_total² = var(**member** trends) + σ_int² + σ_obs², with σ_int from `InternalVariability`'s piControl chunks and σ_obs from `tier2.obs_sigma` + the inter-product spread, converted to a trend σ by `scoring.ols_trend_sigma` (⚠ CB2 interpretation). Rows keep the old columns plus `sigma_internal`/`sigma_obs`. The **aggregated scalars** of §II.1 — the realized warming level, both GMST trends, the Pinatubo cooling and the NH−SH trend difference — get the same test through `score_scalar_output`, each naming its (variable, statistic, window) triple in `tier2.scalar_consistency` (gap item 6, `9d4b7a9`). Still 🟡 versus the paper: a **Gaussian null** (no Mahalanobis, no empirically calibrated null), and Pinatubo's ~2.5-yr window is matched to the nearest reported σ_int length (⚠ decision B.21) | `scoring.py`, `scoring_pass.trend rows`/`score_scalar_output`, `tier2_scores.InternalVariability` |
| Skill score S = 1 − E/E_ref, E_ref = CMIP6 median, leave-one-out | — | ✅ **code** (2026-09-14, `732e860`): `E_ref` = median of the per-model fair CRPS over comparison models with M ≥ 2, excluding any whose name equals the scored model's; `skill`, `e_ref`, `n_ref_models` are metrics columns and the leaderboard shows S per model and variable (clipped at −1), the Climatology skill alongside. ❗ **numerically empty until the upstream post-2015 multi-member CMIP6 generator lands** — today's r1i1p1f1 comparison models are all M = 1, so `E_ref` has nothing to take a median of and the cells fall back to the raw CRPS. Pooled `CMIP6-MME` deleted | `scoring_pass.score_raw_output`, `leaderboard/_crps_table_html` |
| Moving-block-bootstrap CIs; observational-uncertainty draws | (a)/(b) | ✅ both regimes (2026-09-14, `a4c5948` + `a3ff255`): `scoring.moving_block_bootstrap_ci` (blocks from `tier2.bootstrap`, optional member resampling; `crps_ci_lo`/`crps_ci_hi`) for (a) and the same function at `block_length = 1` over the coefficients for (b). `crps_fair_with_obs_draws` now *bites*: σ_obs is `tier2.obs_sigma` (a protocol constant per variable, ⚠ provisional) combined in quadrature with the per-time-step **spread across observational products**, and every model and baseline sees the same draws from `tier2.obs_uncertainty.seed`. σ_obs = 0 still reproduces the plain fair CRPS exactly | `scoring.py`, `scoring_pass.observational_sigma` |
| **Observational uncertainty σ_obs** | (a)/(c) | 🟡 ClimateEval exposes **no** error field for any DataSource (HadCRUT5 CMORizes `tas`/`tasa` only — no ensemble, no uncertainty variable), so the floor is the fixed table `tier2.obs_sigma` (tas/ts 0.05 K, tos 0.05 K, TOA fluxes 0.20 W m⁻², `pr: null`). **Every non-null value is provisional and needs Duncan's ruling; GPCP's is a TODO.** `null` means "unknown" and scores at 0 — an honest no-op, not a claim of zero error. Measured on top of it: the inter-product spread (below). An upstream HadCRUT5 ensemble/error variable would replace the `tas` entry with a real field | `thresholds.yml tier2.obs_sigma`, `scoring_pass.obs_sigma_floor` |
| **Several observational products per variable** | (a)/(b) | ✅ (2026-09-14, `a3ff255`) `data_sources.category` (`observation`/`reanalysis` vs `CMIP6`/`model`) tells an observational product in `other_data` — NOAA-ERSSTv5 and HadISST beside the ESACCI-SST reference, HadISST beside OSI-450 — from a comparison model. Such a product is **never scored as a forecast** and never enters `E_ref`; it gets a row saying `observational product (a term in sigma_obs, not scored)`, and its per-time-step spread against the reference is added in quadrature to σ_obs (paper: "observational uncertainty from the spread across … products") | `scoring_pass.is_observational`/`observational_sigma` |
| Multi-member submissions | — | ✅ (2026-09-14, gap items 4 + 3, `a4cca38`/`732e860`; extended to the Tier II **events** suite by gap item 6, `5185c72`): `--member LABEL=PATH` and DRS `r*i*p*f*` auto-discovery run every **per-member** suite once per member — the cube suites, and now `ClimateBench2_TierII_events`, whose aggregated scalars are scored across the ensemble and which therefore takes *each member's own* record under the `historical` key (`SuiteSpec.per_member`; Tier I and Tier III stay once-per-model) — appending rows with distinct `data_id`s (`variant`); the scoring pass then **groups those rows by model name** (`data_sources` maps id → (name, variant)) and stacks the members on the times they share with the reference into one fair-CRPS forecast. `n_members` is reported per row | `_cli.py`, `scoring_pass.group_members`/`stack_members` |
| tas monthly/annual anomalies | (a) | 🟡 scored vs **HadCRUT5 only** (paper: GISS, Berkeley Earth, HadCRUT, NOAA GlobalTemp — ClimateEval has no DataSource for the other three, so there is also no inter-product σ_obs term for `tas`; the pass's multi-product machinery needs no change to pick them up, only a suite entry, so this is purely an *upstream* gap); HadCRUT5 publishes a 200-member analysis ensemble but ClimateEval's CMORizer exposes only `tas`/`tasa` (and only `tas` is in the variable registry), so σ_obs falls back to the provisional 0.05 K constant. The GSAT **blending correction** is applied to the aggregated GMST scalars of §II.1 (gap item 6, `9d4b7a9`), not to the monthly series row | `ScoredAnnualMeanTimeSeries` + `climateeval.data.HadCRUT5` |
| tas daily extremes (TXx, TNn, TX90p, warm-spell duration) | scalars | ✅ **computed** (WP6b, `d8df85b`) — `diags.tier2_daily.ETCCDIExtremes`, suite entry `extremes`: conservative regrid to `tier2.extremes.grid` = 1°, the index per year per grid point, a cos-weighted mean over each `tier2.extremes.regions` land band, reduced to a **climatological mean + OLS trend per decade**; ❌ **unscored** — no ClimateEval DataSource supplies daily `tasmax`/`tasmin` (ERA5's `VARIABLE_MAPPING` has neither and `ERA5Hourly` downloads one hard-wired year), so the suite gives them no `reference_data:` and the pass skips a scalar with no observed value. **HadEX3** (ESMValTool CMORizer exists) is the natural reference. The old `tasmax_txx` block-maximum series stays as a deterministic display | `diags/tier2_daily.py`, `physics.annual_extreme`/`calendar_percentile`/`spell_duration_days` |
| Perkins skill score (daily T and wet-day pr PDFs, 1 mm/day, ~1° conservative regrid, moving-baseline anomalies) | skill | ✅ (WP6b, `ce509c3` + `d8df85b`) `scoring.perkins_skill_score` = Σ min(f_m, f_o) over the pre-registered `tier2.perkins.bins`, renormalising so a density and a frequency agree; `diags.tier2_daily.PerkinsSkillScore` computes it per season for daily `tas` anomalies and wet-day (≥ 1 mm/day) `pr` intensity on the 1° conservative grid, against **ERA5Hourly**. It is a **skill, not an error**, so it is written as a *metric* (`perkins_<season>`, `perkins_all`) and shown in the leaderboard's own **distribution-skill table**, labelled in-sample — never in `E_ref` or `S = 1 − E/E_ref`. ⚠ the anomaly baseline is the fixed 1985–2014 monthly climatology, not a moving one | `scoring.py`, `diags/tier2_daily.py`, `leaderboard._distribution_table_html` |
| ts (skin temperature) | (a) | ❌ — only `tos` vs ESACCI-SST (reference) with ERSSTv5/HadISST now recognised as **observational products**, not comparison models: they feed σ_obs through their spread and are reported `n/a` rather than ranked (2026-09-14). No CRU TS / HadSST DataSource | ClimateEval, `scoring_pass` |
| pr anomalies | (a) | 🟡 vs **GPCP only** (IMERG, MSWEP ❌ in ClimateEval) | `ScoredAnnualMeanTimeSeries` + `GPCP` |
| pr intensity PDF, Rx1day/Rx5day/R95pTOT/CDD | scalars + skill | ✅ **computed** (WP6b, `d8df85b`): all four ETCCDI precipitation indices in `ETCCDIExtremes` (Rx5day as the annual maximum 5-day running total; R95pTOT as the fraction of the **annual total** above the base-period wet-day 95th percentile; CDD truncated at the year boundary) plus the wet-day intensity PDF in the Perkins entry above. 🟡 the indices themselves stay **unscored** for the same missing-daily-reference reason, though `pr` *could* be referenced against `ERA5Hourly` through `daily_statistics` — the suite carries that stanza commented out rather than scoring against a single ERA5 year. The old hourly `Histogram`/EMD display remains | `diags/tier2_daily.py`, `physics.annual_max_running_sum`/`heavy_precipitation_fraction`/`max_consecutive_dry_days` |
| TOA fluxes (LW/SW, all- and clear-sky) | (a) | ✅ (gap item 6, `9d4b7a9`) `rsut`, `rlut`, `rtnt` **and `rsutcs`/`rlutcs`** vs CERES-EBAF, all in `core_variables` so they are scored by the pass and carried through the annual-cycle, map, zonal-line, baseline and EOF entries alike | suite + `CERESEBAF` |
| Sea ice extent, Sep/Feb minima, trends | (a)/(b) | 🟡 ClimateEval `SeaIceAreaAnnualCycle`/`SeaIceAreaTimeSeries` compute **area** (Σ siconc·A), the paper says **extent** (Σ A where siconc > 15 %) — the suite now carries a **commented-out** `SeaIceExtentTimeSeries` stanza against *upstream* PR #47 with the 15 % definition rather than mislabelling area as extent, and says so. ✅ the NH-Sep/SH-Feb minimum **series is scored** by the pass (gap item 6, `5185c72`): it is an annual series with a reference, and the per-variable reference fix is what let the SH half of the entry be scored at all. The annual-cycle entry stays deterministic (a `month_number` axis is neither regime) | `ClimateBench2_TierII.yml` |
| OHC 0–100 m, 0–2000 m | (a) | ✅ (gap item 6, `9d4b7a9`) total column, **0–2000 m and 0–100 m** (`extract_volume`) vs EN4/IAP via `OceanHeatContentTimeSeries` on `phcint`; all three are annual series with a reference, so the pass scores them as regime (a) — verified, and reached only after the per-variable reference fix | suite |
| Surface fluxes (pattern/seasonal-cycle scoring; FLUXNET/OceanSITES/BSRN sites) | (b) | ❌ (Extended; no obs DataSource; no site machinery) | — |
| Cloud properties (LWP, fraction, CTT/CTP) | (a)/(b) | 🟡 `clt`, **`clwvi` and `clivi`** vs ESACCI-Cloud, all scored (gap item 6, `9d4b7a9`; ESACCICloud's CMORizer supports all three plus `lwp`); CTT/CTP ❌ — no DataSource | suite |
| prw | (a) | 🟡 vs `ERA5Monthly` (paper: RSS primary, ERA5 as reference) — acceptable pending an RSS DataSource | suite |
| Realized warming level 2015+ vs 1985–2014 (primary); 1950–present trend; test-period trend (secondary); GSAT blending | (a)/(c) | ✅ **all four** (gap item 6, `5185c72` + `9d4b7a9`): `diags.tier2_diagnostics.RealizedWarmingLevel` (`historical`, one run per member) emits `gmst_warming_level` — the mean global annual-mean `tas` from `tier2.test_window_start` to the record end minus the 1985–2014 mean, the paper's **primary** test-window scalar — plus `gmst_trend_test_window` (secondary) and `gmst_trend_1950` (`tier2.long_trend_start`), with the observed counterparts from HadCRUT5 **corrected to a SAT basis** by `tier2.gsat_blending_factor` and `tier2.gsat_blending_relative_uncertainty` of the change carried into each row's σ_obs. `scoring_pass.score_scalar_output` scores them with fair CRPS across the members *and* writes the consistency row §II.1 asks for, σ_int coming from `InternalVariability` through `tier2.scalar_consistency`. ⚠ the blending factor (1.09) and its 10 % uncertainty reading are provisional | `RealizedWarmingLevel`, `scoring_pass.score_scalar_output`, `InternalVariability` |
| Pinatubo response | (a)/(c) | 🟡 `PinatuboResponseGate`: global-mean `rsds`/`tas` anomalies Jul 1991–Dec 1993 vs `tier2.climatology_baseline_period` ([1985, 2014]). ✅ the **`tas` magnitude is now scored** (gap item 6, `9d4b7a9`): the diagnostic emits the observed anomaly from HadCRUT5 over the same window and baseline, corrected to a SAT basis, as a `reference` row, and the pass takes the fair CRPS across the members plus a consistency row. The two sign flags survive as `requirement: diagnostic` gate rows, outside the entry ticket. ❌ still: the `rsds` dimming stays **model-only** (no BSRN or CERES-SYN DataSource, documented in the class and the suite), no joint [Δrsds, Δtas] co-variation test, no ENSO removal | `diags/tier2_diagnostics.py`, `suites/ClimateBench2_TierII_events.yml` |
| Hemispheric asymmetry | (a)/(c) | 🟡 `HemisphericAsymmetryGate`: NH−SH `tas` trend over `tier2.hemispheric_asymmetry.era` ([1950, 1985]) and the zonal-mean-pr-maximum latitude trend. ✅ the **NH−SH trend is now scored against HadCRUT5** (gap item 6, `9d4b7a9`) over the same era, on a SAT basis (a multiplicative correction scales a hemispheric difference too), with the fair-CRPS and consistency rows the pass writes for any aggregated scalar; the two sign flags stay `requirement: diagnostic` gate rows. ❌ the ITCZ shift stays **model-only**: GPCP starts in 1979, after the aerosol era | `tier2_diagnostics.py`, `suites/ClimateBench2_TierII_events.yml` |
| Seasonal cycle: land annual T range; SST–low-cloud covariance; seasonal CRE–SST feedback | scalars | ✅ all three (WP6b, `d8df85b`) as complex diagnostics in the per-member events suite, scored by the aggregated-scalar regime: `LandAnnualTemperatureRange` (gridpoint max−min of the 12-month `tas` climatology, area-meaned over land; ERA5 reference — CRU once #49 lands), `SSTLowCloudCovariance` (`clt` on `tos` over the five `tier2.seasonal.stratocumulus_regions`, per deck and their mean; ESACCI-CLOUD + ESACCI-SST) and `SeasonalCloudRadiativeFeedback` (derived `swcre` on `tos`, same decks; CERES-EBAF + ESACCI-SST). All over the fixed 1985–2014 climatology window, labelled in-sample. ⚠ `clt` is the low-cloud proxy. `nbp` remains deferred by the paper | `diags/tier2_diagnostics.py`, `ObservedScalarMixin` (now multi-product) |
| Diurnal cycle (first-harmonic amplitude/phase of pr and CRE, local solar time) | scalars | ✅ (WP6b, `ce509c3` + `d8df85b`) `diags.tier2_daily.DiurnalHarmonic`: regrid, `esmvalcore.preprocessor.local_solar_time` (the lon/15 h shift), the season's mean cycle over the day, area-mean per `tier2.diurnal.regions` band, then `physics.first_harmonic` — generalised from 12 points to any sub-daily sampling. Emits amplitude and the phase as **(cos, sin)** and no hour column at all (⚠ fair CRPS on an angle is ill-defined: 23 h and 1 h are not 22 h apart). Scored against **ERA5Hourly** `pr`, land and ocean as separate suite variables. 🟡 CRE diurnal is wired only where a model supplies 3-hourly TOA fluxes — no sub-daily observational CRE product exists upstream (CERES-SYN ❌, IMERG ❌) | `diags/tier2_daily.py`, `physics.first_harmonic`/`phase_components` |
| Held-out vs in-sample labelling | — | ✅ (gap item 6, `5185c72`) `tier2.window_labels` in `thresholds.yml` maps a `var_id` (first) or a diagnostic (the suite entry name) to `held-out` / `in-sample`, with `held-out` the default; the pass stamps the label on **every** row it writes in all three regimes, a consistency row inheriting the label of the variable it tests; the leaderboard orders the skill table's columns **held-out first**, badges each one, and sorts the consistency table the same way | `thresholds.yml`, `scoring_pass.window_label`, `leaderboard.variable_windows` |
| Baselines | — | 🟡 **Climatology** row wired as a *distribution* of the 1985–2014 values per calendar month (30 pseudo-members; ⚠ CB2 interpretation, see the Tier II preamble), scored on the test-window steps, its window carried past the test cut by `ReferenceBaselineRecord` (`a3ff255`). ✅ **Pattern scaling is now scored for a GMST-type annual series** (WP6b, `ce509c3` + `74a4841`): the packaged annual ERF table (`climatebench2/data/erf_ar6_ssp245.csv`) drives `two_layer_ebm`, `calibrate_two_layer_ebm` fits **one** parameter (λ by default) by least squares to the observed GMST **through 2014** with both series reduced to anomalies about the 1985–2014 window, and `ebm_pseudo_members` displaces the trajectory by the detrended observed residuals of that window so fair CRPS is defined (⚠ CB2 interpretation, as for the climatology). The row is scored on the test window only, carries the fitted parameter in `value`, and is written for the variables of `tier2.pattern_scaling.variables` alone — a variable the EBM says nothing about gets no row, one that cannot be fitted gets a `reason`. ⚠ the ERF table is **provisional**: a linear interpolation of published AR6 anchor values with **no natural forcing**, not the AR6 annual series (TODO in its header). ❌ the **spatial** half (the normalized CMIP6-MMM warming pattern) emits a `reason` row naming upstream PR #44; ❌ no climatology baseline for **regime (b)**. **CMIP6 MME**: pooled row deleted; the headline reference is the median of per-model scores | `baselines.py`, `scoring_pass._pattern_scaling_row`/`_eof_pattern_scaling_row`, `climatebench2/data/` |
| σ_int (piControl internal variability) | (c) | ✅ (2026-09-14, `a3ff255`) `InternalVariability` — a `CB2ComplexDiagnostic` on the `picontrol` key in the **Tier I** suite (that is where the control is loaded in full), tagged `tier2.internal_variability.requirement: diagnostic` and emitting **no** gate row. For the global-mean annual series of each core variable it finds it reports `chunked_statistic_std` of the window **mean** and the OLS **trend** at both scored window lengths — the test window and 1950–present (`tier2.long_trend_start`) — plus the lengths themselves, so the pass can match a σ_int to the record it is scoring. `score_databases` collects the rows across every database of a run, which is how the Tier I control reaches the Tier II test | `tier2_scores.InternalVariability`, `scoring_pass.collect_internal_variability` |
| Row identity across tiers | — | ✅ (2026-09-14, `a3ff255`) Tier I gate rows carry the full `DataSourceInformation.id` (they are written per data source) while the scoring pass writes the model **name**, so one model used to appear twice on the scorecard. `leaderboard.build_scores` now maps every frame's `data_id` through the `data_sources` tables, and its gate/CRPS/consistency routing is per **row** rather than per column — the pass writes consistency rows (carrying both `passes` and `p_value`) into the same `metrics` tables as the gates | `leaderboard/_label_by_model` |
| **CMIP6 reference ensemble for the test window** | — | ❌ (*upstream*) ClimateEval's `CMIP6HistoricalR1I1P1F1` generator is hard-wired to `ensemble: r1i1p1f1` and `timerange: 19790101/20141231`; there is **no SSP2-4.5 or historical+SSP2-4.5 generator and no multi-member variant**, so neither a per-model fair CRPS of the CMIP6 reference (≥ 2 members) nor any post-2015 CMIP6 comparison can be assembled — an upstream `CMIP6HistoricalSSP245` generator with `ensemble: "r*i1p1f1"` is the blocking dependency. CB2 now runs the Tier II suites on the test window regardless and warns that the comparison rows will be empty until it lands | `climateeval/data/_cmip6_generators.py` |

## II.0 Machinery as built (`climatebench2/scoring.py`, `scoring_pass.py`, `windows.py`, `diags/tier2_scores.py`, `diags/tier2_reference.py`, `baselines.py`, `leaderboard/`)

**Data & preprocessing (ClimateEval).** `climatebench2 score MODEL` calls
`climateeval._loader.load_cmor_dir` (NetCDF file, flat directory or DRS tree) and hands
each CB2 suite the data *shape* and window the protocol asks for, from the CLI's suite
registry (`_cli.SUITE_REGISTRY`, ✅ 2026-09-14, gap item 4): the Tier I / Tier II-events
/ Tier III suites get an experiment dict whose `historical` entry is the submission
loaded **in full**; `ClimateBench2_TierI_variability` gets the **piControl** experiment
in full (falling back to the model's own output with a loud warning); the Tier II suites
get the model's cubes cut to the **post-2015 test window**
(`tier2.test_window_start = 2015` → `20150101/<last complete year>1231`), which
`--timerange` overrides. Ensemble members come from `--member LABEL=PATH` or from
auto-discovered sibling `r*i*p*f*` directories in a DRS tree, and each cube suite runs
once per member (`DataSourceInformation(variant=LABEL)`, appending into the one DuckDB
per suite). The data then go to `climateeval.suites.Suite.get_database`, which writes
one DuckDB per suite
(`raw_output`, `metrics`, `variables`, `data_sources`; `climatebench2 leaderboard`
reads them with `climateeval.report._db.read_database`). Reference and comparison data
are ClimateEval DataSources named in the suite YAML (`reference_data:` /
`other_data:`), regridded to the common 2° grid and reduced with ESMValCore
preprocessors. No data loading, regridding or unit handling remains in CB2.

**Scoring engine (`scoring.py`, numpy/scipy only, no protocol constants, 45 unit
tests).**
- `crps_fair(members, obs)` — per-time-step **fair (Ferro)** CRPS,
  `E|X−y| − (1/(2M(M−1)))ΣᵢΣⱼ|xᵢ−xⱼ|`, i.e. the spread term averaged over the i ≠ j
  pairs, so the expected score of a calibrated ensemble does not depend on M ✅.
  **Raises for M < 2** — the paper's "undefined for a deterministic forecast" is
  enforced, not approximated by |x − y|. The empirical `crps_ensemble` is deleted.
- `crps_fair_with_obs_draws(members, obs, obs_sigma, n_draws, seed)` — the fair CRPS
  averaged over pseudo-observations `y_k ~ N(obs, σ_obs)` drawn from a fixed seed, so
  a submission and its baselines see the *same* draws; `σ_obs = 0` reproduces
  `crps_fair` exactly and draws no random numbers ✅. σ_obs is now supplied by
  `scoring_pass` (the `tier2.obs_sigma` floor plus the inter-product spread), so the
  draws are no longer a no-op wherever the protocol has a value.
- `moving_block_bootstrap_ci(crps_t, block_length, n_boot, alpha, seed, members, obs)`
  — percentile CI of the time-mean CRPS from moving blocks of the per-step series,
  optionally resampling ensemble members and recomputing the fair CRPS per replicate
  ✅. Defaults for the protocol are in `thresholds.yml tier2.bootstrap`.
- `lag1_autocorrelation`, `effective_sample_size`, `crps_ess_score`,
  `crps_ess_from_series` → `CRPSScore(score, standard_error, t_eff, r1, n_members,
  n_time)` ✅ regime (a); the ESS correction is on the SE only.
- `chunked_statistic_std(series, chunk_length, "mean"|"trend")` — piControl
  internal-variability σ for an observation-length statistic ✅, **now called** by
  `diags.tier2_scores.InternalVariability` on the `picontrol` experiment.
- `ols_trend(y)` and `ols_trend_sigma(sigma_step, n_time)` — the regime-(c) warming-rate
  statistic and the σ of an OLS slope under independent per-step errors,
  `σ_step·sqrt(12/(T(T²−1)))`, which is how a per-step σ_obs becomes the σ_obs of a
  *trend* ✅ (⚠ CB2 interpretation: the paper states the quadrature sum, not this
  conversion; unit-tested against a Monte Carlo).
- `ensemble_consistency(values, obs, sigma_internal, sigma_obs, p_threshold)` →
  `ConsistencyResult(z, p_value, passes, ensemble_mean, total_sigma)` ✅ scalar regime
  (c) with a Gaussian null.
- `eof_basis(fields, weights=…, variance_explained=…, max_modes=…)` — area-weighted
  SVD EOFs ✅ **truncated by the protocol's pre-registered variance-explained
  criterion** (`tier2.eof.variance_explained` = 0.9, capped at `max_modes` = 20)
  rather than a hard mode count; it reports `explained_variance_ratio` and `pc_std`,
  the sample's own PC standard deviations — for a basis built on the reference's
  pre-2015 record, the paper's "pre-2015 observational standard deviation".
  `standardised_coefficients(basis, field)` = `project_onto_eofs` divided by that σ
  (a degenerate zero-σ mode is left unscaled, never divided by zero);
  `cos_latitude_weights(lats, n_lon)` is the area weighting of the common 2° grid.
- `crps_independent_summary(crps_k, n_members)` — the regime-(b) summary: mean over
  coefficients with `SE = std/sqrt(K)` and `T_eff = K`, and `r1 = NaN` because the
  mode index has no ordering to autocorrelate along ✅.
- `project_onto_eofs`, `field_consistency` — the old model-variability regime-(b)
  z-test 🟡, left in place but **unwired**: the protocol's regime (b) is now the
  reference-EOF fair CRPS above.
- Tier III: `proxy_site_consistency`, `sample_at_sites`, `le_variance_ratio`,
  `le_spread_pattern_correlation` (§III).

**Scored diagnostics (`diags/tier2_scores.py`).** ✅ **Restructured 2026-09-14 (gap
item 3, `732e860`).** `ScoredAnnualMeanTimeSeries` / `ScoredMonthlyMeanTimeSeries` /
`ScoredAnnualMaxTimeSeries` are now **thin subclasses of the ClimateEval diagnostics**
so the suite YAMLs stay valid; they emit the raw series and ClimateEval's
deterministic metrics and nothing else (`ScoredAnnualMaxTimeSeries` still overrides
`_preprocess` to a per-gridpoint annual maximum before the area mean). They no longer
emit M = 1 CRPS rows, and the pooled `CMIP6-MME` row is gone.
`TrendConsistency` is now **a thin alias too** (2026-09-14, `a3ff255`) and is no longer
named by `ClimateBench2_TierII.yml` — the `annual_mean_timeseries` entry already carries
the series the pass needs. The class survives so any existing YAML stays valid. The
regime-(c) computation moved into `scoring_pass`, which is the only place that has a
model's members grouped together, the reference, *and* the σ_int rows; inside a
diagnostic the "ensemble" could only be the submission pooled with the CMIP6 comparison
*models* (structural disagreement, not the model's own spread) and σ_int was 0.

**`InternalVariability` (`diags/tier2_scores.py`, ✅ 2026-09-14, `a3ff255`).** A
`CB2ComplexDiagnostic` on the `picontrol` key, in `ClimateBench2_TierI.yml` because
that is where the control is loaded in full, tagged
`tier2.internal_variability.requirement: diagnostic` and defining **no** `_gate_checks`
— it emits numbers, never a pass/fail row, so it cannot reach the entry ticket. For the
global-mean annual series of each variable in `tier2.internal_variability.variables`
that the control actually carries (a missing one is logged and skipped) it writes
`<var>_sigma_int_{mean,trend}_{test,long}` plus `window_years_{test,long}` and
`<var>_n_years_picontrol`, where `test` is the reserved test window and `long` the
1950-present window (`tier2.long_trend_start`). A control too short for
`tier2.internal_variability.min_chunks` = 2 chunks of a window gets no σ_int for it,
with a warning.

**Scoring pass (`scoring_pass.py`, ✅ 2026-09-14, gap item 3, `732e860` + `a3ff255`).** The
probabilistic score is a **post-processing pass over the finished database**, not a
diagnostic: ensemble members are ingested as separate data sources (gap item 4), so a
model's fair CRPS can only be formed after every member has run. `climatebench2 score`
runs it over the databases it wrote (`--no-score` skips), and `climatebench2
leaderboard --rescore DB…` re-runs it over existing ones. Per time-series diagnostic
(a `raw_output` with a `time` column and a `reference` source) and per variable:
1. `source_names` / `source_categories` read `data_sources` for `data_id → name` and
   `data_id → category` (the id is `category_name_exp_variant`, so members differ only
   in `variant`), and `group_members` groups the non-reference rows by
   **(data_type, name)** — one entry per model, however many members it has. A
   `data_id` missing from `data_sources` keeps its id as its name, so older/hand-built
   databases still work. The reference's `reference_baseline*` rows are excluded from
   the grouping: they are a *sample*, never a forecast.
2. A group in `other_data` whose category is `observation`/`reanalysis` is an
   **observational product**, not a comparison model: it is not scored, does not enter
   `E_ref`, and gets a row saying so. Its series joins the reference in
   `observational_sigma`, whose per-time-step spread across products is added in
   quadrature to the `tier2.obs_sigma` floor for the variable.
3. `stack_members` inner-joins the members on the times they share with the reference
   → `(M, T)` plus the observed series.
4. M ≥ 2 → fair CRPS per step (through `crps_fair_with_obs_draws` with the σ_obs of
   step 2), time mean, ESS-corrected SE, moving-block-bootstrap CI. M = 1 → a row
   with `crps = NaN` and `reason = "single member"`, which the leaderboard renders
   `n/a (single member)`.
5. For an **annual** series, one **regime-(c)** row per model:
   `<var>_trend_consistency`, the observed OLS trend against the distribution of that
   model's member trends with σ_total² = var(member trends) + σ_int² + σ_obs(trend)².
   σ_int comes from the `InternalVariability` rows that `score_databases` collected
   across every database of the run (nearest window length; 0 when no piControl was
   supplied, which degrades the test to the spread-plus-σ_obs form). Monthly series get
   no trend row — σ_int is chunked annually.
6. The `Climatology` baseline row (see Baselines above), built from the
   `reference_baseline` rows when they are present, and `E_ref` = **median of the
   per-model fair CRPS over the `other` models with M ≥ 2, leaving out any whose name
   equals the scored model's**; `skill = 1 − E/E_ref`.

A `raw_output` carrying `mode`/`coefficient`/`var_id` instead of a time axis is a
**regime-(b)** table and goes to `score_eof_output`, which does the same thing with the
mode index in place of time: fair CRPS per coefficient, equal-weight mean over modes,
`crps_independent_summary` for the SE, an iid bootstrap over coefficients
(`block_length = 1`) for the interval, and the same `E_ref`/skill.

**Aggregated scalars (✅ 2026-09-14, gap item 6, `5185c72`).** A `raw_output` with **no
time axis at all** — one number per data source and `var_id`, the shape a CB2 complex
diagnostic writes through `_scalar_outputs` — and with `reference` rows carrying the
observed value of the same scalar goes to `score_scalar_output`. It is the same
machinery on a **single-point scoring axis**: `crps_fair_with_obs_draws` over the
members' values, `crps_independent_summary` (so `T_eff = 1`, `r1 = NaN` and no
bootstrap interval — `moving_block_bootstrap_ci` honestly returns NaN below two
points), the same leave-one-out CMIP6 median for `E_ref` and the skill, an
observational product still recognised and never ranked, and one **regime-(c)
consistency row per scalar**. Two details are specific to this regime:
- **σ_obs.** `tier2.obs_sigma` is a per-*time-step* floor for a series and says nothing
  about an aggregated statistic, so a diagnostic that knows its own observational error
  emits it as a `<scalar>_sigma_obs` companion column on the reference row (for the GMST
  scalars, the GSAT blending term); the two are combined in quadrature. The companion
  columns, and the anonymous `level_0` index column a scalar cube contributes through
  `as_data_frame(...).reset_index()`, are excluded from the scored variables.
- **σ_int.** The consistency test needs to know *which* piControl-chunk σ applies, so
  `tier2.scalar_consistency` names, per scalar, the `(variable, statistic, window)`
  triple — e.g. `gmst_warming_level: (tas, mean, test)`, `gmst_trend_1950: (tas, trend,
  long)` — which `windows.window_lengths()` turns into a length in years and
  `sigma_internal_for` matches to the nearest reported one. An unregistered scalar gets
  σ_int = 0 and the test rests on the ensemble spread and σ_obs alone.

A scalar whose reference carries no value (the Pinatubo `rsds` dimming, the ITCZ shift)
is simply not scored — model-only, by design, not by accident. A Tier I gate table has
no `reference` rows at all and is therefore never mistaken for this regime.

**Held-out vs in-sample (✅ 2026-09-14, gap item 6, `5185c72`).** Every row the pass
writes, in all three regimes, now carries a `window` column — `held-out` or
`in-sample`. The mapping is protocol metadata, so it lives in `thresholds.yml`
(`tier2.window_labels`) rather than in a diagnostic: a `var_ids` entry wins over a
`diagnostics` entry (keyed by the suite entry name, which is the DuckDB schema the rows
land in), anything unlisted takes `default: held-out`, and a `<var>_trend_consistency` /
`<var>_consistency` row inherits the label of the variable it tests. The leaderboard
orders the skill table's columns held-out first and badges each one
(`leaderboard.variable_windows`), per the paper's §5.6 scorecard rule.

⚠ **Bug fixed on the way (`5185c72`).** `score_raw_output` took "the first `reference`
`data_id` in the table" as the reference for **every** variable. One diagnostic holds
*several* references — `annual_mean_timeseries` scores `tas` against HadCRUT5, `pr`
against GPCP and the TOA fluxes against CERES-EBAF; `sea_ice_minimum` scores the NH
series against OSI-450-NH and the SH one against OSI-450-SH — and each reference's rows
carry only its own variable (the others are NULL after the union), so every variable but
one was **silently unscored**. `reference_for_variable` now picks the reference per
variable, which is also what makes the OHC and sea-ice series of the status table
scorable at all.

Rows are appended to the diagnostic's **own `metrics` table** — never a new schema —
with `ALTER TABLE ADD COLUMN` for the new numeric columns
(`scorer`, `reason`, `crps`, `crps_se`, `crps_ci_lo`, `crps_ci_hi`, `t_eff`, `r1`,
`n_members`, `n_time`, `block_length`, `e_ref`, `n_ref_models`, `skill`, and for the
consistency rows `value`, `z`, `p_value`, `passes`, `ensemble_mean`, `total_sigma`,
`sigma_internal`, `sigma_obs`) and `scorer = "climatebench2"` on every row, deleted
before a re-run, so the pass is idempotent.

**Baselines (`baselines.py`).** Baseline (ii), `climatology_pseudo_members` ✅ (wired
through `scoring_pass`) — the climatology as a *distribution* rather than a
deterministic mean (⚠ CB2 interpretation, Tier II preamble). Baseline (iii) is now
wired too (work package 6b, `ce509c3` + `74a4841`): `load_erf_series` reads the
packaged annual ERF table, `two_layer_ebm` (Held/Geoffroy, explicit Euler, parameters
from `thresholds.yml tier2.ebm`) integrates it, `calibrate_two_layer_ebm` fits one
parameter to the observed GMST through 2014, and `ebm_pseudo_members` gives the
trajectory the spread fair CRPS needs; `scoring_pass._pattern_scaling_row` writes the
row through `PATTERN_SCALING_DATA_ID`. **Still a pure, unwired function:**
`pattern_scaling_forecast` — the *spatial* half needs the CMIP6-MMM normalized warming
pattern, which upstream PR #44 supplies, so `_eof_pattern_scaling_row` emits a `reason`
naming it instead of a score.

**Leaderboard (`leaderboard/__init__.py`).** `build_scores` classifies `metrics` rows
into gates (a **row** with `passes` and no `p_value`, plus declared-N/A rows with
`applicable = 0` — the test is per row since 2026-09-14, because the pass writes
consistency rows carrying both columns into the same tables), CRPS (`crps`, **plus
every row the pass wrote — a NaN score with a `reason` is a result to show** — minus
the consistency rows), consistency (`p_value`), deterministic (`weighted_*`) and
Tier III (`*_site_consistency` in `raw_output`), filling `requirement`/`applicable`
from the gate classes for databases written before those columns existed. Every frame's
`data_id` is then relabelled by **model name** through the `data_sources` tables
(`_label_by_model`), so a model whose Tier I rows carry the full data-source id and
whose Tier II rows carry the name is **one row everywhere** (and its members collapse
into one gate row, which is what a gate means: every member must pass).
`render_html` writes a
self-contained static page: the Tier I scorecard in its three groups (Required with the
`Entry ticket` column, Extended, extra), the **Tier II skill table** (✅ 2026-09-14),
the Tier II event flags, the consistency table and the Tier III fractions.
The Tier II table shows, per model and variable, the headline
`S = 1 − E/E_ref` against the CMIP6 median — **clipped at −1 for display** (▼), per
the paper — with the Climatology-baseline skill in small text underneath, the fair
CRPS, its bootstrap interval, SE and ensemble size in the cell tooltip,
`n/a (single member)` where the protocol cannot score, and a final row giving the
number of CMIP6 models behind `E_ref`. Where no comparison ensemble exists (today's
normal case) the cell falls back to the raw CRPS and says so in the tooltip.
`build_scores_table` reuses ClimateEval's `build_leaderboard_data` for the
deterministic CSV summary (`--csv`, unchanged). Still missing versus the paper's
scorecard (§5.6): held-out/in-sample labels, per-region resolution, the
"non-conforming" category.

**Mapping to the Tier II spec (2026-09-14, after gap item 3b).** Present: **fair CRPS
with the M = 1 rule**, **member stacking by model name**, ESS-corrected SE, **moving-
block bootstrap**, **observational-uncertainty draws that now bite** (a `tier2.obs_sigma`
floor plus the measured spread across observational products), **CMIP6-median `E_ref`
with leave-one-out**, the climatology baseline on the 1985–2014 window *with that window
actually in the database*, **regime (b) as fair CRPS on the reference's fixed pre-2015
EOF basis**, the consistency test **with a real σ_int from piControl chunks**, one label
per model across the tiers, and the static leaderboard with the skill table.

Added by **gap item 6 (work package 6a)**: the **aggregated-scalar regime** of the pass,
the **realized warming level** and the two GMST trends, the **GSAT blending
correction**, the Pinatubo and hemispheric-asymmetry magnitudes as *scored* scalars with
HadCRUT5 references, the **held-out / in-sample label** on every row (and held-out-first
ordering in the leaderboard), **per-member runs of the events suite**, and the Tier II
suite's missing variables (clear-sky TOA, `clwvi`/`clivi`, OHC 0–100 m) — together with
the per-variable-reference fix without which most of those suite variables were never
scored at all.

Added by **work package 6b** (`ce509c3`, `d8df85b`, `74a4841`): the eight **ETCCDI
extremes** as aggregated scalars on the 1° conservative grid, the **Perkins**
PDF-overlap skill as a metric with its own leaderboard table, the three
**seasonal-cycle** metrics, the **diurnal** first harmonic in local solar time
(phase as (cos, sin)), the **pattern-scaling baseline** for GMST-type series —
ERF-driven, one parameter calibrated through 2014, pseudo-members so fair CRPS
is defined — and the daily suite's move to the **full historical record**.

Absent or misaligned: a **regime-(b) climatology baseline** (it would be the projections
of each baseline year's own anomaly field, which the EOF diagnostic does not emit); the
**spatial** half of pattern scaling (the CMIP6-MMM warming pattern, upstream PR #44 —
a `reason` row says so); a real observational **error field** (every σ_obs value is a
provisional protocol constant — see the ⚠ in the status table — as are the GSAT blending
factor and the packaged ERF table); **a daily observational product**, without which the
ETCCDI extremes are computed but unscored; sea-ice **extent** rather than area; and —
**the binding constraint on every Tier II number** — the post-2015 multi-member CMIP6
reference ensemble (an upstream ClimateEval gap: without it `E_ref` has no models with
M ≥ 2 and the skill column is empty, in every regime).

**Target pseudocode for regime (b) as built:**
```python
# once, from the reference alone, over 1985-2014 — fixed for every submission
anom   = anomalies(regrid(ref_pre2015), period="month")        # (T, lat, lon)
basis  = eof_basis(anom[:, valid], weights=coslat[valid],      # SVD, area-weighted
                   variance_explained=0.9, max_modes=20)       # -> K modes, pc_std
clim   = time_mean(ref_pre2015)                                # baseline climatology

def coefficients(source):                                      # per member / product
    return standardised_coefficients(basis, (time_mean(source) - clim)[valid])

x = np.vstack([coefficients(m) for m in members])              # (M, K), M >= 2
y = coefficients(reference_test_window)                        # (K,)
crps_k = crps_fair(x, y)                                       # per coefficient
E      = crps_k.mean()                                         # equal-weight over modes
lo, hi = moving_block_bootstrap_ci(crps_k, block_length=1)     # ESS = K (CB2 reading)
S      = 1 - E / median(E_m for m in CMIP6 if m is not model)
```

**Target pseudocode for regime (a) as specced:**
```python
fc  = model_anom(ensemble=..., time=...)       # 2015..present, monthly anomalies, M >= 2
obs = obs_anom(time=...)
crps_t = crps_fair(fc, obs, member_dim="ensemble")   # fair: spread term / (M(M-1))
r1 = lag1_autocorr(crps_t - crps_t.mean())
T_eff = len(crps_t) * (1 - r1) / (1 + r1)
score = crps_t.mean();  score_se = crps_t.std() / np.sqrt(T_eff)   # ESS on the SE only
```

**OHC.** Provided by ClimateEval's `OceanHeatContentTimeSeries` on the derived
`phcint` variable (0–2000 m via `esmvalcore.preprocessor.extract_volume`), scored with
ClimateEval's deterministic metrics against EN4/IAP; the legacy gsw/TEOS-10 derivation
is gone. Add the 0–100 m stanza and route the series through
`ScoredAnnualMeanTimeSeries` for regime (a).

## II.1 Per-diagnostic specs (regime and formulas)

Each item below inherits the scoring machinery of §II.0 — fair CRPS for time-resolved
quantities (a) or for projected EOF coefficients (b), with the consistency test (c) as a
complementary diagnostic.
Provider column in the status table; spec + pseudocode + a one-line status here.

**GMST warming rate (REVISED 2026-09).** The **primary scalar diagnostic for the test
window is the realized warming level**, not the trend within it: the mean global-mean
surface temperature anomaly over all complete years from 2015 onward, relative to the
fixed **1985–2014** pre-test baseline. Over a single decade the OLS trend is dominated
by internal variability, whereas the mean level is an integrated, variability-robust
measure of the recent warming rate — and is the same quantity whose information content
is demonstrated in the paper's Section 3 idealized experiment.
- **Test window:** realized warming level (primary); test-window OLS trend reported as a
  **secondary** diagnostic.
- **Full historical (1950–present):** OLS trend, where the record is long enough that
  trend uncertainty is acceptable.
- References: GISS / Berkeley Earth / HadCRUT5; observational uncertainty from the spread
  across, and stated uncertainties of, the three products.
- Reported as a **consistency (falsification) statement** as well as a score — see §(c).

**Blending correction (NEW 2026-09).** The observational products blend land air and sea
surface temperatures, whereas model `tas` is a surface air temperature diagnostic.
**Correct the observations to a surface-air-temperature basis** rather than constructing
blended, coverage-masked model fields (which would require `tos` and `siconc` that not
all architectures produce). Carry the correction uncertainty — assessed as at most 10% of
the long-term change, with low confidence in its sign — in the **observational variance
term**.

*Status: ✅ (2026-09-14, gap item 6, `5185c72` + `9d4b7a9`; the secondary trend already
done in gap item 3b).* `diags/tier2_diagnostics.py::RealizedWarmingLevel` is a complex
diagnostic on the `historical` key in `ClimateBench2_TierII_events`, and that suite is
now **per-member** (`_cli.SuiteSpec.per_member`), so each ensemble member contributes
its own record and its own value of each scalar:

- ✅ **`gmst_warming_level`** — the mean global annual-mean `tas` over the complete years
  from `tier2.test_window_start` to the end of the record, minus the fixed
  `tier2.climatology_baseline_period` (1985–2014) mean. **Primary**, labelled
  *held-out*. A submission whose record stops before 2015 (a plain CMIP6 *historical*
  run) gets a logged warning and no such row.
- ✅ **`gmst_trend_test_window`** — OLS K/decade over the same years. Secondary,
  *held-out*.
- ✅ **`gmst_trend_1950`** — OLS K/decade from `tier2.long_trend_start` = 1950 to the
  record end, labelled *in-sample*. `long_trend_first_year`/`_last_year` are emitted so
  a record that starts after 1950 is visible rather than taken on the name's word.
- ✅ **Reference values** from **HadCRUT5** (`climateeval.data.HadCRUT5`), fetched once
  over 1950–present through the DataSource and emitted as `data_type = "reference"` rows
  by the new `ObservedScalarMixin` — the piece that was missing, since a complex
  diagnostic has no suite `reference_data:` and so had nothing to be scored against.
  ⚠ *Upstream gap:* GISTEMP, Berkeley Earth and NOAAGlobalTemp — the paper's other three
  products, and the source of its inter-product observational spread — have **no
  ClimateEval DataSource**. The pass's multi-product σ_obs machinery needs no change to
  use them; they only have to appear as observational sources.
- ✅ **Blending correction.** The observed *anomalies* (against the same 1985–2014
  baseline) are multiplied by `tier2.gsat_blending_factor`, so the correction scales the
  warming level and both trends and leaves absolute levels alone;
  `tier2.gsat_blending_relative_uncertainty` of the corrected value is emitted as that
  scalar's `_sigma_obs` companion and enters both the fair-CRPS draws and the
  consistency test's σ_obs.
  ⚠ **Provisional, TODO(Duncan):** the factor **1.09** (≈ 9 % more warming for SAT than
  for a blended product; Cowtan et al. 2015, Richardson et al. 2016) and the **10 %**
  uncertainty — and CB2's reading of "10 % of the long-term change" as 10 % of the
  corrected statistic's own magnitude.
- ✅ **Scoring.** `scoring_pass.score_scalar_output` (§II.0) takes the fair CRPS across
  the members against the observed value and writes the **consistency statement** §II.1
  asks for alongside, with σ_int from `InternalVariability` via
  `tier2.scalar_consistency`.
- ❗ Unexercised on real data: like every observation-fetching CB2 diagnostic, the
  HadCRUT5 branch has only ever run against synthetic cubes.

```python
wl_m  = [gmst(m, 2015, None).mean() - gmst(m, 1985, 2014).mean() for m in members]
wl_ob = obs_gsat_corrected(2015, None).mean() - obs_gsat_corrected(1985, 2014).mean()
score = crps_fair(wl_m, wl_ob)
wl_pi = [seg.mean() for seg in chunk(gmst(piControl), n_years_obs)]
z = (wl_ob - mean(wl_m)) / sqrt(var(wl_m) + var(wl_pi) + sigma_obs**2 + sigma_blend**2)
consistent = abs(z) < 1.96
```

**Pinatubo response.** 1991–93 anomalies (vs the 1985–2014 climatology, ENSO-regressed-out
optional) of global `rsds` and `tas`; test joint co-variation (e.g. regression of tas
lag response on rsds dimming, or 2-D consistency of [Δrsds, Δtas]). Aggregated
diagnostic (§II.0(b)).
Historical simulations include Pinatubo forcing, so 2015+ window does not apply here;
use historical members.

*Status: 🟡 (2026-09-14, gap item 6, `9d4b7a9`).*
`diags/tier2_diagnostics.py::PinatuboResponseGate` (`historical` key, **per member**):
global-mean `rsds` and `tas` anomalies for Jul 1991–Dec 1993 relative to the
`tier2.climatology_baseline_period` [1985, 2014] mean. The two sign flags remain
(`pinatubo_dimming`: Δrsds < 0; `pinatubo_cooling`: Δtas < 0), tagged
`tier2.pinatubo.requirement: diagnostic` in `ClimateBench2_TierII_events.yml`, so they
are reported under Tier II and never gate entry.
- ✅ **`pinatubo_tas_anom` is now scored**: the diagnostic emits the observed anomaly
  from **HadCRUT5** over the same window and the same baseline, corrected to a SAT
  basis, as a `reference` row, and `score_scalar_output` writes the fair CRPS across the
  members plus the consistency row (σ_int keyed `(tas, mean, test)` in
  `tier2.scalar_consistency` — the event window is ≈ 2.5 yr, shorter than either σ_int
  window, so the nearest is an *under*-estimate and the test is conservative). Labelled
  **in-sample**: 1991–93 sits inside the historical record.
- ❌ **`pinatubo_rsds_anom` stays a model-only sign flag** — ClimateEval has no BSRN or
  CERES-SYN DataSource, so there is no observed magnitude to score against; the pass
  skips a scalar whose reference carries no value, and the class, the suite YAML and
  `suites/README.md` each record why.
- ❌ Still no joint [Δrsds, Δtas] co-variation test and no ENSO removal.

Note that the gate machinery applies the sign checks to *every* data source the
diagnostic wrote, so HadCRUT5 now also carries a `pinatubo_cooling` row — the same
"observations sanity-check the thresholds" behaviour the ENSO gates have always had.

**Surface fluxes (NEW 2026-09).** Observation-based synthesis products (CERES SYN,
OAFlux, HOAPS) do not close the global energy budget (residuals O(10) W/m²), and
reanalyses close it by construction rather than by physical fidelity, disagreeing with
in situ measurements and each other by 5–15 W/m² regionally. Therefore:
- score surface fluxes on **spatial pattern and seasonal-cycle statistics** (anomalies
  relative to the local climatological mean), **not absolute magnitudes**;
- retain **point-wise** diurnal and seasonal-cycle evaluation at the in situ networks
  (AmeriFlux/FLUXNET, OceanSITES, BSRN), with site-level observational uncertainty added
  to the internal-variability spread in the consistency test;
- report **ERA5 as a cross-reference alongside** the observational scores, never as the
  primary reference.
- There is **no global-mean surface-flux closure test** in Tier II; global energy closure
  is tested at TOA in Tier I (I.1), where CERES-EBAF is trustworthy.

*Status: ❌* (Extended). `rsds`/`rsus`/`rlds`/`rlus`/`hfss`/`hfls` load fine (they feed
I.2/I.8) but no Tier II stanza, no obs DataSource (CERES SYN, FLUXNET, OceanSITES) and no
site-sampling machinery exists.

**Hemispheric asymmetry.** NH−SH tas trend difference over 1950–1985 (aerosol era) and
the associated tropical precipitation (ITCZ) southward shift; scored as an aggregated
diagnostic (§II.0(b)) against
HadCRUT/GPCP-era reconstructions.

*Status: 🟡 (2026-09-14, gap item 6, `9d4b7a9`).* `HemisphericAsymmetryGate`
(`historical`, **per member**): NH and SH area-mean annual `tas` OLS trends over
`tier2.hemispheric_asymmetry.era` = [1950, 1985] (`physics.ols_trend`; the era is a
threshold, not a class constant), `nh_minus_sh_trend` gated < 0; ITCZ = latitude of the
annual zonal-mean `pr` maximum within ±30°, its trend (°/decade) gated < 0. Both flags
run in `ClimateBench2_TierII_events.yml` with `requirement: diagnostic`, so they are
reported under Tier II rather than counted in the entry ticket.
- ✅ **`nh_minus_sh_trend` is now scored against HadCRUT5** over the same era, on a SAT
  basis — a multiplicative blending correction scales a hemispheric *difference* just as
  it scales a global mean — with the fair-CRPS row and the consistency row
  `score_scalar_output` writes for any aggregated scalar (σ_int keyed `(tas, trend,
  long)`: the 36-yr aerosol era is nearer the 1950-present window than the test one).
  Labelled **in-sample**.
- ❌ **The ITCZ shift stays a model-only sign flag**: GPCP begins in 1979, well after
  the aerosol era, so there is no observed counterpart to score against. Berkeley Earth
  (which would give a second temperature product) has no ClimateEval DataSource.

**Seasonal-cycle metrics.** (i) climatological annual range of tas over land
(max−min of 12-month climatology, land-masked, area-mean or EOF-projected map);
(ii) seasonal amplitude of land carbon uptake (`nbp`; peak-to-trough of climatological
cycle vs atmospheric-inversion products); (iii) SST–low-cloud seasonal covariance
(regression of low-cloud fraction on SST over the seasonal cycle in stratocumulus
regions). All aggregated diagnostics (§II.0(b)).

*Status: ✅ (2026-09-14, work package 6b, `d8df85b`).* All three are complex
diagnostics on the `historical` key in the **per-member** events suite, emitted as
aggregated scalars and scored by `score_scalar_output` against observational
`reference` rows:

- **(i) `land_annual_temperature_range`** — `LandAnnualTemperatureRange`:
  `mask_landsea(cube, "sea")`, the 12-month climatology, then **max − min at each
  land grid point** and a cos-weighted area mean. The order matters: the range of
  the *area-mean* cycle would cancel the hemispheres against each other and come
  out several times too small. Reference **ERA5Monthly** `tas`
  (`VARIABLE_MAPPING` has `2m_temperature`). ⚠ once upstream PR #49 lands, **CRU
  TS** is the better land-only reference.
- **(ii) `sst_low_cloud_slope_<deck>`** — `SSTLowCloudCovariance`: in each of the
  five `tier2.seasonal.stratocumulus_regions` boxes (Californian, Peruvian,
  Namibian, Canarian, Australian — ⚠ TODO(Duncan) to confirm), the 12-month
  climatologies of `clt` and `tos` are area-averaged over the box and regressed
  (12 points), giving one slope per deck plus their unweighted **mean**, which is
  the headline number. References **ESACCI-CLOUD** + **ESACCI-SST**.
  ⚠ **`clt` is the low-cloud proxy.** A genuine low-cloud fraction needs `cl`
  with a level selection (or an ISCCP simulator), which needs a model-level
  coordinate not every submission has and an observational product with a
  matching level definition. In the decks total cover *is* essentially low cloud
  — which is why the decks are the region the constraint is evaluated over — but
  under cirrus the proxy is biased.
- **(iii) `seasonal_swcre_slope_<deck>`** — `SeasonalCloudRadiativeFeedback`: the
  same regression with **`swcre`** (a *derived* variable in ClimateEval's
  registry, so neither CB2 nor the model has to difference fluxes) in place of
  `clt`. References **CERES-EBAF** + **ESACCI-SST**. This is the §5.2
  emergent-constraint diagnostic.

All three are taken over the fixed `tier2.climatology_baseline_period`
(1985–2014) so every submission and every product sees the same years, and are
labelled **in-sample**; the window is emitted as
`seasonal_window_first/last_year` on the *model* side only, which keeps it
provenance rather than a scored statistic (the pass scores a scalar only where
the reference carries a value). A record that does not cover the window is used
whole with a warning — a seasonal cycle is far less window-sensitive than a
trend. `ObservedScalarMixin` grew a per-fetch `source` argument and an
`_observation_products` list for this: (ii) and (iii) regress **two** observed
fields against each other, so the `reference` row is written under the primary
product and every product read is registered in `data_sources`.
(ii)′ the seasonal amplitude of land carbon uptake (`nbp`) stays deferred by the
paper — no carbon-cycle output is requested of a submission.

**Diurnal cycle.** Amplitude and phase (first harmonic fit) of 3-hourly tas and pr
climatologies vs observational products; aggregated diagnostic (§II.0(b)) on amplitude
and phase separately.
```python
harm = fit_first_harmonic(clim_3hourly)   # A*cos(2*pi*t/24 - phi)
test_consistency(A_obs, A_members); test_consistency(phi_obs, phi_members)  # circular
```

*Status: ✅ (2026-09-14, work package 6b, `ce509c3` + `d8df85b`).*
`diags/tier2_daily.py::DiurnalHarmonic`, suite entry `diurnal_harmonic`:

1. regrid to `tier2.diurnal.grid`, then
   **`esmvalcore.preprocessor.local_solar_time`** — the "shift each longitude
   column by lon/15 h" the protocol asks for. Without it an area mean over the
   tropics cancels the diurnal cycle almost exactly, which is the whole reason
   the statistic is specified in LST;
2. per season in `tier2.diurnal.seasons`, the mean cycle over the day
   (`climate_statistics(..., "hour")`), area-averaged over each
   `tier2.diurnal.regions` latitude band;
3. `physics.first_harmonic`, **generalised from 12 points to any sampling**
   (24 hourly, 8 three-hourly), giving amplitude and phase in the input's own
   step.

Columns are `<variable>_<region>_<season>_amplitude`, `…_phase_cos` and
`…_phase_sin`. The land/sea contrast that makes the diagnostic worth computing
is a **mask**, so the suite declares it per variable (`pr_land` / `pr_ocean`
with `landsea_mask`), and the band comes from `thresholds.yml`.

⚠ **CB2 interpretation — the phase is scored as (cos, sin), never as hours.**
Fair CRPS is a distance on the real line, so it would call 23 h and 1 h 22
hours apart, and the mean of an ensemble of angles is not the mean of its
values. CB2 therefore scores the two components of the unit vector
(`physics.phase_components`), each an ordinary number, and emits **no hour
column at all** so nothing downstream can score the circular quantity by
accident. The phase in hours is `atan2(sin, cos)·n/2π mod n`.

Reference **ERA5Hourly** `pr` (IMERG ❌, CERES-SYN ❌ upstream), so this entry
*is* scored. `swcre`/`netcre` join it wherever a model supplies 3-hourly TOA
fluxes; they are not wired by default because no sub-daily observational CRE
product exists upstream to score them against.

**Daily tas extremes / pr intensity PDF.** Annual TXx/TNn-type block maxima or tail
quantiles (tas), and daily-pr histogram/quantile comparison (e.g. CRPS on annual
quantile series, or consistency test on PDF summary statistics like wet-day frequency,
99th percentile). Requires `day`-table data throughout the stack.
The paper (§5.2, 2026-09) now fixes the set: **TXx, TNn, TX90p, warm-spell duration;
Rx1day, Rx5day, R95pTOT, consecutive dry days** (ETCCDI), each a climatological scalar
(and trend) per region scored as an aggregated diagnostic; PDF shape by the **Perkins
skill score** on anomalies relative to a moving climatological baseline, wet days ≥ 1
mm/day, pre-registered bin widths; everything after **conservative regridding of model
and obs to a common ~1° grid**; labelled in-sample.

*Status: ✅ computed, ❌ unscored (2026-09-14, work package 6b, `ce509c3` +
`d8df85b`).* `diags/tier2_daily.py::ETCCDIExtremes`, suite entry `extremes` in
`ClimateBench2_TierII_daily`, which now runs over the **full historical record**
(`_cli.SUITE_REGISTRY` gives it `window: full`) because that is what the paper
computes these over, and is therefore labelled in-sample throughout.

Per suite variable (daily `tasmax`, `tasmin`, `pr`, each `landsea_mask:
land_only` — ETCCDI indices are station-derived **land** indices, and masking is
ClimateEval's job):

1. **conservative regrid** to `tier2.extremes.grid` = `1x1` with
   `regrid_scheme: area_weighted` — the paper's "conservative regridding of
   model and obs to a common ~1 degree grid";
2. the index **per year, per grid point**, in pure numpy
   (`climatebench2.physics`, unit-tested on arrays whose answer is known by
   construction): `annual_extreme` (TXx/TNn), `calendar_percentile` +
   `exceedance_fraction` (TX90p), `spell_duration_days` (WSDI, spells found over
   the whole record so New Year does not break one in two, days counted in their
   own year), `annual_max_running_sum` (Rx1day/Rx5day),
   `wet_day_percentile` + `heavy_precipitation_fraction` (R95pTOT) and
   `max_consecutive_dry_days` (CDD, truncated at the year boundary);
3. a cos-weighted mean over each `tier2.extremes.regions` latitude band
   (global / tropical / NH- and SH-extratropical land);
4. that annual regional series reduced to a **climatological mean** and an
   **OLS trend per decade** — the two scalars per (index, region), written in the
   aggregated-scalar shape `score_scalar_output` reads.

⚠ **Choices to confirm.** The TX90p/WSDI threshold is the base-period
(`tier2.extremes.base_period` = 1985–2014) percentile **per calendar month**, not
per calendar day: the ETCCDI calendar-day form needs a 5-day window and Zhang et
al.'s bootstrap to avoid an inhomogeneity at the base-period edge, which a
monthly threshold sidesteps at the cost of a slightly smoother annual cycle of
the threshold. R95pTOT divides by the **annual total** precipitation (the
reading of "fraction of annual precipitation"), not the wet-day total. A record
that does not overlap the base period falls back to its own record for the
thresholds, with a loud warning, because the alternative is no index at all.

❌ **No observational reference exists, so these are reported model-only and
unscored.** `ERA5.VARIABLE_MAPPING` has `tas` and `pr` but **no `tasmax`/`tasmin`**,
and `ERA5Hourly`'s CDS request is hard-wired to a single year, so no ClimateEval
DataSource can serve daily temperature extremes however the `Variable` is
spelled. The `extremes` entry therefore carries no `reference_data:`, and the
pass — which scores a scalar only where the reference has a value — leaves them
as reported numbers. This is the documented state, not an accident: the shape is
already the scored one, so the day a **HadEX3** DataSource lands upstream (its
ESMValTool CMORizer already exists) the suite needs one line. Berkeley daily,
HadGHCND, IMERG and MSWEP have no DataSource either. The precipitation indices
*could* be referenced against `ERA5Hourly` `pr` through `daily_statistics`; the
suite carries that stanza **commented out** rather than scoring a model against
one ERA5 year.

❗ Memory: the whole daily record is realised as one `(time, lat, lon)` array on
the 1° grid — fine for a few decades, heavy for a full historical run. Like the
other daily diagnostics (I.3b, I.5d) this has only been exercised on synthetic
cubes. The older `ScoredAnnualMaxTimeSeries` global-mean TXx series
(`tasmax_txx`, against the `ERA5Monthly` placeholder) survives as a familiar
deterministic display. Also see the ClimateEval variable `prw`/`pr` `3hr`
frequencies for the Extended sub-daily list (Table A2).

**Baselines.** (i) **CMIP6 MME — the headline reference**: `E_ref` = median of the
per-model fair CRPS (see §II.0). (ii) climatology persistence: forecast = **1985–2014**
monthly climatology — the no-skill floor, reported alongside. (iii) pattern scaling:
ΔT_global(t) from a 2-layer EBM calibrated to observations **through 2014** × CMIP6 MMM
normalized warming pattern (+ climatology) — the simplest defensible emulator, reported
alongside. All three run through the identical scoring pipeline, but only (i) sets the
headline `S`.

*Status: 🟡.* (i) ✅ **median of the per-model fair CRPS with leave-one-out**
(2026-09-14, `732e860`; the pooled `CMIP6-MME` row is deleted) — but numerically empty
until the upstream multi-member CMIP6 generator lands, and pending the paper's own
§5.4 mixture-vs-median fix; (ii) `Climatology` row wired from
`tier2.climatology_baseline_period` = ✅ [1985, 2014], scored as the **distribution**
of that window's per-calendar-month values (⚠ CB2 interpretation, Tier II preamble);
(iii) ✅ **the GMST half is wired and calibrated** (2026-09-14, work package 6b,
`ce509c3` + `74a4841`), 🟡 the spatial half is not:

- `baselines.load_erf_series` reads the packaged annual ERF table
  `climatebench2/data/erf_ar6_ssp245.csv` (⚠ **provisional**: a linear
  interpolation of published AR6 anchor values, **no natural forcing** — no
  volcanic pulses, no solar cycle — and not the AR6 annual series itself. The
  file's own header carries the anchors, the consequences and a TODO(Duncan) to
  replace it with the digitised AR6 Ch.7 / Annex III series);
- `baselines.calibrate_two_layer_ebm` fits **exactly one** parameter — the
  feedback λ by default, or a scaling of the forcing
  (`tier2.pattern_scaling.calibrated_parameter`, bounded by `lambda_bounds`) —
  by least squares to the observed GMST through
  `tier2.pattern_scaling.calibration_end_year` = 2014, with **both** series
  reduced to anomalies about the 1985–2014 window so the EBM's arbitrary
  absolute level cancels. One degree of freedom is deliberate: the emulator has
  to stay the "simplest defensible" reference rather than a tuned competitor;
- ⚠ **CB2 interpretation.** A deterministic emulator is M = 1 and fair CRPS is
  undefined for it, exactly as for the climatology. `baselines.ebm_pseudo_members`
  therefore displaces the trajectory by the **detrended observed residuals of the
  baseline window** — one pseudo-member per baseline year. The members differ by
  a constant offset: the ensemble says "we do not know which phase of internal
  variability the real world is in", not that the emulator simulates noise.
  Either the manuscript adopts this reading or the baseline needs another score;
- `scoring_pass._pattern_scaling_row` writes it as the `PatternScaling` row for
  the variables of `tier2.pattern_scaling.variables` (`tas`/`ts`/`tos`) — scored
  on the **test window only**, never on the years it was calibrated to, with the
  fitted parameter carried in the row's `value`. The pre-2015 observations it
  needs come from the same `ReferenceBaselineRecord` rows the climatology uses,
  so a database cut to the test window still has them. A variable the EBM says
  nothing about (pr, fluxes, sea ice) gets **no row**; one that qualifies but
  cannot be fitted gets a `reason` row, so the absence is visible;
- ❌ the **spatial** pattern — the mean over comparison models of
  (test-window map − baseline map)/ΔGMST — needs CMIP6 baseline-window maps that
  the EOF diagnostic does not emit and that no post-2015 CMIP6 member exists for.
  `baselines.pattern_scaling_forecast` is the arithmetic;
  `scoring_pass._eof_pattern_scaling_row` emits a `reason` row naming **upstream
  ClimateEval PR #44** rather than letting the baseline disappear from the
  scorecard.

---

# Tier III — Paleoclimate time-slices and perfect-model tests

## Tier III status summary

| Diagnostic | Spec (short) | Protocol status | Impl. (2026-09-14, gap item 7) | Code |
|---|---|---|---|---|
| lig127k vs proxies | PMIP4 BCs; Osman 2026 / Hoffman 2017 SST; Otto-Bliesner 2021 land T; Scussolini 2019 (+ SISALv3) precip | **Extended** | ✅ wired to the pipeline: `PaleoProxyScore` stanzas for **Otto-Bliesner 2021 `tas`** (92 sites) and **Scussolini 2019 `pr`** (manual download; no `pr_std`, so it writes a reason). Hoffman 2017 and SISALv3 are `NOT_SCOREABLE` with their reasons; Osman 2026 has no public archive | `diags/tier3_paleo.py`; data via `paleo_scripts/` |
| lgm vs proxies | Tierney 2020 / Osman 2021 SST; Bartlein 2011 / Cleator 2020 land T | **Required** | ✅ **Tierney 2020 `tos`** (512 sites, the raw compilation behind lgmDA), **Bartlein 2011 `tas`/`pr`** (gridded pollen) scored; **Cleator 2020 `tas`/`pr`** computed and reported but tagged `data_assimilation` and excluded (App. D). The lgmDA / LGMR *fields* are left out of the suite entirely — Tierney 2020 is their raw input, and scoring both double-counts it. Osman 2021's site file is uncalibrated geochemistry, so it is `NOT_SCOREABLE` | same |
| midHolocene vs proxies | Osman 2021 SST 5–7 ka; Temp12K; Bartlein 2011 tas + water balance | **Extended** | 🟡 **Bartlein 2011 `tas`/`pr`** scored; **Temp12k** has a live stanza that writes a reason — the processed file is a *latitude-band ensemble* (method × latband × age × member), which needs a zonal-mean comparison rather than site sampling (**deferred**); Osman 2021 MH SST uncalibrated as above | same |
| midHolocene North-Africa monsoon check | JJAS pr anomaly ≥ +0.5 mm/day, 10–30N, 20W–30E, vs piControl | Extended (with midHolocene) | ✅ `MidHoloceneMonsoonGate`, now also reporting the model's **annual**-mean North-Africa anomaly and, beside it, the **Harrison & Prentice 2015** observed magnitude (`northafrica_pr_anom_obs_mmday`) when the pipeline has processed it — reported, never gated, because Harrison is an annual profile and the gate is JJAS | `diags/tier3_paleo.py` |
| Proxy-aware scoring | **Fair CRPS vs proxies**, proxy error in the observational variance term; pseudo-members from non-overlapping equilibrated blocks | — | ✅ `scoring.proxy_crps` — per-site fair CRPS with σ_proxy as the observational variance term (the same common draws as Tier II), equal-weight mean over sites — on the pseudo-ensemble `scoring.block_climatologies` builds from `nonoverlapping_blocks` of the equilibrated run. ✅ the site-consistency fraction survives as the complementary diagnostic, now with the pseudo-member spread in its denominator. 🟡 `paleo_benchmark.py` still computes the inverse *Gaussian* CRPS for the AR6-style figures (#19) | `scoring.py`, `diags/tier3_paleo.py` |
| Perfect-model: CESM2 train→SSP2-4.5 daily tas/pr, Tier II scoring | **Required (ML only)** | | 🟡 **structure, no data**: `score --truth DIR [--truth-member LABEL=PATH]` swaps the cube suites' `reference_data:` to `diags.truth_reference.LocalCMORReference` (a thin `load_cmor_dir` adapter; upstream candidate) via a materialised suite YAML, drops the CMIP6 comparison models, zeroes σ_obs and labels every row `window = perfect-model`. CESM2/MPI-ESM/GISS-E2 staging is **pending** | `diags/truth_reference.py`, `_cli.py` |
| Perfect-model: MPI-ESM, GISS ModelE2 | **Extended (ML only)** | | 🟡 the same path, just a different `--truth DIR`; no data | same |
| Large-ensemble spread test vs CESM-LE (variance ratio + spatial corr of inter-member variability) | **Extended** | | 🟡 wired: `scoring_pass.le_spread_rows` runs both statistics whenever truth members are in the database, gates the ratio at `tier3.le_spread.variance_ratio_range` [0.5, 2.0] (**TODO bound**) as a Tier III Extended check and reports the correlation unbounded. Synthetic databases only — no CESM-LE | `scoring.py`, `scoring_pass.py` |

## III.1 Paleo time-slices (lig127k, lgm, midHolocene)

**Measures.** Out-of-sample generalization: can the model reproduce climates far from
the instrumental record, given PMIP4 boundary conditions (orbit, GHG, ice sheets)?

**Spec.**
- Experiments: PMIP4 `lig127k`, `lgm`, `midHolocene`; anomalies vs the model's own
  piControl.
- Proxy targets (paper Appendix D, 2026-09 — **raw proxy data, not the assimilated
  global products**, whose spatial covariances come from the models used in the
  assimilation): LGM — Tierney et al. 2020 and Osman et al. 2021 SST compilations;
  Bartlein et al. 2011 pollen land T and/or Cleator et al. 2020 (noting the latter is a
  DA product). LIG — Osman et al. 2026 updated SST compilation (building on Hoffman et
  al. 2017); Otto-Bliesner et al. 2021 terrestrial T; Scussolini et al. 2019
  terrestrial precipitation (Table 3 also lists SISALv3, Kaushal et al. 2024).
  mid-Holocene — Osman et al. 2021 5–7 ka SST averages; Temp12K (Kaufman et al. 2020);
  Bartlein et al. 2011 temperature and water balance; Harrison et al. 2015 Saharan
  lake status for the monsoon check.
- Scoring: **fair CRPS against the proxy reconstructions** (the same primary score as
  Tier II), with the large proxy uncertainties entering as the observational variance
  term; evaluate at proxy sites or on low-order EOFs / zonal means. For a single-member
  equilibrium experiment, **pseudo-members and pseudo-observations are drawn from
  non-overlapping blocks of the equilibrated portion of that experiment**, block length
  matching the scored climatology (paper §5.1). The ensemble-consistency test is
  reported as a complementary diagnostic. Comparisons are **seasonal climatological
  anomalies**.
- **Protocol status:** LGM **Required**; LIG and mid-Holocene **Extended**
  (set 2026-09).
- Specific hard requirement: **mid-Holocene JJAS precipitation anomaly ≥ +0.5 mm/day
  over North Africa (10–30N, 20W–30E) vs piControl** (Green Sahara / monsoon
  amplification).

```python
# per period p in {lig127k, lgm, midHolocene}:
anom = clim(exp_p) - clim(piControl)                     # per variable (tas, tos, pr)
members = [clim(block) - clim(piControl) for block in nonoverlapping_blocks(exp_p)]   # pseudo-ensemble
model_at_proxy = sample_at(members, proxy_sites)
score_p = mean(crps_fair(model_at_proxy[:, s] + N(0, sigma_proxy[s]), proxy_val[s]) for s in sites)
z = (proxy_val - ens_mean(model_at_proxy)) / sqrt(var_ens + sigma_proxy**2)   # complementary
# mid-Holocene monsoon check:
dP = (clim_JJAS(midHolocene.pr) - clim_JJAS(piControl.pr)) * 86400
passes = area_mean(dP.sel(lat=slice(10,30), lon=slice(-20 % 360 ... 30))) >= 0.5
# note: 20W-30E crosses lon=0; handle 0-360 wraparound explicitly
```

**Status: ✅ wired to the pipeline and scored (2026-09-14, gap item 7).**
- ✅ `diags/tier3_paleo.py::MidHoloceneMonsoonGate` (`midholocene` + `picontrol`):
  `extract_region` 340–30°E × 10–30N (wrap handled), `climate_statistics(period="month")`,
  JJAS cos-weighted mean, anomaly × 86400 gated ≥ `tier3.midholocene_monsoon.jjas_pr_anom_min`
  = 0.5 mm/day (row `midholocene_monsoon`). Matches the spec. It now also emits the
  model's **annual**-mean North-Africa anomaly and the observed magnitude from
  **Harrison & Prentice 2015** (`Harrison2015_pr.nc`, a latitudinal mm/yr profile
  cos-weighted over 10–30N and converted to mm/day) as
  `northafrica_pr_anom_obs_mmday` — reported beside the gate, never gated with it,
  because the compilation is an *annual* anomaly and the requirement is JJAS.
- ✅ **`PaleoProxyScore`** replaces `PaleoProxyConsistencyGate` and its CSV contract.
  Per suite stanza — one (period, dataset, variable) triple, kwargs `period_key`,
  `dataset` (the file stem), `var_name`, `model_var`, `landsea_mask`, `season_months`,
  `paleo_data_root`:
  1. **pseudo-members.** The paleo run's per-year climatologies of the scored season
     are cut into non-overlapping blocks of `tier3.block_years` after dropping
     `tier3.spinup_years` (`scoring.nonoverlapping_blocks`/`block_climatologies`);
     each block mean minus the **full piControl climatology** is one member. A short
     remainder is dropped rather than averaged over fewer years. Fewer than
     `tier3.min_pseudo_members` = 2 blocks → a `reason` row, never an |x − y| fallback.
  2. **sampling.** Every member is sampled at the proxy sites with
     `scoring.sample_at_sites` (nearest gridpoint, longitude modulo 360). A *gridded*
     compilation is flattened to its own cell centres first, which is exactly
     nearest-neighbour regridding of the model onto the proxy grid — the right
     treatment for a sparse product, where interpolating invents data. Curvilinear
     2-D `lat`/`lon` (LGMR) flatten the same way.
  3. **the score.** `scoring.proxy_crps`: per-site fair CRPS with σ_proxy as the
     observational variance term through `crps_fair_with_obs_draws`
     (`tier2.obs_uncertainty` seed and draw count, so Tier II and Tier III see the
     same machinery), summarised as the **equal-weight mean over sites**
     (`tier3.site_weighting: equal` — cos-latitude weights weight grid cells, not
     cores). ⚠ the standard error is `std / sqrt(n_sites)`, which **ignores spatial
     correlation between nearby sites** and is optimistic: a CB2 reading.
  4. **the complementary diagnostic.** `scoring.proxy_site_consistency` with the
     pseudo-member spread *and* σ_proxy in the denominator (previously σ_proxy alone),
     emitted as `<period>_<dataset>_<var>_site_consistency`.
  Rows land in the diagnostic's own `metrics` table in the scoring pass's column
  vocabulary (`crps`, `crps_se`, `n_members`, `n_sites`, `dataset_type`,
  `window = held-out`), tagged `scorer = climatebench2.tier3` so that
  `leaderboard --rescore` — which deletes rows tagged `climatebench2` — leaves them
  alone. `skill`/`e_ref` stay NaN with `reason = "no PMIP4 comparison ensemble
  (ClimateEval PR #45)"`.
- ✅ **Units and masking.** The model anomaly is converted to the dataset's own units
  from its `units` attribute (`_units_factor`): temperature anomalies are identical in
  K and degC, precipitation is not — Bartlein/Harrison/Cleator publish **mm/yr**, so
  the factor is 86400 × 365.25. An unrecognised unit is a `reason` row, never an
  assumed 1 (for `pr` that would be 3 × 10⁷ wrong). The model variable carries
  ClimateEval's own `landsea_mask` (`land_only` for pollen, `sea_only` for SST), so a
  site whose nearest gridpoint is masked is dropped rather than compared to the wrong
  surface.
- ✅ **Seasonality.** Comparisons are climatological anomalies of the **annual mean**
  (`tier3.seasonality: annual`) unless a stanza names `season_months`; no processed
  dataset is explicitly seasonal today (Bartlein's MTCO/MTWA are in the source archive
  but the pipeline does not extract them), so every live stanza is annual.
- ✅ **Dataset coverage vs App. D** (`climatebench2/suites/ClimateBench2_TierIII.yml`,
  one stanza per row): LGM — `Tierney2020_tos` (site, 512), `Bartlein2011_tas`,
  `Bartlein2011_pr`, plus `Cleator2020_tas`/`_pr` **reported not scored**;
  mid-Holocene — `Bartlein2011_tas`/`_pr` and `Temp12k_tas` (reason row, see below);
  LIG — `OttoBliesner2021_tas` and `Scussolini2019_pr`. Excluded with a written
  reason, in the suite and in `tier3_paleo.NOT_SCOREABLE`: `Osman2021Proxies_proxy`
  (uncalibrated UK′37/TEX86/Mg-Ca/δ¹⁸O in native units — calibration needs the
  Bayesian forward models the pipeline deliberately does not choose),
  `SISALv3_d18O` (needs isotope-enabled output), `Hoffman2017_tos` (superseded by
  Osman 2026, which has no public archive), `Temp12k_tas` (a latitude-band ensemble,
  not a site or gridded field). The lgmDA / LGMR *fields* are omitted from the suite:
  Tierney 2020 is the raw compilation behind lgmDA, so scoring both double-counts it.
- **Still open here.** (i) A **zonal-mean comparison** for Temp12k — the only App. D
  dataset with a live stanza that cannot be scored as written; (ii) Scussolini 2019
  ships `pr_reliability`, a semi-quantitative flag rather than a σ, and needs a ruling
  on what σ_proxy should be; (iii) `block_years = 30` and `spinup_years = 100` are CB2
  defaults, not paper values (TODO(Duncan)); (iv) neither the proxy files nor the PMIP4
  model runs have been put through the diagnostic end to end — the tests build
  synthetic NetCDFs in `tmp_path` so they never depend on the gitignored data cache.
- 🟡 `paleo_scripts/paleo_benchmark.py` (the pre-protocol benchmark) still reports
  RMSE, MAE and a Gaussian CRPS whose distribution is the *proxy* (μ, σ) and whose
  "observation" is the model value — useful for the AR6-style figures, the inverse of
  the protocol's statistic (#19). Its `--use-picontrol` **no longer uses
  `benchmark_utils.DataFinder`**: it takes `--picontrol-dir DIR` and reads the run with
  plain xarray, which is what allowed `constants.py`, `utils.py`, `benchmark_scrips/`
  and `env.yml` to be deleted (delineation plan §9). The three helpers the paleo
  scripts still needed moved to `paleo_scripts/paleo_utils.py`.
- Tier III experiments enter through `--experiment midholocene=DIR` etc. (local
  CMOR directories from `download_model_data/*.sh` + `process_paleo_models.py`), and
  the proxy targets through `--paleo-data-root DIR` (default
  `tier3.paleo_data_root`); there is no ClimateEval PMIP4 DataSource generator yet —
  **upstream PR #45** adds the `lgm`/`midHolocene`/`lig127k` model generators, and a
  `PMIP4Proxies` CMORizer for the compilations is the obvious companion, which is
  where `PaleoProxyScore`'s NetCDF reading belongs in the end.

## III.2 Perfect-model experiments

**Measures.** Emulator/ML-submission validity where truth is fully known: train on one
ESM's historical output, predict its SSP2-4.5 future, score with Tier II machinery —
isolates model skill from observational uncertainty.

**Spec.**
- Truth models: **CESM2 (required)**; MPI-ESM and GISS ModelE2 (extended tier).
- Task: train on historical; predict **daily tas and pr** under SSP2-4.5;
  score predictions with the **Tier II metrics** (fair CRPS time series and
  aggregated diagnostics + the consistency flag) against the held-out truth run.
- **Large-ensemble spread test** vs CESM-LE: compare predicted inter-member spread to
  CESM-LE's — (i) **variance ratio** (predicted/true inter-member variance, per grid
  point or aggregated) and (ii) **spatial correlation** of the inter-member variability
  pattern.

```python
truth = cesm_le.ssp245.daily[["tas","pr"]]
pred  = submission.predict(hist_train)                    # ensemble of trajectories
tier2_scores = run_tier2(pred, obs=truth)                 # fair CRPS + consistency, no obs error
var_ratio = pred.var("member") / truth.var("member")      # target ~1 (e.g. within [0.5, 2])
r_spatial = pattern_corr(pred.var("member"), truth.var("member"), weights=coslat)
```

**Status: 🟡 the structure exists; no data is staged (2026-09-14, gap item 7).**
The design intent of delineation plan §5 — a Tier II suite instance whose
`reference_data` points at the held-out truth, so the identical scored diagnostics run
unchanged — is now built:

- **The truth as a DataSource.** `diags/truth_reference.py::LocalCMORReference` is a
  `climateeval.data.DataSource` over a **local CMOR directory**, delegating to
  `climateeval._loader.load_cmor_dir` (the same loader the submission goes through)
  and then to the base class's `get_prepared_cube`, so the truth gets the identical
  unit conversion, masking and time extraction as any published product. ⚠ **upstream
  candidate**: ClimateEval has no "local directory" DataSource — every one of its
  sources downloads and CMORizes a published dataset — and a generic
  `LocalCMORDataSource(path, information)` belongs beside
  `ESMValToolCMORizerDataSource`. The class adds no preprocessing of its own.
- **The CLI.** `climatebench2 score MODEL --truth DIR [--truth-member LABEL=PATH]...
  [--truth-name CESM2]`. A suite YAML names a *class*, which ClimateEval instantiates
  with no arguments, so the directories are registered on the module
  (`configure_truth`) before any `Suite` is built, and each extra member gets its own
  generated subclass (hence its own `data_id`). `_cli.materialise_truth_suite` then
  writes a temporary copy of each **cube** suite with every `reference_data:` swapped
  and `other_data:` replaced by the truth members — keeping the suite *stem*, so the
  suite name and its `.ddb` filename are unchanged. The experiment suites (Tier I,
  Tier III paleo) and the piControl-fed variability suite are untouched: they have no
  observations to replace.
- **What the pass does with it.** The truth records itself in `data_sources` with
  `category = "truth"`, which makes the behaviour self-describing and survive
  `leaderboard --rescore`: `scoring_pass.is_perfect_model` labels every row
  `window = perfect-model` (a third label beside held-out/in-sample — out-of-sample
  evidence, but against a model, not the world), **σ_obs is zero** (the truth is known
  exactly; carrying the instrumental floor would flatter every submission equally),
  the CMIP6 comparison models are gone so `E_ref` and the skill are empty by
  construction, and a truth member gets a `reason` row rather than being scored as a
  competitor against itself.
- **The large-ensemble spread test.** `scoring_pass.le_spread_rows` runs whenever truth
  members are present, for each variable of `tier3.le_spread.variables` (`tas`, `pr`):
  `scoring.le_variance_ratio`, gated at `tier3.le_spread.variance_ratio_range`
  = [0.5, 2.0] (**still a TODO bound**) as a Tier III **Extended** check — so it is
  reported for credit and never part of the entry ticket — and
  `scoring.le_spread_pattern_correlation`, reported without a bound because the paper
  sets none. On a time-series `raw_output` the remaining axis is time, so "pattern"
  means the shape of the spread through the record; the same two functions apply to a
  Map `raw_output` whose axis is space, and only the stacking would differ.
- ❌ **Data staging is pending.** No CESM2, MPI-ESM, GISS-E2 or CESM-LE output exists
  in this repository or upstream (the paper promises them on publication), so *none*
  of the above has run against real data: the tests build synthetic databases and a
  synthetic CMOR directory. The submission side is also untested — nothing has yet
  produced daily `tas`/`pr` predictions to score.

---

# Overall coverage summary

| Tier | Specced diagnostics | ✅ | 🟡 | ❌ |
|---|---|---|---|---|
| I | 18 sub-checks (16 Table-1 rows) + 2 code-only extras; all tagged Required / Extended / extra, entry ticket over the Required group only | **18 — every Table-1 row**: I.1, I.2a, I.2b, I.3a, I.3b, **I.3c**, I.4a, I.4b, I.5a, I.5b, **I.5c**, I.5d, I.6a, I.6b, I.6c, **I.7**, I.8a, I.8b (+ Bjerknes, C–C vs their own specs); I.6a/b, I.6c and I.8a are thin CB2 gates over ClimateEval `main`'s own diagnostics | 0 | 0 — but six gates (I.3b, I.3c, I.4a, I.4b, I.5c, I.5d) have only ever run on synthetic cubes, I.3c's stored reference slope is null, and I.5c has no ERA5 temperature reference upstream |
| II | fair-CRPS engine + skill score + baselines + ~20 diagnostic families | **fair CRPS with the M = 1 rule; member stacking by model name; ESS correction; moving-block bootstrap; observational-uncertainty draws with a real σ_obs; CMIP6-median `E_ref` with leave-one-out; regime (b) as fair CRPS on the reference's fixed pre-2015 EOF basis; the aggregated-scalar regime; σ_int from piControl chunks in the consistency test; the reference's pre-test record carried past the test-window cut; one label per model across the tiers; the realized warming level and both GMST trends with the GSAT blending correction; held-out / in-sample labelling end to end; per-member runs of the Tier II events suite; the skill table in the leaderboard; the eight **ETCCDI extremes** on the 1° conservative grid; the **Perkins** PDF skill and its own leaderboard table; the three **seasonal-cycle** metrics; the **diurnal** first harmonic in local solar time with a (cos, sin) phase; the **pattern-scaling** baseline for GMST-type series, ERF-driven and calibrated through 2014**; deterministic metrics for tas/pr/TOA(all- and clear-sky)/prw/clouds/tos/OHC(total, 2000 m, 100 m)/sea-ice via ClimateEval | climatology baseline scored as a distribution (CB2 interpretation, ⚠) and only for regime (a); every σ_obs value — the GSAT blending factor and the packaged ERF table — provisional (⚠); the regime-(b) bootstrap axis, the model-anomaly definition, the EBM pseudo-members, the (cos, sin) phase, the per-calendar-month extremes threshold and `clt` as the low-cloud proxy are CB2 readings (⚠); Gaussian consistency null; Pinatubo `rsds` and the ITCZ shift still sign-only (no obs product); **the ETCCDI extremes computed but unscored — no daily obs DataSource (HadEX3)**; `tas` scored against HadCRUT5 alone, so no inter-product σ_obs; sea-ice area not extent (PR #47 stanza commented in) | ts; surface fluxes; the **spatial** half of pattern scaling (CMIP6-MMM pattern, PR #44); a regime-(b) climatology baseline; **post-2015 multi-member CMIP6 reference (ClimateEval) — without it `E_ref` and every skill number stay empty** |
| III | 3 paleo periods + monsoon check + proxy scoring + perfect model + LE spread | **the monsoon gate (with the Harrison 2015 magnitude beside it); the fair CRPS of a block pseudo-ensemble against the proxy compilations, with σ_proxy as the observational variance term and the site-consistency fraction beside it; one suite stanza per (period, dataset, variable) reading the pipeline's own NetCDFs; the App. D scored/reported split by `dataset_type`; a `tier` tag on every gate so Tier III has its own scorecard section** | Temp12k needs a zonal-mean comparison (live stanza, writes its reason); Scussolini 2019 has a reliability flag, not a σ; `block_years`/`spinup_years` are CB2 defaults (⚠); the site standard error ignores inter-site correlation (⚠); **the perfect-model path and the LE-spread test are wired end to end but have never seen data** — no CESM2/MPI-ESM/GISS-E2/CESM-LE is staged, and the variance-ratio bound is a TODO | the PMIP4 comparison ensemble behind `E_ref` (upstream PR #45); a PMIP4-proxy DataSource upstream; Osman 2026 LIG SST (unarchived); calibrated Osman 2021 SSTs |

**Cross-cutting discrepancies (paper vs current `climatebench2/` code) — complete list,
2026-09-14:**
1. ~~**I.2b atmospheric energy identity reversed in code**~~ — **DONE (2026-09-14, gap
   item 1, `a030496`):** `physics.atmospheric_energy_residual` returns the paper's
   `|Q_rad − (LP + SHF)|` with `Q_rad = sfc_net_rad − TOA_net`.
2. ~~I.1 evaluated over the whole supplied piControl~~ — **DONE (2026-09-14, gap
   item 1, `a030496`):** both
   criteria use the last `tier1.energy_balance.evaluation_years = 100` annual values
   (the stale `min_years: 500 # TODO` is gone); shorter controls are used whole with a
   warning and reported through `n_years`.
3. ~~I.3a regresses annual means~~ — **DONE (2026-09-14, gap item 1, `a030496`):**
   deseasonalised monthly
   anomalies (`anomalies(period="month")`) for both `rlutcs` and `ts`.
4. ~~I.5a — σ of a smoothed index, computed on the historical cubes~~ — **DONE
   2026-09-14, `a030496` + `a4cca38`:** the unsmoothed monthly index
   (`_rolling_window_length = 1`, gap item 1) *and* the right record — the CLI's suite
   registry feeds
   `ClimateBench2_TierI_variability` the `picontrol` experiment in full (gap item 4),
   re-confirmed with gap item 5. *Residual:* the unsmoothed index needs CB2's
   `ENSOGate._preprocess` override until **ClimateEval PR #46** merges.
5. ~~I.5b band-power ratio uses mean PSD per band~~ — **DONE (2026-09-14, gap item 1,
   `a030496`):** integrated
   power (`np.trapezoid`) per band, so the 1.5 bound means what the paper says.
6. ~~I.5c implements the superseded scalar criterion (ta500 / Maritime-Continent sign
   checks); the pattern-correlation test and its HadISST/ERA5/GPCP reference patterns do
   not exist; four stale keys in `thresholds.yml`.~~ **DONE (2026-09-14, gap item 5,
   `8f8a36a`):** the standardised-index gridpoint regression over 30S–30N, the
   HadISST/GPCP reference patterns, the centred cos-weighted pattern correlation gated
   at 0.7 with one row per field, and the four stale keys deleted. *Open:* ClimateEval
   exposes no ERA5 `ts`, so the temperature reference is HadISST alone (SST-only, land
   masked pairwise), and the reference branch has never run against real files.
7. ~~I.6a emits both the `> 1` and the `[1.2, 1.6]` checks~~ — **DONE (2026-09-14, gap
   item 0, `b7e8593`):** one strict-range check `land_ocean_warming` on
   `tier1.land_ocean_warming.range`; `required_min`/`expected_range` removed.
8. ~~I.7 "2015" = last-30-yr mean (paper: decadal mean centred on 2015); no
   parallel-segment drift removal.~~ **DONE (2026-09-14, gap item 5, `8f8a36a`):**
   `tier1.aerosol_forcing.window = [2010, 2019]`, clipped to the hist-aer record with a
   warning and emitted; drift removed with the branch-time-aligned piControl segment,
   with the long-term mean as a logged fallback and a `parallel_segment` flag.
   *Still open, paper-side:* App. B.8 writes `F = ΔN + λΔT` with a negative Gregory λ —
   sign should read `ΔN − λΔT` (code is right). *Also not done:* the online
   double-call / fixed-SST aerosol ERF App. B.8 prefers where a model provides it.
9. ~~**Fair vs empirical CRPS** — `scoring.crps_ensemble` uses the `M²` spread
   normalisation; M = 1 falls through to |x − y| instead of being undefined.~~
   **DONE (2026-09-14, gap item 3, `a4c5948`):** `scoring.crps_fair` normalises the
   spread term by `1/(2M(M−1))` and **raises** for M < 2; the empirical estimator is
   deleted, and a single-member model is reported as `n/a (single member)` rather
   than scored on |x − y|.
10. **`E_ref`** — **code DONE (2026-09-14, gap item 3, `732e860`):** `E_ref` is the
    median of the per-model fair CRPS over comparison models with M ≥ 2, excluding any
    whose name equals the scored model's (leave-one-out); the pooled `CMIP6-MME` row is
    deleted and the leaderboard's headline is `S` against that median, with the
    Climatology skill alongside. *Still open, paper-side:* §5.4 still defines the
    reference as an "unweighted **mixture**" while the Fig. 4 caption says "**median**
    E" — the code follows Fig. 4, and §5.4 needs Duncan's fix. *Still open,
    upstream:* with today's single-member r1i1p1f1 comparison ensemble no comparison
    model reaches M ≥ 2, so `E_ref` is empty in practice (#13).
11. ~~`tier2.climatology_baseline_period = [1990, 2020]` overlaps the reserved test
    window~~ — **DONE (2026-09-14, gap item 1, `a030496`):** `[1985, 2014]` for both the
    Climatology baseline and the Pinatubo reference; `baselines.py` docstrings follow,
    and the hemispheric-asymmetry era is now `tier2.hemispheric_asymmetry.era`.
12. ~~Aggregated-diagnostic scoring is still the old model-variability-EOF z-test
    (`field_consistency`, unwired); the paper wants reference-EOF fair CRPS with
    standardised coefficients and a block bootstrap.~~ **DONE (2026-09-14, gap items 3
    and 3b, `a4c5948` + `a3ff255`):** `ReferenceEOFProjection` builds the
    **reference's** fixed pre-2015 basis (area-weighted, truncated by
    `tier2.eof.variance_explained`), standardises every coefficient by its pre-2015 PC
    σ and emits one row per (source, variable, mode); `scoring_pass.score_eof_output`
    scores them with fair CRPS per coefficient and takes the equal-weight mean.
    `field_consistency` stays in `scoring.py` but is no longer the protocol's (b).
    *Two CB2 interpretations remain open for Duncan* (both in the Tier II preamble):
    the **bootstrap axis** — CB2 resamples the orthogonal coefficients with `T_eff = K`
    rather than spatial blocks, on the reading that the modes *are* the discounted
    effective sample — and the **definition of the model's test-window anomaly**
    (test-window mean minus the *reference's* baseline climatology, so a mean bias is
    penalised).
13. **Test window** — ~~the CLI default `--timerange 19790101/20141231` applies to
    every suite~~ **CB2 side DONE 2026-09-14 (gap item 4, `a4cca38`):** each suite gets its own
    window from `_cli.SUITE_REGISTRY`, and the Tier II suites default to
    `20150101/<last complete year>1231` derived from `tier2.test_window_start`;
    `--timerange` is now only an explicit override. ~~A side effect was that the cut
    removed the *reference's* pre-2015 record, so the Climatology baseline could not be
    formed and regime (b) had no basis window.~~ **Also DONE (gap item 3b,
    `a3ff255`):** `ReferenceBaselineRecord` and `ReferenceEOFProjection` reach back past
    the cut through their own copy of the `Variable`'s `timerange`, and every window the
    protocol names is resolved in one place (`climatebench2/windows.py`) so the CLI, the
    diagnostics and the pass cannot disagree. *Still open (upstream):*
    ClimateEval's `CMIP6HistoricalR1I1P1F1` is hard-wired to 1979–2014 and r1i1p1f1 and
    there is no SSP2-4.5 generator, so the post-2015 CMIP6 reference rows are empty —
    the CLI says so rather than failing.
14. ~~Multi-member submissions — the scoring layer treats each member as its own
    M = 1 ensemble.~~ **DONE:** ingestion 2026-09-14 (gap item 4, `a4cca38`) —
    `--member LABEL=PATH` plus `r*i*p*f*` DRS auto-discovery, one run per member per
    cube suite with distinct `data_id`s appended into the same database (complex
    suites run once, on the first member) — and **stacking** the same day (gap item 3,
    `732e860`): `scoring_pass` maps `data_id → (name, variant)` through the
    `data_sources` table, groups by name and scores each model's members as one
    fair-CRPS ensemble.
15. **OPEN (blocked on upstream #47).** Sea ice: ClimateEval computes area, the paper
    scores extent (15 % threshold).
    *Since 2026-09-14 (gap item 6, `9d4b7a9`)* `ClimateBench2_TierII.yml` carries a
    **commented-out** `SeaIceExtentTimeSeries` stanza with the 15 % definition, keyed to
    *upstream* PR #47, plus a note that the active rows are AREA — so the mismatch is
    visible in the suite itself rather than only here. Uncomment it when #47 merges.
16. **PARTIAL — computed, not scored (blocked on upstream #53/#54).**
    TXx now uses daily `tasmax` (registry variable, suite id `tasmax_txx`; **done**
    2026-09-14 with gap item 0) but still against an `ERA5Monthly` placeholder
    reference. **Superseded 2026-09-14 (work package 6b, `d8df85b`):** the
    protocol-conforming statistic is the `extremes` entry — the eight ETCCDI
    indices on the 1° conservative grid — and `tasmax_txx` survives only as a
    deterministic display. *Still open, upstream:* **a daily observational
    product**. ERA5 has no `tasmax`/`tasmin` at all and `ERA5Hourly` downloads a
    single hard-wired year, so the extremes are computed model-only and
    unscored; **HadEX3** has an ESMValTool CMORizer and needs only a DataSource.
17. ~~**Entry ticket** — the leaderboard `ALL` column spans every gate present,
    including the Bjerknes and C–C extras, the Extended GFMIP/MJO gates and the Tier II
    Pinatubo / hemispheric-asymmetry gates; there is no Required/Extended/extra tag and
    no three-valued pass/fail/N-A state.~~ **DONE (2026-09-14, gap item 2, `5d600d3`):**
    every gate
    block in `thresholds.yml` carries `requirement:` (required / extended / extra /
    diagnostic), read by one helper (`pass_fail.gate_requirement`); gate rows carry
    `requirement` + `applicable`; `score --not-applicable NAME` declares a test N/A
    (`applicable = 0`, NaN pass/fail); `pinatubo`/`hemispheric_asymmetry` moved to
    `ClimateBench2_TierII_events.yml`; the leaderboard renders Required / Extended /
    extra separately and computes the entry ticket (✓ / ✗ / ⚠ incomplete) over the
    Required group alone, with the full Required set taken from the gate classes so an
    unrun gate reads as a hole, not a pass.
18. ~~Tier III proxy gates read `{period}_proxies.csv` files the pipeline does not
    write; the pipeline's LGM targets are DA products the paper now excludes;
    tas-only.~~ **DONE (2026-09-14, gap item 7, `f1fbdfe`/`f39a9f2`):**
    `PaleoProxyScore` reads one processed dataset NetCDF per (period, dataset,
    variable) — site or gridded, `tas`/`tos`/`pr` — from `--paleo-data-root`; the raw
    compilations (Tierney 2020, Bartlein 2011, Otto-Bliesner 2021, Scussolini 2019)
    are scored, the DA products (Cleator 2020) reported and tagged, the lgmDA/LGMR
    fields dropped as duplicates of Tierney 2020, and the primary statistic is the
    **fair CRPS of a block pseudo-ensemble** rather than the consistency fraction
    alone. *Open:* Temp12k's latitude bands need a zonal-mean comparison, and
    Scussolini 2019 publishes a reliability flag rather than a σ.
19. **RESOLVED as won't-fix.** `paleo_benchmark.py`'s Gaussian CRPS treats the proxy as
    the forecast distribution — the inverse of the protocol's model-ensemble fair CRPS.
    **Unchanged and deliberate** (2026-09-14): the script now serves only the AR6-style figures, and
    the protocol's statistic lives in `PaleoProxyScore`. What *did* change is its data
    path — `--picontrol-dir DIR` instead of `benchmark_utils.DataFinder`, which
    retired the last of the legacy island (§9 of the delineation plan).
20. ~~Duplicate physics vs ClimateEval `main` — land–ocean, Arctic and MHT exist upstream
    with identical outputs; `_MISSING_FROM_REGISTRY`/`RegistryFreeVariable` are obsolete
    (`rsds`/`rsus`/`rlds`/`rlus` landed upstream); the pin is 2 months stale.~~
    **DONE (2026-09-14, gap item 0, `b7e8593`):** pin bumped to `b0e941c`;
    `LandOceanWarmingGate`,
    `ArcticAmplificationGate` and `MeridionalHeatTransportGate` are `GateMixin`
    wrappers over the upstream classes; `_WarmingResponseGate`, `_transport_profiles`,
    `_MISSING_FROM_REGISTRY`, `RegistryFreeVariable` and `physics.nh_peak` deleted.
21. **OPEN, paper-side (no code change) — the manuscript items**, consolidated with
    the rest in "Decisions needed from Duncan", group A. App. E says "the Tier I–III diagnostics
    are hosted in the ClimateEval repository" — today 3 of 18 Tier I sub-checks and none
    of the Tier II/III scoring are; the Open Research section places ClimateBench under
    `climate-federation`, but the repository is `climate-analytics-lab/ClimateBench2`;
    the ENSO paragraph in §4.3 cross-references `app:implementation` where `app:tier1`
    is meant.

# Prioritized gap list (what to build next)

**Goal (2026-09):** run every CB2 suite against CMIP6 data with ClimateEval `main`,
keeping CB2 a thin protocol wrapper (thresholds, scoring, baselines, leaderboard) over
ClimateEval's data and diagnostics. Items marked *upstream* are ClimateEval PRs.

0. ~~**Sync with ClimateEval `main`**~~ — **DONE 2026-09-14 (`b7e8593`).** Pin bumped
   `4de03ed → b0e941c`; `LandOceanWarmingGate`, `ArcticAmplificationGate` and
   `MeridionalHeatTransportGate` are now `SupersetExperimentMixin`/`GateMixin` wrappers
   over `climateeval.diags.complex.{LandOceanWarmingRatio, ArcticAmplification,
   MeridionalHeatTransport}` on the `ECSGate` pattern, feeding `equilibrium_years`,
   `arctic_latitude` and the AMET/OMET search bands from `thresholds.yml` into the
   upstream kwargs; `_WarmingResponseGate`, `_transport_profiles`,
   `_MISSING_FROM_REGISTRY`/`RegistryFreeVariable` and `physics.nh_peak` deleted; the
   daily suite scores `tasmax` (`tasmax_txx`). The graceful skip-with-warning on absent
   experiments moved into the shared `SupersetExperimentMixin`, so `ECSGate` gets it
   too. This was the first concrete "retire as parity is reached" step of
   delineation-plan §7.
1. ~~**Fix the gates that are wrong as written**~~ — **DONE 2026-09-14 (`a030496`).**
   I.2b identity (#1); I.1 last-100-yr slice with `evaluation_years` (#2); I.3a monthly
   anomalies (#3); I.5a unsmoothed index (#4, statistic only); I.5b integrated power
   (#5); `thresholds.yml` clean-up — `min_years` TODO and `required_min`/`expected_range`
   gone (the latter with gap item 0, #7), `climatology_baseline_period → [1985, 2014]`
   and the new `tier2.hemispheric_asymmetry.era` (#11). *Still open here:* the four
   stale ENSO-teleconnection keys, which go with the I.5c rewrite (#6, item 5), and the
   aerosol-forcing window (#8, item 5).
2. ~~**Entry-ticket semantics**~~ — **DONE 2026-09-14 (`5d600d3`).** `requirement:` tags in
   `thresholds.yml` for every gate block (required / extended / extra / diagnostic) read
   through `pass_fail.gate_requirement`; `requirement` + `applicable` columns on every
   gate row; declared N/A via `climatebench2 score --not-applicable NAME`
   (`SupersetExperimentMixin`, no data needed, NaN value/passes) as distinct from a gate
   that did not run; `pinatubo`/`hemispheric_asymmetry` moved into the new
   `ClimateBench2_TierII_events.yml` (a CLI default suite) as
   `requirement: diagnostic`; the leaderboard renders the three Tier I groups with an
   `Entry ticket` column computed over the Required group only — ✓ (all applicable
   Required passed, N/A allowed), ✗ (an applicable Required failed), ⚠ (a Required check
   has no row), — for cells that were never run (#17).
3. **Scoring engine to the 2026-09 spec** — **core DONE 2026-09-14
   (`a4c5948` + `732e860`).** `scoring.crps_fair` is Ferro's fair estimator with the
   `1/(2M(M−1))` spread term and a hard `ValueError` for M < 2 (#9);
   `crps_fair_with_obs_draws` averages over common pseudo-observation draws and
   `moving_block_bootstrap_ci` gives the reported interval (part of #12);
   `climatology_pseudo_members` makes the no-skill floor scorable under fair CRPS
   (⚠ CB2 interpretation, Tier II preamble). The scoring layer moved out of the
   diagnostics into **`climatebench2/scoring_pass.py`**, a post-processing pass over
   the finished DuckDBs (`score` runs it, `--no-score` skips, `leaderboard --rescore`
   re-runs; idempotent via a `scorer` column): it groups `raw_output` rows by model
   **name** through the `data_sources` table, stacks a model's members into one
   fair-CRPS ensemble (#14), computes `E_ref` = median of the per-model scores with
   leave-one-out and writes `skill`, `e_ref`, `n_ref_models` next to `crps`,
   `crps_se`, `crps_ci_lo/hi`, `t_eff`, `n_members`, `n_time` in the diagnostic's own
   `metrics` table (#10, code side); the pooled `CMIP6-MME` row is deleted and the
   leaderboard renders S per model and variable, clipped at −1.
   **Second half DONE 2026-09-14 (work package 3b, `519ef72` + `a3ff255`):**
   - the **regime-(b) engine** (#12) — `ReferenceEOFProjection` builds the reference's
     fixed pre-2015, area-weighted EOF basis truncated by
     `tier2.eof.variance_explained`, records each mode's pre-2015 PC σ and projects the
     test-window climatological anomaly of the model (per member), the reference and
     every comparison source onto it; `scoring_pass.score_eof_output` scores the
     standardised coefficients with fair CRPS, takes the equal-weight mean and reuses
     the leave-one-out CMIP6 median. Two ⚠ CB2 readings are recorded in the Tier II
     preamble: the bootstrap axis (coefficients, `T_eff = K`, not spatial blocks) and
     the definition of the model's test-window anomaly;
   - the **reference's pre-2015 record** (#13, CB2 side) — `ReferenceBaselineRecord`
     puts the 1985-2014 monthly and annual series back into a database the test-window
     cut had emptied, so the Climatology baseline is formed from real values instead of
     a "window absent" reason; all windows now come from `climatebench2/windows.py`;
   - **σ_int** — `InternalVariability` (Tier I suite, `picontrol`,
     `requirement: diagnostic`) reports `chunked_statistic_std` of the window mean and
     OLS trend at both scored window lengths, and the regime-(c) test moved out of
     `TrendConsistency` into the pass, which collects those rows across the run;
   - **σ_obs** — the `tier2.obs_sigma` protocol table (⚠ provisional, `null` where
     unknown; GPCP is a TODO for Duncan) plus the measured spread across observational
     products, which `data_sources.category` now distinguishes from comparison models
     so an obs product is never ranked as a model;
   - **row identity** — the leaderboard labels gate, CRPS, consistency and Tier III
     rows by model name through the `data_sources` tables.

   *Still open here:* the pattern-scaling baseline (hook:
   `scoring_pass.PATTERN_SCALING_DATA_ID`); a regime-(b) climatology baseline; a real
   observational error field to replace the σ_obs constants. (The realized-warming-level
   statistic and the 1950-start trend row landed with **gap item 6**, `9d4b7a9`.)
   *Blocking, upstream:* item 4's `CMIP6HistoricalSSP245` multi-member generator —
   until it lands no comparison model has M ≥ 2, so `E_ref` is empty and the skill
   column has nothing to show, in regime (b) exactly as in regime (a).
4. **Test-window data path** — **CB2 side DONE 2026-09-14 (`a4cca38`).** A per-suite
   registry in `_cli.py` gives every suite the data shape and window the protocol asks
   for: the experiment-based suites load `historical` (and every other experiment) in
   **full**, so the aerosol-era, Pinatubo, clear-sky and ITCZ–EFE gates see the whole
   record instead of the old 1979–2014 slice; `ClimateBench2_TierI_variability` takes
   the `picontrol` experiment in full (#4); the Tier II suites take the model cubes over
   `20150101/<last complete year>1231`, derived from the new
   `tier2.test_window_start = 2015` (#13); `--timerange` remains an explicit override
   for the cube suites. Multi-member ingestion landed with it: `--member LABEL=PATH`
   and `r*i*p*f*` DRS auto-discovery, one run per member with
   `DataSourceInformation(variant=LABEL)` appended into the same per-suite DuckDB
   (`Suite.get_database(append=True)`), complex suites once per model (#14).
   *Still open (upstream, blocking):* a `CMIP6HistoricalSSP245` DataSource generator
   (historical + ssp245 concatenation, `ensemble: "r*i1p1f1"`, open-ended timerange) in
   ClimateEval — until it lands the CMIP6 comparison rows for the test window are empty
   and the CLI says so, so Tier II numbers are only interpretable in-sample.
5. **Re-specced Tier I physics** — **DONE 2026-09-14 (`bbf7d43` + `8f8a36a`,
   work package 5).**
   - **I.5c** (#6) is the paper's pattern test: standardised unsmoothed piControl
     Niño-3.4, per-gridpoint regression of monthly `ts`/`pr` anomalies over 30S–30N,
     the same for HadISST `tos` + GPCP `pr` over
     `tier1.enso.teleconnection_obs_window` = 1979–2014 (the observed index taken from
     HadISST so both observed patterns share one), centred cos-weighted pattern
     correlation (`physics.banded_pattern_correlation`) gated at the new
     `teleconnection_pattern_corr_min = 0.7` — rows `enso_teleconnection_ts` /
     `enso_teleconnection_pr`; the four stale keys are gone.
   - **I.3c** is new: `PrecipBuoyancyGate` in the Tier I suite — the mass-weighted
     column integral of `c_p·ta + g·zg + L_v·hus` over the available `plev`, monthly
     anomalies of P and ⟨h⟩ over 20S–20N, pooled slope (mm day⁻¹ per MJ m⁻²), gated at
     ±30% of the GPCP/ERA5 slope computed at run time or of the stored
     `tier1.precip_buoyancy.reference_slope`.
   - **I.7** (#8) uses `tier1.aerosol_forcing.window` = 2010–2019, clipped to the
     hist-aer record and reported, and removes drift with the branch-time-aligned
     piControl segment (long-term mean as a logged fallback). The segment selector
     lives in `physics` for now; it is still the natural *upstream* helper next to
     `ECS`, which has the same need.
   - **I.3a** (#3) and **I.5a** (#4) were already done in gap items 1 and 4; I.5a's
     piControl input was re-confirmed here.

   *Still open here:* pin `tier1.precip_buoyancy.reference_slope` (TODO(Duncan)); add
   `zg` (and `ts`) to ClimateEval's ERA5 mapping so I.3c's reference column needs no
   hydrostatic fallback and I.5c can use ERA5 for temperature; exercise
   I.3b/I.5d/I.4a/b — and now the I.3c/I.5c observational branches — on real daily,
   fixed-SST and satellite data.
6. **Tier II missing diagnostics** — **DONE 2026-09-14** (work package 6a,
   `5185c72` + `9d4b7a9`; work package 6b, `ce509c3` + `d8df85b` + `74a4841`).
   **First half (6a):**
   - **The scalar diagnostics of §II.1.** `RealizedWarmingLevel` emits the protocol's
     primary test-window statistic (mean 2015+ `tas` minus the 1985–2014 mean), the
     secondary test-window trend and the 1950-present trend; `PinatuboResponseGate` and
     `HemisphericAsymmetryGate` keep their sign flags (`requirement: diagnostic`) and
     now also emit **scored magnitudes**. All four take their observed counterpart from
     **HadCRUT5** through the new `ObservedScalarMixin`, which is what lets a *complex*
     diagnostic emit `reference` rows at all, with the **GSAT blending correction**
     (`tier2.gsat_blending_factor` = 1.09, ⚠ TODO(Duncan)) applied to the observed
     anomalies and `tier2.gsat_blending_relative_uncertainty` = 0.10 of the change
     carried into each row's σ_obs.
   - **The pass's aggregated-scalar regime** (`score_scalar_output`): fair CRPS on a
     single-point axis, the same leave-one-out CMIP6 median, and a regime-(c)
     consistency row whose σ_int comes from `InternalVariability` through the new
     `tier2.scalar_consistency` registry of (variable, statistic, window).
   - **Held-out vs in-sample end to end**: `tier2.window_labels` in `thresholds.yml`,
     a `window` column on every row the pass writes, and a leaderboard that badges each
     entry and puts the held-out ones first (paper §5.6).
   - **Per-member Tier II events**: `SuiteSpec.per_member` makes
     `ClimateBench2_TierII_events` run once per ensemble member with that member's own
     `historical` record, which is what the fair CRPS of a scalar needs.
   - **Suite completeness**: `rsutcs`/`rlutcs` vs CERES-EBAF, `clwvi`/`clivi` vs
     ESACCI-CLOUD, OHC 0–100 m, and a commented `SeaIceExtentTimeSeries` stanza for
     PR #47 (#15). Verified that the sea-ice and OHC series are scored — which needed
     the **per-variable reference** fix, since a diagnostic holding several references
     scored only the first one's variable.

   **Second half DONE 2026-09-14 (work package 6b, `ce509c3` + `d8df85b` +
   `74a4841`).**
   - **The ETCCDI set** (`diags/tier2_daily.py::ETCCDIExtremes`): TXx, TNn,
     TX90p, WSDI, Rx1day, Rx5day, R95pTOT and CDD per year and grid point after
     a **conservative regrid to `tier2.extremes.grid` = 1°**, reduced to a
     climatological mean and an OLS trend per decade over each
     `tier2.extremes.regions` land band, in the aggregated-scalar shape the pass
     scores. The index maths is pure numpy in `physics` with unit tests on
     synthetic daily arrays. ❌ **unscored**: ERA5 carries no
     `tasmax`/`tasmin` and no other daily observational DataSource exists, so
     the suite gives them no reference and the pass skips them — **HadEX3** (an
     ESMValTool CMORizer already) is the one upstream addition that would score
     them.
   - **The Perkins skill score** (`scoring.perkins_skill_score`,
     `diags.tier2_daily.PerkinsSkillScore`): Σ min(f_m, f_o) over the
     pre-registered `tier2.perkins.bins`, per season, for daily `tas` anomalies
     and wet-day `pr` intensity against ERA5Hourly. It is a **skill, not an
     error**, so it is a *metric* and gets its own leaderboard table rather than
     a CRPS column, and never enters `E_ref`.
   - **The seasonal-cycle triplet and the SST–CRE feedback**
     (`LandAnnualTemperatureRange`, `SSTLowCloudCovariance`,
     `SeasonalCloudRadiativeFeedback`), scored against ERA5 / ESACCI-CLOUD /
     ESACCI-SST / CERES-EBAF through a now multi-product `ObservedScalarMixin`.
   - **Diurnal first-harmonic scoring** (`DiurnalHarmonic`) in local solar time,
     with `physics.first_harmonic` generalised to any sub-daily sampling and the
     phase emitted only as (cos, sin).
   - **Pattern-scaling wiring and calibration** (`baselines.load_erf_series`,
     `calibrate_two_layer_ebm`, `ebm_pseudo_members`,
     `scoring_pass._pattern_scaling_row`): the GMST trajectory is a scored
     baseline row; the spatial half emits a `reason` row naming PR #44.
   - The daily suite now runs over the **full historical record**
     (`_cli.SUITE_REGISTRY`), which is what makes all of the above in-sample.

   *Still open here:* the packaged ERF table is a provisional interpolation of
   AR6 anchors with no natural forcing (TODO(Duncan)); `clt` stands in for low
   cloud; the Perkins anomaly baseline is fixed, not moving; the extremes use a
   per-calendar-**month** percentile threshold; AR6 region masks instead of
   latitude bands; a regime-(b) climatology baseline.
   *Still open, upstream:* a daily observational product (**HadEX3** first,
   then Berkeley daily / HadGHCND / IMERG / MSWEP), sea-ice extent (#47, #15),
   the CMIP6-MMM warming pattern (#44) and the additional obs DataSources
   (GISTEMP, Berkeley Earth, NOAAGlobalTemp — without which the GMST scalars
   have a single observational product and no inter-product σ_obs — HadSST/CRU
   TS, NSIDC Sea Ice Index, RSS, CERES SYN, BSRN).
7. ~~**Tier III**: read the pipeline's per-dataset NetCDFs instead of the non-existent
   CSVs, one stanza per (period, dataset, variable) (#18); add the raw SST compilations
   (Tierney 2020, Osman 2021/2026, Hoffman 2017), Cleator 2020, Harrison 2015 and SISALv3
   processing and drop the DA products from scoring; fair CRPS with block pseudo-members
   from the equilibrated run; a PMIP4 DataSource generator *upstream*; the perfect-model
   + LE-spread suite once CESM2/MPI/GISS/CESM-LE data are staged (#19); retire
   `paleo_benchmark.py --use-picontrol` and with it `constants.py`, `utils.py`,
   `benchmark_utils.py`.~~ — **DONE 2026-09-14 (work package 7, `f1fbdfe`, `f39a9f2`,
   `8cfa36f`, `d21be52`):**
   - **The maths** (`f1fbdfe`): `scoring.nonoverlapping_blocks` /
     `block_climatologies` / `proxy_crps` — the equilibrated-portion rule, the block
     pseudo-members it selects, and the per-site fair CRPS with σ_proxy as the
     observational variance term, meaned with equal weight over sites. The `tier3`
     protocol constants (`block_years`, `spinup_years`, `paleo_data_root`,
     `site_weighting`, `scored_dataset_types`, `seasonality`) and a `tier:` tag on
     every gate block joined `thresholds.yml`.
   - **The wiring** (`f39a9f2`): `PaleoProxyScore` replaces
     `PaleoProxyConsistencyGate`, reading one processed NetCDF per stanza; the suite
     carries a stanza for every scoreable (period, dataset, variable) and explains, in
     place, each dataset it omits; the DA products are reported and tagged rather than
     scored; gate rows carry their protocol `tier` and the leaderboard groups by it,
     which moves `midholocene_monsoon` out of the Tier I Extended table.
   - **The perfect model** (`8cfa36f`): `LocalCMORReference`, `score --truth DIR
     --truth-member LABEL=PATH`, the materialised suite YAML, the `perfect-model`
     window label with σ_obs = 0, and `le_spread_rows` for the III.2 spread test.
   - **The legacy island** (`d21be52`): `paleo_benchmark.py --picontrol-dir DIR`
     replaces `DataFinder`, `paleo_scripts/paleo_utils.py` holds the three helpers the
     paleo scripts needed, and `constants.py`, `utils.py`, `benchmark_scrips/` and
     `env.yml` are **deleted**.

   *Still open here:* a zonal-mean comparison for Temp12k; a σ for Scussolini 2019;
   Duncan's ruling on the block length, the spin-up allowance and the site weighting;
   the LE variance-ratio bound; and the whole of III.2 against real data —
   CESM2/MPI-ESM/GISS-E2/CESM-LE staging is pending, so the perfect-model path has
   only ever run on synthetic databases.
   *Still open, upstream:* a PMIP4 model DataSource generator (**PR #45**) and a
   `PMIP4Proxies` CMORizer for the compilations, which is where `PaleoProxyScore`'s
   NetCDF reading ultimately belongs; a generic `LocalCMORDataSource` beside
   `ESMValToolCMORizerDataSource`.
8. **Upstream track** (delineation plan §7) — **proposed 2026-09-14, awaiting review.**
   The generic physics still in CB2 has been offered to ClimateEval as three PRs:
   **#50** (energy balance, budget closure, clear-sky β, precipitation–buoyancy,
   Clausius–Clapeyron), **#51** (geostrophic balance, MJO ratio, ITCZ–EFE, Bjerknes,
   ENSO teleconnection patterns) and **#52** (amip-4xCO2 ERF, GFMIP Δλ, aerosol ERF +
   the branch-time helper). When they merge, CB2 deletes its copies in
   `diags/tier1_physics.py` / `diags/tier1_extended.py` and keeps only `GateMixin`
   wrappers, as `ECSGate` already is. *Not offered, deliberately:* the Pinatubo and
   hemispheric-anomaly diagnostics, which are Tier II protocol scalars with a
   CB2-specific observational correction, not reusable physics.
   *Still open:* the paper's App. E claim becomes accurate only once #50–#52 land, so
   either they merge before submission or the sentence is softened (#21, decision A.3).

---

## What is left to run against CMIP6

The protocol is complete in code and empty of results. **Nothing in this repository has
been exercised on real model or observational data** — every number in every test comes
from synthetic cubes, synthetic databases or pure-function fixtures. Five concrete
things stand between here and a first real scorecard, roughly in order:

1. **Merge of upstream #44 and a pin bump.** Until `CMIP6HistoricalSSP245` exists, no
   comparison model has M ≥ 2 over the test window, so `E_ref` has nothing to take a
   median of and **every Tier II skill cell falls back to the raw CRPS** — in regime (b)
   exactly as in regime (a). This is the single blocking dependency; the other eleven
   PRs each widen coverage, but only #44 turns the headline score on.
2. **Pin `tier1.precip_buoyancy.reference_slope`.** Null today, so I.3c either computes
   the GPCP/ERA5 slope at run time (never yet attempted against real files) or writes no
   gate row at all — which the entry ticket reads as ⚠ incomplete, not a pass.
3. **Settle the provisional constants.** Every `tier2.obs_sigma` value, the GSAT
   blending factor and its uncertainty, the ERF table, `tier3.block_years` /
   `spinup_years`, and the LE variance-ratio bound — section "Decisions needed from
   Duncan", groups B and C. None blocks a run; all of them change the numbers a run
   produces, so ratifying them before the first real run avoids re-publishing.
4. **Data staging for the perfect model.** §III.2 is wired end to end —
   `score --truth DIR`, the `perfect-model` window label, the large-ensemble spread
   test — and has never seen a file. It needs CESM2 (Required, ML only), MPI-ESM and
   GISS-E2 (Extended) and CESM-LE for the spread test.
5. **The first real run itself.** Six gates (I.3b, I.3c, I.4a, I.4b, I.5c, I.5d) have
   only ever seen synthetic cubes; the daily suite has never met a real `day`-table DRS
   tree (memory footprint unknown); the observational branches of I.3c and I.5c have
   never fetched a real GPCP/HadISST/ERA5 file; and no Tier III stanza has been run
   against a real PMIP4 experiment. Expect this step, not the code, to be where the
   remaining surprises are.
