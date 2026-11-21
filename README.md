# alberta-power-pipeline

A small, tested data pipeline that downloads hourly **Alberta electricity pool prices** from the AESO (Alberta Electric System Operator). It cleans the data, runs data-quality checks, and loads it into SQLite without duplicates. It runs every day on GitHub Actions.

> **Status:** the pipeline code, checks, load and tests are finished, and the tests pass. The AESO endpoint details (URL, key header, parameter names, field names) are **still placeholders** until I confirm them from the AESO developer portal. See [Setup](#setup).

## The question it answers

*When is electricity in Alberta expensive, and how often do price spikes happen?*

To answer that, you need a reliable, complete, duplicate-free hourly price history. This pipeline builds that history. `sql/analysis.sql` then asks the questions: average price by hour of day, spike hours per month, the most expensive hours in each month, and daily trends.

## Data source

- **AESO Pool Price Report API**, through the AESO API gateway at https://developer-apim.aeso.ca. It needs a free account registration and an API key. AESO's overview page: https://aeso.ca/market/market-and-system-reporting/aeso-application-programming-interface-api/
- The pool price is the hourly wholesale electricity price in Alberta, in $/MWh.
- Fallback if the API isn't workable: AESO's downloadable reports at https://aeso.ca/market/market-and-system-reporting/ (only `fetch.py` would need to change).

## Pipeline steps

```
 fetch.py ──► clean.py ──► checks.py ──► load.py ──► SQLite (data/alberta_power.db)
 download      fix types,     quality        upsert on
 + retries     rename cols,   report         timestamp_utc
               drop bad rows  (pass/fail)
                                │
                                └─ FAIL ► stop, nothing loaded, exit code 2
 pipeline.py runs all four steps and writes logs/pipeline_<time>.log + logs/checks_<time>.json
```

1. **fetch.py**: splits the date range into chunks and calls the API. Network errors, timeouts, HTTP 429 and HTTP 5xx are retried up to 3 times, waiting 5s and then 10s. Permanent errors (401 bad key, 404 wrong URL) stop at once. Every attempt is logged, and the API key is never written to the log.
2. **clean.py**: standardizes column names, parses timestamps as UTC, converts prices to numbers, and drops rows with no usable timestamp or price. It also adds an Alberta local-time column (`timestamp_mpt`) worked out from UTC, so daylight saving is handled correctly. It doesn't remove duplicates or fill gaps; that's the checks' job.
3. **checks.py**: returns a pass/fail report (see below).
4. **load.py**: `INSERT ... ON CONFLICT(timestamp_utc) DO UPDATE`. Each hour can exist only once, so running the pipeline twice for the same day leaves the row count unchanged. If AESO corrects a price, the rerun updates it.
5. **pipeline.py**: runs the stages in order. Exit codes: `0` OK, `1` fetch/clean failed, `2` quality checks failed.

## Data-quality checks

| Check | Fails when |
|---|---|
| `no_duplicate_timestamps` | the same hour appears more than once |
| `no_missing_hours` | any expected hour in the date range is missing |
| `prices_in_range` | a price is below $0 or above $999.99/MWh (Alberta's historical floor and cap; *to be re-confirmed*) |
| `row_count_matches` | the row count isn't the expected number of hours |

The expected number of hours comes from the time zone database. It's usually 24 per day, but 23 or 25 on clock-change days.

**Price spikes** (hours ≥ $500/MWh, my own threshold) are **listed in the report, not deleted, and don't fail the run**. Spikes are real market events, not errors.

## How to run

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env               # then paste your AESO API key into .env

pytest                              # run the tests (no network or key needed)
python pipeline.py                  # load yesterday (Alberta time)
python pipeline.py --start 2026-10-01 --end 2026-10-31   # backfill a range
sqlite3 data/alberta_power.db < sql/analysis.sql         # run the analysis queries
```

### Setup

These values in the code are placeholders until confirmed from the AESO developer portal:

- `fetch.py`: `API_URL`, `KEY_HEADER`, `START_PARAM`, `END_PARAM`, `DATE_FORMAT`, `MAX_DAYS_PER_REQUEST`
- `clean.py`: `COLUMN_MAP` (AESO's JSON field names → our column names)
- `checks.py`: `PRICE_MIN`, `PRICE_MAX`

### GitHub Actions

`.github/workflows/pipeline.yml` runs the tests and the pipeline every day at 14:00 UTC. It can also be started by hand from the **Actions** tab, with an optional date range. Add the key under **Settings → Secrets and variables → Actions** as `AESO_API_KEY`. Each run uploads its logs, checks report and database as a downloadable artifact. Between runs, the database is kept in the Actions cache.

## Tests

`pytest` runs 20 tests with the network faked out. Some examples:
- the checks catch a missing hour, a duplicate hour, an out-of-range price and empty data
- a spike is flagged but doesn't fail the run
- loading the same data twice leaves the row count unchanged, and an upsert updates a corrected price
- fetch retries temporary errors, gives up after 3 tries and doesn't retry a bad key (401)
- a full pipeline run twice gives 24 rows, not 48, and failed checks mean nothing is loaded

## What failed during development and how I fixed it

- **Couldn't find the API docs automatically.** The AESO developer portal builds its API list with JavaScript, so fetching the page returned an empty list. AESO's access-instructions PDF couldn't be read as text either. Fix: register on the portal and read the docs there. Until then, every unconfirmed value is an isolated, clearly marked placeholder, so the rest of the pipeline could still be built and tested.
- **Daylight-saving test failed.** I wrote a test assuming Alberta would fall back on Nov 1, 2026 (a 25-hour day). It failed: the installed time zone database (IANA tzdata 2026f) shows Alberta staying on UTC−6 after March 2026. The code was right; my assumption was wrong. Fix: the test now uses past clock-change days (Nov 2, 2025 and Mar 8, 2026). The pipeline gets expected hours from tzdata instead of a hard-coded rule, and `tzdata` is in `requirements.txt` so it can be kept up to date.
- *(Add the problems you hit when connecting to the real API here.)*

## Limitations (what it does not do)

- **Not yet tested against the real API.** The endpoint, parameters and field names are unconfirmed, and the tests use fake data shaped like my best guess.
- Only the pool price report. No demand, generation or system marginal price.
- If the checks fail, the **whole run** loads nothing. It doesn't load the good part of a partial day. That's on purpose: it's simpler, and it avoids silently storing gaps.
- Running "yesterday" early in the morning could hit data that AESO hasn't finalized yet. Prices that are revised later are only picked up if that date is re-run.
- The price range and the $500 spike threshold are fixed numbers, not learned from the data.
- SQLite in the GitHub Actions cache is fine for a portfolio project, but it isn't durable storage. GitHub can evict a cache that isn't used for a week. A real deployment would use a hosted database or cloud storage.
- No alerting beyond GitHub's default "workflow failed" email.

## Loading the same data into Databricks Free Edition (optional)

A simple manual route: export the table to CSV, upload it, and query it with the same SQL ideas.

```bash
sqlite3 -header -csv data/alberta_power.db "SELECT * FROM pool_price" > pool_price.csv
```

Then in Databricks, use the UI's upload-data option to create a table from `pool_price.csv`, and rewrite the queries in Databricks SQL. For example, `strftime('%H', ts)` becomes `hour(ts)` and `strftime('%Y-%m', ts)` becomes `date_format(ts, 'yyyy-MM')`; window functions and CTEs work the same way. The Free Edition's features and limits change over time, so check its current documentation before relying on any of this.
