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
    """处理一段真实时间窗口的数据, 算出每台机组每个5分钟的加权平均报价, 存成一个 parquet 文件。

    做的事情, 按顺序:
    1. 从 AEMO 拉这段时间 NSW1 的真实需求和可用发电量, 算出备用容量。
    2. 拉这段时间四台机组 (Bayswater/Eraring) 的真实报价 (10档价格 + 每档数量)。
    3. 只保留每个时间点最新生效的报价 (机组盘中会反复改价, 要用最后一次)。
    4. 用价格和数量算出每个时间点的成交量加权平均报价。
    5. 把报价数据和需求/备用容量数据按时间对齐、合并。
    6. 打印一下每台机组"报价 vs 备用容量"的相关系数, 方便肉眼检查。
    7. 存成 parquet 文件, 文件名带上 label, 供后续脚本 (比如 backtest_holdout.py) 使用。

    参数:
        start_time: 起始时间, 格式 "YYYY/MM/DD HH:MM:SS"
        end_time: 结束时间, 格式同上
        label: 这段窗口的名字, 会出现在存盘文件名里, 比如 "monthly_202408"

    返回:
        合并好的 DataFrame (跟存盘的内容一样)
    """
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

    out_path = f"{RAW_DATA_CACHE}/scarcity_curve_data_{label}.parquet"
    scarcity.to_parquet(out_path, index=False)
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
