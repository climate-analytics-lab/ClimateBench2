"""Tier II diagnostics that reach back past the reserved test window.

The Tier II suites are cut to the post-2015 test window
(``_cli.SUITE_REGISTRY``), which is what the protocol scores — but two parts
of the protocol need the reference's **pre-2015** record, which that cut
removes from the results database:

- :class:`ReferenceBaselineRecord` writes the reference's 1985-2014
  (``tier2.climatology_baseline_period``) area-mean series so the scoring
  pass can build the **Climatology baseline's** pseudo-members from it
  (metrics_reference.md Tier II preamble, baseline (i)). Without it the pass
  can only record "the reference has no baseline window".
- :class:`ReferenceEOFProjection` builds the **regime-(b)** scoring basis:
  the area-weighted EOFs of the reference's pre-2015 monthly anomaly fields,
  truncated by the pre-registered ``tier2.eof.variance_explained``
  criterion, and projects the test-window climatological anomaly of the
  model, of the reference and of every comparison source onto it, each
  coefficient standardised by its pre-2015 σ.

Both are ClimateEval ``SimpleDiagnostic`` subclasses, so they take their
reference (and comparison) datasets from the suite YAML exactly like every
other Tier II entry; both load those datasets through
``DataSource.get_cube`` with a **copy of the suite ``Variable`` carrying a
different** ``timerange`` (:func:`with_timerange`), which is precisely how
ClimateEval itself applies a window (``_utils.get_prepared_cube`` →
``_extract_time_and_region``). No data loading, regridding or unit handling
is done here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, ClassVar

import ibis
import numpy as np
import pandas as pd
from esmvalcore.preprocessor import (
    annual_statistics,
    anomalies,
    area_statistics,
    climate_statistics,
    regrid,
    regrid_time,
)
from loguru import logger

from climateeval import Coordinate, Variable
from climateeval._config import setup_esmvaltool_config_and_logging
from climateeval._utils import get_prepared_cube
from climateeval._variable import COORDINATES
from climateeval.diags._base import DiagnosticOutput
from climateeval.diags._utils import DEFAULT_GRID
from climateeval.diags.simple._base import SimpleDiagnostic

from climatebench2 import scoring, windows
from climatebench2._thresholds import get_threshold
from climatebench2.diags.tier1_physics import _filled
from climatebench2.scoring_pass import (
    BASELINE_ANNUAL_DATA_TYPE,
    BASELINE_MONTHLY_DATA_TYPE,
)

if TYPE_CHECKING:
    from iris.cube import Cube, CubeList
    from xarray import Dataset

    from climateeval.data import DataSource, DataSourceInformation

logger = logger.opt(colors=True)

# The reference's baseline-window rows carry their own ``data_type`` —
# distinct from ``reference`` (the test-window target) so the scoring pass
# can tell the baseline *sample* from the values being scored, and so nothing
# downstream mistakes a pre-2015 record for something to score a model
# against. The names live in ``scoring_pass``, which is the consumer.
__all__ = [
    "BASELINE_ANNUAL_DATA_TYPE",
    "BASELINE_MONTHLY_DATA_TYPE",
    "ReferenceBaselineRecord",
    "ReferenceEOFProjection",
    "with_timerange",
]

#: ``data_type`` of the EOF row that is the *target*: the reference's own
#: test-window climatological anomaly, projected onto its own basis.
EOF_REFERENCE_DATA_TYPE = "reference"


def with_timerange(variable: Variable, timerange: str) -> Variable:
    """A copy of ``variable`` restricted to another ``timerange``.

    Rebuilds the ``Variable`` from its own preprocessing settings — the same
    move ``Variable.get_required_variables`` makes — so the new window flows
    into ``DataSource.get_cube`` → ``get_prepared_cube`` →
    ``_extract_time_and_region`` exactly as the suite's own window does.
    """
    settings = variable.get_preprocessing_settings()
    settings["timerange"] = timerange
    return Variable(variable.id, variable.var_name, variable.frequency, **settings)


def _years(cube: Cube) -> np.ndarray:
    """Calendar years of a cube's time coordinate."""
    coord = cube.coord("time")
    return np.array(
        [coord.units.num2date(p).year for p in coord.points],
        dtype=int,
    )


