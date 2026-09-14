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
against the `climatebench2/` package at commit `d6b0513` (migration Phase 6 of
`docs/climateeval_delineation_plan.md`) and against **ClimateEval `main` @ `b0e941c`**
(2026-09), which now contains the merged CB2 upstream PR #35 (`LandOceanWarmingRatio`,
`ArcticAmplification`, `MeridionalHeatTransport` complex diagnostics; the
`rsds`/`rsus`/`rlds`/`rlus`/`tasmax`/`tasmin` variables), the ocean-transport
diagnostics of #34, and the relative-score leaderboard of #37. **`pyproject.toml` now
pins `b0e941c`** (gap item 0, `b7e8593`): the three duplicated Tier I diagnostics are
thin `GateMixin` wrappers over the upstream classes, the CB2-side registry stopgap
(`RegistryFreeVariable`) is gone and the daily suite scores `tasmax`. **Gap item 1**
(the same day) then corrected the gates that were wrong as written — the I.2b identity,
the I.1 evaluation window, the I.3a monthly anomalies, the I.5a unsmoothed index, the
I.5b integrated band power and the 1985–2014 Tier II baseline window — so the status
entries for I.1, I.2b, I.3a, I.5a/b and the Pinatubo/Climatology rows below describe
the corrected code. The legacy
`benchmark_scrips/*.py` scripts that earlier revisions of this document audited were
deleted in migration Phases 1–5; **every status entry below refers to
`climatebench2/`**, and the only legacy survivors are `constants.py`, `utils.py` and
`benchmark_scrips/benchmark_utils.py`, kept for `paleo_scripts/paleo_benchmark.py
--use-picontrol`.

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
  `metrics` rows `var_id | value | bound_lower | bound_upper | passes`
  (`diags/pass_fail.py`), so the leaderboard reads one schema for every check.
- Status legend: ✅ implemented per the (2026-09) spec · 🟡 implemented but deviates
  from spec · ❌ missing · ⬆ generic physics now provided by ClimateEval `main`
  (CB2 should keep only the threshold wrapper).

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
| I.3b | Midlatitude geostrophic balance | spatial ρ(u, u_g) at 850 hPa daily, 30–60°, > 0.9. **Skipped (N/A) for models with no dynamical representation** | Req. (N/A allowed) | ✅ per spec (daily `ua`/`zg` at 850 hPa, optional `ps` orography mask, pooled 30–60° both hemispheres); N/A only implicit (gate skipped when no `day` data supplied); untested on real daily data | `diags.tier1_extended.GeostrophicBalanceGate` |
| I.3c | Tropical precipitation–buoyancy | monthly P′ vs column-MSE′ slope, 20S–20N, ±30% of GPCP/ERA5 | Req. | ❌ missing — the legacy log(pr)-vs-prw proxy was retired with the scripts and nothing replaced it | — |
| I.4a | GFMIP SST patch experiments | Δλ = ΔR_EP/ΔTs_EP − ΔR_WP/ΔTs_WP > 0.5 W/m²/K — **Extended** | Ext. | ✅ per spec; needs submission-provided `amip`/`patch_ep`/`patch_wp` | `GFMIPPatchGate` |
| I.4b | amip-4xCO2 ERF | 6.5–9.0 W/m² | Req. | ✅ (TOA-net difference amip-4xCO2 − amip; no land-warming correction, none asked) | `Amip4xCO2ERFGate` |
| I.5a | ENSO amplitude | σ(Niño-3.4) ∈ [0.5, 1.4] K | Req. | ✅ σ of the **unsmoothed** deseasonalised monthly index (`ENSOGate._rolling_window_length = 1`); 🟡 the variability suite is still fed the CLI's historical cubes (1979–2014 default), not ≥ 100 yr piControl — a later CLI work package | `diags.pass_fail.ENSOGate` |
| I.5b | ENSO spectrum | power(2–7 yr)/power(1–2 yr) > 1.5 | Req. | ✅ Welch PSD **integrated** over each band (`np.trapezoid`), so 1.5 means what the paper says (white noise now scores ≈ 0.71, not ≈ 1.0) | `pass_fail.band_power_ratio` |
| I.5c | ENSO teleconnections | gridpoint regression of `ts` and `pr` on standardized Niño-3.4, 30S–30N; centred spatial correlation of modelled vs observed regression patterns > 0.7 (R² > 0.5), vs HadISST/ERA5 and GPCP | Req. | 🟡 implements the **superseded** scalar criterion (tropical ta500 regression > 0, Maritime-Continent pr < 0, sign only, no observations) | `diags.tier1_extended.ENSOTeleconnectionsGate` |
| I.5d | MJO Wheeler–Kiladis | east/west power ratio (k=1–3, 30–90 d) > 1.5 — **Extended** | Ext. | ✅ (2-D FFT east/west ratio, k = 1–3, 30–90 d, ±15°, daily `pr`) | `MJOGate`, `physics.mjo_east_west_ratio` |
| I.6a | Land–ocean warming ratio | ratio ∈ [1.2, 1.6] (**strict** — resolved 2026-09); a4x last 50 yr | Req. | ✅ one strict-range gate row `land_ocean_warming`; thin wrapper over `climateeval.diags.complex.LandOceanWarmingRatio` (⬆ done) | `LandOceanWarmingGate` |
| I.6b | Arctic amplification | (ΔT>66.5N)/(ΔT global) ≥ 1.5; a4x last 50 yr | Req. | ✅ thin wrapper over `climateeval.diags.complex.ArcticAmplification` (⬆ done) | `ArcticAmplificationGate` |
| I.6c | ECS (Gregory, 150 yr) | ∈ [1, 7] K | Req. | ✅ gate wrapper over ClimateEval's `ECS` (the template for the ⬆ rows) | `ECSGate` |
| I.7 | Aerosol forcing (hist-aer) | 2015 aerosol ERF ∈ [−2.0, −0.5] W/m²; ΔT(2015) < 0 — **Required** (promoted from Extended) | Req. | 🟡 ERF = ΔN − λ_Gregory·ΔT ✓, range ✓, cooling ✓; but "2015" = mean of the **last 30 yr** of hist-aer (paper: decadal mean centred on 2015) and anomalies vs the piControl long-term mean — **no parallel-segment drift removal** (paper App. B.8) | `AerosolForcingGate`, `physics.aerosol_erf` |
| I.8a | Meridional heat transport | OMET peak 1.5–2.0 PW near 15–20°; AMET peak 4–5 PW near ~45° | Req. | ✅ thresholds per paper (15–20°, 45 ± 5°); thin wrapper over `climateeval.diags.complex.MeridionalHeatTransport`, search bands from `thresholds.yml` (⬆ done) | `MeridionalHeatTransportGate` |
| I.8b | ITCZ–EFE relationship | 12-month climatology; slope within ±50% of ~3°/PW; r > 0.9 | Req. | ✅ 12-month climatology, slope ±50% of 3°/PW, \|r\| > 0.9; the hard-coded-1980 bug is gone | `ITCZEFEGate`, `physics.itcz_efe_regression` |
| (extra) | Bjerknes compensation 40–70N | not in paper's Tier I list as specced | — | ✅ vs its own spec — but **counted in the leaderboard's entry ticket** (see wiring note) | `BjerknesGate` |
| (extra) | Clausius–Clapeyron scaling | not in paper's Tier I list as specced | — | ✅ vs its own spec — same entry-ticket problem | `CCScalingGate` |

