#!/usr/bin/env python3
"""
Download raw paleoclimate observational datasets.

Downloads proxy/reanalysis observations into paleo_data_cache/raw/observations/.

Paper Appendix D (2026-09) scores Tier III against RAW proxy compilations, not
data-assimilation products. Each dataset below is tagged proxy / DA / recon;
the tag becomes the `dataset_type` attribute of the processed NetCDFs so the
protocol can exclude DA products from scoring.

Datasets (kind, DOI):
  ipcc_ar6             recon  IPCC AR6 Fig 7.19 CSV — Eocene/Pliocene global mean anomalies
  lgmda                DA     lgmDA v2.1 (Tierney et al. 2020) — LGM assimilation FIELDS
                              10.1038/s41586-020-2617-x
  tierney2020_proxies  proxy  Tierney et al. 2020 — site-level LGM/late-Holocene SST proxy
                              compilation underlying lgmDA  10.1038/s41586-020-2617-x
  bartlein2011         proxy  Bartlein et al. 2011 — pollen temp/precip (LGM, mid-Holocene)
                              10.1007/s00382-010-0904-1
  cleator2020          DA     Cleator et al. 2020 — LGM 3D-VAR multi-variable benchmark
                              (pollen + PMIP3 prior)  10.17864/1947.244
  temp12k              recon  Temp12k (Kaufman et al. 2020) — Holocene temperature
                              reconstruction  10.1038/s41597-020-0530-7
  osman2021            DA     Osman et al. 2021 LGMR — LGM Reanalysis FIELDS
                              10.1038/s41586-021-03984-4
  osman2021_proxies    proxy  Osman et al. 2021 proxyDatabase.nc — the site-level marine
                              geochemistry assimilated into LGMR (262 MB)  10.25921/njxd-hg08
  harrison2015         proxy  Harrison & Prentice — mid-Holocene North-Africa moisture
                              (lake-status/biome) benchmark  10.17864/1947.176
  sisal_v3             proxy  SISAL v3 speleothem d18O (Kaushal et al. 2024; 112 MB)
                              10.5194/essd-16-1933-2024
  lig127k              proxy  Otto-Bliesner et al. 2021 — LIG proxy anomaly tables
                              10.5194/cp-17-63-2021
  hoffman2017          proxy  Hoffman et al. 2017 — LIG SST compilation  10.1126/science.aai8464
                              (manual download required — Science.org blocks automated downloads)
  osman2026            proxy  Osman et al. 2026 updated LIG SST compilation — NOT publicly
                              archived as of 2026-09; use hoffman2017 instead
  scussolini2019       proxy  Scussolini et al. 2019 — LIG boreal precipitation proxy
                              10.1126/sciadv.aax7047
                              (manual download required — Science.org blocks automated downloads)
  tierney_hansen       recon  Tierney THansenMethod.csv — Hansen-method deep-time reconstruction

Usage:
    python download_paleo_observations.py
    python download_paleo_observations.py --dataset lgmda
    python download_paleo_observations.py --dataset lig127k osman2021
    python download_paleo_observations.py --dry-run
    python download_paleo_observations.py --list
"""

import argparse
import logging
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

RAW_DIR = Path(__file__).parent / "paleo_data_cache" / "raw"

# ---------------------------------------------------------------------------
# URL registries
# ---------------------------------------------------------------------------

LGMDA_FILES = {
    "lgmDA_lgm_ATM_monthly_climo.nc": "https://github.com/jesstierney/lgmDA/raw/refs/heads/master/version2.1/lgmDA_lgm_ATM_monthly_climo.nc",
    "lgmDA_hol_ATM_monthly_climo.nc": "https://github.com/jesstierney/lgmDA/raw/refs/heads/master/version2.0/lgmDA_hol_ATM_monthly_climo.nc",
}

TEMP12K_BASE_URL = (
    "https://www.ncei.noaa.gov/pub/data/paleo/reconstructions/kaufman2020/"
)
TEMP12K_FILES = ["temp12k_alldata.nc"]

