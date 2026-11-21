"""Tests for checks.py: each check should catch the problem it's meant to catch."""

from datetime import date

import pandas as pd

from checks import expected_hours, run_checks
from helpers import make_clean_df

DAY = date(2026, 1, 15)


def result(report, name):
    """Pick one check's pass/fail out of the report."""
    return next(c["passed"] for c in report["checks"] if c["name"] == name)


def test_good_data_passes():
    report = run_checks(make_clean_df(DAY, DAY), DAY, DAY)
    assert report["passed"]
    assert report["spikes"] == []


def test_missing_hour_is_caught():
    df = make_clean_df(DAY, DAY).drop(index=5)  # remove one hour
    report = run_checks(df, DAY, DAY)
    assert not report["passed"]
    assert not result(report, "no_missing_hours")
    assert not result(report, "row_count_matches")


def test_duplicate_row_is_caught():
    df = make_clean_df(DAY, DAY)
    df = pd.concat([df, df.iloc[[0]]], ignore_index=True)  # repeat the first hour
    report = run_checks(df, DAY, DAY)
    assert not report["passed"]
    assert not result(report, "no_duplicate_timestamps")


def test_out_of_range_price_is_caught():
    df = make_clean_df(DAY, DAY)
    df.loc[3, "pool_price"] = -10.0
    report = run_checks(df, DAY, DAY)
    assert not result(report, "prices_in_range")


def test_spike_is_flagged_but_not_a_failure():
    df = make_clean_df(DAY, DAY)
    df.loc[17, "pool_price"] = 750.0
    report = run_checks(df, DAY, DAY)
    assert report["passed"]                  # still passes...
    assert len(report["spikes"]) == 1        # ...but the spike is reported
    assert report["spikes"][0]["pool_price"] == 750.0


def test_empty_data_fails():
    df = make_clean_df(DAY, DAY).iloc[0:0]
    assert not run_checks(df, DAY, DAY)["passed"]


def test_daylight_saving_days_have_23_or_25_hours():
    # Alberta's clocks went back on Nov 2, 2025 (25-hour day) and forward on
    # March 8, 2026 (23-hour day). We use past dates on purpose: the time zone
    # database we installed (tzdata 2026f) shows no fall-back in November 2026,
    # so the expected hours come from tzdata rather than a hard-coded rule.
    assert len(expected_hours(date(2025, 11, 2), date(2025, 11, 2))) == 25
    assert len(expected_hours(date(2026, 3, 8), date(2026, 3, 8))) == 23
    assert len(expected_hours(date(2026, 1, 15), date(2026, 1, 15))) == 24
