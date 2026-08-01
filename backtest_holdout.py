"""
Phase 2 起点: 留出法 (leave-one-window-out) 回测 scarcity_curve.py 的核心结论 ——
"分机组、按需求指数化的报价曲线" 是否真的比 "一条通用稀缺曲线套所有机组" 预测得更准。

背景: README 原计划是拿一个真实的 AEMO MPC/CPT 触发事件 (2024-05-08~15 NSW1
Administered Pricing) 做回测, 但那次事件正好落在 AEMO 报价数据缺失区间
(2021-03~2024-07) 里, 完全没有 BIDDAYOFFER_D/BIDPEROFFER_D 数据, 没法验证。
退而求其次: 用已有的三个真实窗口 (May 2025 / Aug 2024 / Nov 2025) 做
留一法交叉验证 —— 每次用两个窗口拟合模型, 在没见过的第三个窗口上检验预测效果。
这不是文档里设想的"针对真实监管事件"的回测, 但同样是严格的样本外 (out-of-sample) 检验。

对比两个模型 (都只用 TOTALDEMAND 一个变量, 训练/测试严格分离):
  Model A "plant-specific": 每台 DUID 单独按需求分箱取均价 (非参数, 能画出非单调曲线)
  Model B "pooled naive"  : 四台机组数据混在一起分箱取均价
                            (对应 README 想替换掉的"通用稀缺 alpha"做法)
  Baseline "constant"     : 直接预测训练集里该 DUID 的历史均价 (最起码的对照组)

第一版用的是直线拟合 (price = a + b*demand), 但 README Exhibit 2 里 BW01 的真实行为
是非单调的 (真高峰报地板价, 中等需求反而报高价, 形状更像倒U型), 直线完全抓不住这种
折返, 会系统性低估 plant-specific 曲线的价值。这版换成按需求分箱取均价的非参数模型
(regime-based), 不假设任何函数形状, 能直接体现这种自保式报价。

指标: 样本外 MAE + 样本外 R² (相对于常数基线)。
"""
import glob
import os
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

CACHE_DIR = str(Path(__file__).resolve().parent / "nemosis_cache")
DUIDS = ["BW01", "BW02", "ER01", "ER02"]
COLS = ["DUID", "INTERVAL_DATETIME", "TOTALDEMAND", "RESERVE_MARGIN_MW", "WEIGHTED_AVG_PRICE"]
N_BINS = 8  # 训练集每台机组约4000行, 8箱 => 每箱约500个点, 够稳定又不至于太粗
MIN_ROWS_PER_FOLD = 50  # 单个 DUID 在训练集/测试集里少于这个行数, 该折直接跳过


def load_windows():
    """自动发现 CACHE_DIR 下所有 scarcity_curve_data_*.parquet (不再写死3个窗口) --
    跑过 fetch_monthly_bids.py 之后, 新拉的月份会自动被这里捡起来, 折数会跟着变多。
    空窗口 (比如刚结束没几天、AEMO 还没归档完的当月数据) 会被跳过, 不然 corrcoef 遇到
    空数组会直接崩 (numpy 对长度0/1的输入有个诡异的内部报错)。"""
    paths = sorted(glob.glob(f"{CACHE_DIR}/scarcity_curve_data_*.parquet"))
    if not paths:
        raise FileNotFoundError(f"没在 {CACHE_DIR} 找到 scarcity_curve_data_*.parquet, 先跑 scarcity_curve.py")
    data = {}
    skipped_empty = []
    for path in paths:
        label = os.path.basename(path)[len("scarcity_curve_data_"):-len(".parquet")]
        d = pd.read_parquet(path, columns=COLS)
        if d.empty:
            skipped_empty.append(label)
            continue
        d["window"] = label
        data[label] = d
    print(f"发现 {len(data)} 个窗口: {list(data.keys())}")
    if skipped_empty:
        print(f"跳过 {len(skipped_empty)} 个空窗口 (可能是数据还没归档完): {skipped_empty}")
    return data


def fit_binned(x, y, n_bins=N_BINS):
    """按 x (demand) 的分位数切箱, 每箱取 y 的均值 -- 非参数, 能拟合任意形状 (包括倒U型)。"""
    x, y = np.asarray(x), np.asarray(y)
    edges = np.unique(np.quantile(x, np.linspace(0, 1, n_bins + 1)))
    interior_edges = edges[1:-1]
    bin_idx = np.searchsorted(interior_edges, x, side="right")
    overall_mean = y.mean()
    bin_means = np.array([
        y[bin_idx == k].mean() if np.any(bin_idx == k) else overall_mean
        for k in range(len(interior_edges) + 1)
    ])
    return interior_edges, bin_means


