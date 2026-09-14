"""Tests for the Tier II aggregated scalar diagnostics (§II.1).

``RealizedWarmingLevel``, ``PinatuboResponseGate`` and
``HemisphericAsymmetryGate`` all run on synthetic cubes with the HadCRUT5
fetch monkeypatched, so nothing is downloaded: the point under test is the
statistic, the GSAT blending correction and the ``reference`` rows the
scoring pass needs in order to score them at all.
"""

from __future__ import annotations

import numpy as np
import pytest

climateeval = pytest.importorskip("climateeval")

from cf_units import Unit  # noqa: E402
from iris.coords import DimCoord  # noqa: E402
from iris.cube import Cube, CubeList  # noqa: E402

from climateeval.data import DataSourceInformation  # noqa: E402

from climatebench2 import windows  # noqa: E402
from climatebench2._thresholds import get_threshold  # noqa: E402
from climatebench2.diags.tier2_diagnostics import (  # noqa: E402
    HemisphericAsymmetryGate,
    PinatuboResponseGate,
    RealizedWarmingLevel,
    blended_to_sat,
    blending_factor,
)
from climatebench2.scoring_pass import (  # noqa: E402
    SCALAR_SIGMA_OBS_SUFFIX,
    is_scalar_output,
    score_scalar_output,
)

FIRST_YEAR = 1980
LAST_YEAR = windows.last_complete_year()
N_YEARS = LAST_YEAR - FIRST_YEAR + 1
YEARS = np.arange(FIRST_YEAR, LAST_YEAR + 1)


def _monthly_tas(
    annual: np.ndarray,
    *,
    var_name: str = "tas",
    units: str = "K",
    hemispheric_offset: np.ndarray | None = None,
) -> Cube:
    """A (time, lat, lon) monthly cube whose annual global mean is ``annual``.

    ``hemispheric_offset`` (one value per year) is *added* in the northern
    hemisphere and subtracted in the southern one, leaving the global mean
    untouched — which is how the aerosol-era NH−SH asymmetry is built.
    """
    n_lat, n_lon = 18, 36
    n_time = annual.size * 12
    time = DimCoord(
        np.arange(n_time, dtype=float) * 30.0 + 15.0 + (FIRST_YEAR - 1850) * 360.0,
        standard_name="time",
        units=Unit("days since 1850-01-01", calendar="360_day"),
    )
    lat = DimCoord(
        np.linspace(-85.0, 85.0, n_lat),
        standard_name="latitude",
        units="degrees",
    )
    lon = DimCoord(
        np.linspace(5.0, 355.0, n_lon),
        standard_name="longitude",
        units="degrees",
        circular=True,
    )
    for coord in (time, lat, lon):
        coord.guess_bounds()
    monthly = np.repeat(np.asarray(annual, dtype=float), 12)
    data = np.broadcast_to(monthly[:, None, None], (n_time, n_lat, n_lon)).copy()
    if hemispheric_offset is not None:
        offset = np.repeat(np.asarray(hemispheric_offset, dtype=float), 12)
        sign = np.where(lat.points >= 0.0, 1.0, -1.0)
        data = data + offset[:, None, None] * sign[None, :, None]
    return Cube(
        data.astype(np.float32),
        var_name=var_name,
        units=units,
        dim_coords_and_dims=[(time, 0), (lat, 1), (lon, 2)],
    )


def _linear_warming(rate_per_year: float = 0.02, base: float = 287.0) -> np.ndarray:
    """A clean linear GMST record, so every statistic is analytic."""
    return base + rate_per_year * (YEARS - FIRST_YEAR)


def _info(variant: str = "r1i1p1f1") -> DataSourceInformation:
    return DataSourceInformation(
        name="SynthModel",
        category="model",
        exp="historical",
        variant=variant,
    )


def _run(diag_class, cubes: CubeList, *, observed: Cube | None, variant="r1i1p1f1"):  # noqa: ANN001, ANN202
    """Run one event diagnostic with the HadCRUT5 fetch stubbed out."""
    diag = diag_class(diag_class.__name__.lower(), fail_on_missing_data=False)
    if observed is None:

        def _missing(_self):  # noqa: ANN001, ANN202
            msg = "no HadCRUT5 here"
            raise FileNotFoundError(msg)

        diag._observation_record = _missing.__get__(diag)
    else:
        diag._observation_record = (lambda _self: observed).__get__(diag)
    return diag.get_output({"historical": cubes}, _info(variant))


def _raw(output) -> "object":  # noqa: ANN001
    return output.raw_output.to_pandas()


def _value(frame, data_type: str, column: str) -> float:  # noqa: ANN001
    series = frame[frame["data_type"] == data_type][column].dropna()
    return float(series.iloc[0]) if not series.empty else float("nan")


# ---------------------------------------------------------------------------
# The blending correction
# ---------------------------------------------------------------------------


