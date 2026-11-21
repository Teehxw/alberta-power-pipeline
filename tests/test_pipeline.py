"""End-to-end test of pipeline.py with the API call faked out."""

import sqlite3
from datetime import date

import fetch
import pipeline
from helpers import make_raw_rows

DAY = date(2026, 1, 15)


def count_rows(db):
    conn = sqlite3.connect(db)
    n = conn.execute("SELECT COUNT(*) FROM pool_price").fetchone()[0]
    conn.close()
    return n


def test_full_run_twice_loads_24_rows_once(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, "LOG_DIR", tmp_path / "logs")
    monkeypatch.setattr(fetch, "fetch_pool_price", lambda s, e: make_raw_rows(s, e))
    db = tmp_path / "test.db"
    args = ["--start", str(DAY), "--db", str(db)]

    assert pipeline.main(args) == 0
    assert pipeline.main(args) == 0          # second run: same data again
    assert count_rows(db) == 24              # still 24, no duplicates


def test_failed_checks_stop_the_load(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, "LOG_DIR", tmp_path / "logs")
    rows = make_raw_rows(DAY, DAY)[:-1]      # one hour missing
    monkeypatch.setattr(fetch, "fetch_pool_price", lambda s, e: rows)
    db = tmp_path / "test.db"

    assert pipeline.main(["--start", str(DAY), "--db", str(db)]) == 2
    assert not db.exists()                   # nothing was loaded
