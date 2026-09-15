# Paleoclimate Scripts

Four Python scripts (plus the ESGF wget scripts in `download_model_data/`) cover the full paleo benchmark workflow: download observations, download model data, process both, then run benchmarks.

---

## Workflow

```bash
cd paleo_scripts

# Step 1 — Download proxy/reanalysis observations
python download_paleo_observations.py
# `all` includes two large files: osman2021_proxies (262 MB) and sisal_v3 (112 MB).
# hoffman2017 and scussolini2019 need a browser (science.org blocks scripts).

# Step 2 — Download CMIP6 model data (ESGF-generated wget scripts)
# Note: best to download and process model data one period/var at a time as the raw data is large.
cd download_model_data
bash lgm_tas.sh
bash lgm_pr.sh

cd ..

# Step 3 — Process observations into period-sorted folders
python process_paleo_observations.py

# Step 4 — Compute monthly climatologies from raw model files
python process_paleo_models.py --model all --period all

# Step 5 — Run benchmarks
python paleo_benchmark.py --model all --period all
```

Raw files land in `paleo_data_cache/raw/`, processed outputs in `paleo_data_cache/processed/`.

---

## How the protocol uses this pipeline

`paleo_scripts/` is **data preparation, not protocol**. Tier III of ClimateBench v2 —
`climatebench2/diags/tier3_paleo.py::PaleoProxyScore`, wired up in
`climatebench2/suites/ClimateBench2_TierIII.yml` — reads the processed NetCDFs of step 3
directly:

```bash
climatebench2 score /path/to/model/Amon --name MyModel \
    --experiment picontrol=DIR --experiment lgm=DIR \
    --suite ClimateBench2_TierIII \
    --paleo-data-root paleo_scripts/paleo_data_cache/processed/observations
```

One suite stanza per **(period, dataset, variable)**; each reads
`<paleo_data_root>/<period>/<dataset>.nc`, samples the model's block pseudo-ensemble at
the dataset's sites (or, for a gridded compilation, at its cell centres) and scores it
with fair CRPS, with `<var>_std` as the observational uncertainty. Three parts of the
file contract matter to it, so **do not change them without updating
`tier3_paleo.py`**:

- the variable name (`tas` / `tos` / `pr` / …) and its `<var>_std` companion — with no
  `_std` there is no observational variance term and the stanza is not scored;
- `lat` / `lon`, on the same dimensions as the values (site, gridded or curvilinear);
- the `units` and `dataset_type` global attributes. `units` drives the conversion from
  the model's CMIP6 units (an unrecognised spelling is refused, not guessed:
  precipitation in mm/yr differs from kg m⁻² s⁻¹ by 3 × 10⁷). `dataset_type` decides
  whether the result counts: only `proxy_compilation` is scored
  (`tier3.scored_dataset_types`), while `data_assimilation` products are computed and
  reported but excluded from the protocol score, per paper Appendix D.

`Harrison2015_pr.nc` is not a scored stanza: it supplies the observed North-Africa
magnitude reported beside the mid-Holocene monsoon gate.

---

## Script Reference

### `download_paleo_observations.py` — Download proxy and reanalysis datasets

```bash
python download_paleo_observations.py                        # all datasets
python download_paleo_observations.py --dataset lgmda lig127k
python download_paleo_observations.py --dry-run
python download_paleo_observations.py --list                 # show all dataset keys
```

Downloads are skipped if the file already exists and its size is non-zero. 0-byte failed downloads are re-fetched. `wget` is used when present, `curl` otherwise.

**Dataset keys** (`--list` prints this table with the DOIs):

