"""The CMIP6 historical+SSP2-4.5 comparison ensemble, read from a staged root.

Why this exists
---------------
Tier II's ``E_ref`` is the median fair CRPS over the **CMIP6 comparison
models** (metrics_reference.md §II.0, paper §5.6), so every core variable's
``other_data`` has to resolve to a multi-member historical+SSP2-4.5 ensemble
over the reserved post-2015 test window. Upstream ClimateEval has exactly that
generator — :class:`climateeval.data.CMIP6HistoricalSSP245` (PR #44) — and it
remains the **documented alternative**: the data source ids this module
produces are byte-identical to its, so a database written either way scores the
same and the two can be mixed.

What differs is only *discovery*:

* upstream globs the CMIP6 pool through ESMValCore
  (``Dataset(...).from_files()``), which takes on the order of half a minute
  **per variable per diagnostic instance** on a DKRZ-sized replica — a Tier II
  suite instantiates a dozen diagnostics over ten variables, so the discovery
  alone would dominate the run;
* upstream's ``ensemble: r*i1p1f1`` facet silently drops every model whose
  members carry a non-``f1`` forcing index (UKESM1-0-LL, CNRM-*, HadGEM3-* are
  all ``f2``/``f3``), and it has no member cap, so one large ensemble can
  outvote the whole multi-model spread in the ``E_ref`` median;
* upstream falls back to intake-esgf when a variable is missing locally, which
  on an HPC login/compute node means a network path that bypasses the local
  pool entirely.

This generator instead **enumerates directories** in a staged root that has
already been built to the protocol's member policy
(``runs/staging_scripts/build_comparison_root.py``): members with ``i1p1`` and
any forcing index ``f``, capped at the first ten by realization number per
model. The policy and the cap live in that staging step, where they are
recorded in a manifest, rather than in a facet dict that no reviewer sees.

Where the staged root is
------------------------
``CLIMATEBENCH2_STAGED_CMIP6_ROOT``, if set; otherwise the ``--data-root`` that
``climatebench2 score`` passes to the diagnostics (``climatebench2._cli``
exports it into the environment for exactly this reason, because ClimateEval
instantiates a generator with no arguments and calls ``generate(variable)``
before the diagnostic's data root is known). Pointing the variable at a subset
of the root is how a smoke run limits the comparison ensemble without
restaging: discovery uses the subset, while loading still uses ``--data-root``.

Layout it expects — ClimateEval's own
:meth:`climateeval.data.DataSource._get_data_dir` layout::

    <root>/CMIP6_<model>_historical-ssp245_<member>/<frequency>/<var_name>/*.nc

A model/member/variable that has no such directory is simply not yielded, so a
variable staged for only some members gives a smaller ensemble for that
variable rather than an error.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar

from climateeval.data import DataSourceGenerator, DataSourceInformation
from climateeval.data._esmvaltool_intake import ESMValToolIntakeDataSource

if TYPE_CHECKING:
    from collections.abc import Generator

    from climateeval import Variable

#: Environment variable naming the staged comparison-ensemble root. Unset
#: means "the data root ``climatebench2 score`` was given".
STAGED_ROOT_ENV = "CLIMATEBENCH2_STAGED_CMIP6_ROOT"

#: ``exp`` of the concatenated historical+SSP2-4.5 record, as
#: :func:`climateeval.data._utils.facet_to_str` renders ``["historical",
#: "ssp245"]``. This string is half of the data source id, so it must not
#: drift from upstream's.
STAGED_EXP = "historical-ssp245"

#: The ``exp`` facet list itself (what upstream puts in
#: ``esmvaltool_dataset_facets``).
STAGED_EXP_FACET: tuple[str, ...] = ("historical", "ssp245")

#: Directory name of one staged member:
#: ``CMIP6_<model>_historical-ssp245_<member>``.
_SOURCE_DIR_RE = re.compile(
    rf"^CMIP6_(?P<model>.+)_{STAGED_EXP}_(?P<member>r\d+i\d+p\d+f\d+)$",
)

#: A CMOR filename, ``<var>_<table>_<model>_<exp>_<member>_<grid>[_<time>].nc``.
_CMOR_FILE_RE = re.compile(
    r"^(?P<short_name>[^_]+)_(?P<mip>[^_]+)_(?P<dataset>[^_]+)_(?P<exp>[^_]+)_"
    r"(?P<ensemble>r\d+i\d+p\d+f\d+)_(?P<grid>[^_]+)(?:_(?P<time>[^_]+))?\.nc$",
)


def staged_root(data_root_dir: Path | str | None = None) -> Path | None:
    """The staged comparison-ensemble root, or ``None`` if there is none.

    ``CLIMATEBENCH2_STAGED_CMIP6_ROOT`` wins over ``data_root_dir`` so a run
    can point discovery at a subset of a larger root.
    """
    from_env = os.environ.get(STAGED_ROOT_ENV, "").strip()
    root = Path(from_env) if from_env else None
    if root is None and data_root_dir is not None:
        root = Path(data_root_dir)
    if root is None or not root.is_dir():
        return None
    return root


#: ``(root, frequency, var_name) -> [(model, member, files)]``. A Tier II suite
#: instantiates ~7 diagnostics over ~10 variables and ClimateEval calls
#: ``generate`` once per (diagnostic, variable), so without this the same
#: directory walk — and the same few hundred ``Path.resolve()`` calls on
#: symlinks into the pool — would run ~70 times per member set.
_DISCOVERY_CACHE: dict[tuple[str, str, str], list[tuple[str, str, list[Path]]]] = {}

#: ``(root, model) -> institute``.
_INSTITUTE_CACHE: dict[tuple[str, str], str] = {}


def _institute(files: list[Path], model: str) -> str:
    """Institute of a model: from the staged file's DRS path, else CMOR tables.

    The staged files are symlinks into a CMIP6 DRS replica
    (``.../CMIP6/<activity>/<institute>/<model>/...``), which is the
    authoritative spelling for that pool. The institute is provenance only —
    it is not part of the data source id — so an empty string is harmless.
    """
    for path in files[:1]:
        try:
            parts = path.resolve().parts
        except OSError:  # pragma: no cover - broken symlink
            continue
        for index in reversed([i for i, p in enumerate(parts) if p == "CMIP6"]):
            if len(parts) > index + 3 and parts[index + 3] == model:
                return parts[index + 2]
    try:
        from esmvalcore.cmor.table import CMOR_TABLES  # noqa: PLC0415

        institutes = CMOR_TABLES["CMIP6"].institutes.get(model, [])
    except Exception:  # noqa: BLE001
        return ""
    return str(institutes[0]) if institutes else ""


def _facets_from_filename(files: list[Path]) -> dict[str, str]:
    """``mip``/``grid`` of a staged leaf, read off its CMOR filenames."""
    for path in files:
        match = _CMOR_FILE_RE.match(path.name)
        if match is not None:
            return {"mip": match["mip"], "grid": match["grid"]}
    return {}


def _required_var_names(variable: Variable) -> list[str]:
    """Variable names a member must carry for ``variable`` to be loadable.

    A **derived** variable (``rtnt`` = ``rsdt − rsut − rlut``) is never staged
    itself: :meth:`climateeval.data.DataSource.get_cube` derives it from the
    variables ESMValCore says it requires, and returns nothing unless *all* of
    them are present. Discovering on the variable's own directory would
    therefore yield an empty comparison ensemble for every derived variable —
    which is how ``rtnt`` silently lost its ``E_ref``.
    """
    if not variable.derived:
        return [variable.var_name]
    try:
        return [v.var_name for v in variable.get_required_variables()]
    except Exception:  # noqa: BLE001 - CMOR tables unavailable
        return [variable.var_name]


def _discover(root: Path, variable: Variable) -> list[tuple[str, str, list[Path]]]:
    """``[(model, member, files)]`` staged for one variable, cached per root."""
    key = (str(root), variable.frequency, variable.var_name)
    if key in _DISCOVERY_CACHE:
        return _DISCOVERY_CACHE[key]
    var_names = _required_var_names(variable)
    found: list[tuple[str, str, list[Path]]] = []
    for source_dir in sorted(root.iterdir()):
        match = _SOURCE_DIR_RE.match(source_dir.name)
        if match is None or not source_dir.is_dir():
            continue
        files: list[Path] = []
        for var_name in var_names:
            var_dir = source_dir / variable.frequency / var_name
            var_files = sorted(var_dir.glob("*.nc")) if var_dir.is_dir() else []
            if not var_files:
                files = []
                break
            files.extend(var_files)
        if files:
            found.append((match["model"], match["member"], files))
    _DISCOVERY_CACHE[key] = found
    return found


def clear_discovery_cache() -> None:
    """Forget the staged-root directory walk (used by the tests)."""
    _DISCOVERY_CACHE.clear()
    _INSTITUTE_CACHE.clear()


class StagedCMIP6HistoricalSSP245(DataSourceGenerator):
    """CMIP6 historical+SSP2-4.5 comparison ensemble from a staged data root.

    Yields one :class:`~climateeval.data._esmvaltool_intake.ESMValToolIntakeDataSource`
    subclass per staged ``(model, member)`` that actually carries the variable,
    with

    * ``name`` = the model, ``category`` = ``CMIP6``, ``exp`` =
      ``historical-ssp245``, ``variant`` = the member — i.e. the data source id
      ``CMIP6_<model>_historical-ssp245_<member>``, the same id upstream's
      :class:`climateeval.data.CMIP6HistoricalSSP245` produces, so
      :func:`climatebench2.scoring_pass.group_members` stacks the members of
      one model into one comparison ensemble;
    * ``esmvaltool_dataset_facets`` filled in, so a source that *is* missing
      locally can still be downloaded when ``--download`` is given.
    """

    #: Facets of the ensemble this generator stands for. Not used for
    #: discovery (that is the directory walk); they are what the yielded data
    #: sources carry, and what a ``--download`` fallback would use.
    esmvaltool_dataset_facets: ClassVar[dict[str, Any]] = {
        "project": "CMIP6",
        "exp": list(STAGED_EXP_FACET),
        "dataset": "*",
        "institute": "*",
        "ensemble": "r*i1p1f*",
        "grid": "*",
        "timerange": "19790101/*",
    }

    def __init__(self, data_root_dir: Path | str | None = None) -> None:
        """Remember an explicit root (ClimateEval instantiates with none)."""
        self._data_root_dir = data_root_dir

    def generate(
        self,
        variable: Variable,
    ) -> Generator[ESMValToolIntakeDataSource]:
        """Yield one data source per staged member carrying ``variable``."""
        root = staged_root(self._data_root_dir)
        if root is None:
            return

        for model, member, files in _discover(root, variable):
            institute_key = (str(root), model)
            if institute_key not in _INSTITUTE_CACHE:
                _INSTITUTE_CACHE[institute_key] = _institute(files, model)
            institute = _INSTITUTE_CACHE[institute_key]
            facets: dict[str, Any] = {
                **self.esmvaltool_dataset_facets,
                "dataset": model,
                "institute": institute or "*",
                "ensemble": member,
                "short_name": variable.var_name,
                "frequency": variable.frequency,
                "mip": variable.cmip6_table_id,
            }
            facets.update(_facets_from_filename(files))

            information = DataSourceInformation(
                name=model,
                category="CMIP6",
                institute=institute,
                exp=STAGED_EXP,
                variant=member,
                references=(
                    "https://www.wdc-climate.de/ui/cmip6?input=CMIP6.CMIP."
                    f"{institute}.{model}",
                    "https://www.wdc-climate.de/ui/cmip6?input=CMIP6.ScenarioMIP."
                    f"{institute}.{model}",
                ),
            )
            yield type(
                f"{self.__class__.__name__}DataSource",
                (ESMValToolIntakeDataSource,),
                {
                    "_information": information,
                    "esmvaltool_dataset_facets": facets,
                },
            )()
