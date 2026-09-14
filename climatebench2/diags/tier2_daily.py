"""Tier II daily and sub-daily diagnostics (metrics_reference.md §II.1).

The three statistics the protocol computes from ``day``/``1hr`` data, all
labelled **in-sample** (they are climatologies of the full historical
record, not of the reserved post-2015 test window — which is why
``ClimateBench2_TierII_daily`` is the one cube suite the CLI does *not* cut
to the test window):

- :class:`ETCCDIExtremes` — the eight ETCCDI indices the paper's §5.2 fixes
  (TXx, TNn, TX90p, WSDI; Rx1day, Rx5day, R95pTOT, CDD), each reduced to a
  **climatological mean and an OLS trend per region**;
- :class:`DiurnalHarmonic` — the first-harmonic amplitude and phase of the
  sub-daily climatology in **local solar time**, by season and region;
- :class:`PerkinsSkillScore` — the overlap of the modelled and observed
  **daily PDFs** (temperature anomalies, wet-day precipitation intensity).

Shapes and why
--------------
The first two write **aggregated scalars**: one row per data source with one
column per (index, region, statistic), which is exactly the table
:func:`climatebench2.scoring_pass.score_scalar_output` scores — fair CRPS
across the submission's members against the reference's value of the same
scalar, plus the regime-(c) consistency row. They get there through
:class:`ScalarTableDiagnostic`, a ``SimpleDiagnostic`` whose raw output is a
bag of named numbers rather than a series (the ``Histogram`` precedent for
overriding the table shape), so the suite's ``reference_data:`` gives the
observed value for free — no ``ObservedScalarMixin`` and no complex
diagnostic needed.

The Perkins score is **not** an error and must never enter ``E_ref`` or
``S = 1 − E/E_ref``, so it is written as a *metric* (one ``perkins_<season>``
column per variable in the diagnostic's ``metrics`` table) and shown in the
leaderboard's own distribution-skill table.

Observational references — the binding gap
------------------------------------------
⚠ **ClimateEval has no daily observational product for the extremes.**
``ERA5.VARIABLE_MAPPING`` carries ``tas`` and ``pr`` but **no ``tasmax`` or
``tasmin``** (there is no CMOR daily-extremes entry to map), and
``ERA5Hourly``'s download request is hard-wired to a single year, so it
cannot serve TXx/TNn as an interim reference however the ``Variable`` is
spelled. The extremes therefore run **model-only and unscored**: the scalars
are written, the pass finds no ``reference`` row for them and skips them by
design (the same treatment as the Pinatubo ``rsds`` dimming). The natural
reference is **HadEX3**, which already has an ESMValTool CMORizer — an
upstream DataSource is all that is needed; Berkeley daily, HadGHCND, IMERG
and MSWEP have none. The precipitation indices *could* be referenced against
``ERA5Hourly`` ``pr`` through ``daily_statistics``, which is why the suite
carries that stanza commented out rather than silently scoring a model
against a single ERA5 year.

The diurnal cycle and the Perkins score **do** have a reference
(``ERA5Hourly`` ``pr``/``tas``), so those are scored.

Everything numerical is in :mod:`climatebench2.physics` /
:mod:`climatebench2.scoring`; this module only arranges cubes and reads
``thresholds.yml``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

import ibis
import numpy as np
import pandas as pd
from esmvalcore.preprocessor import climate_statistics, local_solar_time, regrid
from loguru import logger

from climateeval import Coordinate
from climateeval._config import setup_esmvaltool_config_and_logging
from climateeval.diags._utils import union
from climateeval.diags.simple._base import SimpleDiagnostic

from climatebench2 import physics, scoring
from climatebench2._thresholds import get_threshold
from climatebench2.diags.tier1_physics import _cube_years_months, _filled

if TYPE_CHECKING:
    from iris.cube import Cube

    from climateeval import Variable

logger = logger.opt(colors=True)

#: Calendar months of each meteorological season.
SEASON_MONTHS: dict[str, tuple[int, ...]] = {
    "DJF": (12, 1, 2),
    "MAM": (3, 4, 5),
    "JJA": (6, 7, 8),
    "SON": (9, 10, 11),
}

#: Minimum years for a trend to be reported (``physics.ols_trend`` needs 3).
_MIN_TREND_YEARS = 5


# ---------------------------------------------------------------------------
# A SimpleDiagnostic whose raw output is a bag of named scalars
# ---------------------------------------------------------------------------


class ScalarTableDiagnostic(SimpleDiagnostic):
    """A ``SimpleDiagnostic`` that reduces each variable to named scalars.

    ClimateEval's simple diagnostics write one column per suite variable over
    a coordinate axis (time, hour, bin, …). A Tier II *aggregated* diagnostic
    needs the other shape — **one row per data source** with one column per
    named scalar and no coordinate at all — because that is what
    :func:`climatebench2.scoring_pass.score_scalar_output` recognises: fair
    CRPS of the submission's members against the reference's value of the
    same scalar, on a single-point scoring axis.

    Subclasses implement :meth:`_scalars`, which turns one preprocessed cube
    into ``{name: value}``; the reference, the submission's members and every
    comparison source all go through it, so the reference row the pass needs
    comes from the suite's ordinary ``reference_data:`` entry.

    Overriding the table shape follows ClimateEval's own ``Histogram``
    precedent. Deterministic metrics are switched off: ``distance_metric`` on
    a bag of unrelated scalars would be meaningless.
    """

    _output_metrics_table: ClassVar[bool] = False

    def _scalars(self, cube: Cube, variable: Variable) -> dict[str, float]:
        """``{scalar name: value}`` for one preprocessed cube."""
        raise NotImplementedError

    def _get_raw_output_table(
        self,
        cube: Cube,
        *,
        variable: Variable,
        data_id: str,
        data_type: str,
    ) -> ibis.Table:
        """One row of named scalars for this (source, variable)."""
        values = self._scalars(cube, variable)
        frame = pd.DataFrame(
            {name: pd.Series([float(value)], dtype="float64") for name, value in values.items()},
        )
        table = ibis.memtable(frame)
        table = table.cast(dict.fromkeys(table.columns, self._dtype))
        table = table.mutate(**{self._data_id_column: ibis.literal(data_id)})
        return table.mutate(**{self._data_type_column: ibis.literal(data_type)})

    def _combine_raw_output_tables(
        self,
        *raw_output_tables: ibis.Table,
    ) -> ibis.Table | None:
        """Collapse every variable's scalars into one row per data source."""
        if not raw_output_tables:
            return None
        table = union(*raw_output_tables)
        scalar_columns = [
            c
            for c in table.columns
            if c not in (self._data_id_column, self._data_type_column)
        ]
        return self._remove_superfluous_rows(
            table,
            unique_columns=(self._data_id_column, self._data_type_column),
            variable_columns=scalar_columns,
        )


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _regional_series(
    field: np.ndarray,
    latitudes: np.ndarray,
    bounds: tuple[float, float],
) -> np.ndarray:
    """cos(lat)-weighted mean of a ``(n, lat, lon)`` field over a latitude band.

    The band is the protocol's region (``thresholds.yml``); the land/sea
    surface is *not* handled here — it is a mask, which ClimateEval owns, and
    the suite declares it per variable with ``landsea_mask``.
    """
    lats = np.asarray(latitudes, dtype=float)
    inside = (lats >= float(bounds[0])) & (lats <= float(bounds[1]))
    if not inside.any():
        return np.full(field.shape[0], np.nan)
    band = np.asarray(field, dtype=float)[:, inside, :]
    return np.array(
        [physics.area_weighted_mean(step, lats[inside]) for step in band],
        dtype=float,
    )


