"""Tests for the staged CMIP6 comparison ensemble.

`climatebench2.data.StagedCMIP6HistoricalSSP245` is what makes Tier II's
``E_ref`` exist: the median fair CRPS over the comparison models. The contract
that matters is that its data source **ids are identical to upstream's**
(`climateeval.data.CMIP6HistoricalSSP245`), because the scoring pass groups
members into one model by the ``name`` behind that id.
"""

from __future__ import annotations

import pytest

from climatebench2.data import (
    STAGED_ROOT_ENV,
    StagedCMIP6HistoricalSSP245,
    staged_root,
)
from climatebench2.data.cmip6_staged import clear_discovery_cache

pytest.importorskip("climateeval")

MODELS = {
    "CMIP6_MPI-ESM1-2-LR_historical-ssp245_r1i1p1f1": {
        "tas": ["tas_Amon_MPI-ESM1-2-LR_historical_r1i1p1f1_gn_185001-186912.nc"],
        "rsdt": ["rsdt_Amon_MPI-ESM1-2-LR_ssp245_r1i1p1f1_gn_201501-203412.nc"],
        "rsut": ["rsut_Amon_MPI-ESM1-2-LR_ssp245_r1i1p1f1_gn_201501-203412.nc"],
        "rlut": ["rlut_Amon_MPI-ESM1-2-LR_ssp245_r1i1p1f1_gn_201501-203412.nc"],
    },
    "CMIP6_MPI-ESM1-2-LR_historical-ssp245_r2i1p1f1": {
        "tas": ["tas_Amon_MPI-ESM1-2-LR_historical_r2i1p1f1_gn_185001-186912.nc"],
    },
    # A non-f1 forcing index: upstream's `ensemble: r*i1p1f1` facet would miss
    # it, which is half the reason the staged generator exists.
    "CMIP6_UKESM1-0-LL_historical-ssp245_r1i1p1f2": {
        "tas": ["tas_Amon_UKESM1-0-LL_historical_r1i1p1f2_gn_185001-194912.nc"],
    },
    # Not part of this ensemble: a single-experiment directory.
    "CMIP6_MPI-ESM1-2-LR_historical_r1i1p1f1": {"tas": ["tas.nc"]},
    "observation_HadCRUT5": {"tas": ["obs.nc"]},
}


@pytest.fixture
def staged(tmp_path, monkeypatch):  # noqa: ANN001, ANN201
    """A staged comparison root with a handful of members."""
    for source_id, variables in MODELS.items():
        for var_name, files in variables.items():
            var_dir = tmp_path / source_id / "mon" / var_name
            var_dir.mkdir(parents=True)
            for name in files:
                (var_dir / name).touch()
    monkeypatch.setenv(STAGED_ROOT_ENV, str(tmp_path))
    clear_discovery_cache()
    yield tmp_path
    clear_discovery_cache()


def _variable(var_name: str):  # noqa: ANN202
    from climateeval import Variable

    return Variable(var_name, var_name, "mon")


def test_ids_match_the_upstream_generator(staged) -> None:  # noqa: ANN001, ARG001
    sources = list(StagedCMIP6HistoricalSSP245().generate(_variable("tas")))
    assert [s.id for s in sources] == [
        "CMIP6_MPI-ESM1-2-LR_historical-ssp245_r1i1p1f1",
        "CMIP6_MPI-ESM1-2-LR_historical-ssp245_r2i1p1f1",
        "CMIP6_UKESM1-0-LL_historical-ssp245_r1i1p1f2",
    ]
    # The scoring pass groups members of one model by `name`.
    assert [s.name for s in sources] == [
        "MPI-ESM1-2-LR",
        "MPI-ESM1-2-LR",
        "UKESM1-0-LL",
    ]
    assert {s.information.exp for s in sources} == {"historical-ssp245"}
    assert {s.information.category for s in sources} == {"CMIP6"}


