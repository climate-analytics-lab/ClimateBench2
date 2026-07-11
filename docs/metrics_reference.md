# ClimateBench v2 — Metrics Reference

**Purpose.** Single authoritative reference for every metric/diagnostic required by the
ClimateBench v2 protocol (JAMES draft), with (a) scientific rationale, (b) exact
calculation spec (inputs, preprocessing, formula, threshold/score), (c) implementation
status in this repository, and (d) pseudocode. Definitions are tool-agnostic; a note on
each Tier II entry states whether it is expected to be provided by **ClimateEval**
(YAML-suite diagnostic framework on ESMValCore, derived from ICONEval — see
`docs/iconeval_integration_plan.md`) or by **bespoke** code.

**Codebase surveyed** (staged read-only copy at `/mnt/user-data/uploads/ClimateBench2/`;
paths below are repo-relative):
`benchmark_scrips/*.py`, `constants.py`, `utils.py`, `esmvaltool/recipe_pr_rmse.yml`,
`docs/iconeval_integration_plan.md`, `paleo_scrips/paleo_benchmarks.ipynb`.
Note the intentional directory typos `benchmark_scrips/` and `paleo_scrips/`.

**Conventions.**
- TOA net downward flux: `N = rsdt − rsut − rlut` (`utils.compute_toa_net`).
- Surface net downward flux: `F_sfc = (rsds − rsus) + (rlds − rlus) − hfss − hfls`
  (`utils.compute_sfc_net`; hfss/hfls positive upward in CMIP6).
- Global means are area-weighted; scripts use `cos(lat)` weights
  (`utils.compute_weighted_annual_mean`, `utils.area_mean`); `DataFinder.load_cell_area_ds`
  can supply true `areacella/areacello` but the Tier I scripts use cos(lat) directly.
- All Tier I scripts load data via `benchmark_scrips/benchmark_utils.DataFinder`
  (`load_experiment_ds` for piControl/abrupt-4xCO2/hist-aer; `load_model_ds` for
  historical+SSP), take the ensemble mean over `r*i1p1f1` members, and write one-row
  CSVs via `utils.save_results_csv` into `results/<benchmark>/`.
- Status legend: ✅ implemented · 🟡 partial / deviates from spec · ❌ missing.

---

# Tier I — Physical consistency (entry ticket, pass/fail)

Every check is binary pass/fail. A model must pass Tier I to be scored in Tier II/III.

## Tier I status summary

| # | Diagnostic | Paper requirement (short) | Status | Code |
|---|---|---|---|---|
| I.1 | Energy balance (piControl) | \|μ(N)\| < 0.1 W/m²; 10-yr-running-mean drift \|δ\| < 0.02 W/m²/decade; ≥500 yr | 🟡 partial — drift threshold 0.1 not 0.02, linear-trend method, no mean-imbalance pass/fail, ≥100 yr default | `energy_balance_benchmark.py` |
| I.2a | Water budget closure | \|⟨P⟩−⟨E⟩\| < 0.05 mm/day | 🟡 partial — relative test \|P−E\|/P < 1% instead of absolute | `covariance_benchmark.py` (check 3) |
| I.2b | Atmospheric energy budget | \|⟨L·P⟩ − (⟨Q_rad⟩+⟨SHF⟩)\| < 2 W/m² | 🟡 partial — surface budget ratio test substituted, not the atmospheric-column form | `covariance_benchmark.py` (check 4) |
| I.3a | Clear-sky LW feedback β = ∂rlutcs/∂Ts | global-mean gridpoint slope within ±25% of 2.2 W/m²/K, historical | 🟡 partial — global-mean (not gridpoint) regression, piControl (not historical), 2.0±0.5 window | `covariance_benchmark.py` (check 2) |
| I.3b | Midlatitude geostrophic balance | spatial ρ(u, u_g) at 850 hPa daily, 30–60°, > 0.9 | ❌ missing | — |
| I.3c | Tropical precipitation–buoyancy | monthly P′ vs column-MSE′ slope, 20S–20N, ±30% of GPCP/ERA5 | 🟡 divergent — climatological log(pr)-vs-prw spatial regression, 30S–30N, fixed slope/r² thresholds | `covariance_benchmark.py` (check 5) |
| I.4a | GFMIP SST patch experiments | Δλ = ΔR_EP/ΔTs_EP − ΔR_WP/ΔTs_WP > 0.5 W/m²/K | ❌ missing | — |
| I.4b | amip-4xCO2 ERF | 6.5–9.0 W/m² | ❌ missing | — |
| I.5a | ENSO amplitude | σ(Niño-3.4) ∈ [0.5, 1.4] K | 🟡 partial — code window [0.4, 1.8] K | `enso_benchmark.py` |
| I.5b | ENSO spectrum | power(2–7 yr)/power(1–2 yr) > 1.5 | 🟡 partial — peak-period-in-band check, not band-power ratio | `enso_benchmark.py` |
| I.5c | ENSO teleconnections | tropical 500 hPa T regression > 0; MC precip regression < 0; within factor 2 of ERA5/GPCP | 🟡 partial — sign-only composites, surface tas not ta500, no amplitude check | `enso_benchmark.py` |
| I.5d | MJO Wheeler–Kiladis | east/west power ratio (k=1–3, 30–90 d) > 1.5 | ❌ missing | — |
| I.6a | Land–ocean warming ratio | ∈ [1.2, 1.6] (>1 required); a4x last 10 yr | 🟡 near-complete — last 50 yr not 10 | `land_ocean_warming_benchmark.py` |
| I.6b | Arctic amplification | (ΔT>66.5N)/(ΔT global) ≥ 1.5; a4x last 10 yr | 🟡 near-complete — last 50 yr not 10 | `arctic_amplification_benchmark.py` |
| I.6c | ECS (Gregory, 150 yr) | ∈ [1, 7] K | 🟡 near-complete — ECS computed, no [1,7] K pass/fail emitted | `ecs_benchmark.py` |
| I.7 | Aerosol forcing (hist-aer) | 2015 aerosol ERF ∈ [−2.0, −0.5] W/m²; ΔT(2015) < 0 | ✅ implemented (end-of-period 30-yr window used for "2015") | `aerosol_forcing_benchmark.py` |
| I.8a | Meridional heat transport | OMET peak 1.5–2.0 PW near 15–20°; AMET peak 4–5 PW near ~45° | 🟡 near-complete — peak-latitude pass windows widened (10–25°, 30–50°) | `meridional_heat_transport_benchmark.py` |
| I.8b | ITCZ–EFE relationship | 12-month climatology; slope within ±50% of ~3°/PW; r > 0.9 | 🟡 partial — all monthly timesteps not climatology, r ≥ 0.85, slope window −1.5..−5.0 °/PW, ad-hoc 2-month lag, hard-coded array-size bug | `itcz_efe_benchmark.py` |
| (extra) | Bjerknes compensation 40–70N | not in paper's Tier I list as specced | ✅ code-only extra | `bjerknes_benchmark.py` |
| (extra) | Clausius–Clapeyron scaling | not in paper's Tier I list as specced | ✅ code-only extra | `covariance_benchmark.py` (check 1) |

---

## I.1 Energy balance closure (piControl)

**Measures.** Whether the coupled model conserves energy: an unforced control run must
have near-zero global-mean TOA net flux and negligible secular drift. This is the most
basic "the model is a physically closed system" test.

**Spec (paper).**
- Inputs: piControl monthly `rsdt`, `rsut`, `rlut`; run length ≥ 500 yr
  (⚠ paper elsewhere says ≥ 100 yr — internal inconsistency to be resolved).