def predict_binned(x, interior_edges, bin_means):
    """用 fit_binned 算出来的分箱结果去预测新的 x 值对应的 y。

    参数:
        x: 需要预测的 demand 数组
        interior_edges: fit_binned 返回的分箱边界
        bin_means: fit_binned 返回的每箱均值

    返回:
        每个 x 对应的预测值 (落在哪箱就用哪箱的均值)
    """
    bin_idx = np.searchsorted(interior_edges, np.asarray(x), side="right")
    return bin_means[bin_idx]


def mae(actual, pred):
    """算平均绝对误差 (预测值跟真实值差多少, 取绝对值再平均), 单位跟原始数据一样 ($/MWh)。"""
    return float(np.mean(np.abs(actual - pred)))


def r2_vs_baseline(actual, pred, baseline_pred):
    """算一个模型比"只预测基线值"好多少 (R², 1表示完美预测, 0表示跟基线一样烂, 负数表示比基线还烂)。

    参数:
        actual: 真实值
        pred: 模型的预测值
        baseline_pred: 对照组的预测值 (比如直接猜历史均价)

    返回:
        R² 分数, 越接近1越好
    """
    ss_res = np.sum((actual - pred) ** 2)
    ss_tot = np.sum((actual - baseline_pred) ** 2)
    return 1 - ss_res / ss_tot if ss_tot > 0 else np.nan


def run_backtest():
    """跑一遍完整的留一法交叉验证, 每个窗口轮流当一次测试集, 其余窗口拿来训练。

    每一折都会对比三种预测方式: 分机组建模 (plant-specific)、四台机组混一起建模
    (pooled naive)、直接猜训练集历史均价 (constant, 最起码的对照组), 记录每种方式
    在没见过的测试窗口上预测得准不准。

    返回:
        results: 每一折 (测试窗口 x 机组) 一行的明细表 (DataFrame)
        example_fold: 挑一折 BW01 的数据留着画图用, 方便直观看预测曲线跟真实曲线差多少
    """
    data = load_windows()
    all_labels = list(data.keys())
    rows = []
    example_fold = None  # 留一份细节数据用来画图

    for test_label in all_labels:
        train_labels = [l for l in all_labels if l != test_label]
        train_df = pd.concat([data[l] for l in train_labels], ignore_index=True)
        test_df = data[test_label]

        # Model B: pooled -- 四台机组混在一起按需求分箱 (naive "通用稀缺alpha" 做法)
        edges_pool, means_pool = fit_binned(train_df["TOTALDEMAND"], train_df["WEIGHTED_AVG_PRICE"])

        for duid in DUIDS:
            train_sub = train_df[train_df["DUID"] == duid]
            test_sub = test_df[test_df["DUID"] == duid].sort_values("INTERVAL_DATETIME")

            # 防御性检查: 单个 DUID 在某个窗口里数据点太少 (比如那个月只抓到几天) 会让
            # corrcoef/分箱失去意义, 甚至让 numpy 内部崩掉 -- 直接跳过这一折, 不硬凑结果
            if len(train_sub) < MIN_ROWS_PER_FOLD or len(test_sub) < MIN_ROWS_PER_FOLD:
                print(f"跳过 {test_label}/{duid}: 训练集{len(train_sub)}行, 测试集{len(test_sub)}行, 太少了")
                continue

            # Model A: plant-specific
            edges_a, means_a = fit_binned(train_sub["TOTALDEMAND"], train_sub["WEIGHTED_AVG_PRICE"])
            # Baseline: 训练集里这台机组的历史均价 (常数预测)
            const_pred_value = train_sub["WEIGHTED_AVG_PRICE"].mean()

            actual = test_sub["WEIGHTED_AVG_PRICE"].to_numpy()
            demand = test_sub["TOTALDEMAND"].to_numpy()
            pred_a = predict_binned(demand, edges_a, means_a)
            pred_b = predict_binned(demand, edges_pool, means_pool)
            pred_const = np.full_like(actual, const_pred_value)

            # 方向性检验: 训练集里 demand-price 的相关方向, 是否跟测试窗口里真实方向一致
            # (分箱模型没有单一"斜率", 用训练/测试各自的 corr 符号做对比, 纯描述性, 不参与预测)
            train_corr = np.corrcoef(train_sub["TOTALDEMAND"], train_sub["WEIGHTED_AVG_PRICE"])[0, 1]
            train_pool_corr = np.corrcoef(train_df["TOTALDEMAND"], train_df["WEIGHTED_AVG_PRICE"])[0, 1]
            test_corr = np.corrcoef(demand, actual)[0, 1]
            plant_specific_sign_match = np.sign(train_corr) == np.sign(test_corr)
            pooled_sign_match = np.sign(train_pool_corr) == np.sign(test_corr)

            rows.append({
                "test_window": test_label,
                "DUID": duid,
                "train_corr_plant_specific": train_corr,
                "train_corr_pooled": train_pool_corr,
                "test_actual_demand_price_corr": test_corr,
                "plant_specific_sign_matches_test": plant_specific_sign_match,
                "pooled_sign_matches_test": pooled_sign_match,
                "mae_constant": mae(actual, pred_const),
                "mae_pooled_naive": mae(actual, pred_b),
                "mae_plant_specific": mae(actual, pred_a),
                "r2_pooled_vs_constant": r2_vs_baseline(actual, pred_b, pred_const),
                "r2_plant_specific_vs_constant": r2_vs_baseline(actual, pred_a, pred_const),
            })

            if duid == "BW01" and (example_fold is None or "duckcurve" in test_label):
                example_fold = test_sub.assign(pred_a=pred_a, pred_b=pred_b)
                example_fold.attrs["test_window"] = test_label

    return pd.DataFrame(rows), example_fold