class _ReferenceWindowDiagnostic(SimpleDiagnostic):
    """Shared plumbing: load a suite's reference over another window."""

    _output_metrics_table: ClassVar[bool] = False

    #: Member-invariant results of :meth:`get_output`, while the diagnostic
    #: is shared across a suite's per-member runs; ``None`` = not shared, so
    #: every call recomputes (``climatebench2.shared_sources``).
    _member_memo: dict[Any, Any] | None = None

    def share_across_members(self) -> bool:
        """Opt in to computing the reference/comparison part once per suite.

        Both subclasses override ``get_output``, so the generic stage memo
        of :mod:`climatebench2.shared_sources` cannot see inside them; they
        memoise their own member-invariant part instead (everything except
        the ``to_benchmark`` rows), which is what makes that safe.
        """
        self._member_memo = {}
        return True

    def release_member_cache(self) -> None:
        """Drop what :meth:`share_across_members` memoised."""
        self._member_memo = None

    def _member_invariant(self, key: Any, compute: Any) -> Any:  # noqa: ANN401
        """``compute()``, stored under ``key`` while shared across members."""
        if self._member_memo is None:
            return compute()
        if key not in self._member_memo:
            self._member_memo[key] = compute()
        return self._member_memo[key]

    def _reference_cube_over(
        self,
        source: DataSource,
        variable: Variable,
        timerange: str,
    ) -> Cube | None:
        """Load one reference over ``timerange``; ``None`` (logged) if absent."""
        from climatebench2 import reference_windows

        # A reference whose record stops inside the requested window is
        # dropped by ClimateEval rather than clipped, so ask for the part that
        # is staged; `_covers_window` still rejects a record that is too short
        # to carry the statistic.
        timerange = reference_windows.clip_to_source(
            timerange,
            self.data_root_dir,
            source.id,
            variable.frequency,
            variable.var_name,
        )
        try:
            return source.get_cube(
                self.data_root_dir,
                with_timerange(variable, timerange),
                download_missing_data=self._download_missing_data,
            )
        except Exception as exc:  # noqa: BLE001 - a reference may simply not reach back
            logger.warning(
                f"Diagnostic '{self.name}': skipping {variable} of {source.id} — "
                f"it does not cover {timerange} ({exc})",
            )
            return None

    def _covers_window(
        self,
        cube: Cube,
        variable: Variable,
        source_id: str,
        first: int,
        last: int,
    ) -> bool:
        """Whether a loaded cube really spans enough of ``[first, last]``."""
        minimum = int(get_threshold("tier2.climatology_baseline_min_years"))
        n_years = int(np.unique(_years(cube)).size)
        if n_years < minimum:
            logger.warning(
                f"Diagnostic '{self.name}': skipping {variable} of {source_id} — "
                f"only {n_years} yr inside {first}-{last}, fewer than the "
                f"{minimum} yr the protocol asks of a baseline record",
            )
            return False
        return True