- Compute global annual-mean `N(t) = rsdt − rsut − rlut`.
- Pass criterion 1: long-term mean `|μ(N)| < 0.1 W/m²`.
- Pass criterion 2: drift of the **10-yr running mean** of N, `|δ| < 0.02 W/m²/decade`.

**Implementation status: 🟡 partial** — `benchmark_scrips/energy_balance_benchmark.py`.
- ✅ Loads piControl rsdt/rsut/rlut, computes global annual-mean N.
- 🟡 Drift computed as an **OLS linear trend of the raw annual series**
  (`compute_drift`, `scipy.stats.linregress`, slope×10), not the drift of a 10-yr
  running mean. Threshold `DRIFT_THRESHOLD = 0.1` W/m²/decade — **5× looser than the
  paper's 0.02**. (`constants.REFERENCE_BOUNDS["toa_net_flux"]` also carries 0.1.)
- 🟡 Mean imbalance is **reported** (`toa_mean_imbalance_Wm2`) but there is **no
  |μ|<0.1 pass flag**; `REFERENCE_BOUNDS` carries an unused ±1.0 W/m² "acceptable" range.
- 🟡 `--min_years` defaults to 100 (help text notes "spec: 500") and only warns.
- ➕ Extra: checks mean `rsut`/`rlut` against ICONEval/CERES-EBAF global-mean bounds
  from `constants.REFERENCE_BOUNDS` (rsut ∈ [91.1, 128.8], rlut ∈ [226.4, 246.3] W/m²).
  ⚠ CLAUDE.md says bounds come from `reference_bounds.yaml`; the yaml is only a *plan*
  (`docs/iconeval_integration_plan.md` §2) — the code actually imports the dict from
  `constants.py`.
- Output: `results/energy_balance/energy_balance_results.csv`.

**Pseudocode (per spec).**
```python
N = gmean(rsdt) - gmean(rsut) - gmean(rlut)        # annual, area-weighted, piControl
assert len(N) >= 500                                # paper (>=100 in other paper text)
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

**Status: 🟡 partial** — `covariance_benchmark.py` check 3 (`wb_*` outputs).
Implements the physics correctly but passes on a **relative** criterion
`|P−E|/P < 1%` (≈0.03 mm/day at P≈3 mm/day — slightly stricter in practice but not
the paper's formulation). Uses first `--n_years` (default 150) of piControl.
Output columns `wb_P_mmday, wb_E_mmday, wb_rel_err_pct, wb_pass` in
`results/covariance_consistency/covariance_results.csv`.

```python
P = gmean_annual(pr, piControl).mean()             # kg m-2 s-1
E = gmean_annual(hfls, piControl).mean() / 2.5008e6
passes = abs(P - E) * 86400 < 0.05                 # mm/day  (code: abs(P-E)/P < 0.01)
```

### I.2b Atmospheric energy budget: ⟨L·P⟩ ≈ ⟨Q_rad⟩ + ⟨SHF⟩

**Measures.** Atmospheric-column energy conservation: latent heating from precipitation
must balance net atmospheric radiative cooling plus surface sensible heat input.

**Spec.** piControl global multidecadal means. `Q_rad` = net radiative cooling of the
atmospheric column = (TOA net) − (surface net radiation) with appropriate signs:
`Q_rad = (rsdt − rsut − rlut) − [(rsds − rsus) + (rlds − rlus)]` (negative ≈ −100 W/m²
cooling; convention must be fixed so the identity reads `L_v·P = −Q_rad,cool + SHF` —
implementers should verify signs against one model before hard-coding).
**Pass: |⟨L_v·P⟩ − (⟨Q_rad⟩ + ⟨hfss⟩)| < 2 W/m²** (absolute).

**Status: 🟡 partial / physically different** — `covariance_benchmark.py` check 4
(`lhf_*`) implements a **surface** energy-budget identity instead:
`hfls ≈ (rsds−rsus) + (rlds−rlus) − hfss`, pass if the ratio
`hfls_mean / (Qnet_sfc − hfss)_mean ∈ [0.9, 1.1]`. That is the surface budget
(equivalent only when F_sfc≈0 globally, which piControl approximately satisfies), not
the paper's atmospheric-column LP-vs-Q_rad+SHF test, and it uses a ratio window rather
than the 2 W/m² absolute bound. Needs rework or an explicit decision that the surface
form is the adopted definition.

```python
LP    = 2.5008e6 * gmean(pr).mean()                        # W/m2
Qrad  = gmean(rsds - rsus + rlds - rlus                    # sfc net radiation
              - (rsdt - rsut - rlut)).mean()               # minus TOA net -> atm cooling
SHF   = gmean(hfss).mean()
passes = abs(LP - (Qrad + SHF)) < 2.0                      # W/m2
```

---

## I.3 Diagnostic covariances (historical)

Emergent internal covariances that any physically plausible atmosphere must reproduce.
Paper computes these on the **historical** experiment; current code uses **piControl**.

### I.3a Clear-sky longwave feedback β = ∂rlutcs/∂Ts

**Measures.** The tight, theoretically understood link between surface temperature and
clear-sky OLR (Koll & Cronin 2018); observed value ≈ 2.2 W/m²/K (CERES).

**Spec.** For each grid point, temporally regress monthly (or annual) `rlutcs` on
surface temperature `ts` over the historical period; area-average the slope field.
**Pass: global-mean slope within ±25% of 2.2 W/m²/K → [1.65, 2.75] W/m²/K.**

**Status: 🟡 partial** — `covariance_benchmark.py` check 2 (`tolr_*`):
regresses **global-annual-mean** Δrlutcs on **global-annual-mean** Δtas (a single
regression, not a gridpoint slope map), on **piControl** (first `n_years`), against
**tas** not **ts**, with pass window **2.0 ± 0.5 W/m²/K**. Global-mean-on-global-mean
regression is a related but distinct statistic (weights variability patterns
differently). Update to gridpoint regression + [1.65, 2.75] window, historical period.

```python
beta = xr.apply_ufunc(linregress_slope, ts_anom, rlutcs_anom,   # per grid point, over time
                      input_core_dims=[["time"], ["time"]], vectorize=True)
