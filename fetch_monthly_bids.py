"""
Loops scarcity_curve.py's run_window month by month, covering every available
month from 2024-08 (the end of the AEMO bid-data gap) onward, writing one
scarcity_curve_data_monthly_YYYYMM.parquet per month.

Why: backtest_holdout.py originally had only 3 hand-picked 7-day windows to
cross-validate against, too few independent folds (n=3) for a confident result.
This script raises the fold count from 3 to a dozen-plus real months, so the
backtest no longer depends on which windows happened to get picked.
backtest_holdout.py auto-discovers new scarcity_curve_data_*.parquet files, so
it needs no changes.

Requires network access to nemweb.com.au (won't run in this sandbox).
A single month of BIDPEROFFER_D is about 0.5-1.5GB compressed; pulling all ~24
months can use 10GB+ of disk and take tens of minutes to a few hours. Each month
is saved as it completes and already-saved months are skipped, so the run is
resumable.

Usage:
    python fetch_monthly_bids.py                  # default: 2024-08 to last month
    python fetch_monthly_bids.py 2024-08 2025-06   # custom range (inclusive)
"""
import os
import sys
from datetime import date
from pathlib import Path

import scarcity_curve

# Resolved relative to this script's own directory, not the process's working
# directory. scarcity_curve.py originally used the relative path "./nemosis_cache",
# which resolves against whatever cwd the caller happens to have; launching from
# an IDE's Run button doesn't always give the same cwd as a terminal `cd`, which
# previously caused a "raw_data_location does not exist" failure.
RAW_DATA_CACHE = str(Path(__file__).resolve().parent / "nemosis_cache")
scarcity_curve.RAW_DATA_CACHE = RAW_DATA_CACHE
run_window = scarcity_curve.run_window


def month_range(start_ym, end_ym):
    """Yields (year, month) tuples from start_ym to end_ym inclusive.

    Args:
        start_ym: starting (year, month), e.g. (2024, 8)
        end_ym: ending (year, month), e.g. (2025, 6)

    Returns:
        A generator yielding (year, month) tuples in order.
    """
    y, m = start_ym
    while (y, m) <= end_ym:
        yield y, m
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)


def default_end_month():
    """Default end month: the month before the current one (the current month is often not fully archived yet)."""
    today = date.today()
    return (today.year, today.month - 1) if today.month > 1 else (today.year - 1, 12)


def main():
    """Pulls one month at a time, in order, from a command-line range or the default range.

    Months that already have an output file are skipped, so an interrupted run
    can be resumed by rerunning. A single month failing (e.g. no data exists for
    it) doesn't stop the run; it's logged and the loop moves on.
    """
    if len(sys.argv) >= 3:
        start_ym = tuple(int(x) for x in sys.argv[1].split("-"))
        end_ym = tuple(int(x) for x in sys.argv[2].split("-"))
    else:
        start_ym = (2024, 8)
        end_ym = default_end_month()

    print(f"Pulling range: {start_ym[0]}-{start_ym[1]:02d} ~ {end_ym[0]}-{end_ym[1]:02d}")

    ok, skipped, failed = [], [], []
    for y, m in month_range(start_ym, end_ym):
        label = f"monthly_{y}{m:02d}"
        out_path = f"{RAW_DATA_CACHE}/scarcity_curve_data_{label}.parquet"
        if os.path.exists(out_path):
            print(f"Skipping {label} (already exists: {out_path})")
            skipped.append(label)
            continue

        start_time = f"{y}/{m:02d}/01 00:00:00"
        ny, nm = (y + 1, 1) if m == 12 else (y, m + 1)
        end_time = f"{ny}/{nm:02d}/01 00:00:00"

        try:
            run_window(start_time, end_time, label)
            ok.append(label)
        except Exception as e:
            print(f"!! {label} failed, skipping: {e}")
            failed.append(label)

    print(f"\nDone: {len(ok)} new months, {len(skipped)} already existed, {len(failed)} failed")
    if failed:
        print(f"Failed months (data may genuinely not exist for these, or it was a network issue): {failed}")
    print("\nYou can now run backtest_holdout.py; it will auto-discover all monthly files.")


if __name__ == "__main__":
    main()