**Wiring.** The 16 experiment-based gates plus the two extras and the two Tier II event
gates (`pinatubo`, `hemispheric_asymmetry`, §II.1) live in
`climatebench2/suites/ClimateBench2_TierI.yml` (18 entries) and run from one experiment
dict; ENSO amplitude/spectrum run on cubes in `ClimateBench2_TierI_variability.yml`.
The leaderboard's `ALL` column (`leaderboard/_gate_matrix_html`) is the minimum over
**every gate present** — including the two extras, the two Extended gates and the two
Tier II event gates — and treats an absent gate as "not counted". Until gates carry a
Required / Extended / extra tag and an explicit N/A state (paper §7.1; discrepancy 17
below), the entry ticket the page shows is not the paper's. Neither daily-data gate
(I.3b, I.5d) nor the fixed-SST gates (I.4a/b) has been exercised on real CMIP6 output
yet; only the unit tests (synthetic cubes) cover them.

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

**Applicability (RESOLVED 2026-09).** This test is **skipped and recorded as N/A** for
submissions with no dynamical representation of the atmosphere (e.g. emulators that map
forcing directly to regional `tas`/`pr`). It is required for any model that produces
winds and geopotential. The scorecard must report which Tier I tests were applicable to
each submission rather than treating N/A as either a pass or a fail — otherwise the
inclusivity the protocol claims in §7.1 is contradicted by a gate in Tier I.

**Status: ✅ (structurally; untested on real data)** —
`diags/tier1_extended.py::GeostrophicBalanceGate` (`day` key): `extract_levels` to
850 hPa for daily `ua` and `zg`, `physics.geostrophic_wind_u` (= −(g/f)∂Z/∂y on the
sphere, |lat| < 10° masked), optional orography mask where daily `ps < 870 hPa` when
`ps` is present in the `day` data, then `physics.midlatitude_pattern_correlation` —
cos-weighted correlation pooled over all days and both 30–60° bands — gated at
`tier1.geostrophic_balance.spatial_corr_min = 0.9` (row `geostrophic_balance`).
Gaps: (i) N/A arises only implicitly — if no `day` experiment is supplied the CLI skips
the gate and the leaderboard shows "—" and excludes it from `ALL`; a submission cannot
*declare* "no dynamics", and one that has `ua`/`zg` but omits them silently skips a
Required test. Needs an explicit applicability flag (model card → suite kwarg) and a
three-valued pass/fail/N-A column. (ii) Loading a `day`-table DRS tree through
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

**Status: ❌ missing.** No diagnostic; the retired script's climatological
log(pr)-vs-`prw` spatial fit was not carried over (it was not the paper's statistic).
What is needed: a `CB2ComplexDiagnostic` on the `historical` key that (i) builds the
mass-weighted column integral of `c_p·ta + g·zg + L_v·hus` from monthly pressure-level
data (all three are in ClimateEval's registry with an `alevel` coordinate;
`esmvalcore.preprocessor.extract_levels` + a numpy trapezoid over `plev`), (ii) forms
monthly anomalies of P and ⟨h⟩ over 20S–20N and pools a regression over time and space,
and (iii) compares to an **observational reference slope** from GPCP
(`climateeval.data.GPCP`) and ERA5 pressure-level `ta`/`hus`/`zg`
(`climateeval.data.ERA5Monthly` supports these). Compute the reference slope once and
store it as `tier1.precip_buoyancy.reference_slope` in `thresholds.yml`, as is already
done for the 2.2 W/m²/K clear-sky value, rather than re-deriving it per run.
`tier1.precip_buoyancy.rel_tolerance_vs_obs = 0.30` is already present.

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
**Not in the paper's Tier I list** — keep as a supplementary sanity check tagged
*extra*, and exclude it from the entry ticket.

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
must not count toward the entry ticket (wiring note above).

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
reproduces the upstream chain minus that one step; upstream-PR candidate: accept
`window_length = 1` as a no-op, after which only the ClassVar is needed.) It runs in `ClimateBench2_TierI_variability.yml` on
the model's monthly `tos` cubes (variable id `tos_nino34`) with ESACCI-SST as reference
and ERSSTv5/HadISST as additional data — the gate is applied to the observational series
too, which sanity-checks the thresholds. `ENSOTeleconnectionsGate` recomputes the same
index inside a complex diagnostic on the `picontrol` key.

**(a) Amplitude.**
- Spec: **σ(Niño-3.4) ∈ [0.5, 1.4] K**.
- Code: `std(ddof=1)` of the index, gated at `tier1.enso.amplitude_range`
  = [0.5, 1.4] (row `enso_amplitude`). ✅ The index is now the unsmoothed monthly one
  (the 3-month running mean lowered σ by roughly 5–10%). 🟡 One deviation left: the
  variability suite receives the same cubes as Tier II — the historical run cut to the
  CLI `--timerange` (default 1979–2014, i.e. 36 yr) — not the ≥ 100 yr piControl the
  paper specifies. Feeding it the `picontrol` experiment is a CLI work package.
- Status: ✅ statistic, 🟡 input record.

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
- Code: `ENSOTeleconnectionsGate` still implements the **superseded** criterion —
  `physics.regression_on_index` of the tropical-mean (30S–30N) **`ta` at 500 hPa**
  anomaly and of the Maritime-Continent (90–150E, 10S–10N) `pr` anomaly on the raw
  (un-standardised) index, gated **sign-only** (`teleconnection_t_min = 0`,
  `teleconnection_pr_max = 0`); the factor-2 references
  (`teleconnection_reference_t/pr`) are `null` and were never wired. No observations
  enter.
- Rewrite plan: (1) standardise the index and regress monthly `ts` and `pr` anomalies
  on it at every 2° grid point over 30S–30N (`physics.gridpoint_regression_slope`
  already does the per-point OLS); (2) the same for the references — HadISST (or ERA5
  `ts`) and GPCP over the satellite era — computed once and cached, or pulled as
  reference DataSources inside the complex diagnostic; (3) centred cos-weighted pattern
  correlation (`physics.midlatitude_pattern_correlation` generalised to an arbitrary
  band) gated at a new `tier1.enso.teleconnection_pattern_corr_min = 0.7`, one row per
  field. Retire `teleconnection_obs_factor`, `teleconnection_t_min`,
  `teleconnection_pr_max`, `teleconnection_reference_*` from `thresholds.yml`.
- Status: 🟡 (implements the old spec).

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
`enso_teleconnection_t`, `enso_teleconnection_pr` (Tier I suite), each with
`value`/`passes`.

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
wavenumber) is O(N_t·N_lon); fine for decades of daily data. Being Extended, it must
not count toward the entry ticket.

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