beta_gm = area_mean(beta)
passes = 0.75 * 2.2 <= beta_gm <= 1.25 * 2.2                     # W/m2/K
```

### I.3b Midlatitude geostrophic balance

**Measures.** Large-scale dynamical consistency: daily midlatitude winds must be close
to geostrophic balance with the model's own geopotential field.

**Spec.** Inputs: **daily** 850 hPa zonal wind `ua850` and geopotential height `zg850`
(historical). Geostrophic wind `u_g = −(g/f) ∂Z/∂y`, `f = 2Ω sin(lat)`. For each day (or
pooled), compute the **spatial** Pearson correlation ρ(u, u_g) over 30–60° (each
hemisphere or combined; masking |lat|<30 avoids small f). **Pass: ρ > 0.9.**

**Status: ❌ missing.** No script; would require daily `ua`, `zg` (table `day`), which
`constants.VARIABLE_FREQUENCY_GROUP` does not yet include (all entries are monthly).

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

**Status: 🟡 divergent** — `covariance_benchmark.py` check 5 (`neelin_*`) implements a
different statistic: **time-mean climatology** of log(pr) regressed **spatially across
grid cells** on time-mean `prw` (column water vapour, not MSE), over **30S–30N**, on
**piControl**, with fixed thresholds (slope > 0.01 log(mm/day)/mm and r² > 0.20) and
**no observational reference**. Captures the qualitative pr–CWV relationship but is not
the paper's monthly-anomaly P′-vs-⟨MSE⟩′ regression with a ±30% obs window.

```python
h_col = column_integral(cp*ta + g*zg + Lv*hus)               # J/m2, monthly
Pp, hp = monthly_anom(pr).sel(lat=slice(-20,20)), monthly_anom(h_col).sel(lat=slice(-20,20))
slope_mod = pooled_regression(hp, Pp)                        # over time and space
slope_obs = pooled_regression(era5_mse_anom, gpcp_pr_anom)
passes = abs(slope_mod/slope_obs - 1) <= 0.30
```

### (extra, code-only) Clausius–Clapeyron scaling Δprw vs Δtas

`covariance_benchmark.py` check 1 (`cc_*`): global-annual-mean fractional `prw` anomaly
(%) regressed on Δtas (K) in piControl; pass if slope ∈ 7 ± 2 %/K (Held & Soden 2006;
ported from ICONEval `prw_anom_vs_tas_anom`). **Not in the paper's Tier I list** — keep
as a supplementary sanity check or fold into I.3.

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

**Status: ❌ missing.** No code; flagged in `docs/iconeval_integration_plan.md` (issue
#73, "requires non-standard experiments not in CMIP6 protocol"). Needs a data path for
non-CMIP experiment output (submission-provided), not Pangeo.

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

**Status: ❌ missing.** (Distinct from `ecs_benchmark.py`'s Gregory intercept F_4x,
which is a regression-based forcing estimate from the coupled run, not fixed-SST ERF.)

```python
erf = gmean(toa_net(amip_4xCO2)).mean("time") - gmean(toa_net(amip)).mean("time")
passes = 6.5 <= erf <= 9.0
```

---

## I.5 Coupled variability (piControl ≥ 100 yr)

### I.5a–c ENSO — `benchmark_scrips/enso_benchmark.py`

**Measures.** Existence, amplitude, timescale and teleconnection footprint of the
model's dominant coupled mode of interannual variability.

**Index definition (code, follows ICONEval `recipe_ocean_timeseries.yml`).**
Niño-3.4 = area-mean `tos` in 5S–5N, 190–240°E (=170W–120W); remove monthly
climatology; 3-month centred rolling mean (`compute_nino34`). Handles curvilinear
ocean grids via masking (`_sel_region`, `utils.is_curvilinear`, `utils.area_mean`).

**(a) Amplitude.**
- Spec: **σ(Niño-3.4) ∈ [0.5, 1.4] K**.
- Code: `check_amplitude` uses **[0.4, 1.8] K** ("factor of two around ~0.9 K").
  ⚠ Discrepancy; also `docs/iconeval_integration_plan.md` mentions a third window
  (0.7–1.2 K). Align on the paper's [0.5, 1.4].
- Status: 🟡 partial (threshold mismatch).

**(b) Spectral shape.**
- Spec: **ratio of spectral power in the 2–7 yr band to the 1–2 yr band > 1.5**.
- Code: `check_spectral_peak` computes a Welch periodogram (fs=12/yr, nperseg=120
  months) and passes if the **single dominant peak period** lies in 2–7 yr. A peaked
  spectrum with the max in-band can still fail the paper's band-ratio and vice versa.
- Status: 🟡 partial (different statistic).

```python
f, S = welch(nino34, fs=12, nperseg=120)          # cycles/yr
band = lambda lo, hi: S[(f >= 1/hi) & (f <= 1/lo)].mean()   # periods lo..hi years
ratio = band(2, 7) / band(1, 2)
passes = ratio > 1.5
```

**(c) Teleconnections.**
- Spec: regressions on the Niño-3.4 index — tropical-mean **500 hPa** temperature
  response **positive**, Maritime Continent precipitation response **negative**, each
  **within a factor of 2** of the ERA5/GPCP regression coefficients.
- Code: `check_teleconnections` composites warm months (Niño-3.4 > 0.5 K) and checks
  **sign only** of (i) tropical-mean (30S–30N) **tas** anomaly > 0 and (ii) Maritime
  Continent (10S–10N, 90–150E) pr anomaly < 0. Uses surface tas, not ta500; no
  regression, no obs-amplitude factor-2 check.
- Status: 🟡 partial.

```python
reg_T  = regress(ta500_tropics_anom_gm, nino34)   # K per K of Nino3.4
reg_P  = regress(pr_MC_anom_gm,          nino34)
passes = (reg_T > 0) and (reg_P < 0) \
     and 0.5 <= reg_T/reg_T_era5 <= 2.0 and 0.5 <= reg_P/reg_P_gpcp <= 2.0