| Key | Kind | DOI | Dataset |
|---|---|---|---|
| `ipcc_ar6` | recon | 10.1017/9781009157896.009 | IPCC AR6 Fig 7.19 global mean anomalies |
| `lgmda` | **DA** | 10.1038/s41586-020-2617-x | lgmDA v2.1 LGM assimilation *fields* (Tierney et al. 2020) |
| `tierney2020_proxies` | proxy | 10.1038/s41586-020-2617-x | Tierney et al. 2020 site-level LGM/late-Holocene SST compilation (the raw data behind lgmDA) |
| `bartlein2011` | proxy | 10.1007/s00382-010-0904-1 | Pollen-based temp/precip, LGM + mid-Holocene |
| `cleator2020` | **DA** | 10.17864/1947.244 | Cleator et al. 2020 LGM 3D-VAR multi-variable benchmark |
| `temp12k` | recon | 10.1038/s41597-020-0530-7 | Temp12k Holocene reconstruction (Kaufman et al. 2020) |
| `osman2021` | **DA** | 10.1038/s41586-021-03984-4 | LGMR reanalysis *fields* (SAT/SST/GMST/d18Op) |
| `osman2021_proxies` | proxy | 10.25921/njxd-hg08 | `proxyDatabase.nc` — the site-level marine geochemistry assimilated into LGMR (262 MB) |
| `harrison2015` | proxy | 10.17864/1947.176 | Harrison & Prentice mid-Holocene North-Africa moisture benchmark |
| `sisal_v3` | proxy | 10.5194/essd-16-1933-2024 | SISALv3 speleothem δ18O database (Kaushal et al. 2024; 112 MB) |
| `lig127k` | proxy | 10.5194/cp-17-63-2021 | Otto-Bliesner et al. 2021 LIG proxy anomaly tables |
| `hoffman2017` | proxy | 10.1126/science.aai8464 | Hoffman et al. 2017 LIG SST compilation — **manual download** |
| `osman2026` | proxy | — | Osman et al. 2026 updated LIG SST compilation — **not publicly archived** (2026-09) |
| `scussolini2019` | proxy | 10.1126/sciadv.aax7047 | Scussolini et al. 2019 LIG precipitation proxy — **manual download** |
| `tierney_hansen` | recon | 10.1038/s41586-020-2617-x | Hansen-method deep-time reconstruction |

`kind` becomes the `dataset_type` global attribute of the processed NetCDFs:

- **proxy** → `proxy_compilation` — raw site-level proxy data. Paper Appendix D (2026-09) scores Tier III against these.
- **DA** → `data_assimilation` — assimilated field whose spatial covariances come from the assimilating model. **Excluded from Tier III scoring**; kept for reference and for the AR6-style figures.
- **recon** → `reconstruction` — statistical reconstruction or assessed product.

Two datasets need a browser (science.org serves their supplements behind a Cloudflare
challenge): `hoffman2017` and `scussolini2019`. Each prints the URL and the destination
path; drop the file there and re-run. `osman2026` has no public archive as of 2026-09 —
`hoffman2017` is the LIG SST target until it appears.

Raw files: `paleo_data_cache/raw/observations/`

---

### `download_model_data/` — ESGF wget scripts

Model downloads use ESGF-generated wget scripts that embed per-file SHA-256 checksums and resume logic. Each script routes files into `paleo_data_cache/raw/models/{MODEL}/` automatically.

**Naming convention:** `{period}_{variable}.sh`

| Script | Models |
|---|---|
| `lgm_tas.sh` | AWI-ESM-1-1-LR, CESM2-FV2, CESM2-WACCM-FV2, INM-CM4-8, MIROC-ES2L, MPI-ESM1-2-LR |
| `lgm_pr.sh` | AWI-ESM-1-1-LR, CESM2-WACCM-FV2, INM-CM4-8, MIROC-ES2L, MPI-ESM1-2-LR |
| `midholocene_tas.sh` | ACCESS-ESM1-5, AWI-ESM-1-1-LR, CESM2, EC-Earth3-LR, FGOALS-f3-L, FGOALS-g3, GISS-E2-1-G, HadGEM3-GC31-LL, INM-CM4-8, IPSL-CM6A-LR, MIROC-ES2L, MPI-ESM1-2-LR, MRI-ESM2-0, NESM3, NorESM1-F, NorESM2-LM |
| `midholocene_pr.sh` | ACCESS-ESM1-5, AWI-ESM-1-1-LR, CESM2, EC-Earth3-LR, FGOALS-f3-L, FGOALS-g3, GISS-E2-1-G, HadGEM3-GC31-LL, INM-CM4-8, IPSL-CM6A-LR, MIROC-ES2L, MPI-ESM1-2-LR, MRI-ESM2-0, NESM3, NorESM1-F, NorESM2-LM |
| `lig127k_tas.sh` | ACCESS-ESM1-5, AWI-ESM-1-1-LR, CESM2, CNRM-CM6-1, EC-Earth3-LR, FGOALS-f3-L, FGOALS-g3, GISS-E2-1-G, HadGEM3-GC31-LL, INM-CM4-8, IPSL-CM6A-LR, MIROC-ES2L, NESM3, NorESM1-F, NorESM2-LM |
| `lig127k_pr.sh` | ACCESS-ESM1-5, AWI-ESM-1-1-LR, CESM2, CNRM-CM6-1, EC-Earth3-LR, FGOALS-f3-L, FGOALS-g3, GISS-E2-1-G, HadGEM3-GC31-LL, INM-CM4-8, IPSL-CM6A-LR, MIROC-ES2L, NESM3, NorESM1-F, NorESM2-LM |

