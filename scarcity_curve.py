"""
用真实报价数据 (BIDPEROFFER_D + BIDDAYOFFER_D) 和真实 AEMO 备用容量数据
(DISPATCHREGIONSUM.AVAILABLEGENERATION) 拟合 "备用容量越紧张,机组报价越往高价档集中"
这条真实曲线,用来替代 nem_mvp.py 里手编的 alpha 公式。

跟第一版的区别: 参数化成函数，可以对多个真实尖峰窗口分别跑，
而不是只跑一个"风平浪静"的默认周。
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
    print(f"\n{'='*70}\n窗口: {label} ({start_time} ~ {end_time})\n{'='*70}")

    region_summary = dynamic_data_compiler(
        start_time, end_time, "DISPATCHREGIONSUM", RAW_DATA_CACHE,
        filter_cols=["REGIONID"], filter_values=(["NSW1"],),
        select_columns=["SETTLEMENTDATE", "REGIONID", "TOTALDEMAND", "AVAILABLEGENERATION"],
    )
    region_summary["SETTLEMENTDATE"] = pd.to_datetime(region_summary["SETTLEMENTDATE"])
    region_summary["RESERVE_MARGIN_MW"] = (
        region_summary["AVAILABLEGENERATION"] - region_summary["TOTALDEMAND"]
    )
    print("=== NSW1 reserve margin (真实, AVAILABLEGENERATION - TOTALDEMAND) ===")
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
    print("\n=== 按 DUID 分组: 报价 vs 备用容量 的相关系数 ===")
    for duid, g in scarcity.groupby("DUID"):
        corr = g["RESERVE_MARGIN_MW"].corr(g["WEIGHTED_AVG_PRICE"])
        print(f"{duid}: n={len(g)}, corr(reserve_margin, weighted_avg_price) = {corr:.3f}")

    out_path = f"./nemosis_cache/scarcity_curve_data_{label}.csv"
    scarcity.to_csv(out_path, index=False)
    print(f"\n已保存到 {out_path}")
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