def summarize(results):
    """把 run_backtest 跑出来的明细表打印成几张汇总表, 方便看整体结论。

    打印内容依次是: 每一折的明细、按机组汇总 (分机组建模比混合建模好多少)、
    全局平均、以及"训练集学到的方向是否跟测试集真实方向一致"的比例。

    参数:
        results: run_backtest 返回的明细 DataFrame

    返回:
        按机组汇总后的 DataFrame
    """
    print("=== 每折 (test_window x DUID) 明细 ===")
    print(results.round(2).to_string(index=False))

    n_windows = results["test_window"].nunique()
    print(f"\n=== 按 DUID 汇总 ({n_windows}折平均) ===")
    agg = results.groupby("DUID").agg(
        mae_constant=("mae_constant", "mean"),
        mae_pooled_naive=("mae_pooled_naive", "mean"),
        mae_plant_specific=("mae_plant_specific", "mean"),
        r2_pooled_vs_constant=("r2_pooled_vs_constant", "mean"),
        r2_plant_specific_vs_constant=("r2_plant_specific_vs_constant", "mean"),
        plant_specific_sign_match_rate=("plant_specific_sign_matches_test", "mean"),
        pooled_sign_match_rate=("pooled_sign_matches_test", "mean"),
    ).round(2)
    agg["plant_specific_beats_pooled_by_pct"] = (
        (agg["mae_pooled_naive"] - agg["mae_plant_specific"]) / agg["mae_pooled_naive"] * 100
    ).round(1)
    print(agg.to_string())

    print(f"\n=== 全局平均 (跨4台机组 x {n_windows}折, n={len(results)}) ===")
    overall = results[[
        "mae_constant", "mae_pooled_naive", "mae_plant_specific",
        "r2_pooled_vs_constant", "r2_plant_specific_vs_constant",
    ]].mean().round(2)
    print(overall.to_string())
    print(f"\n方向性 (训练集 demand-price 相关符号 是否匹配 测试窗口真实符号):")
    print(f"  plant-specific 模型: {results['plant_specific_sign_matches_test'].mean()*100:.0f}% 的折匹配")
    print(f"  pooled naive 模型:   {results['pooled_sign_matches_test'].mean()*100:.0f}% 的折匹配")

    return agg


def plot_example(example_fold):
    """画一张图, 对比某一折里 BW01 真实报价曲线和两种模型的预测曲线, 存成 PNG。

    参数:
        example_fold: run_backtest 留下来的那份示例数据, 如果是 None 就什么都不做
    """
    if example_fold is None:
        return
    first_day = example_fold["INTERVAL_DATETIME"].dt.date.iloc[len(example_fold) // 2]
    day = example_fold[example_fold["INTERVAL_DATETIME"].dt.date == first_day]
    test_window = example_fold.attrs.get("test_window", "?")
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(day["INTERVAL_DATETIME"], day["WEIGHTED_AVG_PRICE"], color="#0b0b0b", linewidth=2, label="Actual")
    ax.plot(day["INTERVAL_DATETIME"], day["pred_a"], color="#2a78d6", linewidth=1.6, linestyle="--",
            label="Predicted (plant-specific, held-out)")
    ax.plot(day["INTERVAL_DATETIME"], day["pred_b"], color="#e34948", linewidth=1.6, linestyle="--",
            label="Predicted (pooled naive, held-out)")
    ax.set_title(f"Held-out backtest: BW01 on {first_day} (test window: {test_window})")
    ax.set_ylabel("Weighted-avg bid price ($/MWh)")
    ax.legend(frameon=False, fontsize=9)
    fig.autofmt_xdate()
    plt.tight_layout()
    plt.savefig("backtest_example_bw01_duckcurve.png", dpi=150)
    plt.close()
    print("\n已保存示例图: backtest_example_bw01_duckcurve.png")


if __name__ == "__main__":
    results, example_fold = run_backtest()
    results.to_csv("backtest_results.csv", index=False)
    print("已保存明细: backtest_results.csv\n")
    summarize(results)
    plot_example(example_fold)
