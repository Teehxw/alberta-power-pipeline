"""Shared helpers for the tests: build fake but well-formed data."""

import pandas as pd

from checks import expected_hours
from clean import LOCAL_TZ


def make_clean_df(start, end, price=50.0):
    """A 'perfect' cleaned table: one row per expected hour, all at the same price."""
    hours = expected_hours(start, end)
    return pd.DataFrame({
        "timestamp_utc": hours,
        "timestamp_mpt": hours.tz_convert(LOCAL_TZ),
        "pool_price": price,
        "forecast_pool_price": price,
        "rolling_30day_avg": price,
    })


def make_raw_rows(start, end, price="50.00"):
    """Raw rows shaped like we *guess* the API returns them (see COLUMN_MAP in clean.py)."""
    return [
        {"begin_datetime_utc": ts.strftime("%Y-%m-%d %H:%M"), "pool_price": price}
        for ts in expected_hours(start, end)
    ]
