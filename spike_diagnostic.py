"""
诊断:RRP尖峰(>$1000/MWh)在2023年NSW1的时间分布
输入:nsw1_2023.csv (SETTLEMENTDATE, TOTALDEMAND, RRP 等列)
"""
import pandas as pd

df = pd.read_csv("nsw1_2023.csv", parse_dates=["SETTLEMENTDATE"])

SPIKE_THRESHOLD = 1000  # $/MWh, 可以自己改成 5000 看更极端的情况

spikes = df[df["RRP"] > SPIKE_THRESHOLD].copy()
spikes["month"] = spikes["SETTLEMENTDATE"].dt.month
spikes["hour"] = spikes["SETTLEMENTDATE"].dt.hour

print(f"总尖峰次数 (RRP > ${SPIKE_THRESHOLD}/MWh): {len(spikes)}")
print()

print("按月份分布:")
print(spikes["month"].value_counts().sort_index().to_string())
print()

print("按小时分布:")
print(spikes["hour"].value_counts().sort_index().to_string())
print()

print("尖峰时段 vs 全年 平均需求对比:")
print(f"  尖峰时段平均需求: {spikes['TOTALDEMAND'].mean():.1f} MW")
print(f"  全年平均需求:     {df['TOTALDEMAND'].mean():.1f} MW")
print(f"  全年最高需求:     {df['TOTALDEMAND'].max():.1f} MW")

# 可选:画图（需要 matplotlib）
try:
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.5))
    spikes["month"].value_counts().sort_index().plot(kind="bar", ax=axes[0], color="#C4453E")
    axes[0].set_title(f"Spikes >${SPIKE_THRESHOLD}/MWh by month (2023)")
    axes[0].set_xlabel("Month")
    spikes["hour"].value_counts().sort_index().plot(kind="bar", ax=axes[1], color="#3B6FA0")
    axes[1].set_title(f"Spikes >${SPIKE_THRESHOLD}/MWh by hour (2023)")
    axes[1].set_xlabel("Hour of day")
    plt.tight_layout()
    plt.savefig("spike_time_distribution.png", dpi=130)
    print("\n图已保存: spike_time_distribution.png")
except ImportError:
    pass
