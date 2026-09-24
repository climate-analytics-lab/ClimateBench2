"""MODIS Aqua monthly cloud properties, served from a staged root.

Why this lives here and not upstream
------------------------------------
Same reason, and same caveat, as :mod:`climatebench2.data.imerg`: it is a
data source, so it **belongs upstream** (docs/climateeval_delineation_plan.md,
the ownership test), but ClimateEval is a pinned third-party dependency CB2
does not patch. It subclasses :class:`climateeval.data.DataSource` and adds
nothing CB2-specific, so moving it to ``climateeval/data/_modis.py`` is a
file copy.

What it is for
--------------
The paper's Tier II core list ends with "clouds", and its extended list
names "cloud properties — LWP, fraction". Until 2026-09-24 the only cloud
reference in the stack was ESACCI-CLOUD (``climateeval.data.ESACCICloud``),
which **ends in 2016-12**: two years of the reserved post-2015 test window,
below the scoring pass's minimum overlap, so ``clt``/``clwvi``/``clivi``
were computed and left out of the paper's figure set. MODIS Aqua runs from
2002-07 to the present, so it covers the whole test window.

ESMValTool has a MODIS CMORizer (``modis.ncl``, OBS6 ``MODIS`` / MYD08_M3),
but its output lives in the restricted Tier-3 OBS pool, which is not
readable from this allocation. The staged files are therefore produced by
``runs/modis/fetch_modis.py``, which **mirrors modis.ncl** on MYD08_M3
Collection 6.1 (monthly L3, 1°):

=========  ===========================================================  =========
variable   definition                                                   units
=========  ===========================================================  =========
``clt``    ``100 * Cloud_Fraction_Mean_Mean``                           ``%``
``clivi``  ``1e-3 * Cloud_Water_Path_Ice_Mean_Mean * cif``              ``kg m-2``
``lwp``    ``1e-3 * Cloud_Water_Path_Liquid_Mean_Mean * lif``           ``kg m-2``
``clwvi``  ``lwp + clivi``                                              ``kg m-2``
=========  ===========================================================  =========

MODIS water paths are **in-cloud** values; they become grid-box means as in
modis.ncl, with ``cif`` = ``Cirrus_Fraction_Infrared_FMean`` (the ice-cloud
fraction) and, assuming random overlap, ``lif = max(0, 1 − (1 − ctot) /
(1 − cif))`` (``cif > 0.999`` masked). A model's ``clwvi``/``clivi`` are
grid-box means too, which is the whole point of the conversion.

Staged-file contract
--------------------
:meth:`climateeval.data.DataSource.get_cube` globs
``<data_root>/<id>/<frequency>/<var_name>/*.nc`` — with ``id`` =
``observation_MODIS`` — pre-filters that list by each file's CMOR-style
trailing ``<start>-<end>`` token against the variable's ``timerange``,
concatenates what is left and hands it to ``get_prepared_cube``. So the
staging layout is::

    <data_root>/observation_MODIS/mon/<var>/
        <var>_Amon_MODIS_MYD08-M3_200201-200212.nc   (partial: from 2002-07)
        <var>_Amon_MODIS_MYD08-M3_200301-200312.nc
        ...
        <var>_Amon_MODIS_MYD08-M3_202601-202612.nc   (partial: to the last granule)

for ``<var>`` in ``clt``, ``clwvi``, ``clivi``, ``lwp``: one file per
calendar year, **always named** ``YYYY01-YYYY12`` even when the year is
partial (the filename token only pre-filters; the time axis decides what is
used), on a regular 1° grid (lat −89.5…89.5 ascending, lon −179.5…179.5),
stamped mid-month (the 15th) on the standard calendar, with the CMOR
``standard_name`` and units above. Nothing is converted here: the units are
the CMOR ones, so a model's field and the reference go through the same
``get_prepared_cube`` path.

``lwp`` is **derived** in ClimateEval's registry (``clwvi − clivi``) but is
staged directly, because the glob of the variable's own directory runs
before any derivation. Either way it is the same number.

Record and window
-----------------
The record starts 2002-07, so its first *complete* calendar year is 2003 —
what :func:`climatebench2.reference_windows.source_coverage` reports — and
it ends with the latest granule, whose partial year is dropped the same way.
Consequences (docs/metrics_reference.md, decision B.28):

* the regime-(a) entries (``annual_mean_timeseries``) load MODIS over
  **2003 → the last complete year**, so the anomaly baseline of a cloud
  variable is **2003–2014** — 12 years of the 1985–2014 window, above the
  ``tier2.anomaly_baseline.min_years`` = 10 floor. Every source (submission,
  reference, comparison member) is anomalised about its own climatology
  over the years it has in 1985–2014, exactly as for the CERES-EBAF fluxes
  (baseline 2001–2014);
* the pre-2015 reference record behind ``reference_baseline`` and the
  regime-(b) EOF basis of ``eof_projection`` is 2003–2014 as well.
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


class MODIS(DataSource):
    """MODIS Aqua MYD08_M3 (C6.1) monthly cloud properties, from a staged root.

    Data source id ``observation_MODIS``; monthly ``clt``, ``clwvi``,
    ``clivi`` and ``lwp``.

    There is no download path: ESMValTool's MODIS CMORizer output is in the
    Tier-3 pool, so :meth:`download` always raises and the files must be
    staged under ``<data_root>/observation_MODIS/mon/<var>/`` (see the
    module docstring for the contract). Everything else — the glob, the
    ``timerange`` pre-filter, the concatenation, the region/mask/unit
    preprocessing — is :class:`climateeval.data.DataSource`'s.
    """

    _information = DataSourceInformation(
        name="MODIS",
        category="observation",
        institute="NASA-GSFC",
        references=(
            "https://doi.org/10.5067/MODIS/MYD08_M3.061",
            "https://ladsweb.modaps.eosdis.nasa.gov/missions-and-measurements/products/MYD08_M3",
        ),
    )

    #: The four fields ``fetch_modis.py`` writes. Declared (and enforced in
    #: :meth:`get_cube`) so a suite that asks MODIS for ``rsut`` fails with a
    #: sentence instead of an empty directory.
    _supported_var_names: ClassVar[tuple[str, ...]] = ("clt", "clwvi", "clivi", "lwp")

    #: MYD08_M3 is the **monthly** L3 product; the daily MYD08_D3 is not staged.
    _supported_frequencies: ClassVar[tuple[str, ...]] = ("mon",)

    def get_cube(
        self,
        data_root_dir: Path | str,
        variable: Variable,
        *,
        download_missing_data: bool = True,
    ) -> Cube:
        """The staged cube, after checking the variable is one MODIS has."""
        self._check_supported_variables(variable)
        return super().get_cube(
            data_root_dir,
            variable,
            download_missing_data=download_missing_data,
        )

    def download(self, variable: Variable, data_root_dir: Path | str) -> list[Path]:
        """Never: the MODIS CMORizer output is Tier-3; the files are staged."""
        self._check_supported_variables(variable)
        msg = (
            f"{self.id} cannot be downloaded: ESMValTool's MODIS CMORizer output "
            f"is in the restricted Tier-3 pool. Stage one file per year under "
            f"{data_root_dir}/{self.id}/{variable.frequency}/{variable.var_name}/ "
            f"(see climatebench2.data.modis for the file contract)"
        )
        raise DownloadError(msg)

    def _check_supported_variables(self, variable: Variable) -> None:
        """Raise if the variable, or its frequency, is not one MODIS serves.

        Same wording and behaviour as
        :meth:`climateeval.data.ESMValToolCMORizerDataSource._check_supported_variables`
        (and :meth:`climatebench2.data.IMERG._check_supported_variables`).
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
