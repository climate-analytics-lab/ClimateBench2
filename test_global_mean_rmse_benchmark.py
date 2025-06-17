import numpy as np
import pandas as pd
import pytest
import xarray as xr

from global_mean_rmse_benchmark import global_mean_rmse, standardize_dims


@pytest.fixture
def base_dataset():
    time = pd.date_range("2000-01-01", periods=3, freq="MS") + pd.Timedelta(days=15)
    lat = np.array([60, 0, -60])
    lon = np.array(
        [
            -120,
            60,
            180,
        ]
    )
    data = np.array(
        [
            # t=0
            [
                # -120, 60, 180
                [11, 12, 13],  # 60
                [21, 22, 23],  # 0
                [31, 32, 33],  # -60
            ],
            # t=1
            [
                [14, 15, 16],
                [24, 25, 26],
                [34, 35, 36],
            ],
            # t=2
            [
                [17, 18, 19],
                [27, 28, 29],
                [37, 38, 39],
            ],
        ]
    )

    return xr.Dataset(
        {"tas": (("datetime", "latitude", "longitude"), data)},
        coords={"datetime": time, "latitude": lat, "longitude": lon},
    )


def test_rename_dimensions(base_dataset):
    ds_out = standardize_dims(base_dataset)
    assert "lat" in ds_out.dims
    assert "lon" in ds_out.dims
    assert "time" in ds_out.dims
    assert "latitude" not in ds_out.dims
    assert "longitude" not in ds_out.dims
    assert "datetime" not in ds_out.dims


def test_time_standardization(base_dataset):
    ds_out = standardize_dims(base_dataset)
    expected_times = pd.date_range("2000-01-01", periods=3, freq="MS")
    np.testing.assert_array_equal(ds_out.time.values, expected_times)


def test_coordinate_sorting(base_dataset):
    ds_out = standardize_dims(base_dataset)
    # Check longitude reorder
    expected_lons = np.array([60, 180, 300])
    np.testing.assert_array_equal(ds_out.lon.values, expected_lons)
    # Check latitude reorder
    expected_lats = np.array([-60, 0, 60])
    np.testing.assert_array_equal(ds_out.lat.values, expected_lats)
    # check that data was correctly reordered
    expected_data = np.array(
        [
            # t=0
            [
                [32, 33, 31],
                [22, 23, 21],
                [12, 13, 11],
            ],
            # t=1
            [
                [35, 36, 34],
                [25, 26, 24],
                [15, 16, 14],
            ],
            # t=2
            [
                [38, 39, 37],
                [28, 29, 27],
                [18, 19, 17],
            ],
        ]
    )
    np.testing.assert_array_equal(ds_out.tas.values, expected_data)


def test_coordinate_resolution_assignment(base_dataset):
    ds_out = standardize_dims(base_dataset)
    lat = ds_out.lat.values
    lon = ds_out.lon.values
    assert np.allclose(np.diff(lat), lat[1] - lat[0])
    assert np.allclose(np.diff(lon), lon[1] - lon[0])
    assert lat[0] > -90 and lat[-1] < 90
    assert lon[0] >= 0 and lon[-1] < 360


@pytest.fixture
def sample_dataarrays():
    times = pd.date_range("2000-01-01", periods=12, freq="MS")
    lat = [0, 1]
    lon = [10, 20]

    shape = (12, 2, 2)
    model_data = np.ones(shape) * 3
    obs_data = np.ones(shape) * 2

    model_da = xr.DataArray(
        model_data,
        coords={"time": times, "lat": lat, "lon": lon},
        dims=["time", "lat", "lon"],
    )

    obs_da = xr.DataArray(
        obs_data,
        coords={"time": times, "lat": lat, "lon": lon},
        dims=["time", "lat", "lon"],
    )

    weights_da = xr.DataArray(
        np.ones((2, 2)), coords={"lat": lat, "lon": lon}, dims=["lat", "lon"]
    )

    return model_da, obs_da, weights_da


def test_regular_rmse(sample_dataarrays):
    model, obs, weights = sample_dataarrays
    result = global_mean_rmse(
        model_da=model,
        obs_da=obs,
        weights_da=weights,
        time_slice=slice("2000-01", "2000-12"),
    )
    assert np.isclose(result, 1.0)


def test_bias_adjusted_rmse(sample_dataarrays):
    model, obs, weights = sample_dataarrays
    result = global_mean_rmse(
        model_da=model,
        obs_da=obs,
        weights_da=weights,
        time_slice=slice("2000-01", "2000-12"),
        metric="bias_adjusted",
    )
    assert np.isclose(result, 0.0)


def test_anomaly_rmse(sample_dataarrays):
    model, obs, weights = sample_dataarrays
    result = global_mean_rmse(
        model_da=model,
        obs_da=obs,
        weights_da=weights,
        time_slice=slice("2000-01", "2000-12"),
        metric="anomaly",
    )
    assert np.isclose(result, 0)


def test_weighted_rmse_with_nonuniform_weights():
    times = pd.date_range("2000-01-01", periods=2, freq="MS")
    lat = [0, 1]
    lon = [10, 20]

    # Shape: (time, lat, lon)
    model_vals = np.array([[[3, 5], [7, 9]], [[4, 6], [8, 10]]])  # t=0  # t=1
    obs_vals = np.array([[[1, 2], [3, 4]], [[2, 3], [4, 5]]])

    # Weight lat=0 lower, lat=1 higher
    weights_vals = np.array([[1, 1], [3, 3]])  # lat=0  # lat=1  # shape (lat, lon)

    model_da = xr.DataArray(
        model_vals,
        coords={"time": times, "lat": lat, "lon": lon},
        dims=["time", "lat", "lon"],
    )

    obs_da = xr.DataArray(
        obs_vals,
        coords={"time": times, "lat": lat, "lon": lon},
        dims=["time", "lat", "lon"],
    )

    weights_da = xr.DataArray(
        weights_vals, coords={"lat": lat, "lon": lon}, dims=["lat", "lon"]
    )

    # Expected weighted means (manual calc):
    # time 0:
    #   model: (3+5)*1 + (7+9)*3 = 8*1 + 16*3 = 8 + 48 = 56 → / total weight 8 = 7.0
    #   obs:   (1+2)*1 + (3+4)*3 = 3*1 + 7*3 = 3 + 21 = 24 → / 8 = 3.0
    # time 1:
    #   model: (4+6)*1 + (8+10)*3 = 10 + 54 = 64 → / 8 = 8.0
    #   obs:   (2+3)*1 + (4+5)*3 = 5 + 27 = 32 → / 8 = 4.0

    # So model_mean = [7.0, 8.0], obs_mean = [3.0, 4.0] → diff = [4.0, 4.0]
    # RMSE = sqrt(mean([16, 16])) = sqrt(16) = 4.0

    result = global_mean_rmse(
        model_da=model_da,
        obs_da=obs_da,
        weights_da=weights_da,
        time_slice=slice("2000-01", "2000-02"),
    )
    assert np.isclose(result, 4.0)


# will want to add a test for the full pipeline -- could mock some local files to avoid GCS or ESGF