```

Output: `results/enso/enso_results.csv` (`nino34_std_K`, `spectral_peak_yr`,
composites, per-check pass flags, `pass_all`).

### I.5d MJO (Wheeler–Kiladis)

**Measures.** Eastward-propagating intraseasonal convective variability.

**Spec.** Wheeler–Kiladis wavenumber–frequency spectrum of near-equatorial daily
precipitation (or OLR): **ratio of eastward to westward power for zonal wavenumbers
k = 1–3 and periods 30–90 days > 1.5.**

**Status: ❌ missing.** Requires daily `pr` or `rlut` (table `day`), a symmetric/
background-removed space–time spectrum (e.g. via `wavenumber_frequency` routines).

```python
pr_eq = pr_daily.sel(lat=slice(-15, 15)).mean("lat")           # detrended, tapered
P = abs(np.fft.fft2(pr_eq)) ** 2                               # (freq, wavenumber)
east = P[(1/90 <= f) & (f <= 1/30), (k >= 1) & (k <= 3)].sum() # eastward: k>0,f>0
west = P[(1/90 <= f) & (f <= 1/30), (k <= -1) & (k >= -3)].sum()
passes = east / west > 1.5
```

---

## I.6 Basic forced responses (abrupt-4xCO2)

Paper: averages over the **last 10 yr** annual mean of abrupt-4xCO2 unless stated;
code uses the **last 50 yr** (`--equilibrium_years 50`) for I.6a/b. Decide and unify —
50 yr is less noisy, 10 yr is the written spec.

### I.6a Land–ocean warming ratio — `land_ocean_warming_benchmark.py`

**Measures.** Land must warm faster than ocean under GHG forcing (thermal inertia +
lapse-rate/moisture constraints; Sutton 2007, Joshi 2008).

**Spec.** Ratio = ΔT_land / ΔT_ocean, where Δ is equilibrium-period abrupt-4xCO2 mean
minus the piControl long-term mean, per domain. Domains defined by `sftlf` (fx land
fraction, 0–100). **Required: ratio > 1. Expected range: [1.2, 1.6].**

**Status: 🟡 near-complete.**
- ✅ Loads piControl + abrupt-4xCO2 `tas` and `sftlf` (`load_land_fraction` with
  local→GCS→ESGF cascade); domain weights `cos(lat)·sftlf/100` (land) and
  `cos(lat)·(1−sftlf/100)` (ocean) — correctly fraction-weighted, not binary masks.
- ✅ Pass flag `ratio > 1.0`; `in_expected_range` flag for [1.2, 1.6].
- 🟡 Equilibrium window = last 50 yr of 150 (paper: last 10 yr).
- Output: `results/land_ocean_warming/land_ocean_warming_results.csv`.

```python
w_land, w_ocean = coslat * sftlf/100, coslat * (1 - sftlf/100)
dT_land  = wmean(a4x_tas[-N_eq:], w_land)  - wmean(pi_tas, w_land)     # annual means
dT_ocean = wmean(a4x_tas[-N_eq:], w_ocean) - wmean(pi_tas, w_ocean)
ratio = dT_land / dT_ocean
passes = ratio > 1.0;  in_range = 1.2 <= ratio <= 1.6
```

### I.6b Arctic amplification — `arctic_amplification_benchmark.py`

**Measures.** Polar amplification from ice-albedo and lapse-rate feedbacks and
poleward transport (Pithan & Mauritsen 2014).

**Spec.** ΔT(lat > 66.5N) / ΔT(global) ≥ **1.5**, anomalies as in I.6a.

**Status: 🟡 near-complete.** Correct region (`ARCTIC_LAT_MIN = 66.5`), correct ratio
and threshold; same 50-yr-vs-10-yr window deviation. Output:
`results/arctic_amplification/arctic_amplification_results.csv`.

```python
dT_arc = wmean(a4x_tas[-N_eq:], coslat, lat_min=66.5) - wmean(pi_tas, coslat, lat_min=66.5)
dT_glo = wmean(a4x_tas[-N_eq:], coslat)               - wmean(pi_tas, coslat)
passes = (dT_arc / dT_glo) >= 1.5
```

### I.6c ECS via Gregory regression — `ecs_benchmark.py`

**Measures.** Equilibrium climate sensitivity diagnosed from the transient
abrupt-4xCO2 response (Gregory et al. 2004).

**Spec.** 150 yr of abrupt-4xCO2. Annual global means of ΔT (tas anomaly vs piControl
long-term mean) and ΔN (TOA net anomaly vs piControl mean). OLS: `N = F_4x + λ·ΔT`;
`F_2x = F_4x/2`; `ECS = −F_2x/λ`. **Pass: ECS ∈ [1, 7] K.**

**Status: 🟡 near-complete.** `utils.gregory_regression` implements exactly this
(slope = λ, intercept = F_4x, ECS = −F_2x/λ); baseline is the piControl **long-term
mean** (no drift correction / parallel-segment differencing — acceptable simplification
but worth noting for drifting controls). **No [1, 7] K pass/fail flag is written** —
only ecs_K, lambda, F_4x, F_2x, r². Output: `results/ecs/ecs_results.csv`.

```python
dT = annual_gmean(a4x.tas)  - pi_gmean_tas                      # 150 values
dN = annual_gmean(toa_net(a4x)) - pi_gmean_toa_net
lam, F4x = polyfit(dT, dN, 1)                                    # slope, intercept
ECS = -(F4x / 2) / lam
passes = 1.0 <= ECS <= 7.0                                       # NOT yet in code
```

---

## I.7 Aerosol forcing (hist-aer, DAMIP) — `aerosol_forcing_benchmark.py`

**Measures.** Whether aerosols exert a net negative (cooling) forcing of realistic
magnitude — a key causal-attribution requirement.

**Spec.** From DAMIP `hist-aer` (aerosol-only historical): **2015 aerosol ERF ∈
[−2.0, −0.5] W/m²** and global-mean **ΔT(2015) < 0** (cooling), anomalies vs piControl.

**Status: ✅ implemented** (with a defensible interpretation of "2015"):
- λ-corrected ERF (Forster et al. 2021, AR6 Ch.7): `ERF = ΔN_end − λ·ΔT_end`,
  where λ comes from a fresh abrupt-4xCO2 Gregory regression (`--n_years_ecs 150`) and
  ΔN_end/ΔT_end are means over the **last `--end_period_years` (default 30) years** of
  hist-aer relative to the piControl long-term mean.
- Pass flags: `pass_cooling` (ΔT_end < 0), `pass_erf_range` (−2.0 ≤ ERF ≤ −0.5),
  `passes` = both. Constants `ERF_MIN = −2.0`, `ERF_MAX = −0.5` match the paper.
- ⚠ Nuance: paper says "2015" values; code uses an end-of-record 30-yr mean (hist-aer
  typically ends 2014/2020 depending on model) — a more robust estimator of the same
  quantity, but document the choice.
- Output: `results/aerosol_forcing/aerosol_forcing_results.csv`.

```python
lam = gregory(a4x_dT, a4x_dN).slope                       # W/m2/K from abrupt-4xCO2
dT_end = (histaer_gmean_tas_annual - pi_tas_mean)[-30:].mean()
dN_end = (histaer_gmean_N_annual  - pi_N_mean )[-30:].mean()
ERF = dN_end - lam * dT_end
passes = (dT_end < 0) and (-2.0 <= ERF <= -0.5)
```

---

## I.8 Coupled diagnostics

### I.8a Meridional heat transport partitioning — `meridional_heat_transport_benchmark.py`

**Measures.** Correct partitioning of poleward energy transport: ocean dominates the
deep tropics, atmosphere the midlatitudes (Trenberth & Caron 2001; ECCO/ERA5).

**Method (residual, shared with I.8b and Bjerknes via `utils.py`).**
`F_TOA = rsdt − rsut − rlut`; `F_sfc = (rsds−rsus) + (rlds−rlus) − hfss − hfls`;
`div_A = F_TOA − F_sfc`. Zonal-mean, then
`MET(φ) = 2π a² ∫_{−π/2}^{φ} F̄(φ′) cos φ′ dφ′` (`utils.compute_meridional_transport`,
Riemann cumsum from the S pole). AMET from `div_A`, OMET from `F_sfc`.
Inputs: piControl monthly, 9 Amon variables; `--min_years 200` (warn-only).

**Spec.** **Peak OMET 1.5–2.0 PW near 15–20°N; peak AMET 4–5 PW at ~45°N**
(vs ECCO/ERA5).

**Status: 🟡 near-complete.**
- ✅ Full residual method, time-mean profiles in PW, NH peak finding, magnitude and
  latitude pass flags, plus an extra `pass_crossover` (OMET peak equatorward of AMET
  peak). `pass_all` = all five.
- 🟡 Peak-latitude pass windows are wider than the paper: OMET lat ∈ [10, 25]°
  (paper 15–20°), AMET lat ∈ [30, 50]° (paper "~45°"). Magnitude windows match
  ([1.5, 2.0], [4.0, 5.0] PW). Search bands wider still (5–30°, 25–55°).
- ⚠ Residual OMET inherits any global F_sfc imbalance (no Fasullo–Trenberth-style
  budget correction / forcing the integral to zero at the N pole) — for a
  well-balanced piControl this is small, but a drifting model will show spurious
  transports; consider removing the global-mean flux before integrating.
- Output: `results/meridional_heat_transport/meridional_heat_transport_results.csv`.

```python
div_A, F_sfc = (toa_net - sfc_net), sfc_net                    # (time, lat, lon)
AMET = cumint_from_spole(div_A.mean("lon"))                    # 2*pi*a^2 * sum F cos(lat) dlat
OMET = cumint_from_spole(F_sfc.mean("lon"))
omet_pk, omet_lat = nh_peak(OMET.mean("time")/1e15, 5, 30)     # PW
amet_pk, amet_lat = nh_peak(AMET.mean("time")/1e15, 25, 55)
passes = (1.5<=omet_pk<=2.0) & (15<=omet_lat<=20) \
       & (4.0<=amet_pk<=5.0) & (abs(amet_lat-45)<=5)           # paper windows
