"""IMERG daily precipitation, served from a staged root.

Why this lives here and not upstream
------------------------------------
It **should** live upstream: it is a data source, and
docs/climateeval_delineation_plan.md's ownership test puts "code that
loads data" in ClimateEval. It is here for the same reason
:mod:`climatebench2.data.cmip6_staged` is — ClimateEval is a pinned
third-party dependency and CB2 does not patch it — and it is written so
that moving it to ``climateeval/data/_imerg.py`` is a file copy: it
subclasses :class:`climateeval.data.DataSource` and adds nothing CB2-
specific. Precedent and the same caveat:
:class:`climatebench2.data.cmip6_staged.StagedCMIP6HistoricalSSP245`.

What it is for
--------------
The paper's Table 2 names **IMERG** as the observational reference for the
daily precipitation intensity PDF and for the ETCCDI precipitation extremes
(Rx1day, Rx5day, R95pTOT, CDD). Before it existed, ``pr`` had no daily
observational product anywhere in the stack — ``ERA5.VARIABLE_MAPPING``
carries ``pr`` but ``ERA5Hourly``'s CDS request is hard-wired to a single
year — so the precipitation half of metrics_reference.md §II.1 was computed
and **unscored**, exactly like the temperature half still is (HadEX3 is
merged upstream but nothing is staged).

Staged-file contract
--------------------
IMERG is *not* downloadable from here: there is no ESMValTool CMORizer for
it, so the files are staged by hand and this class only finds them.
:meth:`climateeval.data.DataSource.get_cube` globs
``<data_root>/<id>/<frequency>/<var_name>/*.nc`` — with ``id`` =
``observation_IMERG`` — pre-filters that list to the files whose CMOR-style
trailing ``<start>-<end>`` token overlaps the variable's ``timerange``
(``climateeval.data._base._paths_within_timerange``; with one file per year
and a 25-year record that is the difference between loading 25 files and
loading 14), concatenates them and hands the result to
``get_prepared_cube``. So the staging layout is::

    <data_root>/observation_IMERG/day/pr/
        pr_day_IMERG-V07B_1deg_20000101-20001231.nc   (partial: from 06-01)
        pr_day_IMERG-V07B_1deg_20010101-20011231.nc
        ...
        pr_day_IMERG-V07B_1deg_20250101-20251231.nc

one file per calendar year, ``pr`` in ``kg m-2 s-1`` with
``standard_name = precipitation_flux`` on a regular 1° grid (lat −89.5…89.5,
lon −179.5…179.5), daily at 12:00 on the standard calendar.

**Units.** Nothing is converted here. The suite asks for ``units: mm day-1``
and ``climateeval._utils.get_prepared_cube`` ends with
``convert_units(cube, variable.units)``, whose ESMValCore special conversion
for ``precipitation_flux`` divides by the density of water — the *same* line
that converts every model's ``pr``. That is the point of staging the file
with the CMOR ``standard_name``: the reference and the submission travel the
same code path, so they cannot disagree about a factor of 86400.

**Record and window.** The record starts 2000-06-01, so its first *complete*
calendar year is 2001 — which is what
:func:`climatebench2.reference_windows.source_coverage` reports (it drops a
partial year at either end) and what makes the in-sample precipitation
entries of ``ClimateBench2_TierII_daily`` run over **2001–2014**: the
overlap of the reference's record with the pre-test period. 2001–2014 is
also 14 years of the 1985–2014 anomaly baseline, above the
``tier2.anomaly_baseline.min_years`` = 10 floor, which is what lets the
held-out ``pr_extremes_series`` entry be scored as anomalies at all.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from climateeval.data._base import DataSource
from climateeval.data._utils import DataSourceInformation
from climateeval.exceptions import DownloadError

if TYPE_CHECKING:
    from pathlib import Path

    from iris.cube import Cube

    from climateeval import Variable


class IMERG(DataSource):
    """GPM IMERG daily precipitation (V07B), read from a staged root.

    Data source id ``observation_IMERG``; the only variable is daily ``pr``.

    There is no download path: IMERG has no ESMValTool CMORizer, so
    :meth:`download` always raises and the files must be staged under
    ``<data_root>/observation_IMERG/day/pr/`` (see the module docstring for
    the contract). Everything else — the glob, the ``timerange``
    pre-filter, the concatenation, the region/mask/unit preprocessing — is
    :class:`climateeval.data.DataSource`'s.
    """

    _information = DataSourceInformation(
        name="IMERG",
        category="observation",
        institute="NASA-GSFC",
        references=(
            "https://doi.org/10.5067/GPM/IMERGDF/DAY/07",
            "https://gpm.nasa.gov/data/imerg",
        ),
    )

    #: Only daily precipitation. Declared (and enforced in :meth:`get_cube`)
    #: rather than left implicit so a suite that asks IMERG for ``tasmax``
    #: fails with a sentence instead of an empty directory.
    _supported_var_names: ClassVar[tuple[str, ...]] = ("pr",)

    #: IMERG is half-hourly natively; only the **daily** accumulation is
    #: staged, because that is the resolution §II.1's precipitation
    #: statistics are defined at.
    _supported_frequencies: ClassVar[tuple[str, ...]] = ("day",)

    def get_cube(
        self,
        data_root_dir: Path | str,
        variable: Variable,
        *,
        download_missing_data: bool = True,
    ) -> Cube:
        """The staged cube, after checking the variable is one IMERG has."""
        self._check_supported_variables(variable)
        return super().get_cube(
            data_root_dir,
            variable,
            download_missing_data=download_missing_data,
        )

    def download(self, variable: Variable, data_root_dir: Path | str) -> list[Path]:
        """Never: IMERG is staged by hand (no ESMValTool CMORizer exists)."""
        self._check_supported_variables(variable)
        msg = (
            f"{self.id} cannot be downloaded: there is no ESMValTool CMORizer "
            f"for IMERG. Stage one file per year under "
            f"{data_root_dir}/{self.id}/{variable.frequency}/{variable.var_name}/ "
            f"(see climatebench2.data.imerg for the file contract)"
        )
        raise DownloadError(msg)

    def _check_supported_variables(self, variable: Variable) -> None:
        """Raise if the variable, or its frequency, is not one IMERG serves.

        Same wording and behaviour as
        :meth:`climateeval.data.ESMValToolCMORizerDataSource._check_supported_variables`,
        which cannot be inherited here: that class's ``download`` runs an
        ESMValTool CMORizer, and IMERG has none.
        """
        if variable.var_name not in self._supported_var_names:
            msg = f"{self.id} does not provide variable '{variable.var_name}'"
            raise NotImplementedError(msg)
        if variable.frequency not in self._supported_frequencies:
            msg = (
                f"{self.id} does not provide variable '{variable.var_name}' with "
                f"frequency '{variable.frequency}' (supported frequencies: "
                f"{', '.join(self._supported_frequencies)})"
            )
            raise NotImplementedError(msg)