Note: CESM2-FV2 has no `pr` data for lgm on ESGF — only `tas` was downloaded.

---

### `process_paleo_observations.py` — Process raw observations

```bash
python process_paleo_observations.py                            # all sources
python process_paleo_observations.py --source lgmda bartlein2011
python process_paleo_observations.py --source all --log-level DEBUG
```

**Source keys:** `ipcc_ar6`, `tierney2020`, `lgmda`, `lgmr_sat`, `lgmr_sst`, `tierney2020_proxies`, `osman2021_proxies`, `bartlein2011`, `cleator2020`, `temp12k`, `harrison2015`, `ottobliesner2021`, `hoffman2017`, `scussolini2019`, `sisal_v3`

**Output layout** (`dataset_type` in the last column; `proxy` = scoreable raw compilation, `DA` = excluded from scoring, `recon` = statistical reconstruction):

| File | Dim | Variables | Type |
|---|---|---|---|
| `lgm/Tierney2020_tos.nc` | site (512) | `tos`, `tos_std`, `proxy_type` | proxy |
| `lgm/Tierney2020_absolute_tos.nc` | site (954) | `tos`, `tos_std`, `tos_ref`, `tos_ref_std`, `proxy_type`, `core_name` | proxy |
| `lgm/Tierney2020_5x5_tos.nc` | lat×lon (36×72) | `tos`, `tos_std` | proxy |
| `lgm/Osman2021Proxies_proxy.nc` | site (424) | `proxy`, `proxy_std`, `proxy_abs`, `proxy_ref`, `n_samples`, `proxy_type`, `proxy_family`, `units_per_site`, `site_name` | proxy |
| `lgm/Bartlein2011_tas.nc` | lat×lon (90×180) | `tas`, `tas_std`, `tas_sig_val` | proxy |
| `lgm/Bartlein2011_pr.nc` | lat×lon | `pr`, `pr_std`, `pr_sig_val` | proxy |
| `lgm/Cleator2020_tas.nc` | lat×lon (66×180) | `tas`, `tas_std`, `mtco`, `mtwa`, `gdd5` (+`_std`) | **DA** |
| `lgm/Cleator2020_pr.nc` | lat×lon | `pr`, `pr_std`, `mi`, `mi_std` | **DA** |
| `lgm/lgmDA_v2.1_tas.nc` | month×lat×lon | `pi_tas`, `tas` (anomaly), `tas_std` | **DA** |
| `lgm/LGMR_SAT_tas.nc` | lat×lon | `tas`, `tas_std` | **DA** |
| `lgm/LGMR_SST_tos.nc` | y×x (curvilinear) | `tos`, `tos_std` | **DA** |
| `midHolocene/Osman2021Proxies_proxy.nc` | site (515) | as the LGM file, 5–7 ka slice | proxy |
| `midHolocene/Bartlein2011_tas.nc` | lat×lon | `tas`, `tas_std`, `tas_sig_val` | proxy |
| `midHolocene/Bartlein2011_pr.nc` | lat×lon | `pr`, `pr_std`, `pr_sig_val` (water balance) | proxy |
| `midHolocene/Harrison2015_pr.nc` | lat (29) | `pr`, `pr_std`, `pr_min`, `pr_max` | proxy |
| `midHolocene/SISALv3_d18O.nc` | site (245) | `d18O`, `d18O_std`, `d18O_abs`, `d18O_ref`, `n_samples`, `mean_age`, `entity_id`, `site_name` | proxy |
| `midHolocene/Temp12k_tas.nc` | method×latband×age×ens | `tas_anom`, `latband_weights` | recon |
| `lig127k/OttoBliesner2021_tas.nc` | site (92) | `tas`, `tas_std` | proxy |
| `lig127k/Scussolini2019_pr.nc` | site | `pr`, `pr_reliability` | proxy |
| `lig127k/Hoffman2017_tos.nc` | site | `tos`, `tos_std` | proxy |
| `lig127k/SISALv3_d18O.nc` | site (79) | as the mid-Holocene file, 125–129 ka slice | proxy |
| `multi_period/ipcc_ar6_fig7_19.csv` | — | global mean anomalies | recon |
| `multi_period/tierney2020_global_tas.csv` | — | deep-time global mean | recon |
| `multi_period/lgmDA_v2.1_holocene_tas.nc` | month×lat×lon | `pi_tas`, `pi_tas_std` (PI reference) | **DA** |