```

### I.8b ITCZ–energy flux equator (EFE) — `itcz_efe_benchmark.py`

**Measures.** The energetic constraint on tropical rainfall: the ITCZ sits near the
energy flux equator and migrates with the cross-equatorial atmospheric energy transport
(Donohoe 2013; Schneider 2014; Kang 2008/2009).

**Spec.** Historical **climatological seasonal cycle (12 monthly means)**:
regress the latitude of the zonal-mean precipitation maximum on the EFE latitude
(AMET zero crossing) — equivalently on the cross-equatorial flux F_xeq —
**slope within ±50% of ~3°/PW** (i.e. |slope| ∈ [1.5, 4.5] °/PW, negative sign for
ITCZ-vs-southward-flux convention) and **r > 0.9**.

**Status: 🟡 partial** (and buggy):
- ✅ AMET residual method (as I.8a) on historical (`load_model_ds`, default
  1850–2014); ITCZ = `idxmax` of zonal-mean pr in ±30°; EFE = near-equatorial AMET
  zero crossing in ±40°; F_xeq = AMET interpolated at lat 0.
- 🟡 Uses **every monthly timestep** (~1980 months), not the 12-month climatology.
- 🟡 Thresholds: `r ≥ 0.85` (paper 0.9); slope pass window `[−5.0, −1.5] °/PW`
  (paper ±50% of 3 → [−4.5, −1.5]).
- 🟡 Ad-hoc **2-month lag** between EFE and ITCZ (`efe_v[:-2]` vs `itcz_v[2:]`,
  likewise in the slope fit) — not in the spec; document or remove.
- 🐛 **Bug:** `compute_efe` pads sign-change detection with
  `np.ones((1980, 1))` — a **hard-coded time length** (165 yr × 12). Any other
  period/model length breaks or silently mis-indexes. Also `candidates` picks the
  minimum-|lat| sign change using the derivative array as a mask carrier; fragile.
- Output: `results/itcz_efe/itcz_efe_results.csv`.

```python
clim = monthly_climatology(historical)                     # 12 maps per field
AMET  = cumint_from_spole((toa_net(clim) - sfc_net(clim)).mean("lon")) / 1e15   # PW
itcz  = zonal_mean(clim.pr).sel(lat=slice(-30,30)).idxmax("lat")   # 12 values
efe   = zero_crossing_nearest_equator(AMET, band=20)                # 12 values
fxeq  = AMET.interp(lat=0)
slope, r = linfit(fxeq, itcz)                               # deg per PW
passes = (abs(r) > 0.9) and (1.5 <= abs(slope) <= 4.5)
```

### (extra, code-only) Bjerknes compensation — `bjerknes_benchmark.py`

Not in the paper's Tier I list as provided (it *is* in repo CLAUDE.md); treat as an
optional/extended Tier I check pending paper reconciliation.
**Measures** decadal anti-correlation of AMET and OMET anomalies at 40–70N
(Bjerknes 1964; Outten 2018). **Method:** residual AMET/OMET (as I.8a), 40–70N band
mean, monthly-anomaly (`utils.anomaly`), 121-month centred running mean, Pearson r;
also a DJF-only variant (window 30 months). **Pass:** annual r < −0.3 AND DJF r < −0.3;
reports `winter_stronger` (|r_DJF| > |r_annual|). piControl, `--min_years 200`.
Output: `results/bjerknes_compensation/bjerknes_results.csv`. Status: ✅ (vs its own
spec).

---

# Tier II — Probabilistic scoring against post-2015 observations

**Scope (paper).** Score model *ensembles* against observations over 2015–present.
Core variables: `tas` (incl. **daily extremes**), `ts`, `pr` (incl. **intensity PDF**),
TOA fluxes, **sea ice**. Extended: OHC, surface fluxes, cloud properties, `prw`.
Baselines every submission is compared against: (i) persistence of the **1990–2020
climatology**, (ii) **pattern scaling** (2-layer energy-balance model × CMIP6
multi-model-mean warming pattern), (iii) the **CMIP6 multi-model ensemble** itself.

**Two scoring regimes (supersedes "CRPS for everything"):**

**(a) Time-resolved quantities** — monthly/annual anomaly time series 2015–present:
**CRPS** of the model ensemble against the observed series, averaged over time, with an
**effective-sample-size (autocorrelation) correction** on the time average / its
uncertainty:
```
CRPS(F, y) = ∫ [F(x) − 1{x ≥ y}]² dx ;  score = (1/T_eff) Σ_t CRPS_t ,
T_eff = T · (1 − r1) / (1 + r1)          # lag-1 autocorrelation correction
```

**(b) Aggregated scalar diagnostics** — climatological means, trends, variability
amplitudes, seasonal-cycle amplitude/phase, ENSO teleconnection strength, etc.:
**ensemble-consistency (pass/fail) test** — is the observed value consistent with the
model ensemble distribution, where the distribution's spread combines ensemble spread,
**internal variability estimated from piControl** (chunked into observation-length
segments), and **observational uncertainty** added in quadrature; two-sided test at
**p < 0.05**. Spatial fields are first projected onto a **small number of EOFs**
(of, e.g., the piControl or CMIP6 variability) and each PC tested.

```python
# generic ensemble-consistency test for a scalar diagnostic D
D_members = [diag(m) for m in ensemble]                      # model ensemble values
sigma_int = std([diag(seg) for seg in chunk(piControl, len_obs)])
sigma_obs = obs_uncertainty
mu, sig = mean(D_members), sqrt(var(D_members) + sigma_int**2 + sigma_obs**2)
z = (D_obs - mu) / sig
passes = abs(z) < 1.96                                       # two-sided p < 0.05
# spatial fields: project model+obs onto leading EOFs, test each PC (Bonferroni/Hotelling)
```

**Tooling direction.** Most Tier II preprocessing and per-variable diagnostics will be
provided by a wrapper around **ClimateEval** (ESMValCore-based recipe suites;
`docs/iconeval_integration_plan.md` maps ICONEval recipes to CB2 issues #82–#91,
#100). The **scoring layer** (CRPS with ESS correction; ensemble-consistency test with
piControl variance + obs error + EOF projection) is **not** in ClimateEval/ESMValTool
and must remain bespoke (plan explicitly notes "ICONEval is deterministic only",
issue #97). `esmvaltool/recipe_pr_rmse.yml` is the current (hand-rolled) prototype of
the recipe route: pr zonal-mean time series + weighted-RMSE portrait plot vs GPCP-SG,
2005–2024, four models, hand-listed ensemble members — to be replaced by templated
generation per the integration plan.

## Tier II status summary

| Diagnostic / component | Regime | Status | Code / provider |
|---|---|---|---|
| Generic deterministic metrics (RMSE/MAE, zonal/spatial/temporal) | — | ✅ (machinery) | `MetricCalculation` in `benchmark_utils.py`; ClimateEval will supersede |
| CRPS of ensemble time series | (a) | 🟡 — CRPS exists (`zonal_mean_crps`, `spatial_crps`, xskillscore), **no ESS/autocorrelation correction** | `benchmark_utils.py`; bespoke |
| Ensemble-consistency test (piControl σ + obs error, p<0.05, EOF projection) | (b) | ❌ missing entirely | bespoke (core new build) |
| tas monthly/annual anomalies vs GISS/Berkeley/HadCRUT | (a) | 🟡 — machinery + obs paths exist (`HadCRUT5`, `NASA_GISS`, …); no HadCRUT5_error propagation into scoring | `model_benchmark.py`; ClimateEval |
| tas **daily extremes** (e.g. TXx/TNn or tail quantiles) | (a)/(b) | ❌ — no daily data path (`VARIABLE_FREQUENCY_GROUP` is monthly-only); `tasmax/tasmin` listed in `OBSERVATION_DATA_SOURCES` (HadGHCND) but unused | bespoke/ClimateEval |
| ts (skin temperature) | (a) | ❌ — only `tos` (SST) supported | ClimateEval |
| pr anomalies vs GPCP | (a) | 🟡 — via `model_benchmark.py` + `recipe_pr_rmse.yml` (deterministic RMSE only) | ClimateEval |
| pr **intensity PDF** | (b) | ❌ — needs daily pr, histogram/quantile comparison | bespoke |
| TOA fluxes rsut/rlut/rsutcs/rlutcs vs CERES-EBAF | (a) | 🟡 — deterministic metrics run; single shared CERES NetCDF, manual download | `model_benchmark.py`; ClimateEval |
| Sea ice (extent/area, Sep minimum, trends) | (b) | ❌ — `siconc` has empty source list in `constants.py`; plan maps to ICONEval `recipe_sea_ice_*` | ClimateEval |
| OHC (0–100 m "mixed", 0–2000 m "deep") vs Argo | (a) | ✅ derivation implemented (TEOS-10/gsw); scored with generic metrics | `model_benchmark.py` (`ohc` branch) |
| Surface fluxes (hfss/hfls/rsds/…) vs obs | (a)/(b) | ❌ as Tier II scoring (variables load fine; no obs sources wired) | ClimateEval |
| Cloud properties (clt, od550aer, ctp/ctt/clwvi) | (a)/(b) | 🟡 — clt/od550aer download via GEE + generic metrics; others listed in constants only | ClimateEval (`recipe_clouds_*`) |
| prw (column water vapour) | (a) | ❌ obs source ("—" in table; `tcwv`: ERA5/RSS listed but no download/scoring path) | ClimateEval |
| Global warming rate: GMST trend 2015–present & 1950–present vs GISS/Berkeley/HadCRUT | (b) | ❌ | bespoke/ClimateEval (plan #85) |
| Pinatubo response (rsds + tas anomalies 1991–93 co-variation) | (b) | ❌ — plan notes "new diagnostic script needed" (#89) | bespoke |
| Hemispheric asymmetry: NH−SH warming trend 1950–1985 + tropical precip shift | (b) | ❌ | bespoke |
| Seasonal cycle: land annual T range; land carbon uptake seasonal amplitude; SST–low-cloud seasonal covariance | (b) | ❌ (carbon uptake needs `nbp`/`fgco2`, not in variable map) | ClimateEval + bespoke |
| Diurnal cycle: amplitude/phase of T and pr | (b) | ❌ — needs 3-hourly/sub-daily data | bespoke |
| Baselines: 1990–2020 climatology; 2-layer EBM × CMIP6 MMM pattern scaling; CMIP6 MME | — | ❌ none implemented | bespoke |

## II.0 Generic machinery already implemented (`benchmark_scrips/benchmark_utils.py`, `model_benchmark.py`)

**`DataFinder`** — locates model data (local `~/climate_data/CMIP6/...` → Pangeo GCS
zarr via `pangeo-cmip6.csv` catalogue → ESGF OPeNDAP), historical+SSP245 concatenation
(historical 2005–2014 + ssp245 2015–2024 by default; `SSP_EXPERIMENT="ssp245"` in
`constants.py`), ensemble discovery (`r*i1p1f1` only), grid preference `gr`→`gn` for
Omon, cell-area loading with cos(lat) fallback, observation zarr loading from
`gs://climatebench/observations/` or `../observations/`. `load_experiment_ds()` serves
Tier I (piControl/abrupt-4xCO2/DAMIP hist-aer).

