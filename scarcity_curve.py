"""
Fits the real relationship between bid price and reserve margin
(DISPATCHREGIONSUM.AVAILABLEGENERATION - TOTALDEMAND) from real BIDPEROFFER_D /
BIDDAYOFFER_D data, replacing the hand-tuned alpha formula in nem_mvp.py.

Parameterized as a function so it can run against several real windows, not just
one fixed default week.
"""
import sys
import numpy as np
import pandas as pd
from nemosis import dynamic_data_compiler

RAW_DATA_CACHE = "./nemosis_cache"
PEAKER_DUIDS = ["ER01", "ER02", "BW01", "BW02"]
PRICE_COLS = [f"PRICEBAND{i}" for i in range(1, 11)]
VOL_COLS = [f"BANDAVAIL{i}" for i in range(1, 11)]


def run_window(start_time, end_time, label):
    """Builds the weighted-average bid price series for one real time window and
    saves it as a parquet file.

    Pulls real NSW1 demand/availability and real bid ladders for the four units,
    keeps only the latest live rebid in effect at each interval, computes each
    unit's volume-weighted average bid price, and joins it to reserve margin.

    Args:
        start_time: window start, "YYYY/MM/DD HH:MM:SS"
        end_time: window end, same format
        label: name for this window, used in the output filename (e.g. "monthly_202408")

    Returns:
        The merged DataFrame (same content as what gets saved).
    """
    print(f"\n{'='*70}\nWindow: {label} ({start_time} ~ {end_time})\n{'='*70}")

    region_summary = dynamic_data_compiler(
        start_time, end_time, "DISPATCHREGIONSUM", RAW_DATA_CACHE,
        filter_cols=["REGIONID"], filter_values=(["NSW1"],),
        select_columns=["SETTLEMENTDATE", "REGIONID", "TOTALDEMAND", "AVAILABLEGENERATION"],
    )
    region_summary["SETTLEMENTDATE"] = pd.to_datetime(region_summary["SETTLEMENTDATE"])
    region_summary["RESERVE_MARGIN_MW"] = (
        region_summary["AVAILABLEGENERATION"] - region_summary["TOTALDEMAND"]
    )
    print("=== NSW1 reserve margin (real, AVAILABLEGENERATION - TOTALDEMAND) ===")
    print(region_summary[["TOTALDEMAND", "AVAILABLEGENERATION", "RESERVE_MARGIN_MW"]].describe())

    price_bands = dynamic_data_compiler(
        start_time, end_time, "BIDDAYOFFER_D", RAW_DATA_CACHE,
        filter_cols=["DUID", "BIDTYPE"], filter_values=(PEAKER_DUIDS, ["ENERGY"]),
    )
    volume_bands = dynamic_data_compiler(
        start_time, end_time, "BIDPEROFFER_D", RAW_DATA_CACHE,
        filter_cols=["DUID", "BIDTYPE"], filter_values=(PEAKER_DUIDS, ["ENERGY"]),
    )

    price_bands["TRADE_DATE"] = pd.to_datetime(price_bands["SETTLEMENTDATE"]).dt.date
    volume_bands["TRADE_DATE"] = pd.to_datetime(volume_bands["SETTLEMENTDATE"]).dt.date
    volume_bands["INTERVAL_DATETIME"] = pd.to_datetime(volume_bands["INTERVAL_DATETIME"])
    volume_bands["OFFERDATE"] = pd.to_datetime(volume_bands["OFFERDATE"])

    # A unit can rebid intraday; BIDPEROFFER_D restates every remaining interval
    # each time it does. Keep only the latest rebid actually in effect per interval.
    volume_bands = volume_bands[volume_bands["OFFERDATE"] <= volume_bands["INTERVAL_DATETIME"]]
    volume_bands = volume_bands.sort_values("OFFERDATE").drop_duplicates(
        subset=["DUID", "INTERVAL_DATETIME"], keep="last"
    )

    merged = volume_bands.merge(
        price_bands[["DUID", "TRADE_DATE"] + PRICE_COLS],
        on=["DUID", "TRADE_DATE"], how="left",
    )

    vol = merged[VOL_COLS].to_numpy()
    price = merged[PRICE_COLS].to_numpy()
    total_vol = vol.sum(axis=1)
    weighted_price = np.divide(
        (vol * price).sum(axis=1), total_vol,
        out=np.full(len(merged), np.nan), where=total_vol > 0,
    )
    merged["TOTAL_OFFERED_MW"] = total_vol
    merged["WEIGHTED_AVG_PRICE"] = weighted_price

    scarcity = merged.merge(
        region_summary[["SETTLEMENTDATE", "RESERVE_MARGIN_MW", "TOTALDEMAND", "AVAILABLEGENERATION"]],
        left_on="INTERVAL_DATETIME", right_on="SETTLEMENTDATE", how="inner",
    )
    scarcity = scarcity.dropna(subset=["WEIGHTED_AVG_PRICE"])

    print(f"\nrows: {len(scarcity)}")
    print("\n=== By DUID: correlation between bid price and reserve margin ===")
    for duid, g in scarcity.groupby("DUID"):
        corr = g["RESERVE_MARGIN_MW"].corr(g["WEIGHTED_AVG_PRICE"])
        print(f"{duid}: n={len(g)}, corr(reserve_margin, weighted_avg_price) = {corr:.3f}")

    out_path = f"{RAW_DATA_CACHE}/scarcity_curve_data_{label}.parquet"
    scarcity.to_parquet(out_path, index=False)
    print(f"\nSaved: {out_path}")
    return scarcity


if __name__ == "__main__":
    windows = {
        "sustained_2024aug": ("2024/08/03 00:00:00", "2024/08/08 00:00:00"),
        "duckcurve_2025nov": ("2025/11/24 00:00:00", "2025/11/29 00:00:00"),
    }
    which = sys.argv[1] if len(sys.argv) > 1 else None
    for label, (start, end) in windows.items():
        if which and which != label:
            continue
        run_window(start, end, label)
