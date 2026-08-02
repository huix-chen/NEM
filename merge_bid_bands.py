"""
Merges BIDDAYOFFER_D (daily price ladder) with BIDPEROFFER_D (5-minute volume
ladder) into one full 10-band price x volume table per DUID per dispatch
interval. Reuses the cache already populated by fetch_real_bids_nemosis.py, so
nothing gets re-downloaded.
"""
import pandas as pd
from nemosis import dynamic_data_compiler

RAW_DATA_CACHE = "./nemosis_cache"
START_TIME = "2025/05/01 00:00:00"
END_TIME = "2025/05/08 00:00:00"
PEAKER_DUIDS = ["ER01", "ER02", "BW01", "BW02"]

price_bands = dynamic_data_compiler(
    START_TIME, END_TIME, "BIDDAYOFFER_D", RAW_DATA_CACHE,
    filter_cols=["DUID"], filter_values=(PEAKER_DUIDS,),
)
volume_bands = dynamic_data_compiler(
    START_TIME, END_TIME, "BIDPEROFFER_D", RAW_DATA_CACHE,
    filter_cols=["DUID"], filter_values=(PEAKER_DUIDS,),
)

print("=== price_bands columns ===")
print(list(price_bands.columns))
print(price_bands.head(3))

print("\n=== volume_bands columns ===")
print(list(volume_bands.columns))
print(volume_bands.head(3))

PRICE_COLS = [f"PRICEBAND{i}" for i in range(1, 11)]
VOL_COLS = [f"BANDAVAIL{i}" for i in range(1, 11)]

# BIDDAYOFFER_D's price ladder is set per trading day (SETTLEMENTDATE); BIDPEROFFER_D's
# volume ladder is set per 5-minute interval. Join on DUID + trading date: a unit's
# 10 price bands stay fixed within a day, while volume per band can change interval
# to interval.
price_bands = price_bands.copy()
price_bands["TRADE_DATE"] = pd.to_datetime(price_bands["SETTLEMENTDATE"]).dt.date

volume_bands = volume_bands.copy()
volume_bands["TRADE_DATE"] = pd.to_datetime(volume_bands["SETTLEMENTDATE"]).dt.date \
    if "SETTLEMENTDATE" in volume_bands.columns else pd.to_datetime(volume_bands["INTERVAL_DATETIME"]).dt.date

merged = volume_bands.merge(
    price_bands[["DUID", "TRADE_DATE"] + PRICE_COLS],
    on=["DUID", "TRADE_DATE"],
    how="left",
)

print("\n=== merged shape ===", merged.shape)
print(merged[["DUID", "TRADE_DATE"] + PRICE_COLS[:3] + VOL_COLS[:3]].head(10))

# Sanity check: did this unit's price ladder change at all over the week (looking
# at just the two endpoints, PRICEBAND1/10)?
print("\n=== PRICEBAND1 / PRICEBAND10 per DUID per day ===")
daily = price_bands.groupby(["DUID", "TRADE_DATE"])[["PRICEBAND1", "PRICEBAND10"]].first()
print(daily)

merged.to_feather("./nemosis_cache/merged_bid_bands_202505_week1.feather")
print("\nSaved: ./nemosis_cache/merged_bid_bands_202505_week1.feather")