TEMP12K_V1_BASE_URL = "https://www.ncei.noaa.gov/pub/data/paleo/reconstructions/climate12k/temperature/version1.0.0/"
TEMP12K_V1_FILES = [
    "Temp12k_v1_0_0.pkl",
    "Temp12k_v1_essential_metadata_NOAA.csv",
    "Temp12k_v1_record_list_NOAA.csv",
]

OSMAN2021_BASE_URL = (
    "https://www.ncei.noaa.gov/pub/data/paleo/reconstructions/osman2021/"
)
OSMAN2021_FILES = [
    "LGMR_GMST_climo.nc",
    "LGMR_GMST_ens.nc",
    "LGMR_SAT_climo.nc",
    "LGMR_SST_climo.nc",
]

# The site-level marine geochemistry that was assimilated to make the LGMR
# fields above (uk37, Mg/Ca, TEX86, planktic d18O + BACON age models), i.e. the
# raw compilation rather than the assimilated product. ~262 MB.
OSMAN2021_PROXY_FILES = ["proxyDatabase.nc"]

# Tierney et al. (2020) site-level SST proxy compilation underlying lgmDA:
# calibrated LGM and late-Holocene SSTs per core, the paired LGM-minus-LH
# anomalies, and the 5x5 binned dSST field. Small CSV/NetCDF files.
TIERNEY2020_PROXY_BASE_URL = (
    "https://raw.githubusercontent.com/jesstierney/lgmDA/master/proxyData/"
)
TIERNEY2020_PROXY_FILES = [
    "Tierney2020_LGMProxyData.csv",
    "Tierney2020_LHProxyData.csv",
    "Tierney2020_ProxyDataPaired.csv",
    "Tierney2020_ProxyData_5x5_deltaSST.nc",
]

# Hoffman et al. (2017) LIG SST compilation — Science Data File S1.
# science.org sits behind a Cloudflare challenge, so this one is manual
# (same situation as scussolini2019).
HOFFMAN2017_URL = "https://www.science.org/doi/suppl/10.1126/science.aai8464/suppl_file/aai8464_datafiles1.xlsx"

# Cleator et al. (2020) LGM benchmark — University of Reading Research Data
# Archive. NOTE: a 3D-VAR data-assimilation product (pollen sites + PMIP3
# prior), tagged dataset_type=data_assimilation downstream.
CLEATOR2020_FILES = {
    "LGM_reconstruction.csv": "https://researchdata.reading.ac.uk/244/1/LGM_reconstruction.csv",
    "README.txt": "https://researchdata.reading.ac.uk/244/2/README.txt",
}

# Harrison & Prentice mid-Holocene North-Africa moisture benchmark (the
# lake-status / biome-derived precipitation envelope used by Harrison et al.
# 2015) — University of Reading Research Data Archive.
HARRISON2015_FILES = {
    "precipitation.csv": "https://researchdata.reading.ac.uk/176/4/precipitation.csv",
    "biomes_used_6ka.csv": "https://researchdata.reading.ac.uk/176/1/biomes_used_6ka.csv",
    "biomes_used_0ka.csv": "https://researchdata.reading.ac.uk/176/2/biomes_used_0ka.csv",
    "README_N_Africa_diag.docx": "https://researchdata.reading.ac.uk/176/5/README_N_Africa_diag.docx",
}

SISAL_V3_BASE_URL = "https://www.ncei.noaa.gov/pub/data/paleo/speleothem/SISAL-v3/"
SISAL_V3_FILES = [
    "sisalv3_database_mysql_csv.zip",
    "sisalv3_codes.zip",
]

LIG127K_ZIP_URL = (
    "https://cp.copernicus.org/articles/17/63/2021/cp-17-63-2021-supplement.zip"
)
LIG127K_TABLES = [
    "Table S2. Annual - NH Oceans, Europe, and Greenland (40-90N)_CP-2019-174.xlsx",
    "Table S3. Annual - Low latitudes (40S-40N)_CP-2019-174.xlsx",
    "Table S4. Annual - SH Oceans and Antarctica (40-90S)_CP-2019-174.xlsx",
    "Table S5. JJA - NH Oceans (40-90N) JJA_CP-2019-174.xlsx",
    "Table S6. JJA - NH terrestrial (40-90N) JJA__CP-2019-174.xlsx",
]

