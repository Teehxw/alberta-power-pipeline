"""
clean.py - Stage 2: turn the raw rows into a tidy table.

What it does:
  1. Standardizes column names (lowercase, underscores) and renames AESO's
     names to ours.
  2. Converts text to proper types: timestamps become real datetimes (in UTC),
     prices become numbers.
  3. Drops rows that are clearly broken (no usable timestamp or price).
  4. Adds an Alberta local-time column, worked out from UTC.

Note: duplicates and missing hours are NOT fixed here. checks.py is meant to
catch them, so we don't hide problems by quietly "fixing" them.
"""

import logging

import pandas as pd

log = logging.getLogger(__name__)

LOCAL_TZ = "America/Edmonton"  # Alberta time (MST/MDT, changes for daylight saving)

# TODO: confirm the raw field names from a real API response.
# Left side = the name in AESO's JSON (after lowercasing). Right side = our name.
COLUMN_MAP = {
    "begin_datetime_utc": "timestamp_utc",
    "pool_price": "pool_price",
    "forecast_pool_price": "forecast_pool_price",
    "rolling_30day_avg": "rolling_30day_avg",
}

REQUIRED = ["timestamp_utc", "pool_price"]               # rows can't be used without these
OPTIONAL = ["forecast_pool_price", "rolling_30day_avg"]  # kept if present
OUTPUT_COLUMNS = ["timestamp_utc", "timestamp_mpt", "pool_price", *OPTIONAL]


def clean(rows):
    """Clean a list of raw row dicts and return a pandas DataFrame."""
    df = pd.DataFrame(rows)
    log.info("Cleaning %d raw rows", len(df))
    if df.empty:
        # Keep going with empty columns, so the checks can report "no data" clearly.
        df = pd.DataFrame(columns=REQUIRED)

    # 1. Standardize column names, then map AESO's names to ours.
    df.columns = [str(c).strip().lower().replace(" ", "_") for c in df.columns]
    df = df.rename(columns=COLUMN_MAP)

    missing = [c for c in REQUIRED if c not in df.columns]
    if missing:
        raise ValueError(
            f"Columns {missing} not found after renaming. Columns received: "
            f"{list(df.columns)}. Update COLUMN_MAP in clean.py."
        )
    for col in OPTIONAL:
        if col not in df.columns:
            df[col] = pd.NA

    # 2. Fix types. errors="coerce" turns anything unparseable into NaT/NaN
    #    instead of crashing, so we can drop those rows in step 3.
    #    utc=True means: treat times as UTC (and convert any that carry an offset).
    df["timestamp_utc"] = pd.to_datetime(df["timestamp_utc"], utc=True, errors="coerce")
    for col in ["pool_price", *OPTIONAL]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # 3. Drop clearly bad rows: no usable timestamp or no usable price.
    before = len(df)
    df = df.dropna(subset=REQUIRED)
    dropped = before - len(df)
    if dropped:
        log.warning("Dropped %d rows with a missing or unreadable timestamp/price", dropped)

    # 4. Local Alberta time, worked out from UTC so daylight saving is handled for us.
    df["timestamp_mpt"] = df["timestamp_utc"].dt.tz_convert(LOCAL_TZ)

    df = df.sort_values("timestamp_utc").reset_index(drop=True)
    log.info("Cleaning finished: %d rows", len(df))
    return df[OUTPUT_COLUMNS]


def day_window_utc(start, end):
    """Return the UTC start/end instants covering Alberta days start..end.

    The end is exclusive: midnight (Alberta time) at the start of the day after `end`.
    Midnight is never skipped or repeated by daylight saving in Alberta (the
    clocks change at 2am), so this is always well defined.
    """
    start_utc = pd.Timestamp(start).tz_localize(LOCAL_TZ).tz_convert("UTC")
    end_utc = (pd.Timestamp(end) + pd.Timedelta(days=1)).tz_localize(LOCAL_TZ).tz_convert("UTC")
    return start_utc, end_utc


def filter_to_dates(df, start, end):
    """Keep only the hours that fall inside the requested Alberta dates.

    This matters because the API might return a bit more than we asked for
    (for example, if its end date is inclusive or it works in UTC).
    """
    start_utc, end_utc = day_window_utc(start, end)
    inside = (df["timestamp_utc"] >= start_utc) & (df["timestamp_utc"] < end_utc)
    outside = int((~inside).sum())
    if outside:
        log.info("Removed %d rows outside %s to %s", outside, start, end)
    return df[inside].reset_index(drop=True)