def test_facets_are_filled_in_from_the_cmor_filenames(staged) -> None:  # noqa: ANN001, ARG001
    source = next(iter(StagedCMIP6HistoricalSSP245().generate(_variable("tas"))))
    facets = source.esmvaltool_dataset_facets
    assert facets["project"] == "CMIP6"
    assert facets["exp"] == ["historical", "ssp245"]
    assert facets["dataset"] == "MPI-ESM1-2-LR"
    assert facets["ensemble"] == "r1i1p1f1"
    assert facets["short_name"] == "tas"
    assert facets["frequency"] == "mon"
    assert (facets["mip"], facets["grid"]) == ("Amon", "gn")


def test_a_variable_a_member_does_not_carry_is_skipped(staged) -> None:  # noqa: ANN001, ARG001
    sources = list(StagedCMIP6HistoricalSSP245().generate(_variable("tos")))
    assert sources == []


def test_a_derived_variable_needs_every_required_input(staged) -> None:  # noqa: ANN001, ARG001
    """`rtnt` is never staged: it is derived from rsdt/rsut/rlut."""
    sources = list(StagedCMIP6HistoricalSSP245().generate(_variable("rtnt")))
    assert [s.id for s in sources] == [
        "CMIP6_MPI-ESM1-2-LR_historical-ssp245_r1i1p1f1",
    ]


def test_no_staged_root_yields_nothing(monkeypatch, tmp_path) -> None:  # noqa: ANN001
    monkeypatch.setenv(STAGED_ROOT_ENV, str(tmp_path / "does-not-exist"))
    clear_discovery_cache()
    assert staged_root() is None
    assert list(StagedCMIP6HistoricalSSP245().generate(_variable("tas"))) == []


def test_the_environment_wins_over_an_explicit_root(staged, tmp_path) -> None:  # noqa: ANN001
    """A smoke run points discovery at a subset while loading from --data-root."""
    other = tmp_path / "elsewhere"
    other.mkdir()
    assert staged_root(other) == staged


def test_the_generator_enumerates_daily_directories_too(tmp_path, monkeypatch) -> None:  # noqa: ANN001
    """`frequency: day` needs no special case: the walk uses the variable's own.

    The daily suite's held-out Rx1day/Rx5day series takes its `E_ref` from
    the same comparison ensemble as every monthly entry, so the generator
    has to find `<member>/day/pr/` — a member staged only at `mon` must not
    be yielded for a `day` variable, and vice versa.
    """
    from climateeval import Variable

    layout = {
        "CMIP6_MPI-ESM1-2-LR_historical-ssp245_r1i1p1f1": {
            "day": ["pr_day_MPI-ESM1-2-LR_historical_r1i1p1f1_gn_19790101-19791231.nc"],
            "mon": ["pr_Amon_MPI-ESM1-2-LR_historical_r1i1p1f1_gn_185001-186912.nc"],
        },
        # Monthly only: present for the `mon` ensemble, absent from the daily one
        "CMIP6_UKESM1-0-LL_historical-ssp245_r1i1p1f2": {
            "mon": ["pr_Amon_UKESM1-0-LL_historical_r1i1p1f2_gn_185001-194912.nc"],
        },
    }
    for source_id, by_frequency in layout.items():
        for frequency, files in by_frequency.items():
            var_dir = tmp_path / source_id / frequency / "pr"
            var_dir.mkdir(parents=True)
            for name in files:
                (var_dir / name).touch()
    monkeypatch.setenv(STAGED_ROOT_ENV, str(tmp_path))
    clear_discovery_cache()

    daily = list(StagedCMIP6HistoricalSSP245().generate(Variable("pr", "pr", "day")))
    assert [s.id for s in daily] == [
        "CMIP6_MPI-ESM1-2-LR_historical-ssp245_r1i1p1f1",
    ]
    # ... and the facets carry the daily table, not Amon
    assert daily[0].esmvaltool_dataset_facets["frequency"] == "day"
    assert daily[0].esmvaltool_dataset_facets["mip"] == "day"

    monthly = list(StagedCMIP6HistoricalSSP245().generate(Variable("pr", "pr", "mon")))
    assert len(monthly) == 2  # noqa: PLR2004
    clear_discovery_cache()