BARTLEIN_ZIP_URL = "https://static-content.springer.com/esm/art%3A10.1007%2Fs00382-010-0904-1/MediaObjects/382_2010_904_MOESM2_ESM.zip"

TIERNEY_HANSEN_URL = "https://raw.githubusercontent.com/jesstierney/PastClimates/master/THansenMethod.csv"

IPCC_AR6_URL = "https://dap.ceda.ac.uk/badc/ar6_wg1/data/ch_07/ch7_fig19/v20230118/Figure7_19_obs.csv"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _wget_simple(url: str, dest: Path, dry_run: bool = False) -> None:
    """Download url to dest; skip if dest already exists and is non-empty.

    Uses wget when available and falls back to curl otherwise (macOS ships
    curl but not wget), so the registry works on a bare system.
    """
    if dest.exists() and dest.stat().st_size > 0:
        logging.info(f"  [skip] {dest.name}")
        return
    if dry_run:
        logging.info(f"  [dry-run] would download {dest.name}")
        return
    logging.info(f"  Downloading {dest.name} ...")
    dest.parent.mkdir(parents=True, exist_ok=True)
    if shutil.which("wget"):
        cmd = ["wget", "-q", "-O", str(dest), url]
    elif shutil.which("curl"):
        cmd = ["curl", "-sSfL", "-o", str(dest), url]
    else:
        raise RuntimeError("neither wget nor curl is available on PATH")
    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError:
        # Leave no 0-byte stub behind: the skip test above treats it as done.
        if dest.exists() and dest.stat().st_size == 0:
            dest.unlink()
        raise


def _extract_zip_robust(zip_path: Path, dest_dir: Path) -> Path:
    """Extract a zip into dest_dir and return the top-level extracted directory.

    Uses the zipfile module to discover the actual top-level directory name
    rather than assuming it, which avoids brittle hardcoded path assumptions.
    """
    with zipfile.ZipFile(zip_path) as zf:
        top_dirs = {Path(name).parts[0] for name in zf.namelist() if "/" in name}
        zf.extractall(dest_dir)

    if len(top_dirs) == 1:
        return dest_dir / top_dirs.pop()
    # Multiple top-level dirs: return dest_dir and let the caller search
    return dest_dir


# ---------------------------------------------------------------------------
# Per-dataset download functions
# ---------------------------------------------------------------------------


def _download_ipcc_ar6(obs_dir: Path, dry_run: bool) -> None:
    """IPCC AR6 Figure 7.19 — global mean temperature anomalies."""
    _wget_simple(IPCC_AR6_URL, obs_dir / "Figure7_19_obs.csv", dry_run)


def _download_lgmda(obs_dir: Path, dry_run: bool) -> None:
    """lgmDA v2.1 (Tierney et al.) — LGM and Holocene monthly climatologies."""
    for filename, url in LGMDA_FILES.items():
        _wget_simple(url, obs_dir / filename, dry_run)


def _download_bartlein2011(obs_dir: Path, dry_run: bool) -> None:
    """Bartlein et al. 2011 — pollen-based temperature/precipitation reconstructions."""
    dest = obs_dir / "bartlein2011_pollen_climate_recon.zip"
    _wget_simple(BARTLEIN_ZIP_URL, dest, dry_run)
    if dry_run or not dest.exists():
        return
    # Leave the zip in place; process_paleo_observations.py handles extraction.
    logging.info(f"  bartlein2011 zip ready at {dest.name}")


def _download_temp12k(obs_dir: Path, dry_run: bool) -> None:
    """Temp12k (Kaufman et al. 2020) — Holocene temperature reconstruction."""
    temp12k_dir = obs_dir / "climate12k"
    if not dry_run:
        temp12k_dir.mkdir(exist_ok=True)
    for filename in TEMP12K_FILES:
        _wget_simple(TEMP12K_BASE_URL + filename, obs_dir / filename, dry_run)
    for filename in TEMP12K_V1_FILES:
        _wget_simple(TEMP12K_V1_BASE_URL + filename, temp12k_dir / filename, dry_run)


