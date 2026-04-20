# Paleoclimate Scripts

Tools for downloading and processing paleoclimate temperature data from CMIP6 model simulations and observational proxy datasets.

## Workflow

```
python download_paleo.py --source all
python process_paleo.py  --source all
```

Raw files land in `paleo_data_cache/raw/`, processed outputs in `paleo_data_cache/processed/`.

---

## Available Data

### CMIP6 Model Simulations (`--source cmip6`)

Monthly surface air temperature (`tas`) from PMIP4/CMIP6 paleoclimate experiments, downloaded from ESGF nodes. All files are SHA-256 verified.

| Period | Description | Age |
|---|---|---|
| `lgm` | Last Glacial Maximum | ~21 ka |
| `lig127k` | Last Interglacial | ~127 ka |
| `midHolocene` | Mid-Holocene | ~6 ka |
| `midPliocene-eoi400` | Mid-Pliocene Warm Period | ~3 Ma |

| Model             | lgm   | lig127k | midHolocene | midPliocene |
|-------------------|:-----:|:-------:|:-----------:|:-----------:|
| ACCESS-ESM1-5     |       | ✓       | ✓           |             |
| AWI-ESM-1-1-LR    | ✓     | ✓       | ✓           |             |
| CESM2             |       | ✓       | ✓           | ✓           |
| CESM2-FV2         | ✓     |         |             |             |
| CESM2-WACCM-FV2   | ✓     |         |             |             |
| EC-Earth3-LR      |       | ✓       | ✓           | ✓           |
| FGOALS-f3-L       |       | ✓       | ✓           |             |
| FGOALS-g3         |       | ✓       | ✓           |             |
| GISS-E2-1-G       |       | ✓       | ✓           | ✓           |
| HadGEM3-GC31-LL   |       | ✓       | ✓           | ✓           |
| INM-CM4-8         | ✓     | ✓       | ✓           |             |
| IPSL-CM6A-LR      |       | ✓       | ✓           | ✓           |
| MIROC-ES2L        | ✓     |         |             |             |
| MPI-ESM1-2-LR     | ✓     |         | ✓           |             |
| MRI-ESM2-0        |       |         | ✓           |             |
| NESM3             |       | ✓       | ✓           |             |
| NorESM1-F         |       | ✓       | ✓           | ✓           |
| NorESM2-LM        |       | ✓       | ✓           |             |

Raw files: `paleo_data_cache/raw/{MODEL}/tas_Amon_*.nc`
Processed files: `paleo_data_cache/processed/{MODEL}/{period}_tas_annual.nc` and `{period}_tas_monthly.nc`

---

### Observational Datasets (`--source observations`)

| Dataset | Period | Variable | Source |
|---|---|---|---|
| IPCC AR6 Fig 7.19 CSV | Eocene, Pliocene, LGM, LIG, midHolocene | Global mean GMST anomaly | [CEDA](https://dap.ceda.ac.uk/badc/ar6_wg1/data/ch_07/ch7_fig19/v20230118/) |
| Capron et al. 2021 | Last Interglacial (lig127k) | SST/SAT proxy anomalies by lat band | [Copernicus/CP](https://cp.copernicus.org/articles/17/63/2021/) |
| lgmDA v2.1 (Tierney et al.) | Last Glacial Maximum | Monthly absolute SAT (data assimilation) | [GitHub](https://github.com/jesstierney/lgmDA) |
| Temp12k (Kaufman et al. 2020) | Mid-Holocene (4–8 ka) | SAT reconstruction by lat band, 500 ensemble members | [NCEI](https://www.ncei.noaa.gov/access/paleo-search/study/29712) |

Raw files: `paleo_data_cache/raw/observations/`
Processed outputs: `paleo_data_cache/processed/observations/`

| Output file | Contents |
|---|---|
| `annual_mean_global_obs.csv` | Global mean GMST anomaly ± error for all five periods |
| `annual_mean_zonal_obs.csv` | Area-weighted zonal mean anomalies for LGM, LIG, midHolocene across four regions |
| `monthly_mean_zonal_obs.csv` | Monthly zonal mean anomalies for LGM (only dataset with monthly resolution) |
| `LGM_da.nc` | Combined lgmDA LGM + late-Holocene absolute temperatures and std, gridded |

Regions used for zonal means: `global`, `northern_hemisphere` (0–90°N), `tropics` (30°S–30°N), `southern_hemisphere` (90°S–0°).

---

## Scripts

### `download_paleo.py` — Download raw data

```bash
# Download everything
python download_paleo.py --source all

# CMIP6 only — all models and periods
python download_paleo.py --source cmip6 --model all --period all

# CMIP6 — specific model and period
python download_paleo.py --source cmip6 --model CESM2 --period lgm

# Observations only
python download_paleo.py --source observations

# See all available model/period combinations
python download_paleo.py --list

# Dry run (report what would be downloaded)
python download_paleo.py --dry-run --source cmip6 --model CESM2 --period lgm
```

Downloads are skipped if the file already exists and its SHA-256 checksum matches. Partial downloads (`.part` files) are cleaned up on failure.

### `process_paleo.py` — Process raw data into unified outputs

```bash
# Process everything
python process_paleo.py --source all

# CMIP6 only — all periods
python process_paleo.py --source cmip6 --period all

# CMIP6 only — specific period, keep raw files
python process_paleo.py --source cmip6 --period lgm --skip-cleanup

# Observations only
python process_paleo.py --source observations
```

By default, raw `tas_Amon_*.nc` files are deleted after CMIP6 processing. Use `--skip-cleanup` to keep them.

### `paleo_constants.py` — Download registry

Contains `PALEO_DOWNLOADS`: a nested dict `{model: {period: [(filename, url, sha256), ...]}}` with all 1001 CMIP6 ESGF download entries. Used by `download_paleo.py`. Not intended to be run directly.

---

## Directory Layout

```
paleo_scripts/
├── download_paleo.py       # Download raw data
├── process_paleo.py        # Process raw → unified outputs
├── paleo_constants.py      # CMIP6 ESGF file registry
├── README.md
└── paleo_data_cache/
    ├── raw/
    │   ├── {MODEL}/        # Raw tas_Amon_*.nc per model
    │   └── observations/   # Downloaded proxy/reanalysis files
    │       └── lig127k/    # LIG127k Excel tables
    └── processed/
        ├── {MODEL}/        # {period}_tas_annual.nc, {period}_tas_monthly.nc
        └── observations/   # annual_mean_global_obs.csv, LGM_da.nc, etc.
```