**Status: 🟡** — `diags/tier1_physics.py::AerosolForcingGate` (`picontrol`, `4xco2`,
`histaer` keys):
- ✅ λ from a fresh 150-yr Gregory regression of the a4x run
  (`physics.gregory_regression`, `tier1.ecs.n_years`); `ERF = ΔN − λ·ΔT`
  (`physics.aerosol_erf`) — the correct form for the negative Gregory slope; gate rows
  `aerosol_erf` at `tier1.aerosol_forcing.erf_range = [−2.0, −0.5]` and
  `aerosol_cooling` (`delta_t_end < 0`); `lambda_4x` emitted.
- 🟡 "2015" is the mean over the **last 30 yr** of whatever hist-aer record is supplied
  (`_end_period_years = 30`, a class constant not in `thresholds.yml`). The paper now
  asks for a **decadal mean centred on 2015** — decide the window for records ending in
  2014 (DAMIP hist-aer ends 2014 or 2020 depending on the model) and encode it as
  `tier1.aerosol_forcing.window_years`.
- 🟡 Anomalies are relative to the piControl **long-term mean**; App. B.8 requires the
  **parallel piControl segment** (branch-time aligned) to remove drift. That needs the
  `branch_time_in_parent` attribute and a segment selector — a small ClimateEval-side
  helper would be the natural home, since `ECS` has the same need.
- ⚠ Paper sign nit (for the manuscript, not the code): App. B.8 writes
  `F_aer = ΔN + λΔT`, which is correct only if λ denotes the positive feedback magnitude.
  With λ = the Gregory slope (negative, as the same sentence says) the correct form is
  `F = ΔN − λΔT`, which is what the code does.