def _climatology_and_trend(series: np.ndarray) -> tuple[float, float]:
    """``(climatological mean, OLS trend per decade)`` of an annual series."""
    values = np.asarray(series, dtype=float)
    finite = np.isfinite(values)
    climatology = float(np.nanmean(values)) if finite.any() else float("nan")
    trend = (
        physics.ols_trend(values) * 10.0
        if finite.sum() >= _MIN_TREND_YEARS
        else float("nan")
    )
    return climatology, trend


def _season_indices(months: np.ndarray, season: str) -> np.ndarray:
    """Positions of the time steps belonging to one meteorological season."""
    return np.flatnonzero(np.isin(months, SEASON_MONTHS[season]))


# ---------------------------------------------------------------------------
# ETCCDI daily extremes
# ---------------------------------------------------------------------------


class ETCCDIExtremes(ScalarTableDiagnostic):
    """The eight ETCCDI indices of §II.1, per region, as aggregated scalars.

    Per suite variable (daily ``tasmax``, ``tasmin`` or ``pr``, land-masked
    by the suite because ETCCDI indices are station-derived **land**
    indices):

    1. conservative regrid to the common ~1° grid
       (``tier2.extremes.grid`` / ``regrid_scheme``, the paper's
       "conservative regridding of model and obs to a common ~1 degree
       grid");
    2. the index **per year, per grid point**
       (:mod:`climatebench2.physics`), with the percentile thresholds of
       TX90p / WSDI / R95pTOT taken over the fixed
       ``tier2.extremes.base_period`` (1985-2014);
    3. a cos(lat)-weighted mean over each ``tier2.extremes.regions``
       latitude band, giving one annual series per (index, region);
    4. that series reduced to a **climatological mean** and an **OLS trend
       per decade** — the two scalars the protocol scores.

    Columns are ``<index>_<region>_clim`` and ``<index>_<region>_trend``,
    e.g. ``txx_global_land_clim``, ``cdd_tropical_land_trend``.

    ⚠ **Unscored today.** No ClimateEval DataSource provides daily
    observational extremes (see the module docstring: ERA5 has no
    ``tasmax``/``tasmin``, HadEX3 has an ESMValTool CMORizer but no
    DataSource), so the suite gives these variables no ``reference_data:``
    and the scoring pass, finding no observed value, leaves them as reported
    model numbers. Everything else about them is already in the scored shape.

    ❗ Memory: the whole daily record is realised as one ``(time, lat, lon)``
    array on the 1° grid. That is fine for a few decades and heavy for a
    full historical run; like the other daily diagnostics (I.3b, I.5d) this
    has only ever been exercised on synthetic cubes.
    """

    _final_coordinates = (Coordinate("time"), Coordinate("lat"), Coordinate("lon"))

    #: Which indices each input variable yields (paper §5.2's fixed set).
    _INDICES: ClassVar[dict[str, tuple[str, ...]]] = {
        "tasmax": ("txx", "tx90p", "wsdi"),
        "tasmin": ("tnn",),
        "pr": ("rx1day", "rx5day", "r95ptot", "cdd"),
    }

    def _preprocess(self, cube: Cube, _variable: Variable) -> Cube:
        """Conservative regrid to the protocol's ~1° extremes grid."""
        with setup_esmvaltool_config_and_logging():
            cube = regrid(
                cube,
                str(get_threshold("tier2.extremes.grid")),
                str(get_threshold("tier2.extremes.regrid_scheme")),
                cache_weights=True,
            )
        return cube  # noqa: RET504

    def _base_period_mask(self, years: np.ndarray) -> np.ndarray:
        """Days inside ``tier2.extremes.base_period``, or the whole record.

        A submission whose daily output does not reach back into 1985-2014
        would otherwise have no percentile threshold at all; falling back to
        its own record keeps the index defined and says so loudly, because
        the thresholds are then not comparable across submissions.
        """
        first, last = get_threshold("tier2.extremes.base_period")
        inside = (years >= int(first)) & (years <= int(last))
        if inside.any():
            return inside
        logger.warning(
            f"Diagnostic '{self.name}': the daily record ({years.min()}-"
            f"{years.max()}) does not overlap the {int(first)}-{int(last)} "
            f"base period; using the whole record for the percentile "
            f"thresholds, which makes them submission-specific",
        )
        return np.ones(years.size, dtype=bool)

    def _index_fields(
        self,
        variable: Variable,
        values: np.ndarray,
        years: np.ndarray,
        months: np.ndarray,
    ) -> dict[str, tuple[np.ndarray, np.ndarray]]:
        """``{index: (years, field (n_years, lat, lon))}`` for one variable."""
        base = self._base_period_mask(years)
        fields: dict[str, tuple[np.ndarray, np.ndarray]] = {}
        for index in self._INDICES.get(variable.var_name, ()):
            if index == "txx":
                fields[index] = physics.annual_extreme(values, years, "max")
            elif index == "tnn":
                fields[index] = physics.annual_extreme(values, years, "min")
            elif index in ("tx90p", "wsdi"):
                threshold = physics.calendar_percentile(
                    values,
                    months,
                    base,
                    float(get_threshold("tier2.extremes.warm_day_percentile")),
                )
                if index == "tx90p":
                    fields[index] = physics.exceedance_fraction(
                        values,
                        years,
                        threshold,
                    )
                else:
                    warm = np.isfinite(values) & np.isfinite(threshold)
                    warm &= values > threshold
                    fields[index] = physics.spell_duration_days(
                        warm,
                        years,
                        int(get_threshold("tier2.extremes.wsdi_min_spell_days")),
                    )
            elif index in ("rx1day", "rx5day"):
                fields[index] = physics.annual_max_running_sum(
                    values,
                    years,
                    window=1 if index == "rx1day" else 5,
                )
            elif index == "r95ptot":
                threshold = physics.wet_day_percentile(
                    values,
                    base,
                    float(get_threshold("tier2.extremes.wet_day_percentile")),
                    wet_day_threshold=float(
                        get_threshold("tier2.extremes.wet_day_threshold"),
                    ),
                )
                fields[index] = physics.heavy_precipitation_fraction(
                    values,
                    years,
                    threshold,
                )
            elif index == "cdd":
                fields[index] = physics.max_consecutive_dry_days(
                    values,
                    years,
                    float(get_threshold("tier2.extremes.dry_day_threshold")),
                )
        return fields

    def _scalars(self, cube: Cube, variable: Variable) -> dict[str, float]:
        """Climatology and decadal trend of every index, per region."""
        if variable.var_name not in self._INDICES:
            msg = (
                f"Diagnostic '{self.name}': no ETCCDI index is defined for "
                f"'{variable.var_name}' (expected one of "
                f"{sorted(self._INDICES)})"
            )
            raise ValueError(msg)
        values = _filled(cube.data)
        years, months = _cube_years_months(cube)
        latitudes = cube.coord("latitude").points.astype(float)
        regions = get_threshold("tier2.extremes.regions")

        out: dict[str, float] = {}
        for index, (_index_years, field) in self._index_fields(
            variable,
            values,
            years,
            months,
        ).items():
            for region, bounds in regions.items():
                series = _regional_series(field, latitudes, tuple(bounds))
                climatology, trend = _climatology_and_trend(series)
                out[f"{index}_{region}_clim"] = climatology
                out[f"{index}_{region}_trend"] = trend
        return out