def test_blending_correction_scales_the_anomaly_and_reports_its_sigma() -> None:
    factor = blending_factor()
    relative = float(get_threshold("tier2.gsat_blending_relative_uncertainty"))
    assert factor > 1.0  # SAT warms faster than a blended product
    corrected, sigma = blended_to_sat(0.5)
    assert corrected == pytest.approx(0.5 * factor)
    assert sigma == pytest.approx(abs(corrected) * relative)
    # The sign convention: a cooling anomaly is amplified, not flipped
    cooled, cool_sigma = blended_to_sat(-0.4)
    assert cooled == pytest.approx(-0.4 * factor)
    assert cool_sigma > 0.0


# ---------------------------------------------------------------------------
# Realized warming level
# ---------------------------------------------------------------------------


def test_warming_level_statistics_are_the_paper_definitions() -> None:
    """Mean 2015+ minus the 1985-2014 mean; trends in K/decade."""
    diag = RealizedWarmingLevel.__new__(RealizedWarmingLevel)
    diag._name = "realized_warming_level"
    values = _linear_warming(0.02)
    scalars = diag._scalars(values, YEARS)

    base_first, base_last = windows.baseline_window_years()
    test_first = int(get_threshold("tier2.test_window_start"))
    baseline = values[(YEARS >= base_first) & (YEARS <= base_last)].mean()
    level = values[YEARS >= test_first].mean() - baseline

    assert scalars["gmst_warming_level"] == pytest.approx(level)
    assert scalars["gmst_trend_test_window"] == pytest.approx(0.2)  # K/decade
    assert scalars["gmst_trend_1950"] == pytest.approx(0.2)
    assert scalars["warming_level_first_year"] == test_first
    assert scalars["warming_level_last_year"] == LAST_YEAR
    # The record starts in 1980, so the "1950" trend says which window it used
    assert scalars["long_trend_first_year"] == FIRST_YEAR


def test_a_record_ending_before_the_test_window_has_no_warming_level() -> None:
    """A plain CMIP6 historical run stops in 2014."""
    diag = RealizedWarmingLevel.__new__(RealizedWarmingLevel)
    diag._name = "realized_warming_level"
    years = np.arange(FIRST_YEAR, 2015)
    values = 287.0 + 0.02 * (years - FIRST_YEAR)
    scalars = diag._scalars(values, years)
    assert "gmst_warming_level" not in scalars
    assert "gmst_trend_test_window" not in scalars
    assert scalars["gmst_trend_1950"] == pytest.approx(0.2)


def test_warming_level_emits_model_and_blended_reference_rows() -> None:
    model = _linear_warming(0.02)
    # The "observations" warm more slowly, and are on a BLENDED basis
    observed = _linear_warming(0.015)
    output = _run(
        RealizedWarmingLevel,
        CubeList([_monthly_tas(model)]),
        observed=_monthly_tas(observed),
    )
    frame = _raw(output)
    assert is_scalar_output(frame)

    base_first, base_last = windows.baseline_window_years()
    test_first = int(get_threshold("tier2.test_window_start"))
    inside = (YEARS >= base_first) & (YEARS <= base_last)
    expected_obs = (
        observed[YEARS >= test_first].mean() - observed[inside].mean()
    ) * blending_factor()

    assert _value(frame, "to_benchmark", "gmst_warming_level") == pytest.approx(
        model[YEARS >= test_first].mean() - model[inside].mean(),
        rel=1e-3,
    )
    assert _value(frame, "reference", "gmst_warming_level") == pytest.approx(
        expected_obs,
        rel=1e-3,
    )
    # ... with the blending uncertainty attached as the sigma_obs companion
    sigma = _value(
        frame,
        "reference",
        f"gmst_warming_level{SCALAR_SIGMA_OBS_SUFFIX}",
    )
    assert sigma == pytest.approx(
        abs(expected_obs) * float(get_threshold("tier2.gsat_blending_relative_uncertainty")),
        rel=1e-3,
    )
    # Provenance columns stay model-side (the pass never scores them)
    assert np.isnan(_value(frame, "reference", "warming_level_first_year"))

    # The reference is recorded as an observation, so the pass never ranks it
    sources = output.data_sources.to_pandas()
    hadcrut = sources[sources["name"] == "HadCRUT5"].iloc[0]
    assert hadcrut["category"] == "observation"


def test_warming_level_degrades_to_model_only_without_observations() -> None:
    output = _run(
        RealizedWarmingLevel,
        CubeList([_monthly_tas(_linear_warming())]),
        observed=None,
    )
    frame = _raw(output)
    assert "reference" not in set(frame["data_type"])
    assert np.isfinite(_value(frame, "to_benchmark", "gmst_warming_level"))
    # ... and the pass then simply has nothing to score
    assert score_scalar_output(frame, None) == []