class ReferenceBaselineRecord(_ReferenceWindowDiagnostic):
    """The reference's 1985-2014 area-mean series (the Climatology sample).

    For each suite variable, loads the reference DataSource over
    ``tier2.climatology_baseline_period`` and writes both the **monthly** and
    the **annual** area-mean series into ``raw_output`` under the data types
    :data:`BASELINE_MONTHLY_DATA_TYPE` / :data:`BASELINE_ANNUAL_DATA_TYPE`.
    :mod:`climatebench2.scoring_pass` reads those rows and builds the
    Climatology baseline's pseudo-members from them (one per baseline year
    and calendar month), which the post-2015 cut had made impossible.

    No model data is touched and no metric is computed: this diagnostic
    exists to carry a *window* into the database, and its rows are inputs to
    the scoring pass, never scores.
    """

    _final_coordinates = (Coordinate("time"),)

    def _preprocess(self, cube: Cube, _variable: Variable) -> Cube:
        """Global (area-weighted) mean on the common grid, monthly."""
        with setup_esmvaltool_config_and_logging():
            cube = regrid(cube, DEFAULT_GRID, "linear", cache_weights=True)
            cube = area_statistics(cube, "mean")
        return cube  # noqa: RET504

    @staticmethod
    def _annual(cube: Cube) -> Cube:
        """Annual means on ClimateEval's standard time axis (as upstream)."""
        with setup_esmvaltool_config_and_logging():
            cube = annual_statistics(cube, "mean")
            cube = regrid_time(
                cube,
                frequency="yr",
                calendar="standard",
                units=COORDINATES["time"]["units"],
            )
        return cube  # noqa: RET504

    def get_output(
        self,
        data: CubeList | Dataset,  # noqa: ARG002 - the model plays no part here
        data_information: DataSourceInformation,
    ) -> DiagnosticOutput:
        """Write the reference's baseline-window series, nothing else."""
        first, last = windows.baseline_window_years()
        tables, source_infos = self._member_invariant("baseline", self._baseline)
        infos: list[DataSourceInformation] = [data_information, *source_infos]

        if not tables:
            logger.warning(
                f"Diagnostic '{self.name}': no reference covers the "
                f"{first}-{last} baseline window; the Climatology baseline "
                f"cannot be formed for this suite",
            )
            return DiagnosticOutput(
                raw_output=None,
                metrics=None,
                variables=None,  # type: ignore[arg-type] - Suite skips None tables
                data_sources=None,  # type: ignore[arg-type]
            )
        return DiagnosticOutput(
            raw_output=self._combine_raw_output_tables(*tables),
            metrics=None,
            variables=self._get_variables_table(self._variables),
            data_sources=self._get_data_sources_table(infos),
        )

    def _baseline(
        self,
    ) -> tuple[list[ibis.Table], list[DataSourceInformation]]:
        """``(raw-output tables, reference infos)`` — the member plays no part."""
        first, last = windows.baseline_window_years()
        window = windows.baseline_timerange()
        tables: list[ibis.Table] = []
        infos: list[DataSourceInformation] = []

        for variable, source in self._reference_data.items():
            cube = self._reference_cube_over(source, variable, window)
            if cube is None:
                continue
            if not self._covers_window(cube, variable, source.id, first, last):
                continue
            monthly = self._safely_preprocess(cube, variable)
            tables.append(
                self._get_raw_output_table(
                    monthly,
                    variable=variable,
                    data_id=source.id,
                    data_type=BASELINE_MONTHLY_DATA_TYPE,  # type: ignore[arg-type]
                ),
            )
            tables.append(
                self._get_raw_output_table(
                    self._annual(monthly),
                    variable=variable,
                    data_id=source.id,
                    data_type=BASELINE_ANNUAL_DATA_TYPE,  # type: ignore[arg-type]
                ),
            )
            infos.append(source.information)
        return tables, infos