Every NetCDF carries global attributes: `source`, `doi`, `source_url`, `variable`, `units`, `period`, `anomaly_ref`, `dataset_type`, `processing_date`.

**Anomaly references.** Compilations that publish absolute values also get their
baseline written out, so the choice is auditable and reversible:

| Dataset | `anomaly_ref` |
|---|---|
| Tierney 2020 (site, 5×5) | late Holocene (4–0 ka) SST of the same core — the paper's own pairing |
| Tierney 2020 (absolute) | none; `tos_ref` holds the same core's late-Holocene SST |
| Osman 2021 proxies | late Holocene (0–2 ka) mean **of the same record**; NaN where a record has no such samples |
| SISALv3 | late Holocene (0–2 ka) mean **of the same entity**; NaN where absent |
| Bartlein 2011, Cleator 2020 | modern (present-day climatology) |
| Otto-Bliesner 2021 | pre-industrial / modern, as reported per site |
| Scussolini 2019, Harrison 2015 | present |
| Hoffman 2017 | 1870–1889, as published |
| lgmDA | Holocene (lgmDA v2.0) |
| LGMR | modern (reanalysis-internal) |

**Time-slice windows** (calendar years BP): LGM 19 000–23 000, mid-Holocene 5000–7000
(paper App. D "5–7 ka"), LIG 125 000–129 000, late-Holocene baseline 0–2000.

**Two caveats worth knowing before scoring:**

- `Osman2021Proxies_proxy.nc` holds **uncalibrated** geochemistry (UK′37, TEX86, Mg/Ca,
  planktic δ18O) in native proxy units — the compilation ships measurements, not SSTs.
  Converting to `tos` needs the Bayesian forward models (BAYSPLINE / BAYMAG / BAYFOX /
  BAYSPAR), which this pipeline deliberately does not choose. Use
  `lgm/Tierney2020_tos.nc` for calibrated LGM SSTs.
- `SISALv3_d18O.nc` can only be scored against **isotope-enabled** model output (δ18O of
  precipitation or drip water); no calcite–precipitation fractionation is applied here.

---

### `process_paleo_models.py` — Compute monthly climatologies from raw model data

```bash
python process_paleo_models.py                                         # all models, all periods
python process_paleo_models.py --model AWI-ESM-1-1-LR --period lgm
python process_paleo_models.py --model AWI-ESM-1-1-LR --period lgm --variable pr
python process_paleo_models.py --model all --period all --overwrite
python process_paleo_models.py --model all --period lgm --delete-raw
```

For each model/period/variable with raw files, concatenates all Amon chunks and computes a 12-month climatology. Annual mean is computed on the fly by callers.

| Flag | Default | Description |
|---|---|---|
| `--model` | `all` | Model name(s) or `all` (discovers from `raw/models/` subdirs) |
| `--period` | `all` | `lgm`, `lig127k`, `midHolocene`, `midPliocene-eoi400`, or `all` |
| `--variable` | `all` | `tas`, `pr`, or `all` |
| `--overwrite` | False | Reprocess even if output already exists |
| `--delete-raw` | False | Delete raw source files after successful processing |

**Output layout:**
```
paleo_data_cache/processed/models/
  {MODEL}/
    {period}_{variable}_monthly_climo.nc    # shape: (month=12, lat, lon)
```

---

### `paleo_benchmark.py` — Spatial benchmark against proxy reconstructions

Compares PMIP4/CMIP6 model climatologies against paleoclimate proxy and data assimilation products. Scores with RMSE, MAE, and CRPS (using proxy uncertainty as the forecast spread).