def test_the_pass_scores_the_warming_level_across_members() -> None:
    """Two members of one model make a fair-CRPS ensemble of one scalar."""
    import pandas as pd

    frames, sources = [], []
    observed = _monthly_tas(_linear_warming(0.015))
    for variant, rate in (("r1i1p1f1", 0.020), ("r2i1p1f1", 0.022)):
        output = _run(
            RealizedWarmingLevel,
            CubeList([_monthly_tas(_linear_warming(rate))]),
            observed=observed,
            variant=variant,
        )
        frames.append(_raw(output))
        sources.append(output.data_sources.to_pandas())
    raw = pd.concat(frames, ignore_index=True)
    data_sources = pd.concat(sources, ignore_index=True).drop_duplicates()

    rows = pd.DataFrame(
        score_scalar_output(raw, data_sources, diagnostic="realized_warming_level"),
    )
    scored = rows[
        (rows["var_id"] == "gmst_warming_level")
        & (rows["data_type"] == "to_benchmark")
    ].iloc[0]
    assert scored["data_id"] == "SynthModel"
    assert scored["n_members"] == 2  # the two members, one ensemble
    assert scored["crps"] > 0
    assert scored["sigma_obs"] > 0  # the blending term reached the draws
    assert scored["window"] == "held-out"
    # ... and the consistency statement the paper asks for alongside
    consistency = rows[rows["var_id"] == "gmst_warming_level_consistency"].iloc[0]
    assert consistency["p_value"] >= 0.0
    assert consistency["window"] == "held-out"
    # The 1950 trend is the in-sample one
    long_trend = rows[rows["var_id"] == "gmst_trend_1950"].iloc[0]
    assert long_trend["window"] == "in-sample"


# ---------------------------------------------------------------------------
# Pinatubo
# ---------------------------------------------------------------------------


def _pinatubo_series(cooling: float = -0.4) -> np.ndarray:
    """A flat record with a cooling dip over 1991-1993."""
    values = np.full(N_YEARS, 287.0)
    dip = (YEARS >= 1991) & (YEARS <= 1993)
    values[dip] += cooling
    return values


def test_pinatubo_emits_a_scored_tas_anomaly_and_a_model_only_rsds_flag() -> None:
    tas = _monthly_tas(_pinatubo_series(-0.4))
    rsds = _monthly_tas(_pinatubo_series(-2.0) - 287.0 + 180.0, var_name="rsds")
    rsds.units = "W m-2"
    output = _run(
        PinatuboResponseGate,
        CubeList([tas, rsds]),
        observed=_monthly_tas(_pinatubo_series(-0.3)),
    )
    frame = _raw(output)

    # The dip years sit inside the 1985-2014 baseline, so the anomaly is the
    # cooling less its own contribution to the climatology (3 of 30 years).
    def _expected(cooling: float) -> float:
        return cooling - cooling * 3.0 / 30.0

    assert _value(frame, "to_benchmark", "pinatubo_tas_anom") == pytest.approx(
        _expected(-0.4),
        rel=0.02,
    )
    assert _value(frame, "to_benchmark", "pinatubo_rsds_anom") < 0
    # HadCRUT5 gives the observed cooling, corrected to a SAT basis ...
    observed = _value(frame, "reference", "pinatubo_tas_anom")
    assert observed == pytest.approx(_expected(-0.3) * blending_factor(), rel=0.02)
    assert _value(frame, "reference", f"pinatubo_tas_anom{SCALAR_SIGMA_OBS_SUFFIX}") > 0
    # ... and rsds has no observational product at all (no BSRN DataSource)
    assert np.isnan(_value(frame, "reference", "pinatubo_rsds_anom"))

    # The sign flags survive as `diagnostic`-tagged gate rows
    metrics = output.metrics.to_pandas()
    assert {"pinatubo_dimming", "pinatubo_cooling"} <= set(metrics["var_id"])
    assert set(metrics["requirement"]) == {"diagnostic"}


# ---------------------------------------------------------------------------
# Hemispheric asymmetry
# ---------------------------------------------------------------------------


def test_hemispheric_asymmetry_emits_a_scored_nh_minus_sh_trend() -> None:
    era_first, era_last = get_threshold("tier2.hemispheric_asymmetry.era")
    # NH cools relative to SH through the aerosol era at -0.01 K/yr
    offset = np.where(
        (YEARS >= era_first) & (YEARS <= era_last),
        -0.005 * (YEARS - era_first),
        0.0,
    )
    tas = _monthly_tas(np.full(N_YEARS, 287.0), hemispheric_offset=offset)
    pr = _monthly_tas(np.full(N_YEARS, 3e-5), var_name="pr", units="kg m-2 s-1")
    observed_offset = 0.6 * offset
    output = _run(
        HemisphericAsymmetryGate,
        CubeList([tas, pr]),
        observed=_monthly_tas(
            np.full(N_YEARS, 287.0),
            hemispheric_offset=observed_offset,
        ),
    )
    frame = _raw(output)

    modelled = _value(frame, "to_benchmark", "nh_minus_sh_trend")
    observed = _value(frame, "reference", "nh_minus_sh_trend")
    assert modelled < 0  # NH warming suppressed
    assert observed < 0
    # The observation is 60% of the model's asymmetry, times the SAT factor
    assert observed == pytest.approx(0.6 * modelled * blending_factor(), rel=0.05)
    assert _value(frame, "reference", f"nh_minus_sh_trend{SCALAR_SIGMA_OBS_SUFFIX}") > 0
    # The ITCZ shift has no pre-1979 observational product
    assert np.isnan(_value(frame, "reference", "itcz_shift_deg_per_decade"))
