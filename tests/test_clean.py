"""Tests for clean.py."""

from datetime import date

import pytest

from clean import clean, filter_to_dates


def test_renames_and_converts_types():
    rows = [{"Begin_Datetime_UTC": "2026-01-15 07:00", "Pool_Price": "45.50", "extra": "x"}]
    df = clean(rows)
    assert list(df.columns) == [
        "timestamp_utc", "timestamp_mpt", "pool_price", "forecast_pool_price", "rolling_30day_avg"
    ]
    assert df.loc[0, "pool_price"] == 45.5
    # 07:00 UTC is midnight in Alberta in January (MST = UTC-7)
    assert df.loc[0, "timestamp_mpt"].hour == 0


def test_drops_clearly_bad_rows():
    rows = [
        {"begin_datetime_utc": "2026-01-15 07:00", "pool_price": "45.50"},
        {"begin_datetime_utc": "not a date", "pool_price": "30"},
        {"begin_datetime_utc": "2026-01-15 09:00", "pool_price": "abc"},
        {"begin_datetime_utc": "2026-01-15 10:00", "pool_price": None},
    ]
    assert len(clean(rows)) == 1


def test_missing_required_column_gives_clear_error():
    with pytest.raises(ValueError, match="COLUMN_MAP"):
        clean([{"some_other_time": "2026-01-15 07:00", "pool_price": "1"}])


def test_filter_keeps_only_requested_alberta_day():
    rows = [
        {"begin_datetime_utc": "2026-01-15 06:00", "pool_price": "1"},  # 11pm Jan 14 in Alberta
        {"begin_datetime_utc": "2026-01-15 07:00", "pool_price": "1"},  # midnight Jan 15
        {"begin_datetime_utc": "2026-01-16 06:00", "pool_price": "1"},  # 11pm Jan 15
        {"begin_datetime_utc": "2026-01-16 07:00", "pool_price": "1"},  # midnight Jan 16
    ]
    df = filter_to_dates(clean(rows), date(2026, 1, 15), date(2026, 1, 15))
    assert len(df) == 2
