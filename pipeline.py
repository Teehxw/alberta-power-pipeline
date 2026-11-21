"""
pipeline.py - runs every stage in order: fetch -> clean -> check -> load.

Usage:
    python pipeline.py                                   # yesterday (Alberta time)
    python pipeline.py --start 2026-11-01 --end 2026-11-07

Exit codes (so GitHub Actions or another script can tell what happened):
    0 = success
    1 = fetch or clean failed
    2 = data-quality checks failed (nothing was loaded)
"""

import argparse
import json
import logging
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import checks
import clean
import fetch
import load

PROJECT_DIR = Path(__file__).parent
LOG_DIR = PROJECT_DIR / "logs"
DEFAULT_DB = PROJECT_DIR / "data" / "alberta_power.db"

log = logging.getLogger("pipeline")


def setup_logging(run_id):
    """Log to the screen and to logs/pipeline_<run_id>.log."""
    LOG_DIR.mkdir(exist_ok=True)
    log_file = LOG_DIR / f"pipeline_{run_id}.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        handlers=[logging.FileHandler(log_file), logging.StreamHandler()],
        force=True,  # replace any earlier logging setup (useful in tests)
    )
    return log_file


def parse_args(argv=None):
    # Default to yesterday in Alberta time: today's data is still incomplete.
    yesterday = datetime.now(ZoneInfo(clean.LOCAL_TZ)).date() - timedelta(days=1)
    parser = argparse.ArgumentParser(description="Alberta pool price pipeline")
    parser.add_argument("--start", type=date.fromisoformat, default=yesterday,
                        help="first Alberta date, YYYY-MM-DD (default: yesterday)")
    parser.add_argument("--end", type=date.fromisoformat, default=None,
                        help="last Alberta date, YYYY-MM-DD (default: same as --start)")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB, help="SQLite database file")
    args = parser.parse_args(argv)
    if args.end is None:
        args.end = args.start
    return args


def main(argv=None):
    args = parse_args(argv)
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = setup_logging(run_id)
    log.info("Pipeline started for %s to %s (log: %s)", args.start, args.end, log_file)

    if args.start > args.end:
        log.error("--start (%s) is after --end (%s)", args.start, args.end)
        return 1

    # Stage 1: fetch
    try:
        raw_rows = fetch.fetch_pool_price(args.start, args.end)
    except fetch.FetchError as err:
        log.error("FETCH FAILED: %s", err)
        return 1

    # Stage 2: clean
    try:
        df = clean.clean(raw_rows)
    except ValueError as err:
        log.error("CLEAN FAILED: %s", err)
        return 1
    df = clean.filter_to_dates(df, args.start, args.end)

    # Stage 3: checks. The full report is saved as JSON next to the log.
    report = checks.run_checks(df, args.start, args.end)
    report_file = LOG_DIR / f"checks_{run_id}.json"
    report_file.write_text(json.dumps(report, indent=2))
    for check in report["checks"]:
        level = logging.INFO if check["passed"] else logging.ERROR
        log.log(level, "Check %-24s %s  %s", check["name"],
                "PASS" if check["passed"] else "FAIL", check["detail"])
    if report["spikes"]:
        log.warning("%d hour(s) at or above $%.2f flagged as spikes (kept, see %s)",
                    len(report["spikes"]), report["spike_threshold"], report_file.name)

    if not report["passed"]:
        log.error("DATA-QUALITY CHECKS FAILED. Nothing was loaded. Details: %s", report_file)
        return 2

    # Stage 4: load
    total = load.load(df, args.db)
    log.info("Pipeline finished OK: %d rows loaded, %d rows in the database", len(df), total)
    return 0


if __name__ == "__main__":
    sys.exit(main())
