# Perfect-model test: does present-day GMST skill predict mid-century skill?

Illustrative test of the ClimateBench v2 core assumption (Task definition) — that skill
at recent climate is informative for skill at the 2050 change — using global-mean surface
temperature (GMST) only. Fuller perfect-model emulation treatment: Watson-Parris et al.
(2023, doi:10.1029/2023MS003926).

## Data
CMIP6 `tas` (Amon, `r1i1p1f1`), `historical` + `ssp245`, from the Pangeo Google-Cloud
archive (`https://storage.googleapis.com/cmip6/pangeo-cmip6.json`). 33 models with full
1975–2050 coverage. GMST = cos(lat)-weighted global annual mean; anomalies wrt 1990–2020.

- `extract_gmst.py` — pulls and caches annual GMST for all models → `gmst_cmip6.csv`.
- `perfect_model_skill.py` — computes the metrics and builds the figure.
- `skill_summary.csv` — per-model recent trend, 2050 change, leave-one-out CV prediction.

## Metrics
- Present-day (pre-2015, "seen"): GMST warming trend 1975–2014 (K decade⁻¹).
- Future (held-out target): 2050 change = mean(2041–2050) anomaly vs 1990–2020 (K).

## Result (honest)
- Across models, recent warming rate vs 2050 change: **r = 0.48, R² = 0.23**.
- Leave-one-out prediction of a held-out model's 2050 change from its recent trend alone:
  **CV R² = 0.11** (CV RMSE 0.24 K vs 0.26 K for a climatology guess).

Recent global-mean warming is a **real but only partial** predictor of the mid-century
change — consistent with the observational-constraint literature (e.g. Tokarska et al.
2020; Nijsse et al. 2020), where aerosol-forcing spread and internal variability decouple
recent GMST trend from the forced future response. The single most aggregated diagnostic
(GMST) is therefore the *weakest* possible version of the assumption; it motivates, rather
than proves, the benchmark's use of multiple diagnostics, ensembles, regional patterns,
and paleo constraints. If used in the paper, frame accordingly (see revision tracker 1.1).