```python
lam = gregory(a4x_dT, a4x_dN).slope                       # W/m2/K from abrupt-4xCO2 (negative)
dT_end = (histaer_gmean_tas_annual - pi_parallel_tas)[2010:2020].mean()   # code: last 30 yr, pi long-term mean
dN_end = (histaer_gmean_N_annual  - pi_parallel_N  )[2010:2020].mean()
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
variant was not ported. piControl. Status: ✅ (vs its own spec); tag *extra* and
exclude from the entry ticket.

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
- **pattern-scaling baseline** — multi-linear: global-mean temperature trajectory from a
  two-layer EBM calibrated to observations **through 2014**, multiplied by a fixed CMIP6
  multi-model-mean response pattern; the simplest defensible emulator.
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
`E_ref` as "the **median** E across the ensemble" (the form adopted here). Resolve in the
manuscript before the code is aligned; the current code implements the *pooled* form
(`CMIP6-MME` row, §II.0).

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
`diags/tier2_scores.py` (`ScoredAnnualMeanTimeSeries`, `ScoredMonthlyMeanTimeSeries`,
`ScoredAnnualMaxTimeSeries`, `TrendConsistency`), `diags/tier2_diagnostics.py`
(Pinatubo, hemispheric asymmetry), `baselines.py`, `leaderboard/` — and was built
against the **previous** two-regime spec; it has **not yet been re-aligned** to the
2026-09 fair-CRPS protocol. Nothing probabilistic exists in ClimateEval/ESMValTool (they
are deterministic-only), so the scoring layer stays bespoke by design. The legacy
`esmvaltool/recipe_pr_rmse.yml` prototype and `benchmark_utils.MetricCalculation` are
gone.

## Tier II status summary

| Diagnostic / component | Spec regime | Status (2026-09-14) | Code / provider |
|---|---|---|---|
| Deterministic metrics (weighted RMSE / Pearson / EMD; maps, zonal lines, annual cycles) | — | ✅ from ClimateEval for every suite variable; shown by `climateeval report` and `climatebench2 leaderboard --csv` — display only, EMD is **not** a protocol score | ClimateEval `SimpleDiagnostic` metrics |
| **Fair** CRPS of ensemble time series | (a) | 🟡 `scoring.crps_ensemble` is the **empirical** estimator — spread term `½·(1/M²)ΣᵢΣⱼ\|xᵢ−xⱼ\|`, not `1/(2M(M−1))`; M = 1 silently falls through to \|x−y\| (paper: undefined) | `climatebench2/scoring.py`, `diags/tier2_scores.py` |
| ESS correction on the reported SE | (a) | ✅ `crps_ess_score` (lag-1 r → T_eff; `crps_se`, `t_eff`, `r1` emitted) | `scoring.py` |
| Fair CRPS on fixed pre-2015 **reference** EOFs, standardised coefficients, block bootstrap | (b) | ❌ — `eof_basis`/`project_onto_eofs` exist but build the basis from *model/piControl* variability and feed a Bonferroni z-test (`field_consistency`); no reference basis, no per-coefficient fair CRPS, no bootstrap; **no diagnostic wires them** | `scoring.py` (unwired) |
| Ensemble-consistency test — complementary | (c) | 🟡 `ensemble_consistency` (Gaussian z, σ² = var_ens + σ_int² + σ_obs²) wired only through `TrendConsistency`; `sigma_internal` hard-wired 0 (`chunked_statistic_std` exists, never called), `sigma_obs` a kwarg defaulting to 0; no Mahalanobis / empirically calibrated null / variance-explained truncation | `scoring.py`, `tier2_scores.TrendConsistency` |
| Skill score S = 1 − E/E_ref, E_ref = CMIP6 median, leave-one-out | — | 🟡 leaderboard shows skill vs the **Climatology** row only; the `CMIP6-MME` row is a **pooled** r1i1p1f1 mixture (the form ruled out above); no leave-one-out | `leaderboard/_crps_table_html`, `tier2_scores._ScoredTimeSeriesMixin` |
| Moving-block-bootstrap CIs; observational-uncertainty draws | (a)/(b) | ❌ | — |
| Multi-member submissions | — | ❌ `load_cmor_dir` yields one member, the CLI has no `--member`, `Suite` passes one `data_id`; every "ensemble" scored today has **M = 1** | `_cli.py`, `tier2_scores.py` |
| tas monthly/annual anomalies | (a) | 🟡 scored vs **HadCRUT5 only** (paper: GISS, Berkeley Earth, HadCRUT, NOAA GlobalTemp — ClimateEval has no DataSource for the other three); no GSAT blending correction; HadCRUT5 error field not used as σ_obs | `ScoredAnnualMeanTimeSeries` + `climateeval.data.HadCRUT5` |
| tas daily extremes (TXx, TNn, TX90p, warm-spell duration) | (b) | 🟡 only a TXx-like global-mean annual block maximum (`ScoredAnnualMaxTimeSeries`) on daily **`tasmax`** (id `tasmax_txx`, ✅ 2026-09-14), against a **placeholder `ERA5Monthly` reference** (wrong frequency) — no daily obs DataSource (Berkeley daily, HadGHCND) exists; TNn/TX90p/WSDI ❌ | `ClimateBench2_TierII_daily.yml` |
| Perkins skill score (daily T and wet-day pr PDFs, 1 mm/day, ~1° conservative regrid, moving-baseline anomalies) | — | ❌ (ClimateEval `Histogram` yields EMD, not the protocol statistic; regridding is linear to 2°) | — |
| ts (skin temperature) | (a) | ❌ — only `tos` vs ESACCI-SST/ERSSTv5/HadISST; no CRU TS / HadSST DataSource | ClimateEval |
| pr anomalies | (a) | 🟡 vs **GPCP only** (IMERG, MSWEP ❌ in ClimateEval) | `ScoredAnnualMeanTimeSeries` + `GPCP` |
| pr intensity PDF, Rx1day/Rx5day/R95pTOT/CDD | (b) | 🟡 `Histogram` of **hourly** pr vs `ERA5Hourly` (0–15 mm/day bins, global + 30S–30N) — deterministic EMD, not the daily wet-day Perkins score vs IMERG/MSWEP; the ETCCDI pr indices ❌ | `ClimateBench2_TierII_daily.yml` |
| TOA fluxes (LW/SW, all- and clear-sky) | (a) | 🟡 `rsut`, `rlut`, `rtnt` vs CERES-EBAF scored; `rsutcs`/`rlutcs` not in the suite (CERES-EBAF has them — one stanza) | suite + `CERESEBAF` |
| Sea ice extent, Sep/Feb minima, trends | (b) | 🟡 ClimateEval `SeaIceAreaAnnualCycle`/`SeaIceAreaTimeSeries` compute **area** (Σ siconc·A), the paper says **extent** (Σ A where siconc > 15 %); NH-Sep/SH-Feb minima wired vs OSI-450/NSIDC/HadISST; deterministic only — no (a)/(b) score, no trend consistency | `ClimateBench2_TierII.yml` |
| OHC 0–100 m, 0–2000 m | (a) | 🟡 total-column and 0–2000 m (`extract_volume`) vs EN4/IAP via `OceanHeatContentTimeSeries` on `phcint`; 0–100 m layer missing (one stanza); deterministic only | suite |
| Surface fluxes (pattern/seasonal-cycle scoring; FLUXNET/OceanSITES/BSRN sites) | (b) | ❌ (Extended; no obs DataSource; no site machinery) | — |
| Cloud properties (LWP, fraction, CTT/CTP) | (a)/(b) | 🟡 `clt` vs ESACCI-Cloud scored; `clwvi`/`clivi` not in the suite (ESACCICloud carries them); CTT/CTP ❌ | suite |
| prw | (a) | 🟡 vs `ERA5Monthly` (paper: RSS primary, ERA5 as reference) — acceptable pending an RSS DataSource | suite |
| Realized warming level 2015+ vs 1985–2014 (primary); 1950–present trend; test-period trend (secondary); GSAT blending | (a)/(c) | ❌ — `TrendConsistency` tests the OLS trend of **whatever window is loaded** (CLI default 1979–2014 → no test window at all); no warming-level statistic, no 1950 start, no blending correction | `TrendConsistency` |
| Pinatubo response | (b) | 🟡 `PinatuboResponseGate`: global-mean `rsds`/`tas` anomalies Jul 1991–Dec 1993 vs `tier2.climatology_baseline_period` (✅ now [1985, 2014]), **sign-only** gates; no BSRN/obs magnitude comparison, no co-variation test | `diags/tier2_diagnostics.py` |
| Hemispheric asymmetry | (b) | 🟡 `HemisphericAsymmetryGate`: NH−SH `tas` trend over `tier2.hemispheric_asymmetry.era` (✅ [1950, 1985], no longer a hard-coded class constant) and zonal-mean-pr-maximum latitude trend, **sign-only** gates; no HadCRUT/Berkeley comparison | `tier2_diagnostics.py` |
| Seasonal cycle: land annual T range; SST–low-cloud covariance; seasonal CRE–SST feedback | (b) | ❌ (ClimateEval `AnnualCycle` runs deterministically for the core variables; none of the three protocol statistics is computed) | — |
| Diurnal cycle (first-harmonic amplitude/phase of pr and CRE, local solar time) | (b) | 🟡 ClimateEval `DiurnalCycle` of hourly pr vs `ERA5Hourly`, deterministic; `physics.first_harmonic` exists, unwired; CRE diurnal ❌; IMERG / CERES-SYN DataSources ❌ | `ClimateBench2_TierII_daily.yml` |
| Held-out vs in-sample labelling | — | ❌ leaderboard has no such column | `leaderboard/` |
| Baselines | — | 🟡 **Climatology** row wired (`_climatology_row`) from `tier2.climatology_baseline_period` (✅ now [1985, 2014] — no longer overlapping the reserved test window); **pattern scaling**: `baselines.two_layer_ebm` + `pattern_scaling_forecast` are pure functions — unwired, uncalibrated (Geoffroy-2013 defaults in `tier2.ebm`), no ERF series or CMIP6-MMM pattern in the package; **CMIP6 MME**: pooled (see skill-score row) | `baselines.py`, `tier2_scores.py` |
| **CMIP6 reference ensemble for the test window** | — | ❌ ClimateEval's `CMIP6HistoricalR1I1P1F1` generator is hard-wired to `ensemble: r1i1p1f1` and `timerange: 19790101/20141231`; there is **no SSP2-4.5 or historical+SSP2-4.5 generator and no multi-member variant**, so neither a per-model fair CRPS of the CMIP6 reference (≥ 2 members) nor any post-2015 CMIP6 comparison can be assembled — an upstream `CMIP6HistoricalSSP245` generator with `ensemble: "r*i1p1f1"` is the blocking dependency | `climateeval/data/_cmip6_generators.py` |

## II.0 Machinery as built (`climatebench2/scoring.py`, `diags/tier2_scores.py`, `baselines.py`, `leaderboard/`)

**Data & preprocessing (ClimateEval).** `climatebench2 score MODEL` calls
`climateeval._loader.load_cmor_dir` (NetCDF file, flat directory or DRS tree;
`--timerange`, default `19790101/20141231`) and hands the cubes to each CB2 suite via
`climateeval.suites.Suite.get_database`, which writes one DuckDB per suite
(`raw_output`, `metrics`, `variables`, `data_sources`; `climatebench2 leaderboard`
reads them with `climateeval.report._db.read_database`). Reference and comparison data
are ClimateEval DataSources named in the suite YAML (`reference_data:` /
`other_data:`), regridded to the common 2° grid and reduced with ESMValCore
preprocessors. No data loading, regridding or unit handling remains in CB2.

**Scoring engine (`scoring.py`, numpy/scipy only, 24 unit tests).**
- `crps_ensemble(members, obs)` — per-time-step **empirical** CRPS
  `E|X−y| − ½E|X−X′|` with the pairwise mean over all M² ordered pairs → 🟡 make it
  fair (multiply the spread term by `M/(M−1)`, or average over i ≠ j) and raise for
  M = 1 instead of returning |x − y|.
- `lag1_autocorrelation`, `effective_sample_size`, `crps_ess_score` →
  `CRPSScore(score, standard_error, t_eff, r1, n_members, n_time)` ✅ regime (a).
- `chunked_statistic_std(series, chunk_length, "mean"|"trend")` — piControl
  internal-variability σ for an observation-length statistic ✅ (never called).
- `ensemble_consistency(values, obs, sigma_internal, sigma_obs, p_threshold)` →
  `ConsistencyResult(z, p_value, passes, ensemble_mean, total_sigma)` ✅ scalar regime
  (c) with a Gaussian null.
- `eof_basis`, `project_onto_eofs`, `field_consistency` — area-weighted SVD EOFs of a
  *variability sample* plus per-mode Bonferroni consistency 🟡 (the old regime b; the
  new spec wants the *reference's* pre-2015 EOFs, standardised coefficients, fair CRPS
  per coefficient, block bootstrap).
- Tier III: `proxy_site_consistency`, `sample_at_sites`, `le_variance_ratio`,
  `le_spread_pattern_correlation` (§III).

**Scored diagnostics (`diags/tier2_scores.py`).** `_ScoredTimeSeriesMixin.get_output`
post-processes any ClimateEval time-series diagnostic's `raw_output`: per variable it
(i) scores the submission and each `other` CMIP6 model as an M = 1 "ensemble" against
the `reference` series (→ |x − y|, see above), (ii) pools **all** `other` members into
one `CMIP6-MME` baseline row, (iii) adds a `Climatology` baseline row from the
reference's own climatology over `tier2.climatology_baseline_period`; rows carry
`crps`, `crps_se`, `t_eff`, `n_members`, `n_time`. `ScoredAnnualMaxTimeSeries`
overrides `_preprocess` to a per-gridpoint annual maximum before the area mean.
`TrendConsistency` emits `<var>_trend_consistency` rows (`value` = observed trend, `z`,
`p_value`, `ensemble_mean`, `total_sigma`, `n_members`, `passes`) with the ensemble =
submission + CMIP6 members' trends.

**Baselines (`baselines.py`).** `climatology_forecast` ✅ (wired), `two_layer_ebm`
(Held/Geoffroy two-layer, explicit Euler, parameters from `thresholds.yml tier2.ebm`)
and `pattern_scaling_forecast` — pure functions, **not wired** into any diagnostic; no
ERF series, no observational calibration through 2014, no CMIP6-MMM pattern in the
package.

**Leaderboard (`leaderboard/__init__.py`).** `build_scores` classifies `metrics` rows
into gates (`passes` without `p_value`), CRPS (`crps`), consistency (`p_value`),
deterministic (`weighted_*`) and Tier III (`*_site_consistency` in `raw_output`);
`render_html` writes a self-contained static page: Tier I gate matrix with an `ALL`
column (minimum over every gate present), CRPS table with skill relative to the
**Climatology** row only, consistency table, Tier III fractions. `build_scores_table`
reuses ClimateEval's `build_leaderboard_data` for the deterministic CSV summary.
Missing versus the paper's scorecard (§5.6): `S` against the CMIP6 median with
leave-one-out, Required/Extended/N-A gate tagging, held-out/in-sample labels, bootstrap
intervals, per-region resolution, the "non-conforming" category.

**Mapping to the Tier II spec.** Present: ESS-corrected time-averaged CRPS, scalar
consistency test, EOF primitives, climatology baseline, MME row, static leaderboard.
Absent or misaligned: fair normalisation and the M = 1 rule, reference-EOF fair-CRPS
scoring, block bootstrap, observational-uncertainty propagation, piControl σ wiring,
CMIP6-median skill score, leave-one-out, multi-member ingestion, the 1985–2014 baseline
window, and the post-2015 CMIP6 reference ensemble (an upstream ClimateEval gap).

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

*Status: ❌.* `TrendConsistency` (§II.0) tests the OLS trend of the loaded window
against the pooled CMIP6 trend distribution with σ_int = 0; there is no warming-level
statistic, no fixed 1985–2014 baseline, no 1950-start trend, no multi-product obs
spread, and no blending correction. `scoring.chunked_statistic_std(…, "mean")` is the
ready-made σ_int for the level statistic once a piControl series reaches the diagnostic.

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

*Status: 🟡.* `diags/tier2_diagnostics.py::PinatuboResponseGate` (`historical` key):
global-mean `rsds` and `tas` anomalies for Jul 1991–Dec 1993 relative to the
`tier2.climatology_baseline_period` mean (✅ [1985, 2014] since 2026-09-14) — gated
**sign-only** (`pinatubo_dimming`: Δrsds < 0;
`pinatubo_cooling`: Δtas < 0). No observational magnitudes (BSRN / HadCRUT), no
co-variation test, no ENSO removal; the gate sits in the Tier I suite and currently
counts toward the entry ticket.

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

*Status: 🟡.* `HemisphericAsymmetryGate` (`historical`): NH and SH area-mean annual
`tas` OLS trends over `tier2.hemispheric_asymmetry.era` = [1950, 1985]
(`physics.ols_trend`; the era is a threshold now, not a class constant),
`nh_minus_sh_trend` gated < 0;
ITCZ = latitude of the annual zonal-mean `pr` maximum within ±30°, its trend
(°/decade) gated < 0. Sign-only; no HadCRUT/Berkeley comparison; also counts toward the
entry ticket today.

**Seasonal-cycle metrics.** (i) climatological annual range of tas over land
(max−min of 12-month climatology, land-masked, area-mean or EOF-projected map);
(ii) seasonal amplitude of land carbon uptake (`nbp`; peak-to-trough of climatological
cycle vs atmospheric-inversion products); (iii) SST–low-cloud seasonal covariance
(regression of low-cloud fraction on SST over the seasonal cycle in stratocumulus
regions). All aggregated diagnostics (§II.0(b)).

*Status: ❌.* ClimateEval's `AnnualCycle` runs (deterministic RMSE/Pearson of the
12-month climatology) for every core variable, but none of the three protocol
statistics is computed. (ii) is deferred by the paper (no carbon-flux output requested);
the paper's §5.2 now also names a **seasonal cloud-radiative feedback** (SST–CRE
covariance) as an emergent-constraint diagnostic — `swcre`/`lwcre`/`netcre` are derived
variables in ClimateEval's registry, so this is a small CB2 diagnostic once the (b)
engine exists.

**Diurnal cycle.** Amplitude and phase (first harmonic fit) of 3-hourly tas and pr
climatologies vs observational products; aggregated diagnostic (§II.0(b)) on amplitude
and phase separately.
```python
harm = fit_first_harmonic(clim_3hourly)   # A*cos(2*pi*t/24 - phi)
test_consistency(A_obs, A_members); test_consistency(phi_obs, phi_members)  # circular
```

*Status: 🟡* (Extended). ClimateEval `DiurnalCycle` of hourly `pr` vs `ERA5Hourly` in
`ClimateBench2_TierII_daily.yml` (deterministic metrics only); `physics.first_harmonic`
returns amplitude/phase of a 12-point cycle but is unwired and not in local solar time;
CRE diurnal cycle, IMERG and CERES-SYN references ❌.

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

*Status: 🟡.* `ScoredAnnualMaxTimeSeries` gives a global-mean TXx series from
daily `tasmax` (registry variable since `b0e941c`; suite id `tasmax_txx`) against an
`ERA5Monthly` placeholder reference — a daily obs product is the remaining gap;
`Histogram` gives hourly-pr EMD vs ERA5Hourly. None of the eight
ETCCDI indices, the Perkins score, the 1° conservative regrid or the daily obs products
(Berkeley daily, HadGHCND, IMERG, MSWEP) exist. Also see the ClimateEval variable
`prw`/`pr` `3hr` frequencies for the Extended sub-daily list (Table A2).

**Baselines.** (i) **CMIP6 MME — the headline reference**: `E_ref` = median of the
per-model fair CRPS (see §II.0). (ii) climatology persistence: forecast = **1985–2014**
monthly climatology — the no-skill floor, reported alongside. (iii) pattern scaling:
ΔT_global(t) from a 2-layer EBM calibrated to observations **through 2014** × CMIP6 MMM
normalized warming pattern (+ climatology) — the simplest defensible emulator, reported
alongside. All three run through the identical scoring pipeline, but only (i) sets the
headline `S`.

*Status: 🟡.* (i) pooled `CMIP6-MME` row (single r1i1p1f1 member per model, all
pooled) — not the median of per-model scores, and pending the paper's own
mixture-vs-median resolution; (ii) `Climatology` row wired, from
`tier2.climatology_baseline_period` = ✅ [1985, 2014]; (iii) `baselines.two_layer_ebm`
+ `pattern_scaling_forecast` unwired, uncalibrated, no ERF series or MMM pattern.

---

# Tier III — Paleoclimate time-slices and perfect-model tests

## Tier III status summary

| Diagnostic | Spec (short) | Protocol status | Impl. (2026-09-14) | Code |
|---|---|---|---|---|
| lig127k vs proxies | PMIP4 BCs; Osman 2026 / Hoffman 2017 SST; Otto-Bliesner 2021 land T; Scussolini 2019 (+ SISALv3) precip | **Extended** | 🟡 `PaleoProxyConsistencyGate(period_key="lig127k")` — site-wise z-fraction, tas-only, and it **expects `paleo_scripts/paleo_observations/processed/lig127k_proxies.csv`, a file the pipeline never writes** (it produces `paleo_data_cache/processed/observations/lig127k/OttoBliesner2021_tas.nc`, `Scussolini2019_pr.nc`) | `diags/tier3_paleo.py`; data via `paleo_scripts/` |
| lgm vs proxies | Tierney 2020 / Osman 2021 SST; Bartlein 2011 / Cleator 2020 land T | **Required** | 🟡 same disconnect; the pipeline's LGM targets are **lgmDA (Tierney 2020) and LGMR (Osman 2021) data-assimilation fields**, whereas paper App. D (2026-09) says use the **raw proxy compilations, not DA products**; Bartlein 2011 tas/pr gridded ✓; Cleator 2020 ❌ | same |
| midHolocene vs proxies | Osman 2021 SST 5–7 ka; Temp12K; Bartlein 2011 tas + water balance | **Extended** | 🟡 same disconnect; Temp12K and Bartlein 2011 processed ✓; Osman 2021 MH SST ❌; Harrison 2015 lake status ❌ | same |
| midHolocene North-Africa monsoon check | JJAS pr anomaly ≥ +0.5 mm/day, 10–30N, 20W–30E, vs piControl | Extended (with midHolocene) | ✅ `MidHoloceneMonsoonGate` | `diags/tier3_paleo.py` |
| Proxy-aware scoring | **Fair CRPS vs proxies**, proxy error in the observational variance term; pseudo-members from non-overlapping equilibrated blocks | — | ❌ fair CRPS; ❌ block pseudo-members; 🟡 site-consistency fraction (`scoring.proxy_site_consistency`) as the complementary diagnostic. `paleo_scripts/paleo_benchmark.py` computes RMSE/MAE and a *Gaussian* CRPS with the **proxy** σ as the forecast width (proxy-as-distribution, model-as-point) — the inverse of the protocol's statistic | `scoring.py`, `paleo_benchmark.py` |
| Perfect-model: CESM2 train→SSP2-4.5 daily tas/pr, Tier II scoring | **Required (ML only)** | | ❌ no suite, no data path | — |
| Perfect-model: MPI-ESM, GISS ModelE2 | **Extended (ML only)** | | ❌ | — |
| Large-ensemble spread test vs CESM-LE (variance ratio + spatial corr of inter-member variability) | **Extended** | | 🟡 `scoring.le_variance_ratio`, `le_spread_pattern_correlation` pure functions + `tier3.le_spread.variance_ratio_range` [0.5, 2.0] (TODO bound); no diagnostic, suite or CESM-LE data path | `scoring.py` |

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

**Status: 🟡 protocol diagnostics exist but are not connected to the data pipeline.**
- ✅ `diags/tier3_paleo.py::MidHoloceneMonsoonGate` (`midholocene` + `picontrol`):
  `extract_region` 340–30°E × 10–30N (wrap handled), `climate_statistics(period="month")`,
  JJAS cos-weighted mean, anomaly × 86400 gated ≥ `tier3.midholocene_monsoon.jjas_pr_anom_min`
  = 0.5 mm/day (row `midholocene_monsoon`). Matches the spec.
- 🟡 `PaleoProxyConsistencyGate(period_key, proxy_csv, var_name="tas")`: full-period
  climatological anomaly (period − piControl) on the 2° grid, nearest-gridpoint sampling
  at proxy sites (`scoring.sample_at_sites`, longitude modulo 360), per-site z with the
  proxy `error` as σ (`scoring.proxy_site_consistency`, p < 0.05 two-sided); emits
  `<period>_site_consistency` (fraction consistent), `<period>_n_sites`,
  `<period>_mean_abs_z`. No gate check (the paper sets no bound on the fraction); the
  leaderboard shows the fraction. This is the *complementary* statistic — the primary
  fair CRPS with block pseudo-members is ❌.
- ❌ **Data contract mismatch.** `ClimateBench2_TierIII.yml` points the three gates at
  `paleo_scripts/paleo_observations/processed/{midholocene,lgm,lig127k}_proxies.csv`
  (columns `lat`, `lon`, `tas_anom`/`anom`, `error`). `paleo_scripts/process_paleo_observations.py`
  writes nothing of the kind: its outputs are per-dataset NetCDFs under
  `paleo_scripts/paleo_data_cache/processed/observations/<period>/` — gridded
  (`lgmDA_v2.1_tas.nc` with `tas`/`tas_std`, `LGMR_SAT_tas.nc`, `LGMR_SST_tos.nc`,
  `Bartlein2011_{tas,pr}.nc` with `*_std`/`*_sig_val`, `Temp12k_tas.nc` with `tas_anom`)
  or on a `site` dimension (`OttoBliesner2021_tas.nc`, `Scussolini2019_pr.nc` with
  `pr_reliability`). The gate must read these NetCDFs (per dataset, per variable —
  `tas`, `tos`, `pr`) instead of a CSV, and the suite needs one stanza per (period,
  dataset). Paths are also CWD-relative; make them a `--data-root`-relative kwarg.
- ❌ **Dataset coverage vs App. D.** Present in the pipeline: Bartlein 2011 (tas, pr;
  lgm + midHolocene), Temp12K (midHolocene), Otto-Bliesner 2021 (lig127k tas),
  Scussolini 2019 (lig127k pr), the IPCC AR6 Fig. 7.19 global means; `sisal_v3` is
  downloadable but not processed. LGM SST/SAT come only from the **lgmDA / LGMR
  assimilation products**, which the paper now excludes from scoring. Missing: Tierney
  2020 and Osman 2021 **raw** SST proxy compilations (LGM, and Osman's 5–7 ka MH
  averages), Osman 2026 / Hoffman 2017 LIG SST, Cleator 2020, Harrison 2015 lake status,
  SISALv3 processing. `download_paleo_observations.py` keys today: `ipcc_ar6`, `lgmda`,
  `bartlein2011`, `temp12k`, `osman2021`, `sisal_v3`, `lig127k`, `scussolini2019`,
  `tierney_hansen`.
- 🟡 `paleo_scripts/paleo_benchmark.py` (the pre-protocol benchmark, `--model
  --period [--use-picontrol]`) regrids model climatologies to each proxy product and
  reports RMSE, MAE and a Gaussian CRPS whose distribution is the *proxy* (μ, σ) and
  whose "observation" is the model value, plus a skill score against a climatological
  proxy distribution. Useful for the AR6-style figures, but not the protocol's fair CRPS
  of a model pseudo-ensemble against the proxy value. `--use-picontrol` is the last user
  of the legacy `constants.py`/`utils.py`/`benchmark_utils.DataFinder` island; it
  retires once the Tier III suite takes piControl via `--experiment picontrol=`.
- Tier III experiments enter through `--experiment midholocene=DIR` etc. (local
  CMOR directories from `download_model_data/*.sh` + `process_paleo_models.py`); there
  is no ClimateEval PMIP4 DataSource generator yet (an obvious upstream addition:
  `CMIP6LgmR1I1P1F1` etc. by analogy with `CMIP6PiControlR1I1P1F1`).

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

**Status: ❌ (functions only).** `scoring.le_variance_ratio` and
`scoring.le_spread_pattern_correlation` implement (i) and (ii) with unit tests, and
`thresholds.yml` carries a provisional `tier3.le_spread.variance_ratio_range = [0.5,
2.0]` (marked TODO). There is no diagnostic class, no suite, no CLI path for a
"truth" run in place of observations, and no CESM2 / MPI-ESM / GISS-E2 / CESM-LE data
staging (the paper promises these on publication). Design intent (delineation plan §5):
a Tier II suite instance whose `reference_data` is a `ESMValToolCMORizerDataSource`
pointing at the held-out SSP2-4.5 truth, so the identical scored diagnostics run
unchanged; the spread test is one small `ComplexDiagnostic` taking `{"prediction":
members, "truth": CESM-LE members}`. Blocked on multi-member ingestion (§II.0) as much
as on data.

---

# Overall coverage summary

| Tier | Specced diagnostics | ✅ | 🟡 | ❌ |
|---|---|---|---|---|
| I | 18 sub-checks (16 Table-1 rows) + 2 code-only extras | 14 — I.1, I.2a, I.2b, I.3a, I.3b, I.4a, I.4b, I.5b, I.5d, I.6a, I.6b, I.6c, I.8a, I.8b (+ Bjerknes, C–C vs their own specs); I.6a/b, I.6c and I.8a are thin CB2 gates over ClimateEval `main`'s own diagnostics | 3 — I.5a (statistic ✅, but run on historical cubes not ≥ 100 yr piControl), I.5c (superseded criterion), I.7 (window, drift) | 1 — I.3c precip–buoyancy |
| II | fair-CRPS engine + skill score + baselines + ~20 diagnostic families | ESS correction; deterministic metrics for tas/pr/TOA/prw/clt/tos/OHC/sea-ice via ClimateEval; climatology-baseline row on the correct 1985–2014 pre-test window; static leaderboard | empirical (not fair) CRPS; single-member scoring; Gaussian consistency test without σ_int; pooled MME; sign-only Pinatubo & hemispheric asymmetry; TXx reference still a monthly placeholder; sea-ice area not extent; single obs product per variable | reference-EOF fair-CRPS scoring; block bootstrap; obs-uncertainty draws; CMIP6-median skill score; realized warming level & blending; ETCCDI set & Perkins score; ts; surface fluxes; seasonal-cycle triplet; diurnal harmonic scoring; pattern-scaling wiring; held-out labels; **post-2015 multi-member CMIP6 reference (ClimateEval)** |
| III | 3 paleo periods + monsoon check + proxy scoring + perfect model + LE spread | monsoon gate | site-consistency fraction for the three periods — disconnected from the pipeline's NetCDFs, tas-only, DA products instead of raw proxies; LE-spread functions | fair CRPS with block pseudo-members; raw SST proxy compilations; perfect-model suite and data |

**Cross-cutting discrepancies (paper vs current `climatebench2/` code) — complete list,
2026-09-14:**
1. ~~**I.2b atmospheric energy identity reversed in code**~~ — **DONE (2026-09-14, gap
   item 1):** `physics.atmospheric_energy_residual` returns the paper's
   `|Q_rad − (LP + SHF)|` with `Q_rad = sfc_net_rad − TOA_net`.
2. ~~I.1 evaluated over the whole supplied piControl~~ — **DONE (2026-09-14):** both
   criteria use the last `tier1.energy_balance.evaluation_years = 100` annual values
   (the stale `min_years: 500 # TODO` is gone); shorter controls are used whole with a
   warning and reported through `n_years`.
3. ~~I.3a regresses annual means~~ — **DONE (2026-09-14):** deseasonalised monthly
   anomalies (`anomalies(period="month")`) for both `rlutcs` and `ts`.
4. I.5a — σ is now of the **unsmoothed** monthly index (`_rolling_window_length = 1`,
   **done** 2026-09-14); *still open:* the variability suite is fed the historical cubes
   (36 yr by default) rather than ≥ 100 yr piControl (CLI work package).
5. ~~I.5b band-power ratio uses mean PSD per band~~ — **DONE (2026-09-14):** integrated
   power (`np.trapezoid`) per band, so the 1.5 bound means what the paper says.
6. I.5c implements the superseded scalar criterion (ta500 / Maritime-Continent sign
   checks); the pattern-correlation test and its HadISST/ERA5/GPCP reference patterns do
   not exist; four stale keys in `thresholds.yml`.
7. ~~I.6a emits both the `> 1` and the `[1.2, 1.6]` checks~~ — **DONE (2026-09-14, gap
   item 0):** one strict-range check `land_ocean_warming` on
   `tier1.land_ocean_warming.range`; `required_min`/`expected_range` removed.
8. I.7 "2015" = last-30-yr mean (paper: decadal mean centred on 2015); no parallel-segment
   drift removal. Paper-side: App. B.8 writes `F = ΔN + λΔT` with a negative Gregory λ —
   sign should read `ΔN − λΔT` (code is right).
9. **Fair vs empirical CRPS** — `scoring.crps_ensemble` uses the `M²` spread normalisation;
   M = 1 falls through to |x − y| instead of being undefined.
10. **`E_ref`** — the leaderboard's only skill is vs Climatology; the `CMIP6-MME` row is a
    pooled mixture. The paper itself says "unweighted mixture" (§5.4) and "median E"
    (Fig. 4 caption) — resolve in the manuscript, then implement median-of-per-model
    with leave-one-out.
11. ~~`tier2.climatology_baseline_period = [1990, 2020]` overlaps the reserved test
    window~~ — **DONE (2026-09-14, gap item 1):** `[1985, 2014]` for both the
    Climatology baseline and the Pinatubo reference; `baselines.py` docstrings follow,
    and the hemispheric-asymmetry era is now `tier2.hemispheric_asymmetry.era`.
12. Aggregated-diagnostic scoring is the old model-variability-EOF z-test
    (`field_consistency`, unwired); the paper wants reference-EOF fair CRPS with
    standardised coefficients and a block bootstrap.
13. **Test window never loaded** — the CLI default `--timerange 19790101/20141231`
    applies to every suite; ClimateEval's `CMIP6HistoricalR1I1P1F1` is hard-wired to the
    same window and to r1i1p1f1, and there is no SSP2-4.5 generator — the post-2015
    multi-member CMIP6 reference cannot be built with today's ClimateEval.
14. Single-member ingestion end-to-end (no `--member`, one `data_id` per model).
15. Sea ice: ClimateEval computes area, the paper scores extent (15 % threshold).
16. TXx now uses daily `tasmax` (registry variable, suite id `tasmax_txx`; **done**
    2026-09-14 with gap item 0) but still against an `ERA5Monthly` placeholder
    reference; a daily obs product is still missing.
17. **Entry ticket** — the leaderboard `ALL` column spans every gate present, including
    the Bjerknes and C–C extras, the Extended GFMIP/MJO gates and the Tier II Pinatubo /
    hemispheric-asymmetry gates; there is no Required/Extended/extra tag and no
    three-valued pass/fail/N-A state.
18. Tier III proxy gates read `{period}_proxies.csv` files the pipeline does not write;
    the pipeline's LGM targets are DA products the paper now excludes; tas-only.
19. `paleo_benchmark.py`'s Gaussian CRPS treats the proxy as the forecast distribution —
    the inverse of the protocol's model-ensemble fair CRPS.
20. ~~Duplicate physics vs ClimateEval `main` — land–ocean, Arctic and MHT exist upstream
    with identical outputs; `_MISSING_FROM_REGISTRY`/`RegistryFreeVariable` are obsolete
    (`rsds`/`rsus`/`rlds`/`rlus` landed upstream); the pin is 2 months stale.~~
    **DONE (2026-09-14, gap item 0):** pin bumped to `b0e941c`; `LandOceanWarmingGate`,
    `ArcticAmplificationGate` and `MeridionalHeatTransportGate` are `GateMixin`
    wrappers over the upstream classes; `_WarmingResponseGate`, `_transport_profiles`,
    `_MISSING_FROM_REGISTRY`, `RegistryFreeVariable` and `physics.nh_peak` deleted.
21. Paper-side items to fix in the manuscript: App. E says "the Tier I–III diagnostics
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
1. ~~**Fix the gates that are wrong as written**~~ — **DONE 2026-09-14 (this commit).**
   I.2b identity (#1); I.1 last-100-yr slice with `evaluation_years` (#2); I.3a monthly
   anomalies (#3); I.5a unsmoothed index (#4, statistic only); I.5b integrated power
   (#5); `thresholds.yml` clean-up — `min_years` TODO and `required_min`/`expected_range`
   gone (the latter with gap item 0, #7), `climatology_baseline_period → [1985, 2014]`
   and the new `tier2.hemispheric_asymmetry.era` (#11). *Still open here:* the four
   stale ENSO-teleconnection keys, which go with the I.5c rewrite (#6, item 5), and the
   aerosol-forcing window (#8, item 5).
2. **Entry-ticket semantics** (a day): tag every gate Required / Extended / extra
   (suite kwarg or `thresholds.yml`), add pass/fail/N-A, compute `ALL` over Required
   only, and move `pinatubo`/`hemispheric_asymmetry` out of the Tier I suite (#17).
3. **Scoring engine to the 2026-09 spec** (blocking for any Tier II number): fair CRPS
   with the M = 1 rule (#9); multi-member ingestion — `--member` / DRS variant discovery
   in `_cli.py` feeding a member dimension into the scored diagnostics (#14); `E_ref` =
   median per-model fair CRPS with leave-one-out once the paper settles #10;
   reference-EOF fair-CRPS for fields, block bootstrap, observational-uncertainty draws
   (#12); wire `chunked_statistic_std` as σ_int through a `picontrol` path.
4. **Test-window data path** (blocking; *upstream*): Tier II `--timerange` default to
   2015–present; a `CMIP6HistoricalSSP245` DataSource generator (historical + ssp245
   concatenation, `ensemble: "r*i1p1f1"`, open-ended timerange) in ClimateEval (#13).
   Until it lands, Tier II can only be run in-sample.
5. **Re-specced Tier I physics**: I.5c pattern-correlation teleconnections with
   HadISST/ERA5/GPCP reference patterns (#6); I.3c precip–buoyancy (new, with a stored
   GPCP/ERA5 reference slope); I.7 decadal window and parallel-segment drift removal
   (#8, helper *upstream* next to `ECS`); I.3a monthly anomalies (#3); I.5a on the
   piControl experiment (#4). Exercise I.3b/I.5d/I.4a/b on real daily and fixed-SST
   output.
6. **Tier II missing diagnostics**: realized warming level + 1950-start trend +
   blending; the ETCCDI set and Perkins score on a 1° conservative grid; sea-ice extent
   (*upstream* variant of `SeaIceArea*`, #15); seasonal-cycle triplet and the SST–CRE
   feedback; diurnal first-harmonic scoring; pattern-scaling baseline wiring and
   calibration; `rsutcs`/`rlutcs`, `clwvi`/`clivi`, OHC 0–100 m stanzas; additional obs
   DataSources *upstream* (GISTEMP, Berkeley Earth, NOAAGlobalTemp, IMERG, MSWEP,
   HadSST/CRU TS, NSIDC Sea Ice Index, Berkeley daily / HadGHCND, RSS, CERES SYN).
7. **Tier III**: read the pipeline's per-dataset NetCDFs instead of the non-existent
   CSVs, one stanza per (period, dataset, variable) (#18); add the raw SST compilations
   (Tierney 2020, Osman 2021/2026, Hoffman 2017), Cleator 2020, Harrison 2015 and SISALv3
   processing and drop the DA products from scoring; fair CRPS with block pseudo-members
   from the equilibrated run; a PMIP4 DataSource generator *upstream*; the perfect-model
   + LE-spread suite once CESM2/MPI/GISS/CESM-LE data are staged (#19); retire
   `paleo_benchmark.py --use-picontrol` and with it `constants.py`, `utils.py`,
   `benchmark_utils.py`.
8. **Upstream track** (delineation plan §7): the generic physics still in CB2 —
   geostrophic balance, MJO ratio, ITCZ–EFE, clear-sky β, closure residuals,
   teleconnection regression maps, amip-4xCO2 ERF, GFMIP Δλ, Pinatubo / hemispheric
   anomalies — are candidates for ClimateEval; the paper's App. E claim becomes accurate
   only once they land, so either upstream them before submission or soften the
   sentence (#21).