```bash
python paleo_benchmark.py --model all --period all
python paleo_benchmark.py --model AWI-ESM-1-1-LR --period lgm
python paleo_benchmark.py --model MIROC-ES2L --period lgm \
    --picontrol-dir /data/MIROC-ES2L/piControl
python paleo_benchmark.py --model all --period lgm --obs-source lgmDA
python paleo_benchmark.py --model all --period lgm --obs-source Bartlein2011 --variable tas
python paleo_benchmark.py --model all --period all --save-to-cloud
```

| Flag | Default | Description |
|---|---|---|
| `--model` | `all` | Model name or `all` (discovers from `processed/models/`) |
| `--period` | `all` | `lgm`, `midHolocene`, `lig127k`, or `all` |
| `--obs-source` | all | Filter to specific observation dataset(s) |
| `--variable` | `all` | `tas`, `pr`, or `all` |
| `--picontrol-dir` | None | Directory of piControl NetCDF files (flat, or a CMOR/DRS tree) to use as the PI reference instead of the lgmDA Holocene field. Read with plain xarray, so the script stays self-contained. Replaced the retired `benchmark_utils.DataFinder` (local → Pangeo GCS → ESGF) |
| `--use-picontrol` | False | Deprecated: now requires `--picontrol-dir`, and exits with an error without it rather than silently changing meaning |
| `--save-to-cloud` | False | Save results to GCS `climatebench` bucket |
| `--overwrite` | False | Overwrite existing results CSV |

**Observation sources by period:**

| Period | Source key | Variable | Dataset |
|---|---|---|---|
| lgm | `lgmDA` | tas | Tierney et al. 2020 data assimilation (absolute + anomaly) |
| lgm | `LGMR_SAT` | tas | Osman et al. 2021 SAT reconstruction |
| lgm | `Bartlein2011` | tas, pr | Pollen-based MAT/MAP anomalies |
| midHolocene | `Bartlein2011` | tas, pr | Pollen-based MAT/MAP anomalies |
| midHolocene | `Temp12k` | tas | Kaufman et al. 2020 (stub — not yet implemented) |
| lig127k | `OttoBliesner2021` | tas | Otto-Bliesner et al. 2021 proxy anomalies |
| lig127k | `Scussolini2019` | pr | Scussolini et al. 2019 semi-quantitative precip |

Note: this legacy benchmark still reads only the sources in the table above — the raw
compilations added for paper Appendix D (`Tierney2020_*`, `Osman2021Proxies_*`,
`Cleator2020_*`, `Harrison2015_pr`, `SISALv3_d18O`, `Hoffman2017_tos`) are written for
the Tier III protocol diagnostics and are not wired into `paleo_benchmark.py`.

Its CRPS is also **not** the protocol's: it treats the proxy (μ, σ) as the forecast
distribution and the model value as the observation — the inverse of Tier III's fair
CRPS of a model pseudo-ensemble against the proxy value. Keep it for the AR6-style
figures; for the protocol score use `climatebench2 score --suite ClimateBench2_TierIII`
(see below).

**Results:** `../results/paleo/{period}_paleo_benchmark_results.csv`  
Columns: `model`, `period`, `dataset`, `variable`, `n_sites`, `rmse`, `mae`, `mean_crps`, `crps_skill`

---

## Directory Layout

```
paleo_scripts/
├── download_paleo_observations.py   # Step 1: download proxy/reanalysis data
├── download_model_data/             # Step 2: ESGF wget scripts per period/variable
│   ├── lgm_tas.sh
│   ├── lgm_pr.sh
│   └── ...
├── process_paleo_observations.py    # Step 3: process raw observations
├── process_paleo_models.py          # Step 4: compute model climatologies
├── paleo_benchmark.py               # Step 5: run spatial benchmarks
├── paleo_utils.py                   # standardize_dims / save_results_csv
│                                    #   (from the retired root utils.py)
├── README.md
└── paleo_data_cache/
    ├── raw/
    │   ├── models/
    │   │   └── {MODEL}/             # Raw tas_Amon_*.nc, pr_Amon_*.nc chunks
    │   └── observations/            # Downloaded proxy/reanalysis files
    └── processed/
        ├── models/
        │   └── {MODEL}/             # {period}_{variable}_monthly_climo.nc
        └── observations/
            ├── lgm/
            ├── midHolocene/
            ├── lig127k/
            └── multi_period/
```
