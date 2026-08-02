"""
Counts NSW1 RRP spikes (>$1000/MWh) in 2023 and breaks them down by month and hour.
Input: nsw1_2023.csv (SETTLEMENTDATE, TOTALDEMAND, RRP, ...).
"""
import pandas as pd

df = pd.read_csv("nsw1_2023.csv", parse_dates=["SETTLEMENTDATE"])

SPIKE_THRESHOLD = 1000  # $/MWh, raise to e.g. 5000 to look at more extreme events

spikes = df[df["RRP"] > SPIKE_THRESHOLD].copy()
spikes["month"] = spikes["SETTLEMENTDATE"].dt.month
spikes["hour"] = spikes["SETTLEMENTDATE"].dt.hour

print(f"Total spikes (RRP > ${SPIKE_THRESHOLD}/MWh): {len(spikes)}")
print()

print("By month:")
print(spikes["month"].value_counts().sort_index().to_string())
print()

print("By hour:")
print(spikes["hour"].value_counts().sort_index().to_string())
print()

print("Spike-period demand vs. annual demand:")
print(f"  Average demand during spikes: {spikes['TOTALDEMAND'].mean():.1f} MW")
print(f"  Annual average demand:        {df['TOTALDEMAND'].mean():.1f} MW")
print(f"  Annual peak demand:           {df['TOTALDEMAND'].max():.1f} MW")

# Optional chart (needs matplotlib)
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
    print("\nSaved: spike_time_distribution.png")
except ImportError:
    pass