class ReferenceEOFProjection(_ReferenceWindowDiagnostic):
    """Regime (b): coefficients on the reference's fixed pre-2015 EOF basis.

    Per suite variable (metrics_reference.md Tier II preamble (b)):

    1. load the reference over its **pre-2015** record
       (``tier2.climatology_baseline_period``), regridded to the common 2°
       grid, and form **monthly anomaly fields** relative to that window's
       monthly climatology (``anomalies(period="month")``);
    2. compute the **area-weighted EOF basis** of those fields, truncated by
       the pre-registered ``tier2.eof.variance_explained`` criterion (capped
       at ``tier2.eof.max_modes``), and record each retained mode's pre-2015
       PC standard deviation;
    3. project the **test-window climatological anomaly field** — the
       test-window time mean minus the reference's baseline climatology — of
       the model (one run per ensemble member), of the reference itself and
       of every comparison source onto that basis, and divide each
       coefficient by its pre-2015 σ.

    Output is one ``raw_output`` row per (source, variable, mode):
    ``data_id | data_type | var_id | mode | coefficient |
    explained_variance | sigma_pre2015``. The fair CRPS *across members* per
    coefficient, its equal-weight mean over modes and the skill against the
    CMIP6 median are computed by :mod:`climatebench2.scoring_pass` — the
    members arrive as separate data sources, so the score cannot be formed
    inside a diagnostic.

    The basis is a property of the **reference alone** and of a window that
    ends before the test period, so it is fixed in advance and identical for
    every submission, as the protocol requires.
    """

    _final_coordinates = ()

    def _preprocess(self, cube: Cube, _variable: Variable) -> Cube:
        """Regrid to the common grid; the projection needs the full field."""
        with setup_esmvaltool_config_and_logging():
            cube = regrid(cube, DEFAULT_GRID, "linear", cache_weights=True)
        return cube  # noqa: RET504

    # -- basis ------------------------------------------------------------

    def _basis_for(
        self,
        variable: Variable,
        source: DataSource,
    ) -> tuple[scoring.EOFBasis, np.ndarray, np.ndarray] | None:
        """``(basis, valid mask, baseline climatology)`` for one variable."""
        first, last = windows.baseline_window_years()
        cube = self._reference_cube_over(source, variable, windows.baseline_timerange())
        if cube is None:
            return None
        if not self._covers_window(cube, variable, source.id, first, last):
            return None
        field_cube = self._preprocess(cube, variable)
        climatology = self._time_mean(field_cube)
        with setup_esmvaltool_config_and_logging():
            anomaly_cube = anomalies(field_cube, period="month")

        # `np.ma.filled` has to see the *masked* array: calling it on the
        # output of `np.asarray` is a no-op, because `np.asarray` has already
        # thrown the mask away and exposed the file's 1e20 fill value.
        fields = _filled(anomaly_cube.data)
        fields = fields.reshape(fields.shape[0], -1)
        valid = np.isfinite(fields).all(axis=0)
        if valid.sum() < 2:  # noqa: PLR2004 - an EOF needs more than a point
            logger.warning(
                f"Diagnostic '{self.name}': {variable} of {source.id} has no "
                f"grid points that are finite through the whole "
                f"{first}-{last} window; skipping",
            )
            return None

        latitudes = field_cube.coord("latitude").points.astype(float)
        n_lon = field_cube.coord("longitude").points.size
        weights = scoring.cos_latitude_weights(latitudes, n_lon)[valid]
        basis = scoring.eof_basis(
            fields[:, valid],
            weights=weights,
            variance_explained=float(get_threshold("tier2.eof.variance_explained")),
            max_modes=int(get_threshold("tier2.eof.max_modes")),
            min_modes=int(get_threshold("tier2.eof.min_modes")),
        )
        logger.info(
            f"Diagnostic '{self.name}': {variable.id} basis from "
            f"{source.id} {first}-{last} — {basis.eofs.shape[0]} mode(s), "
            f"{100 * float(basis.explained_variance_ratio.sum()):.0f}% of the "
            f"variance",
        )
        return basis, valid, climatology

    @staticmethod
    def _time_mean(cube: Cube) -> np.ndarray:
        """Flattened time-mean field of a (time, lat, lon) cube."""
        with setup_esmvaltool_config_and_logging():
            mean_cube = climate_statistics(cube, "mean", "full")
        return _filled(mean_cube.data).reshape(-1)

    # -- projection -------------------------------------------------------

    def _coefficient_rows(
        self,
        cube: Cube,
        *,
        variable: Variable,
        basis: scoring.EOFBasis,
        valid: np.ndarray,
        climatology: np.ndarray,
        data_id: str,
        data_type: str,
    ) -> list[dict[str, Any]]:
        """Standardised coefficients of one source's test-window anomaly."""
        field = self._time_mean(self._preprocess(cube, variable))
        if field.size != valid.size:
            logger.warning(
                f"Diagnostic '{self.name}': {variable} of {data_id} has "
                f"{field.size} grid points against the basis's {valid.size}; "
                f"skipping",
            )
            return []
        anomaly = (field - climatology)[valid]
        # A source may mask a point the reference resolves (a different
        # land/sea mask, a shorter record). Treat it as "no anomaly" rather
        # than dropping the whole source: the basis is fixed and cannot be
        # re-derived per source.
        if not np.isfinite(anomaly).all():
            logger.warning(
                f"Diagnostic '{self.name}': {variable} of {data_id} is missing "
                f"{int((~np.isfinite(anomaly)).sum())} of {anomaly.size} basis "
                f"points; treating them as zero anomaly",
            )
            anomaly = np.nan_to_num(anomaly, nan=0.0)
        coefficients = scoring.standardised_coefficients(basis, anomaly)
        return [
            {
                "data_id": data_id,
                "data_type": data_type,
                "var_id": variable.id,
                "mode": float(k + 1),
                "coefficient": float(coefficients[k]),
                "explained_variance": float(basis.explained_variance_ratio[k]),
                "sigma_pre2015": float(basis.pc_std[k]),
            }
            for k in range(basis.eofs.shape[0])
        ]

    def get_output(
        self,
        data: CubeList | Dataset,
        data_information: DataSourceInformation,
    ) -> DiagnosticOutput:
        """Project model, reference and comparison fields onto the basis."""
        rows: list[dict[str, Any]] = []
        infos: list[DataSourceInformation] = [data_information]

        for variable, source in self._reference_data.items():
            shared = self._member_invariant(
                variable,
                lambda variable=variable, source=source: self._invariant_rows(
                    variable,
                    source,
                ),
            )
            if shared is None:
                continue
            infos.append(source.information)
            if shared.reference_rows is None:
                continue
            rows += shared.reference_rows

            try:
                model_cube = get_prepared_cube(data, variable)
            except Exception as exc:  # noqa: BLE001
                self._handle_missing_data(data_information.id, (variable,), exc)
            else:
                rows += self._coefficient_rows(
                    model_cube,
                    data_id=data_information.id,
                    data_type="to_benchmark",
                    **shared.common,
                )

            rows += shared.other_rows
            infos += shared.other_infos

        if not rows:
            return DiagnosticOutput(
                raw_output=None,
                metrics=None,
                variables=None,  # type: ignore[arg-type] - Suite skips None tables
                data_sources=None,  # type: ignore[arg-type]
            )
        return DiagnosticOutput(
            raw_output=ibis.memtable(pd.DataFrame(rows)),
            metrics=None,
            variables=self._get_variables_table(self._variables),
            data_sources=self._get_data_sources_table(infos),
        )

    def _invariant_rows(
        self,
        variable: Variable,
        source: DataSource,
    ) -> _ProjectionRows | None:
        """Everything of one variable's projection that is not the member.

        The basis, the reference's own coefficients and every comparison
        source's coefficients depend on the reference and the comparison
        ensemble alone, so a shared diagnostic computes them for the first
        member only. ``None`` when there is no basis (the variable is then
        skipped entirely); ``reference_rows is None`` when the reference does
        not reach the test window (the basis's source is still recorded, as
        it always was, but nothing is projected).
        """
        prepared = self._basis_for(variable, source)
        if prepared is None:
            return None
        basis, valid, climatology = prepared
        common = {
            "variable": variable,
            "basis": basis,
            "valid": valid,
            "climatology": climatology,
        }

        # The reference's own test-window anomaly: the target the model
        # coefficients are scored against.
        reference_cube = self._reference_cube_over(
            source,
            variable,
            variable.timerange,
        )
        if reference_cube is None:
            return _ProjectionRows(common=common, reference_rows=None)
        reference_rows = self._coefficient_rows(
            reference_cube,
            data_id=source.id,
            data_type=EOF_REFERENCE_DATA_TYPE,
            **common,
        )

        other_rows: list[dict[str, Any]] = []
        other_infos: list[DataSourceInformation] = []
        for other in self._other_data.get(variable, ()):
            try:
                other_cube = other.get_cube(
                    self.data_root_dir,
                    variable,
                    download_missing_data=self._download_missing_data,
                )
            except Exception as exc:  # noqa: BLE001
                self._handle_missing_data(other.id, (variable,), exc)
                continue
            other_rows += self._coefficient_rows(
                other_cube,
                data_id=other.id,
                data_type="other",
                **common,
            )
            other_infos.append(other.information)
        return _ProjectionRows(
            common=common,
            reference_rows=reference_rows,
            other_rows=other_rows,
            other_infos=other_infos,
        )


@dataclass(frozen=True)
class _ProjectionRows:
    """The member-invariant part of one variable's EOF projection."""

    common: dict[str, Any]
    reference_rows: list[dict[str, Any]] | None
    other_rows: list[dict[str, Any]] = field(default_factory=list)
    other_infos: list[DataSourceInformation] = field(default_factory=list)