# ---------------------------------------------------------------------------
# Diurnal cycle: first harmonic in local solar time
# ---------------------------------------------------------------------------


class DiurnalHarmonic(ScalarTableDiagnostic):
    """First-harmonic amplitude and phase of the sub-daily climatology (§II.1).

    Per suite variable (hourly or 3-hourly ``pr``, and ``swcre``/``netcre``
    wherever a model supplies sub-daily TOA fluxes), per season in
    ``tier2.diurnal.seasons`` and per latitude band in
    ``tier2.diurnal.regions``:

    1. regrid to ClimateEval's common grid and convert the time axis to
       **local solar time** (``esmvalcore.preprocessor.local_solar_time``,
       which is the "shift each longitude column by lon/15 h" the protocol
       asks for — without it the tropics average to nearly no diurnal cycle
       at all);
    2. the season's mean cycle over the day
       (``climate_statistics(..., "hour")``), area-averaged over the band;
    3. :func:`climatebench2.physics.first_harmonic`, generalised to any
       number of points per day.

    Columns are ``<variable>_<region>_<season>_amplitude``,
    ``…_phase_cos`` and ``…_phase_sin``.

    ⚠ **Why (cos, sin) and not the phase itself.** Fair CRPS is a distance on
    the real line, so scoring the phase in hours would call 23 h and 1 h 22
    hours apart. CB2 therefore scores the two components of the unit vector
    ``(cos φ, sin φ)``, each an ordinary number, and emits no hour column at
    all — so nothing downstream can score the circular quantity by accident.
    The phase in hours is ``atan2(sin, cos)·n/2π mod n``. A CB2
    interpretation, recorded in docs/metrics_reference.md §II.1.

    The land/sea contrast that makes this diagnostic worth computing is a
    **mask**, so the suite declares it per variable (``landsea_mask:
    land_only`` / ``sea_only``) rather than the diagnostic applying one.
    """

    _final_coordinates = (Coordinate("time"), Coordinate("lat"), Coordinate("lon"))

    def _preprocess(self, cube: Cube, _variable: Variable) -> Cube:
        """Regrid, then move the time axis to local solar time."""
        with setup_esmvaltool_config_and_logging():
            cube = regrid(
                cube,
                str(get_threshold("tier2.diurnal.grid")),
                "linear",
                cache_weights=True,
            )
            cube = local_solar_time(cube)
        return cube  # noqa: RET504

    def _scalars(self, cube: Cube, variable: Variable) -> dict[str, float]:
        """Amplitude and phase components per season and region."""
        _years, months = _cube_years_months(cube)
        regions = get_threshold("tier2.diurnal.regions")
        out: dict[str, float] = {}
        for season in get_threshold("tier2.diurnal.seasons"):
            indices = _season_indices(months, str(season))
            if indices.size == 0:
                logger.warning(
                    f"Diagnostic '{self.name}': no {season} time steps in "
                    f"{variable.id}; no diurnal harmonic for that season",
                )
                continue
            with setup_esmvaltool_config_and_logging():
                cycle_cube = climate_statistics(cube[indices], "mean", "hour")
            data = _filled(cycle_cube.data)
            latitudes = cycle_cube.coord("latitude").points.astype(float)
            n_hours = data.shape[0]
            for region, bounds in regions.items():
                cycle = _regional_series(data, latitudes, tuple(bounds))
                amplitude, phase = physics.first_harmonic(cycle)
                cos, sin = physics.phase_components(phase, n_hours)
                prefix = f"{variable.id}_{region}_{str(season).lower()}"
                out[f"{prefix}_amplitude"] = amplitude
                out[f"{prefix}_phase_cos"] = cos
                out[f"{prefix}_phase_sin"] = sin
        return out


