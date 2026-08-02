"""
Scans NSW1 RRP from 2024-08 onward (the start of the window where bid data is
available) for the days with the largest real price spikes, used to pick real
weeks for scarcity_curve.py instead of an arbitrary default week.
"""
import pandas as pd
from nemosis import dynamic_data_compiler

RAW_DATA_CACHE = "./nemosis_cache"
START_TIME = "2024/08/01 00:00:00"
END_TIME = "2026/07/28 00:00:00"

price = dynamic_data_compiler(
    START_TIME, END_TIME, "DISPATCHPRICE", RAW_DATA_CACHE,
    filter_cols=["REGIONID"], filter_values=(["NSW1"],),
    select_columns=["SETTLEMENTDATE", "REGIONID", "RRP"],
)
price["SETTLEMENTDATE"] = pd.to_datetime(price["SETTLEMENTDATE"])
price["DATE"] = price["SETTLEMENTDATE"].dt.date

daily = price.groupby("DATE")["RRP"].agg(["max", "mean", "min"]).sort_values("max", ascending=False)
print("=== Top 20 NSW1 spike days (by daily max RRP), 2024-08 onward ===")
print(daily.head(20))

daily.to_csv("./nemosis_cache/nsw1_daily_rrp_2024aug_onward.csv")
print("\nSaved: ./nemosis_cache/nsw1_daily_rrp_2024aug_onward.csv")
