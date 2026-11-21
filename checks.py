"""
checks.py - Stage 3: data-quality checks.

Runs a set of checks on the cleaned table and returns a report (a dict):
  - passed:  True only if every check passed
  - checks:  one entry per check with its name, pass/fail and a short detail
  - spikes:  unusually high-price hours. These are FLAGGED, not deleted, and they
             don't fail the run, because real price spikes do happen in Alberta.
"""

import logging

import pandas as pd

from clean import day_window_utc

log = logging.getLogger(__name__)

# Alberta's pool price has historically had a floor of $0/MWh and a cap of
# $999.99/MWh. TODO: confirm these are still current before relying on them.
PRICE_MIN = 0.0
PRICE_MAX = 999.99

# Our own choice: any hour at or above this price is reported as a spike.
SPIKE_THRESHOLD = 500.0

MAX_EXAMPLES = 5  # how many example timestamps to show in a failure message


def expected_hours(start, end):
    """Every hourly UTC timestamp we expect for the Alberta dates start..end.

    Usually 24 per day, but 23 on the spring daylight-saving day and 25 in the fall.
    """
    start_utc, end_utc = day_window_utc(start, end)
    return pd.date_range(start_utc, end_utc, freq="h", inclusive="left")


def _examples(timestamps):
    """Format a few timestamps for a readable message."""
    shown = [str(t) for t in list(timestamps)[:MAX_EXAMPLES]]
    more = len(timestamps) - len(shown)
    return ", ".join(shown) + (f" (+{more} more)" if more > 0 else "")


def run_checks(df, start, end):
    """Run every check and return the report dict."""
    expected = expected_hours(start, end)
    timestamps = pd.DatetimeIndex(df["timestamp_utc"])
    checks = []

    def add(name, passed, detail):
        checks.append({"name": name, "passed": bool(passed), "detail": detail})

    # 1. No duplicate timestamps (each hour should appear once).
    dupes = timestamps[timestamps.duplicated()].unique()
    add("no_duplicate_timestamps", len(dupes) == 0,
        "OK" if len(dupes) == 0 else f"{len(dupes)} duplicated: {_examples(dupes)}")

    # 2. No missing hours (every expected hour is present).
    missing = expected.difference(timestamps)
    add("no_missing_hours", len(missing) == 0,
        "OK" if len(missing) == 0 else f"{len(missing)} missing (UTC): {_examples(missing)}")

    # 3. Prices inside the allowed range.
    bad = df[(df["pool_price"] < PRICE_MIN) | (df["pool_price"] > PRICE_MAX)]
    add("prices_in_range", bad.empty,
        "OK" if bad.empty
        else f"{len(bad)} prices outside {PRICE_MIN}-{PRICE_MAX}: {_examples(bad['timestamp_utc'])}")

    # 4. Row count equals the number of hours we expected.
    add("row_count_matches", len(df) == len(expected),
        f"expected {len(expected)}, got {len(df)}")

    # Spikes: reported, never deleted, never a failure.
    spike_rows = df[df["pool_price"] >= SPIKE_THRESHOLD]
    spikes = [
        {"timestamp_mpt": str(row.timestamp_mpt), "pool_price": float(row.pool_price)}
        for row in spike_rows.itertuples()
    ]

    report = {
        "start": str(start),
        "end": str(end),
        "rows": len(df),
        "passed": all(c["passed"] for c in checks),
        "checks": checks,
        "spike_threshold": SPIKE_THRESHOLD,
        "spikes": spikes,
    }
    return report
