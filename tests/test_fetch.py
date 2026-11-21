"""Tests for fetch.py. No real network calls: requests.get is replaced with a fake."""

from datetime import date

import pytest
import requests

import fetch


class FakeResponse:
    def __init__(self, status_code, payload=None):
        self.status_code = status_code
        self._payload = payload
        self.text = str(payload)
        self.content = self.text.encode()

    def json(self):
        return self._payload


@pytest.fixture(autouse=True)
def no_sleeping(monkeypatch):
    """Skip the real waits between retries so the tests run instantly."""
    monkeypatch.setattr(fetch.time, "sleep", lambda seconds: None)


def fake_get_sequence(monkeypatch, outcomes):
    """Make requests.get return (or raise) each item in `outcomes` in turn."""
    calls = []

    def fake_get(*args, **kwargs):
        outcome = outcomes[len(calls)]
        calls.append(outcome)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(fetch.requests, "get", fake_get)
    return calls


def test_retries_then_succeeds(monkeypatch):
    calls = fake_get_sequence(monkeypatch, [
        requests.ConnectionError("network down"),
        FakeResponse(503),
        FakeResponse(200, {"rows": [{"a": 1}]}),
    ])
    assert fetch.get_with_retry("http://x", {}, {}) == {"rows": [{"a": 1}]}
    assert len(calls) == 3


def test_gives_up_after_max_attempts(monkeypatch):
    fake_get_sequence(monkeypatch, [requests.Timeout("slow")] * fetch.MAX_ATTEMPTS)
    with pytest.raises(fetch.FetchError, match="Gave up"):
        fetch.get_with_retry("http://x", {}, {})


def test_does_not_retry_a_bad_key(monkeypatch):
    calls = fake_get_sequence(monkeypatch, [FakeResponse(401, "Access denied")])
    with pytest.raises(fetch.FetchError, match="401"):
        fetch.get_with_retry("http://x", {}, {})
    assert len(calls) == 1


def test_extract_records_finds_nested_list():
    payload = {"timestamp": "now", "messages": [], "return": {"Report": [{"a": 1}, {"a": 2}]}}
    assert fetch.extract_records(payload) == [{"a": 1}, {"a": 2}]


def test_date_chunks_split_long_ranges():
    chunks = list(fetch.date_chunks(date(2026, 1, 1), date(2026, 2, 15), 30))
    assert chunks == [
        (date(2026, 1, 1), date(2026, 1, 30)),
        (date(2026, 1, 31), date(2026, 2, 15)),
    ]
