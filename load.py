"""
load.py - Stage 4: save the cleaned rows into a SQLite database.

It uses an "upsert": insert each hour, and if that hour (timestamp_utc) is
already in the table, update it instead. Because timestamp_utc is the primary
key, there can never be two rows for the same hour, so rerunning the pipeline
is safe.
"""

import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

log = logging.getLogger(__name__)

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS pool_price (
    timestamp_utc       TEXT PRIMARY KEY,  -- start of the hour in UTC: the unique key
    timestamp_mpt       TEXT NOT NULL,     -- same hour in Alberta local time
    pool_price          REAL NOT NULL,     -- $/MWh
    forecast_pool_price REAL,
    rolling_30day_avg   REAL,
    loaded_at           TEXT NOT NULL      -- when this row was last written (UTC)
)
"""

# "excluded" means "the row we just tried to insert".
UPSERT_SQL = """
INSERT INTO pool_price
    (timestamp_utc, timestamp_mpt, pool_price, forecast_pool_price, rolling_30day_avg, loaded_at)
VALUES (?, ?, ?, ?, ?, ?)
ON CONFLICT(timestamp_utc) DO UPDATE SET
    timestamp_mpt       = excluded.timestamp_mpt,
    pool_price          = excluded.pool_price,
    forecast_pool_price = excluded.forecast_pool_price,
    rolling_30day_avg   = excluded.rolling_30day_avg,
    loaded_at           = excluded.loaded_at
"""

# Timestamps are stored as plain text without a timezone offset. SQLite has no
# datetime type, and its date functions would silently shift text that has an
# offset, which would break "hour of day" queries on the local column.
TS_FORMAT = "%Y-%m-%d %H:%M:%S"


def _none_if_missing(value):
    """SQLite wants None for missing values, not pandas' NaN/NA."""
    return None if pd.isna(value) else float(value)


def to_db_rows(df):
    """Convert the DataFrame into a list of tuples matching UPSERT_SQL."""
    loaded_at = datetime.now(timezone.utc).strftime(TS_FORMAT)
    return [
        (
            row.timestamp_utc.strftime(TS_FORMAT),
            row.timestamp_mpt.strftime(TS_FORMAT),
            float(row.pool_price),
            _none_if_missing(row.forecast_pool_price),
            _none_if_missing(row.rolling_30day_avg),
            loaded_at,
        )
        for row in df.itertuples(index=False)
    ]


def load(df, db_path):
    """Upsert the rows into SQLite. Returns the total row count in the table afterwards."""
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)  # create data/ if needed

    conn = sqlite3.connect(db_path)
    try:
        conn.execute(CREATE_TABLE_SQL)
        conn.executemany(UPSERT_SQL, to_db_rows(df))
        conn.commit()  # all rows are saved together, or none if something fails
        total = conn.execute("SELECT COUNT(*) FROM pool_price").fetchone()[0]
    finally:
        conn.close()

    log.info("Upserted %d rows into %s (table now has %d rows)", len(df), db_path, total)
    return total