def _download_osman2021(obs_dir: Path, dry_run: bool) -> None:
    """Osman et al. 2021 LGMR — LGM Reanalysis (GMST/SAT/SST)."""
    osman_dir = obs_dir / "osman2021"
    if not dry_run:
        osman_dir.mkdir(exist_ok=True)
    for filename in OSMAN2021_FILES:
        _wget_simple(OSMAN2021_BASE_URL + filename, osman_dir / filename, dry_run)


def _download_osman2021_proxies(obs_dir: Path, dry_run: bool) -> None:
    """Osman et al. 2021 proxyDatabase.nc — the raw marine SST proxy compilation.

    DOI 10.1038/s41586-021-03984-4 (dataset DOI 10.25921/njxd-hg08). ~262 MB:
    326 sediment cores, one netCDF group each, holding the uncalibrated
    geochemistry (uk37, mgca_*, tex86, d18o_*) plus BACON age ensembles.
    """
    osman_dir = obs_dir / "osman2021"
    if not dry_run:
        osman_dir.mkdir(exist_ok=True)
    for filename in OSMAN2021_PROXY_FILES:
        _wget_simple(OSMAN2021_BASE_URL + filename, osman_dir / filename, dry_run)


def _download_tierney2020_proxies(obs_dir: Path, dry_run: bool) -> None:
    """Tierney et al. 2020 LGM SST proxy compilation (DOI 10.1038/s41586-020-2617-x).

    Site-level calibrated SSTs from the lgmDA repository's proxyData/ folder —
    the compilation the lgmDA assimilation was built from, not the DA field.
    """
    tierney_dir = obs_dir / "tierney2020_proxies"
    if not dry_run:
        tierney_dir.mkdir(exist_ok=True)
    for filename in TIERNEY2020_PROXY_FILES:
        _wget_simple(
            TIERNEY2020_PROXY_BASE_URL + filename, tierney_dir / filename, dry_run
        )


def _download_hoffman2017(obs_dir: Path, dry_run: bool) -> None:
    """Hoffman et al. 2017 LIG SST compilation (manual download required).

    DOI 10.1126/science.aai8464. Science.org serves the supplement behind a
    Cloudflare bot challenge (HTTP 403 to wget/curl) and the compilation is
    not mirrored at NOAA WDS-Paleo or PANGAEA, so it must be fetched by hand.
    """
    dest = obs_dir / "hoffman2017_lig_sst_compilation.xlsx"
    orig = obs_dir / "aai8464_datafiles1.xlsx"

    if dest.exists() and dest.stat().st_size > 0:
        logging.info("  [skip] hoffman2017_lig_sst_compilation.xlsx")
        return

    if orig.exists() and orig.stat().st_size > 0:
        if dest.exists():
            dest.unlink()
        orig.rename(dest)
        logging.info(
            "  Renamed aai8464_datafiles1.xlsx → hoffman2017_lig_sst_compilation.xlsx"
        )
        return

    logging.warning(
        "\n"
        "  ACTION REQUIRED: hoffman2017_lig_sst_compilation.xlsx must be downloaded manually.\n"
        "  Science.org blocks automated downloads (Cloudflare challenge), and the\n"
        "  compilation is not mirrored at NOAA WDS-Paleo or PANGAEA.\n"
        "\n"
        "  1. Open this URL in a browser:\n"
        f"     {HOFFMAN2017_URL}\n"
        "  2. Save the file (downloads as aai8464_datafiles1.xlsx).\n"
        "  3. Move it to:\n"
        f"     {dest}\n"
        "  Then re-run this script to rename it automatically.\n"
    )


