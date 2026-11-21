"""
fetch.py - Stage 1: download Alberta pool price data from the AESO API.

What it does:
  1. Splits the date range into chunks (in case the API limits how many days
     you can ask for at once).
  2. Requests each chunk, retrying a few times with a short wait if the request
     fails for a temporary reason (network error, timeout, server error).
  3. Logs every attempt so you can see what happened afterwards.
  4. Returns the raw rows as a list of dictionaries. Cleaning happens in clean.py.
"""

import logging
import os
import time
from datetime import timedelta

import requests
from dotenv import load_dotenv

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# SETTINGS TO CONFIRM FROM THE AESO DEVELOPER PORTAL
# None of these have been confirmed yet. Copy the real values from the
# "Pool Price Report" page on https://developer-apim.aeso.ca once you have access.
# ---------------------------------------------------------------------------

# TODO: paste the full request URL WITHOUT the "?..." query string part.
API_URL = "PASTE_POOL_PRICE_ENDPOINT_HERE"

# TODO: confirm the header name. This is the Azure API Management default, which
# AESO's portal runs on, but AESO might use a different name.
KEY_HEADER = "Ocp-Apim-Subscription-Key"

# TODO: confirm the query parameter names and the date format.
START_PARAM = "startDate"
END_PARAM = "endDate"
DATE_FORMAT = "%Y-%m-%d"  # e.g. 2026-11-01

# TODO: confirm the maximum number of days per request (if there is a limit).
MAX_DAYS_PER_REQUEST = 30

# ---------------------------------------------------------------------------
# Retry settings (our choice, not AESO's)
# ---------------------------------------------------------------------------
MAX_ATTEMPTS = 3        # try each request up to 3 times
WAIT_SECONDS = 5        # wait 5s, then 10s between attempts
TIMEOUT_SECONDS = 30    # give up on a single request after 30s
# Status codes worth retrying: "too many requests" and server-side errors.
# Codes like 401 (bad key) or 404 (wrong URL) won't fix themselves, so we stop at once.
RETRY_STATUS = {429, 500, 502, 503, 504}


class FetchError(Exception):
    """Raised when the data can't be downloaded."""


def get_api_key():
    """Read the API key from the environment (.env locally, a secret on GitHub)."""
    load_dotenv()  # loads variables from a .env file if one exists
    key = os.getenv("AESO_API_KEY")
    if not key:
        raise FetchError(
            "AESO_API_KEY is not set. Put it in a .env file locally, "
            "or add it as a repository secret on GitHub."
        )
    return key


def date_chunks(start, end, max_days):
    """Split start..end (inclusive) into pieces of at most max_days days.

    Example with max_days=30: Jan 1 - Feb 15 -> (Jan 1, Jan 30), (Jan 31, Feb 15)
    """
    current = start
    while current <= end:
        chunk_end = min(current + timedelta(days=max_days - 1), end)
        yield current, chunk_end
        current = chunk_end + timedelta(days=1)


def extract_records(payload):
    """Find the list of data rows inside the JSON response.

    We haven't seen a real response yet, so this searches the JSON for the first
    non-empty list of objects (dicts). Once you know the exact shape, you can
    replace this with something direct, e.g. payload["return"]["Pool Price Report"].
    """
    if isinstance(payload, list):
        if payload and all(isinstance(item, dict) for item in payload):
            return payload
        return []
    if isinstance(payload, dict):
        for value in payload.values():
            rows = extract_records(value)
            if rows:
                return rows
    return []


def get_with_retry(url, params, headers):
    """GET a URL, retrying temporary failures. Returns the parsed JSON."""
    for attempt in range(1, MAX_ATTEMPTS + 1):
        # Note: we log the params but never the headers, because they hold the API key.
        log.info("Attempt %d/%d: GET %s params=%s", attempt, MAX_ATTEMPTS, url, params)
        try:
            response = requests.get(url, params=params, headers=headers, timeout=TIMEOUT_SECONDS)
        except requests.RequestException as err:
            # Network problem or timeout: worth retrying.
            log.warning("Attempt %d failed: %s", attempt, err)
        else:
            if response.status_code == 200:
                log.info("Attempt %d succeeded (%d bytes)", attempt, len(response.content))
                try:
                    return response.json()
                except ValueError as err:
                    raise FetchError(f"Response was not valid JSON: {response.text[:200]}") from err
            if response.status_code not in RETRY_STATUS:
                # A permanent error (bad key, wrong URL, bad parameters): stop now.
                raise FetchError(f"HTTP {response.status_code}: {response.text[:200]}")
            log.warning("Attempt %d got HTTP %d", attempt, response.status_code)

        # Wait a bit longer after each failure, unless that was the last attempt.
        if attempt < MAX_ATTEMPTS:
            wait = WAIT_SECONDS * attempt
            log.info("Waiting %ds before retrying", wait)
            time.sleep(wait)

    raise FetchError(f"Gave up after {MAX_ATTEMPTS} attempts")


def fetch_pool_price(start, end):
    """Download raw pool price rows for the dates start..end (both inclusive)."""
    if "PASTE" in API_URL:
        raise FetchError("API_URL in fetch.py is still a placeholder. Paste the real endpoint first.")

    headers = {KEY_HEADER: get_api_key()}
    all_rows = []

    for chunk_start, chunk_end in date_chunks(start, end, MAX_DAYS_PER_REQUEST):
        params = {
            START_PARAM: chunk_start.strftime(DATE_FORMAT),
            END_PARAM: chunk_end.strftime(DATE_FORMAT),
        }
        payload = get_with_retry(API_URL, params, headers)
        rows = extract_records(payload)
        log.info("Received %d rows for %s to %s", len(rows), chunk_start, chunk_end)
        all_rows.extend(rows)

    log.info("Fetch finished: %d raw rows in total", len(all_rows))
    return all_rows