**`MetricCalculation`** — obs regridded to model grid (xESMF bilinear, periodic) by
`model_benchmark.py` before construction; optional lat band via weight masking
(`lat_min/lat_max`); two preprocessing options from `utils.py`:
- `bias_adjusted`: `model − (model.mean(time) − obs.mean(time))` (mean-shift only);
- `anomaly`: subtract each dataset's own monthly climatology.

Metrics (all xskillscore, `skipna=True`):
- `zonal_mean_rmse` / `zonal_mean_mae`: area-weighted spatial mean first (despite the
  name, this is a full regional/global mean over all non-time dims, not a per-latitude
  zonal mean), then RMSE/MAE over time → scalar.
- `spatial_rmse` / `spatial_mae`: weighted RMSE/MAE over space per timestep → time
  series (saved as zarr).
- `temporal_rmse`: RMSE over time per gridpoint → map.
- `zonal_mean_crps` / `spatial_crps`: `xs.crps_ensemble` with `member_dim="ensemble"`
  (ensemble mean **not** taken when metric contains "crps" — `model_benchmark.py`
  sets `ensemble_mean=False`). ⚠ The ensemble-dim guard is broken:
  `ValueError("no ensemble dimension")` is **constructed but never raised** (missing
  `raise`) in both CRPS methods.

**Mapping to the Tier II spec.** This machinery covers regime (a) *deterministically*
and provides raw CRPS, but: no time-averaging with **effective-sample-size correction**;
no use of observational error fields (HadCRUT5_error is downloadable but unused in
scoring); no regime-(b) ensemble-consistency test; no piControl-variance estimation; no
EOF projection; no baselines. `SaveResults` writes per-variable CSV/zarr to
`results/<variable>/` or GCS — a schema that will need extending for probabilistic
scores (score + p-value + pass flag + provenance).

**Target pseudocode for regime (a) as specced:**
```python
fc  = model_anom(ensemble=..., time=...)       # 2015..present, monthly anomalies
obs = obs_anom(time=...)
crps_t = xs.crps_ensemble(fc, obs, member_dim="ensemble", dim=[])   # per timestep
r1 = lag1_autocorr(crps_t - crps_t.mean())
T_eff = len(crps_t) * (1 - r1) / (1 + r1)
score = crps_t.mean();  score_se = crps_t.std() / np.sqrt(T_eff)
```

**`ohc` derivation (`model_benchmark.py`, variable == "ohc"):** loads `thetao` + `so`;
gsw/TEOS-10 chain: pressure from depth, SA from SP, CT from θ, in-situ T; θ anomaly vs
a 2004–2018 model climatology; density ρ(SA, CT, p) and cp(SA, t, p);
`OHC = V·ρ·cp·t_anom` with `V = areacello·Δlev`; vertical sums over 0–100 m ("mixed")
and 0–2000 m ("deep"); cached to zarr; scored vs Argo with the generic metrics.
⚠ Minor: heat content uses the in-situ *anomaly temperature* passed back through the
gsw conversions — reasonable but nonstandard; document or switch to ρ·cp·(CT−CT_clim).

## II.1 Per-diagnostic specs (regime and formulas)

Each item below inherits the regime-(a) or regime-(b) scoring machinery of §II.0.
Provider column in the status table; only spec + pseudocode given here.

**GMST warming rate.** OLS trend of global-mean tas anomaly for 2015–present *and*
1950–present, vs GISS/Berkeley/HadCRUT5 (obs spread = observational uncertainty).
Regime (b): consistency of observed trend with ensemble trend distribution
(+ piControl trend variability for the same window length).
```python
tr_m = [ols_trend(gmst(m, y0, y1)) for m in members]
tr_pi = [ols_trend(seg) for seg in chunk(gmst(piControl), y1 - y0 + 1)]
z = (tr_obs - mean(tr_m)) / sqrt(var(tr_m) + var(tr_pi) + sigma_obs**2); pass = |z| < 1.96
```

