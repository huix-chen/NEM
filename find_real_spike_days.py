"""
在 bid data 可用的窗口内 (2024-08 之后) 搜真实发生过价格尖峰/备用容量紧张的日子，
用来替换掉 2025-05 那个"风平浪静"的默认周。
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
print("=== Top 20 NSW1 尖峰日 (按当天最高 RRP 排序), 2024-08 ~ now ===")
print(daily.head(20))

daily.to_csv("./nemosis_cache/nsw1_daily_rrp_2024aug_onward.csv")
print("\n已保存到 ./nemosis_cache/nsw1_daily_rrp_2024aug_onward.csv")
