"""The protocol's time windows, derived from ``thresholds.yml``.

One place resolves every window the protocol names, so the CLI (which cuts
the submission's cubes), the reference-window diagnostics (which reach *back*
past that cut for the pre-2015 record) and the scoring pass (which chunks a
control into observation-length segments) cannot drift apart:

- **test window** — ``tier2.test_window_start`` → the last complete year; the
  reserved post-2015 period every Tier II score is taken over. It grows by a
  year every January without a code change.
- **baseline window** — ``tier2.climatology_baseline_period`` = 1985–2014;
  the pre-test record. It is the Climatology baseline's sample, the Pinatubo
  reference climatology, and the reference's PRE-2015 record for the
  regime-(b) EOF basis and its standardisation.
- **long trend window** — ``tier2.long_trend_start`` → the last complete
  year; the "1950-present" window of §II.1, the second length the
  internal-variability diagnostic reports σ_int for.

Timeranges are ISO-like ``YYYYMMDD/YYYYMMDD`` strings, the form ClimateEval
puts on ``Variable.timerange`` and hands to ``DataSource.get_cube``.
"""

from __future__ import annotations

import datetime as dt

from climatebench2._thresholds import get_threshold


def last_complete_year(today: dt.date | None = None) -> int:
    """The last year that has finished (the protocol scores whole years)."""
    return (today or dt.date.today()).year - 1


def timerange(first_year: int, last_year: int) -> str:
    """``YYYY0101/YYYY1231`` for a whole-year window."""
    return f"{int(first_year)}0101/{int(last_year)}1231"


def test_window_years(today: dt.date | None = None) -> tuple[int, int]:
    """``(first, last)`` year of the reserved post-2015 test window."""
    start = int(get_threshold("tier2.test_window_start"))
    return (start, max(last_complete_year(today), start))


def test_window_timerange(today: dt.date | None = None) -> str:
    """ISO timerange of the reserved test window."""
    return timerange(*test_window_years(today))


def baseline_window_years() -> tuple[int, int]:
    """``(first, last)`` year of the pre-test 1985–2014 baseline window."""
    first, last = get_threshold("tier2.climatology_baseline_period")
    return (int(first), int(last))


def baseline_timerange() -> str:
    """ISO timerange of the pre-test baseline window."""
    return timerange(*baseline_window_years())


def long_trend_window_years(today: dt.date | None = None) -> tuple[int, int]:
    """``(first, last)`` year of the "1950-present" trend window (§II.1)."""
    start = int(get_threshold("tier2.long_trend_start"))
    return (start, max(last_complete_year(today), start))


def window_lengths(today: dt.date | None = None) -> dict[str, int]:
    """Length in whole years of every window σ_int is reported for.

    ``{"test": …, "long": …}`` — the keys the internal-variability
    diagnostic tags its output columns with.
    """
    test_first, test_last = test_window_years(today)
    long_first, long_last = long_trend_window_years(today)
    return {
        "test": test_last - test_first + 1,
        "long": long_last - long_first + 1,
    }
