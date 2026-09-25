"""Masked (all-NaN) grid points stay NaN in the windowed / run-length ETCCDI indices."""
import numpy as np

from climatebench2 import physics


def _daily(seed=0):
    rng = np.random.default_rng(seed)
    x = rng.gamma(0.5, 4.0, size=(730, 2, 2))
    x[:, 0, 0] = np.nan  # an ocean point under a land-only mask
    years = np.repeat([2001, 2002], 365)
    return x, years


def test_rx5day_is_nan_on_a_masked_point_and_exceeds_rx1day_elsewhere():
    x, years = _daily()
    _, rx1 = physics.annual_max_running_sum(x, years, window=1)
    _, rx5 = physics.annual_max_running_sum(x, years, window=5)
    assert np.isnan(rx5[:, 0, 0]).all()
    assert np.isnan(rx1[:, 0, 0]).all()
    valid = np.isfinite(rx1)
    assert (rx5[valid] >= rx1[valid]).all()


def test_cdd_is_nan_on_a_masked_point():
    x, years = _daily(1)
    _, cdd = physics.max_consecutive_dry_days(x, years)
    assert np.isnan(cdd[:, 0, 0]).all()
    assert np.isfinite(cdd[:, 1, 1]).all()