def _download_osman2026(obs_dir: Path, dry_run: bool) -> None:
    """Osman et al. 2026 updated LIG SST compilation — not publicly archived.

    Appendix D of the ClimateBench2 paper names an updated LIG SST compilation
    building on Hoffman et al. (2017). As of 2026-09 no public archive (NOAA
    WDS-Paleo, PANGAEA, Zenodo or a journal supplement) carries it, so there is
    no URL to register. Until one appears, `hoffman2017` is the LIG SST target.
    """
    logging.warning(
        "\n"
        "  UNAVAILABLE: Osman et al. (2026) updated LIG SST compilation.\n"
        "  Searched 2026-09: NOAA WDS-Paleo, PANGAEA, Zenodo and the journal\n"
        "  supplements carry no public copy; no DOI has been issued that resolves\n"
        "  to downloadable data.\n"
        "  Fall back to --dataset hoffman2017 (Hoffman et al. 2017, the compilation\n"
        "  Osman et al. 2026 builds on). Re-check when the paper is published and\n"
        "  add the URL to this registry entry.\n"
    )


def _download_cleator2020(obs_dir: Path, dry_run: bool) -> None:
    """Cleator et al. 2020 LGM multi-variable benchmark (DOI 10.17864/1947.244).

    A 3D-VAR data-assimilation product (Bartlein 2011 pollen sites with a PMIP3
    ensemble-mean prior), so it is tagged dataset_type=data_assimilation and is
    excluded from proxy scoring — processed here for reference/diagnostics.
    """
    cleator_dir = obs_dir / "cleator2020"
    if not dry_run:
        cleator_dir.mkdir(exist_ok=True)
    for filename, url in CLEATOR2020_FILES.items():
        _wget_simple(url, cleator_dir / filename, dry_run)


def _download_harrison2015(obs_dir: Path, dry_run: bool) -> None:
    """Harrison & Prentice North-Africa mid-Holocene moisture benchmark.

    DOI 10.17864/1947.176 — the lake-status/biome-derived latitudinal envelope
    of the mid-Holocene precipitation increase over northern Africa used by
    Harrison et al. (2015) as a PMIP benchmark. Feeds the monsoon check.
    """
    harrison_dir = obs_dir / "harrison2015"
    if not dry_run:
        harrison_dir.mkdir(exist_ok=True)
    for filename, url in HARRISON2015_FILES.items():
        _wget_simple(url, harrison_dir / filename, dry_run)


def _download_sisal_v3(obs_dir: Path, dry_run: bool) -> None:
    """SISAL v3 — Speleothem Isotopes Synthesis and Analysis database."""
    sisal_dir = obs_dir / "sisal_v3"
    if not dry_run:
        sisal_dir.mkdir(exist_ok=True)
    for filename in SISAL_V3_FILES:
        _wget_simple(SISAL_V3_BASE_URL + filename, sisal_dir / filename, dry_run)


def _download_lig127k(obs_dir: Path, dry_run: bool) -> None:
    """Otto-Bliesner et al. 2021 LIG127k — Last Interglacial proxy anomaly tables."""
    lig_dir = obs_dir / "lig127k"
    if not dry_run:
        lig_dir.mkdir(exist_ok=True)

    missing_tables = [t for t in LIG127K_TABLES if not (lig_dir / t).exists()]
    if not missing_tables:
        logging.info("  [skip] lig127k tables already extracted")
        return

    zip_dest = obs_dir / "cp-17-63-2021-supplement.zip"
    _wget_simple(LIG127K_ZIP_URL, zip_dest, dry_run)
    if dry_run or not zip_dest.exists():
        return

    logging.info("  Extracting lig127k supplement zip ...")
    extract_root = _extract_zip_robust(zip_dest, obs_dir)

    # Move each expected table from wherever it landed in the extract tree
    for table in LIG127K_TABLES:
        dest = lig_dir / table
        if dest.exists():
            continue
        # Search the extracted tree for the file (handles nested dirs)
        matches = list(obs_dir.rglob(table))
        if matches:
            matches[0].rename(dest)
        else:
            logging.warning(f"  [warn] Table not found in zip: {table}")

    # Clean up extracted tree and zip
    if extract_root != obs_dir and extract_root.exists():
        shutil.rmtree(extract_root, ignore_errors=True)
    for leftover in ["cp-17-63-2021-supplement-title-page.pdf", "__MACOSX"]:
        p = obs_dir / leftover
        if p.is_dir():
            shutil.rmtree(p, ignore_errors=True)
        elif p.exists():
            p.unlink(missing_ok=True)
    zip_dest.unlink(missing_ok=True)