**Pinatubo response.** 1991–93 anomalies (vs 1990–2020 climatology, ENSO-regressed-out
optional) of global `rsds` and `tas`; test joint co-variation (e.g. regression of tas
lag response on rsds dimming, or 2-D consistency of [Δrsds, Δtas]). Regime (b).
Historical simulations include Pinatubo forcing, so 2015+ window does not apply here;
use historical members.

**Hemispheric asymmetry.** NH−SH tas trend difference over 1950–1985 (aerosol era) and
the associated tropical precipitation (ITCZ) southward shift; regime (b) against
HadCRUT/GPCP-era reconstructions.

**Seasonal-cycle metrics.** (i) climatological annual range of tas over land
(max−min of 12-month climatology, land-masked, area-mean or EOF-projected map);
(ii) seasonal amplitude of land carbon uptake (`nbp`; peak-to-trough of climatological
cycle vs atmospheric-inversion products); (iii) SST–low-cloud seasonal covariance
(regression of low-cloud fraction on SST over the seasonal cycle in stratocumulus
regions). All regime (b).

**Diurnal cycle.** Amplitude and phase (first harmonic fit) of 3-hourly tas and pr
climatologies vs observational products; regime (b) on amplitude and phase separately.
```python
harm = fit_first_harmonic(clim_3hourly)   # A*cos(2*pi*t/24 - phi)
test_consistency(A_obs, A_members); test_consistency(phi_obs, phi_members)  # circular
```

**Daily tas extremes / pr intensity PDF.** Annual TXx/TNn-type block maxima or tail
quantiles (tas), and daily-pr histogram/quantile comparison (e.g. CRPS on annual
quantile series, or consistency test on PDF summary statistics like wet-day frequency,
99th percentile). Requires `day`-table data throughout the stack.

**Baselines.** (i) climatology persistence: forecast = 1990–2020 monthly climatology;
(ii) pattern scaling: ΔT_global(t) from a 2-layer EBM driven by SSP2-4.5 forcing ×
CMIP6 MMM normalized warming pattern (+ climatology); (iii) CMIP6 MME as an "ensemble
submission". All three run through the identical scoring pipeline so every submitted
model's scores are reported relative to them.

---

# Tier III — Paleoclimate time-slices and perfect-model tests

## Tier III status summary

| Diagnostic | Spec (short) | Status | Code |
|---|---|---|---|
| lig127k vs proxies | PMIP4 BCs; Hoffman 2017 / Osman 2026 LIG SST | 🟡 prototype (tas-only, CSV obs, MAE) | `paleo_scrips/paleo_benchmarks.ipynb`; `paleo_data` PR builds on this |
| lgm vs proxies | Tierney 2020 / Osman 2021 LGM SST + δ18O; Bartlein 2011 / Cleator 2020 land T | 🟡 prototype (tas-only) | notebook + PR |
| midHolocene vs proxies | Temp12K; Bartlein/Cleator; SISALv3 δ18O optional | 🟡 prototype (tas-only) | notebook + PR |
| midHolocene North-Africa monsoon check | JJAS pr anomaly ≥ +0.5 mm/day, 10–30N, 20W–30E, vs piControl | ❌ missing | — |
| Proxy-aware ensemble-consistency scoring | Tier II regime-(b) test adapted to large proxy errors | ❌ (notebook uses plain MAE/NMAE) | — |
| Perfect-model: CESM2 (req.; MPI-ESM, GISS ModelE2 ext.) train→SSP2-4.5 daily tas/pr, Tier II scoring | | ❌ missing | — |
| Large-ensemble spread test vs CESM-LE (variance ratio + spatial corr of inter-member variability) | | ❌ missing | — |

## III.1 Paleo time-slices (lig127k, lgm, midHolocene)

**Measures.** Out-of-sample generalization: can the model reproduce climates far from
the instrumental record, given PMIP4 boundary conditions (orbit, GHG, ice sheets)?

**Spec.**
- Experiments: PMIP4 `lig127k`, `lgm`, `midHolocene`; anomalies vs the model's own
  piControl.
- Proxy targets: LGM — Tierney et al. 2020 / Osman et al. 2021 (SST + δ18O,
  data-assimilation fields); LIG — Hoffman et al. 2017 / Osman 2026 (SST);
  land temperature — Bartlein et al. 2011 / Cleator et al. 2020 (pollen);
  mid-Holocene — Temp12K; optional speleothem δ18O — SISALv3 (requires water-isotope
  output or forward proxy modelling).
- Scoring: the **same ensemble-consistency test as Tier II regime (b)**, adapted to
  large proxy uncertainties (proxy error dominates σ; test at proxy sites or on
  low-order EOFs/zonal means).
- Specific hard requirement: **mid-Holocene JJAS precipitation anomaly ≥ +0.5 mm/day
  over North Africa (10–30N, 20W–30E) vs piControl** (Green Sahara / monsoon
  amplification).

```python
# per period p in {lig127k, lgm, midHolocene}:
anom = clim(exp_p) - clim(piControl)                     # per variable (tas, tos, ...)
model_at_proxy = sample_at(anom, proxy_sites)            # or forward-model d18O
z = (proxy_val - ens_mean(model_at_proxy)) / sqrt(var_ens + sigma_proxy**2)
score_p = fraction(abs(z) < 1.96)                        # site-wise consistency
# mid-Holocene monsoon check:
dP = (clim_JJAS(midHolocene.pr) - clim_JJAS(piControl.pr)) * 86400
passes = area_mean(dP.sel(lat=slice(10,30), lon=slice(-20 % 360 ... 30))) >= 0.5
# note: 20W-30E crosses lon=0; handle 0-360 wraparound explicitly
```

**Status: 🟡 prototype** — `paleo_scrips/paleo_benchmarks.ipynb` (the open
`paleo_data` PR branch will build on this):
- Loads cached per-model NetCDFs (`{model}/{period}_tas_annual.nc`, `_monthly.nc`)
  produced by `paleo_scrips/paleo_data_cache/paleo_data_cache.py`, for lgm, lig127k,
  midHolocene **plus** midPliocene-eoi400 and DeepMIP Eocene (extras beyond the paper's
  three periods).
- Computes **tas-only** anomalies vs piControl (pulled live from Pangeo GCS),
  global/NH/tropics/SH monthly zonal means and global annual means.
- Scores with **MAE** against processed observation CSVs
  (`paleo_observations/processed/{annual_mean_global_obs,monthly_mean_zonal_obs}.csv`,
  which carry a `tas_anom` and `error` column — errors are merged but **not used** in
  the metric), plus **NMAE** normalized by the per-period median model MAE; replicates
  IPCC AR6 Fig. 7.19. Writes `results/paleo/{annual,monthly}_zonal_means.csv`.
- Missing vs spec: SST/δ18O proxy fields, pollen land-T compilations as gridded/site
  targets, ensemble-consistency scoring using the provided `error` column, the
  mid-Holocene North-Africa JJAS precip check (no `pr` handling at all), SISALv3.
- ⚠ Code smells for the PR to fix: piControl weighting reuses the *paleo* dataset's
  `weight` field on the piControl grid (`.weighted(ds_slice['weight'])` on `piC_zmean`)
  — only valid if grids match; hard-coded `file.split('/')[8]`/`[17]` path indexing.

## III.2 Perfect-model experiments

**Measures.** Emulator/ML-submission validity where truth is fully known: train on one
ESM's historical output, predict its SSP2-4.5 future, score with Tier II machinery —
isolates model skill from observational uncertainty.

**Spec.**
- Truth models: **CESM2 (required)**; MPI-ESM and GISS ModelE2 (extended tier).
- Task: train on historical; predict **daily tas and pr** under SSP2-4.5;
  score predictions with the **Tier II metrics** (CRPS time series +
  ensemble-consistency scalars) against the held-out truth run.
