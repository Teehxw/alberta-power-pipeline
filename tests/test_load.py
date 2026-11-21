"""Tests for load.py: rerunning the load must not create duplicates."""

import sqlite3
from datetime import date

from helpers import make_clean_df
from load import load

DAY = date(2026, 1, 15)


def test_rerunning_load_does_not_change_row_count(tmp_path):
    db = tmp_path / "test.db"  # tmp_path is a fresh temporary folder from pytest
    df = make_clean_df(DAY, DAY)
    first = load(df, db)
    second = load(df, db)
    assert first == second == 24


def test_upsert_updates_existing_hour(tmp_path):
    db = tmp_path / "test.db"
    load(make_clean_df(DAY, DAY, price=50.0), db)
    load(make_clean_df(DAY, DAY, price=80.0), db)  # same hours, corrected prices

    conn = sqlite3.connect(db)
    prices = {p for (p,) in conn.execute("SELECT pool_price FROM pool_price")}
    conn.close()
    assert prices == {80.0}