def _download_scussolini2019(obs_dir: Path, dry_run: bool) -> None:
    """Scussolini et al. 2019 — LIG boreal precipitation proxy (manual download required)."""
    scussolini_dest = obs_dir / "scussolini2019_lig_precip_proxy.xlsx"
    scussolini_orig = obs_dir / "aax7047_external_database_s1.xlsx"

    if scussolini_dest.exists() and scussolini_dest.stat().st_size > 0:
        logging.info("  [skip] scussolini2019_lig_precip_proxy.xlsx")
        return

    if scussolini_orig.exists() and scussolini_orig.stat().st_size > 0:
        if scussolini_dest.exists():
            scussolini_dest.unlink()
        scussolini_orig.rename(scussolini_dest)
        logging.info(
            "  Renamed aax7047_external_database_s1.xlsx → scussolini2019_lig_precip_proxy.xlsx"
        )
        return

    logging.warning(
        "\n"
        "  ACTION REQUIRED: scussolini2019_lig_precip_proxy.xlsx must be downloaded manually.\n"
        "  Science.org blocks automated downloads for this file.\n"
        "\n"
        "  1. Open this URL in a browser:\n"
        "     https://www.science.org/doi/suppl/10.1126/sciadv.aax7047/suppl_file/aax7047_external_database_s1.xlsx\n"
        "  2. Save the file (downloads as aax7047_external_database_s1.xlsx).\n"
        "  3. Move it to:\n"
        f"     {scussolini_dest}\n"
        "  Then re-run this script to rename it automatically.\n"
    )


def _download_tierney_hansen(obs_dir: Path, dry_run: bool) -> None:
    """Tierney THansenMethod.csv — Hansen-method deep-time temperature reconstruction."""
    _wget_simple(TIERNEY_HANSEN_URL, obs_dir / "THansenMethod.csv", dry_run)


# ---------------------------------------------------------------------------
# Dataset registry — maps CLI name → (description, DOI, kind, downloader)
#
# `kind` records what the dataset *is*, and carries through to the
# `dataset_type` global attribute that process_paleo_observations.py writes:
#   proxy  → proxy_compilation  — raw site-level proxy data (scoreable)
#   DA     → data_assimilation  — model-informed assimilated field. Appendix D
#            (2026-09) excludes these from Tier III scoring because their
#            spatial covariances come from the assimilating model.
#   recon  → reconstruction     — statistical reconstruction / assessed product
# ---------------------------------------------------------------------------

