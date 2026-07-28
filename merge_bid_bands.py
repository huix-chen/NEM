"""
把 BIDDAYOFFER_D (每日价格阶梯) 和 BIDPEROFFER_D (每5分钟数量阶梯) 合并成
每台机组每个 dispatch interval 的完整 10 档报价表 (价格 x 数量)。
用的是 fetch_real_bids_nemosis.py 已经跑过并缓存好的数据，这里直接复用缓存，不会重新下载。
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

# BIDDAYOFFER_D 的价格阶梯是按天设的 (SETTLEMENTDATE = 交易日)，
# BIDPEROFFER_D 的数量阶梯是按 5 分钟 interval 设的。
# 用 DUID + 交易日 把两者对齐: 同一天里这台机组的10档价格保持不变，
# 但每个 interval 各档能卖的量会变。
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

# 看看同一台机组，一周里价格阶梯变了没有 (哪怕只看 PRICEBAND1/10 两端)
print("\n=== 每台机组每天的 PRICEBAND1 / PRICEBAND10 (看报价有没有随时间变化) ===")
daily = price_bands.groupby(["DUID", "TRADE_DATE"])[["PRICEBAND1", "PRICEBAND10"]].first()
print(daily)

merged.to_feather("./nemosis_cache/merged_bid_bands_202505_week1.feather")
print("\n已保存合并结果到 ./nemosis_cache/merged_bid_bands_202505_week1.feather")
