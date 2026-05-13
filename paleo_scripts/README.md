# Paleoclimate Scripts

Five scripts cover the full paleo benchmark workflow: download observations, download model data, process both, then run benchmarks.

---

## Workflow

```bash
cd paleo_scripts

# Step 1 — Download proxy/reanalysis observations
python download_paleo_observations.py

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

## Script Reference

### `download_paleo_observations.py` — Download proxy and reanalysis datasets

```bash
python download_paleo_observations.py                        # all datasets
python download_paleo_observations.py --dataset lgmda lig127k
python download_paleo_observations.py --dry-run
python download_paleo_observations.py --list                 # show all dataset keys
```

Downloads are skipped if the file already exists and its size is non-zero. 0-byte failed downloads are re-fetched.

**Dataset keys:** `ipcc_ar6`, `lgmda`, `bartlein2011`, `temp12k`, `osman2021`, `sisal_v3`, `lig127k`, `scussolini2019`, `tierney_hansen`

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

**Source keys:** `ipcc_ar6`, `tierney2020`, `lgmda`, `lgmr_sat`, `lgmr_sst`, `bartlein2011`, `temp12k`, `ottobliesner2021`, `scussolini2019`

**Output layout:**
```
paleo_data_cache/processed/observations/
  lgm/
    lgmDA_v2.1_tas.nc          vars: pi_tas, tas (anomaly), tas_std
    LGMR_SAT_tas.nc            vars: tas, tas_std
    LGMR_SST_tos.nc            vars: tos, tos_std
    Bartlein2011_tas.nc        vars: tas, tas_std, tas_sig_val
    Bartlein2011_pr.nc         vars: pr, pr_std, pr_sig_val
  midHolocene/
    Bartlein2011_tas.nc
    Bartlein2011_pr.nc
    Temp12k_tas.nc             vars: tas_anom, latband_weights
  lig127k/
    OttoBliesner2021_tas.nc    vars: tas, tas_std  (site dimension)
    Scussolini2019_pr.nc       vars: pr, pr_reliability  (site dimension)
  multi_period/
    ipcc_ar6_fig7_19.csv
    tierney2020_global_tas.csv
    lgmDA_v2.1_holocene_tas.nc vars: pi_tas, pi_tas_std  (PI reference)
```

Every NetCDF carries global attributes: `source`, `doi`, `source_url`, `variable`, `units`, `period`, `anomaly_ref`, `processing_date`.

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
python paleo_benchmark.py --model MIROC-ES2L --period lgm --use-picontrol
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
| `--use-picontrol` | False | Use model's own piControl (via DataFinder) as PI reference instead of lgmDA Holocene |
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

**Results:** `../results/paleo/{period}_paleo_benchmark_results.csv`  
Columns: `model`, `period`, `dataset`, `variable`, `n_sites`, `rmse`, `mae`, `mean_crps`, `crps_skill`

---

### `paleo_constants.py` — Model/period registry

Contains `PALEO_MODELS` and `PALEO_PERIODS` lists used by `paleo_benchmark.py`. Not run directly.

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
├── paleo_constants.py               # Model/period registry
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