DATASET_REGISTRY: dict[str, tuple[str, str, str, callable]] = {
    "ipcc_ar6": (
        "IPCC AR6 Fig 7.19 global mean anomalies",
        "10.1017/9781009157896.009",
        "recon",
        _download_ipcc_ar6,
    ),
    "lgmda": (
        "lgmDA v2.1 Tierney et al. — LGM data assimilation FIELDS",
        "10.1038/s41586-020-2617-x",
        "DA",
        _download_lgmda,
    ),
    "tierney2020_proxies": (
        "Tierney et al. 2020 LGM SST proxy compilation (site-level, raw)",
        "10.1038/s41586-020-2617-x",
        "proxy",
        _download_tierney2020_proxies,
    ),
    "bartlein2011": (
        "Bartlein et al. 2011 pollen temp/precip recon",
        "10.1007/s00382-010-0904-1",
        "proxy",
        _download_bartlein2011,
    ),
    "cleator2020": (
        "Cleator et al. 2020 LGM 3D-VAR benchmark (DA product)",
        "10.17864/1947.244",
        "DA",
        _download_cleator2020,
    ),
    "temp12k": (
        "Temp12k Kaufman et al. 2020 — Holocene reconstruction",
        "10.1038/s41597-020-0530-7",
        "recon",
        _download_temp12k,
    ),
    "osman2021": (
        "Osman et al. 2021 LGMR — SAT/SST/GMST reanalysis FIELDS",
        "10.1038/s41586-021-03984-4",
        "DA",
        _download_osman2021,
    ),
    "osman2021_proxies": (
        "Osman et al. 2021 marine SST proxy compilation (site-level, raw; 262 MB)",
        "10.25921/njxd-hg08",
        "proxy",
        _download_osman2021_proxies,
    ),
    "harrison2015": (
        "Harrison & Prentice N-Africa mid-Holocene moisture benchmark",
        "10.17864/1947.176",
        "proxy",
        _download_harrison2015,
    ),
    "sisal_v3": (
        "SISAL v3 speleothem d18O database (Kaushal et al. 2024; 112 MB)",
        "10.5194/essd-16-1933-2024",
        "proxy",
        _download_sisal_v3,
    ),
    "lig127k": (
        "Otto-Bliesner et al. 2021 LIG127k proxy tables",
        "10.5194/cp-17-63-2021",
        "proxy",
        _download_lig127k,
    ),
    "hoffman2017": (
        "Hoffman et al. 2017 LIG SST compilation (MANUAL download)",
        "10.1126/science.aai8464",
        "proxy",
        _download_hoffman2017,
    ),
    "osman2026": (
        "Osman et al. 2026 updated LIG SST compilation (NOT PUBLIC as of 2026-09)",
        "n/a",
        "proxy",
        _download_osman2026,
    ),
    "scussolini2019": (
        "Scussolini et al. 2019 LIG precipitation proxy (MANUAL download)",
        "10.1126/sciadv.aax7047",
        "proxy",
        _download_scussolini2019,
    ),
    "tierney_hansen": (
        "Tierney THansenMethod deep-time reconstruction",
        "10.1038/s41586-020-2617-x",
        "recon",
        _download_tierney_hansen,
    ),
}


# ---------------------------------------------------------------------------
# CLI helpers
# ---------------------------------------------------------------------------


def list_datasets() -> None:
    print("Available datasets (--dataset <name>):")
    print(
        f"  {'key':<20}  {'kind':<6}  {'DOI':<28}  description\n"
        f"  {'-'*20}  {'-'*6}  {'-'*28}  {'-'*11}"
    )
    for key, (description, doi, kind, _) in DATASET_REGISTRY.items():
        print(f"  {key:<20}  {kind:<6}  {doi:<28}  {description}")
    print(
        "\nkind:  proxy = raw proxy compilation (scoreable under paper App. D)\n"
        "       DA    = data-assimilation product (excluded from Tier III scoring)\n"
        "       recon = statistical reconstruction / assessed product"
    )


def download_datasets(dataset_names: list[str], dry_run: bool) -> bool:
    obs_dir = RAW_DIR / "observations"
    if not dry_run:
        obs_dir.mkdir(parents=True, exist_ok=True)

    ok = True
    for name in dataset_names:
        if name not in DATASET_REGISTRY:
            logging.error(
                f"Unknown dataset '{name}'. Run --list to see available options."
            )
            ok = False
            continue
        description, doi, kind, fn = DATASET_REGISTRY[name]
        logging.info(f"\n[{name}] ({kind}) {description}  doi:{doi}")
        try:
            fn(obs_dir, dry_run)
        except Exception as exc:
            logging.error(f"  Failed to download {name}: {exc}")
            ok = False
    return ok


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )

    parser = argparse.ArgumentParser(
        description="Download raw paleoclimate observational datasets.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--dataset",
        nargs="+",
        default=["all"],
        metavar="NAME",
        help=(
            "One or more dataset names to download, or 'all' (default). "
            "Run --list to see available names."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would be downloaded without downloading",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List available datasets and exit",
    )
    args = parser.parse_args()

    if args.list:
        list_datasets()
        return

    # Resolve dataset names; "all" expands to every registered key (order-preserving dedup)
    seen: dict[str, None] = {}
    for token in args.dataset:
        if token == "all":
            for key in DATASET_REGISTRY:
                seen[key] = None
        else:
            seen[token] = None
    names = list(seen)

    success = download_datasets(names, args.dry_run)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