- **Large-ensemble spread test** vs CESM-LE: compare predicted inter-member spread to
  CESM-LE's — (i) **variance ratio** (predicted/true inter-member variance, per grid
  point or aggregated) and (ii) **spatial correlation** of the inter-member variability
  pattern.

```python
truth = cesm_le.ssp245.daily[["tas","pr"]]
pred  = submission.predict(hist_train)                    # ensemble of trajectories
tier2_scores = run_tier2(pred, obs=truth)                 # CRPS + consistency, no obs error
var_ratio = pred.var("member") / truth.var("member")      # target ~1 (e.g. within [0.5, 2])
r_spatial = pattern_corr(pred.var("member"), truth.var("member"), weights=coslat)
```

**Status: ❌ missing.** No code anywhere in the repo (also flagged in the integration
plan, issues #92–96: "No paleoclimate or perfect-model capability in ICONEval" — this
is bespoke work).

---

# Overall coverage summary

| Tier | Specced diagnostics | ✅ | 🟡 | ❌ |
|---|---|---|---|---|
| I | 17 checks across 8 groups | 1 (aerosol ERF) + 2 code-only extras | 11 (implemented with threshold/method/period deviations) | 5 (geostrophic balance, MJO, both GFMIP patch tests, amip-4xCO2 ERF) |
| II | scoring machinery + ~15 diagnostic families | deterministic metric machinery; OHC derivation | raw CRPS (no ESS correction); tas/pr/TOA/clouds deterministic paths; recipe prototype | ensemble-consistency test, EOF projection, all three baselines, daily extremes, pr PDF, ts, sea ice, prw, GMST trends, Pinatubo, hemispheric asymmetry, seasonal/diurnal cycle metrics |
| III | 3 paleo periods + monsoon check + perfect-model + LE spread | — | tas-only paleo prototype (notebook; `paleo_data` PR in flight) | proxy-aware scoring, mid-Holocene precip check, perfect-model suite, LE spread test |

**Cross-cutting discrepancies found (paper vs code) — complete list:**
1. Energy balance: drift threshold 0.1 vs 0.02 W/m²/decade; linear trend of annual
   series vs drift of 10-yr running mean; no |μ|<0.1 W/m² pass flag; ≥100 vs ≥500 yr
   (paper itself inconsistent: ≥500 vs ≥100).
2. Water budget: relative 1% test vs absolute 0.05 mm/day.
3. Atmospheric energy budget: replaced by a surface-budget ratio test (±10% of 1) vs
   |LP−(Q_rad+SHF)| < 2 W/m².
4. Clear-sky LW feedback: global-mean regression on piControl, window 2.0±0.5, vs
   gridpoint regression on historical, ±25% of 2.2.
5. Precip–buoyancy: climatological log(pr)-vs-prw spatial fit (30S–30N, fixed
   thresholds) vs monthly P′-vs-⟨MSE⟩′ (20S–20N, ±30% of obs).
6. ENSO amplitude window [0.4,1.8] vs [0.5,1.4] K (and a third window 0.7–1.2 in the
   integration plan); spectral peak-in-band vs 2–7/1–2-yr band-power ratio >1.5;
   teleconnections sign-only with tas vs ta500 regressions within factor 2 of obs.
7. abrupt-4xCO2 equilibrium window: last 50 yr (code) vs last 10 yr (paper) for
   land–ocean and Arctic; ECS has no [1,7] K pass flag.
8. Aerosol ERF: end-of-record 30-yr mean vs "2015" value (interpretation, document it).
9. MHT peak-latitude windows widened (10–25°/30–50° vs 15–20°/~45°); no budget-residual
   correction before integration.
10. ITCZ–EFE: all timesteps vs 12-month climatology; r≥0.85 vs r>0.9; slope −1.5..−5.0
    vs ±50% of 3°/PW (−1.5..−4.5); undocumented 2-month lag; **hard-coded
    `np.ones((1980,1))` time-length bug in `compute_efe`**.
11. CRPS ensemble-dim check never raised (missing `raise` in `zonal_mean_crps`/
    `spatial_crps`, `benchmark_utils.py`).
12. CLAUDE.md/plan reference `reference_bounds.yaml`; code uses
    `constants.REFERENCE_BOUNDS` dict (yaml not yet created).
13. Bjerknes + C-C scaling implemented but absent from the paper's Tier I list —
    reconcile (add to paper or mark optional).
14. Paleo notebook: proxy `error` column loaded but unused; piControl weighted with the
    paleo grid's weights; hard-coded path indices.
15. `constants.py` monthly-only variable map blocks all daily-data diagnostics
    (geostrophic balance, MJO, daily extremes, pr PDF, diurnal cycle).

# Prioritized gap list (what to build next)

Ordered by (protocol criticality × not-covered-elsewhere). Items marked *ClimateEval*
are expected to arrive via the ClimateEval wrapper; items marked *paleo PR* via the
open `paleo_data` branch — do not duplicate those.

1. **Tier II ensemble-consistency scoring engine (bespoke, blocking).** The regime-(b)
   test (piControl internal-variability estimation by chunking, obs-uncertainty
   quadrature, two-sided p<0.05, EOF projection for fields) plus the ESS/autocorrelation
   correction for regime-(a) CRPS. Nothing in the repo or in ClimateEval provides this;
   every aggregated Tier II/III score depends on it. Fix the un-raised `raise` in the
   CRPS methods while touching this code.
2. **Tier II baselines (bespoke, blocking for headline results).** 1990–2020
   climatology persistence, 2-layer EBM × CMIP6-MMM pattern scaling, CMIP6 MME —
   without these no submission score is interpretable.
3. **Align Tier I thresholds/methods with the paper** (cheap, high audit value):
   energy-balance 0.02 W/m²/decade on 10-yr running mean + |μ|<0.1 pass flag; ENSO
   [0.5,1.4] K + band-power ratio; last-10-yr a4x window (or amend paper to 50);
   ECS [1,7] K flag; absolute water/energy budget bounds; ITCZ–EFE climatology +
   thresholds **and fix the hard-coded-1980 bug**; MHT peak-latitude windows.
4. **Missing Tier I diagnostics:** geostrophic balance (needs daily ua/zg ingestion —
   extend `VARIABLE_FREQUENCY_GROUP` to day tables), MJO Wheeler–Kiladis ratio,
   amip-4xCO2 ERF, GFMIP patch Δλ (needs a submission-data pathway for non-CMIP
   experiments); upgrade covariance checks 2/5 to the paper's gridpoint-β and
   P′-vs-MSE′ forms with observational reference slopes.
5. **Daily-data Tier II diagnostics (bespoke + ClimateEval):** tas extremes, pr
   intensity PDF, diurnal cycle; plus the scalar diagnostics with no provider yet
   (GMST trends, Pinatubo, hemispheric asymmetry, seasonal-cycle triplet) — thin
   bespoke diagnostics feeding the engine from item 1. Sea ice, ts, prw, surface
   fluxes, cloud properties: route through ClimateEval recipes per
   `docs/iconeval_integration_plan.md` Phase 3.
6. **Tier III completion:** mid-Holocene North-Africa JJAS precip check (small,
   standalone — not in the paleo PR's tas-only scope as staged); proxy-aware
   consistency scoring reusing item 1 with the `error` column already present in the
   obs CSVs; then the perfect-model suite (CESM2/CESM-LE variance-ratio and
   spatial-correlation spread tests) — entirely greenfield.