# ---------------------------------------------------------------------------
# Perkins skill score on daily PDFs
# ---------------------------------------------------------------------------


class PerkinsSkillScore(SimpleDiagnostic):
    """PDF-shape skill of daily temperature anomalies and rain intensity.

    The protocol's distributional statistic (§II.1): ``S = Σ min(f_m, f_o)``
    over **pre-registered** bins (``tier2.perkins.bins``), computed per
    season and reported per suite variable — which carries the region, since
    a latitude band and a land mask are ``Variable`` properties ClimateEval
    already applies.

    Two quantities, chosen by ``diagnostic_kwargs: {quantity: …}``:

    - ``tas_anomaly`` — daily ``tas`` minus its own **base-period monthly
      climatology**. ⚠ The paper says "anomalies relative to a *moving*
      climatological baseline"; CB2 uses the fixed
      ``tier2.extremes.base_period`` (1985-2014) climatology per calendar
      month as an explicit simplification, which keeps the baseline
      identical for every submission and avoids a window that would reach
      into the reserved test period. Recorded in metrics_reference.md §II.1.
    - ``pr_intensity`` — **wet days only** (``pr >= 1 mm/day``,
      ``tier2.perkins.wet_day_threshold``), un-anomalised.

    Output: **metrics only**, one ``perkins_<season>`` column per variable
    plus ``perkins_all`` for the pooled distribution; no raw-output table
    (the preprocessed field is the whole daily record). A skill score is not
    an error, so it never enters ``E_ref`` or ``S = 1 − E/E_ref`` — the
    leaderboard shows it in its own distribution-skill table, labelled
    *in-sample*.
    """

    _final_coordinates = (Coordinate("time"), Coordinate("lat"), Coordinate("lon"))
    _output_data_table: ClassVar[bool] = False

    #: The `diagnostic_kwargs["quantity"]` values this diagnostic understands.
    _QUANTITIES: ClassVar[tuple[str, ...]] = ("tas_anomaly", "pr_intensity")

    def _check_variables(self) -> None:
        """Every variable must name a pre-registered quantity and its bins."""
        for variable in self._variables:
            quantity = variable.diagnostic_kwargs.get("quantity")
            if quantity not in self._QUANTITIES:
                msg = (
                    f"Expected diagnostic keyword argument 'quantity' in "
                    f"{self._QUANTITIES} for {variable} (diagnostic "
                    f"'{self.name}'), got {quantity!r}"
                )
                raise ValueError(msg)

    @staticmethod
    def _bin_edges(quantity: str) -> np.ndarray:
        """The pre-registered bins of one quantity (``tier2.perkins.bins``)."""
        spec = get_threshold(f"tier2.perkins.bins.{quantity}")
        low, high = (float(v) for v in spec["range"])
        width = float(spec["width"])
        return np.arange(low, high + 0.5 * width, width)

    def _preprocess(self, cube: Cube, variable: Variable) -> Cube:
        """Conservative regrid, then the quantity whose PDF is compared."""
        with setup_esmvaltool_config_and_logging():
            cube = regrid(
                cube,
                str(get_threshold("tier2.extremes.grid")),
                str(get_threshold("tier2.extremes.regrid_scheme")),
                cache_weights=True,
            )
        return cube  # noqa: RET504

    def _values(self, cube: Cube, quantity: str) -> tuple[np.ndarray, np.ndarray]:
        """``(values, months)`` of the quantity whose PDF is scored."""
        data = _filled(cube.data)
        years, months = _cube_years_months(cube)
        if quantity == "pr_intensity":
            threshold = float(get_threshold("tier2.perkins.wet_day_threshold"))
            return np.where(data >= threshold, data, np.nan), months
        first, last = get_threshold("tier2.extremes.base_period")
        base = (years >= int(first)) & (years <= int(last))
        if not base.any():
            logger.warning(
                f"Diagnostic '{self.name}': the daily record does not reach "
                f"the {int(first)}-{int(last)} baseline; taking the anomaly "
                f"against its own record instead",
            )
            base = np.ones(years.size, dtype=bool)
        anomalies = data.astype(float).copy()
        for month in np.unique(months):
            step = months == month
            climatology = np.nanmean(data[step & base], axis=0)
            anomalies[step] = data[step] - climatology
        return anomalies, months

    def _histogram(self, values: np.ndarray, edges: np.ndarray) -> np.ndarray:
        """Normalised counts of the pooled (time, space) sample."""
        flat = values[np.isfinite(values)]
        if flat.size == 0:
            return np.full(edges.size - 1, np.nan)
        counts, _edges = np.histogram(flat, bins=edges)
        total = counts.sum()
        return counts / total if total else np.full(edges.size - 1, np.nan)

    def _perkins_metrics(
        self,
        cube: Cube,
        reference_cube: Cube,
        variable: Variable,
    ) -> dict[str, pd.Series]:
        """Perkins skill score per season, plus the pooled one."""
        quantity = str(variable.diagnostic_kwargs["quantity"])
        edges = self._bin_edges(quantity)
        model, model_months = self._values(cube, quantity)
        obs, obs_months = self._values(reference_cube, quantity)

        metrics: dict[str, pd.Series] = {}
        for season in get_threshold("tier2.perkins.seasons"):
            name = str(season)
            model_idx = _season_indices(model_months, name)
            obs_idx = _season_indices(obs_months, name)
            score = (
                float("nan")
                if model_idx.size == 0 or obs_idx.size == 0
                else scoring.perkins_skill_score(
                    self._histogram(model[model_idx], edges),
                    self._histogram(obs[obs_idx], edges),
                )
            )
            metrics[f"perkins_{name.lower()}"] = pd.Series(score, dtype=self._dtype)
        metrics["perkins_all"] = pd.Series(
            scoring.perkins_skill_score(
                self._histogram(model, edges),
                self._histogram(obs, edges),
            ),
            dtype=self._dtype,
        )
        return metrics

    def _get_metrics_table(
        self,
        cube: Cube,
        reference_cube: Cube,
        *,
        variable: Variable,
        data_id: str,
    ) -> Any:  # noqa: ANN401 - ibis.Table, as upstream
        """One metrics row of Perkins scores for this (source, variable).

        Overridden rather than ``_get_metrics`` because the bins and the
        quantity are properties of the *variable*, which ClimateEval's
        ``_get_metrics(cube, reference_cube)`` signature does not carry —
        and two variables of this diagnostic may share a ``var_name`` (the
        same field over different regions), so the cube alone cannot
        identify one. The deterministic ``weighted_*`` metrics are dropped
        with it: an RMSE between two daily records is not a distributional
        statement.
        """
        return ibis.memtable(
            pd.DataFrame(
                {
                    self._data_id_column: data_id,
                    self._reference_data_id_column: self._reference_data[variable].id,
                    self._variable_id_column: variable.id,
                    **self._perkins_metrics(cube, reference_cube, variable),
                },
                index=[0],
            ),
        )
