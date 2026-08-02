"""
Generates the three consulting-style exhibit charts used in the README:
  Exhibit 1: 2023 NSW1 price-spike timing distribution (by month + hour), reuses
             spike_diagnostic.py's data
  Exhibit 2: Nov 26 2025 (real duck-curve day) demand vs. BW01 bid price, side by side
  Exhibit 3: corr(demand, weighted_avg_price) across 4 units, compared across three real windows

Colors come from the internal dataviz skill's validated default palette
(references/palette.md); the validator isn't called again here, since these hex
values are copied as-is from the already-validated doc.
"""
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib as mpl

BLUE = "#2a78d6"
ORANGE = "#eb6834"
AQUA = "#1baf7a"
RED = "#e34948"
INK = "#0b0b0b"
INK_SECONDARY = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
SURFACE = "#fcfcfb"

mpl.rcParams.update({
    "font.family": "sans-serif",
    "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans"],
    "axes.edgecolor": GRID,
    "axes.labelcolor": INK_SECONDARY,
    "text.color": INK,
    "xtick.color": MUTED,
    "ytick.color": MUTED,
    "figure.facecolor": SURFACE,
    "axes.facecolor": SURFACE,
    "savefig.facecolor": SURFACE,
})


def clean_axes(ax, keep_bottom=True):
    """Strips the top/right/left spines and leaves only a light grid, for a cleaner consulting-style chart.

    Args:
        ax: a matplotlib Axes object
        keep_bottom: whether to keep the bottom spine, default True
    """
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_visible(False)
    if not keep_bottom:
        ax.spines["bottom"].set_visible(False)
    else:
        ax.spines["bottom"].set_color(MUTED)
    ax.grid(axis="y", color=GRID, linewidth=0.8, zorder=0)
    ax.set_axisbelow(True)


# ---------- Exhibit 1: spike timing ----------
df = pd.read_csv("nsw1_2023.csv", parse_dates=["SETTLEMENTDATE"])
spikes = df[df["RRP"] > 1000].copy()
spikes["month"] = spikes["SETTLEMENTDATE"].dt.month
spikes["hour"] = spikes["SETTLEMENTDATE"].dt.hour

by_month = spikes["month"].value_counts().reindex(range(1, 13), fill_value=0)
by_hour = spikes["hour"].value_counts().reindex(range(0, 24), fill_value=0)

fig, axes = plt.subplots(1, 2, figsize=(12, 4.6))
fig.suptitle(
    "137 price spikes (>$1,000/MWh) in NSW1 in 2023 cluster in the 5-6pm evening ramp, not summer heat",
    fontsize=12.5, fontweight="bold", x=0.02, ha="left", color=INK,
)

colors_m = [RED if m == 5 else BLUE for m in by_month.index]
axes[0].bar(by_month.index.astype(str), by_month.values, color=colors_m, width=0.65, zorder=3)
axes[0].set_title("By month", fontsize=10.5, color=INK_SECONDARY, loc="left")
clean_axes(axes[0])
axes[0].annotate("May: 46 spikes\n(1/3 of the year's total)",
                  xy=(4, 46), xytext=(5.6, 42), fontsize=9, color=RED,
                  arrowprops=dict(arrowstyle="-", color=RED, lw=0.8))

colors_h = [RED if h in (17, 18) else BLUE for h in by_hour.index]
axes[1].bar(by_hour.index.astype(str), by_hour.values, color=colors_h, width=0.65, zorder=3)
axes[1].set_title("By hour of day", fontsize=10.5, color=INK_SECONDARY, loc="left")
clean_axes(axes[1])
axes[1].annotate("5-6pm: 123 of 137 spikes\n(90% of all events)",
                  xy=(17, 69), xytext=(4, 62), fontsize=9, color=RED,
                  arrowprops=dict(arrowstyle="-", color=RED, lw=0.8))

for ax in axes:
    ax.tick_params(axis="x", labelsize=8, rotation=0)
    ax.tick_params(axis="y", labelsize=8)

plt.tight_layout(rect=[0, 0, 1, 0.90])
plt.savefig("exhibit1_spike_timing.png", dpi=160)
plt.close()
print("saved exhibit1_spike_timing.png")

# ---------- Exhibit 2: duck-curve day, demand vs BW01 price ----------
duck = pd.read_csv("./nemosis_cache/scarcity_curve_data_duckcurve_2025nov.csv")
duck["INTERVAL_DATETIME"] = pd.to_datetime(duck["INTERVAL_DATETIME"])
day = duck[(duck["DUID"] == "BW01") & (duck["INTERVAL_DATETIME"].dt.date == pd.Timestamp("2025-11-26").date())]
day = day.sort_values("INTERVAL_DATETIME")

fig, axes = plt.subplots(2, 1, figsize=(11, 6.4), sharex=True, gridspec_kw={"height_ratios": [1, 1.15]})
fig.suptitle(
    "Nov 26, 2025: BW01 bids up on moderate demand, down to the price floor at the actual peak",
    fontsize=12.5, fontweight="bold", x=0.02, ha="left", color=INK,
)

axes[0].plot(day["INTERVAL_DATETIME"], day["TOTALDEMAND"], color=BLUE, linewidth=1.8, zorder=3)
axes[0].set_title("NSW1 regional demand (MW)", fontsize=10, color=INK_SECONDARY, loc="left")
clean_axes(axes[0], keep_bottom=False)

axes[1].plot(day["INTERVAL_DATETIME"], day["WEIGHTED_AVG_PRICE"], color=ORANGE, linewidth=1.8, zorder=3)
axes[1].axhline(0, color=MUTED, linewidth=0.8, zorder=2)
axes[1].set_title("BW01 volume-weighted average bid price ($/MWh)", fontsize=10, color=INK_SECONDARY, loc="left")
clean_axes(axes[1])

axes[1].annotate("9-11am: bids to ~$9,400/MWh\n(demand only ~7,000-9,400 MW)",
                  xy=(pd.Timestamp("2025-11-26 10:00"), 9397), xytext=(pd.Timestamp("2025-11-26 01:30"), 6500),
                  fontsize=9, color=RED, arrowprops=dict(arrowstyle="-", color=RED, lw=0.8))
axes[1].annotate("5-8pm: near price floor\n(demand peaks at 10,760 MW)",
                  xy=(pd.Timestamp("2025-11-26 18:00"), -964), xytext=(pd.Timestamp("2025-11-26 19:30"), 3500),
                  fontsize=9, color=RED, arrowprops=dict(arrowstyle="-", color=RED, lw=0.8))

axes[1].xaxis.set_major_formatter(mpl.dates.DateFormatter("%H:%M"))
for ax in axes:
    ax.tick_params(labelsize=8)

plt.tight_layout(rect=[0, 0, 1, 0.93])
plt.savefig("exhibit2_duckcurve_day.png", dpi=160)
plt.close()
print("saved exhibit2_duckcurve_day.png")

# ---------- Exhibit 3: demand-price correlation by DUID x period ----------
periods = {
    "Typical week (May 2025)": "./nemosis_cache/scarcity_curve_data_202505_week1.csv",
    "Sustained-tight week (Aug 2024)": "./nemosis_cache/scarcity_curve_data_sustained_2024aug.csv",
    "Duck-curve week (Nov 2025)": "./nemosis_cache/scarcity_curve_data_duckcurve_2025nov.csv",
}
period_colors = {"Typical week (May 2025)": BLUE,
                  "Sustained-tight week (Aug 2024)": ORANGE,
                  "Duck-curve week (Nov 2025)": AQUA}

duids = ["BW01", "BW02", "ER01", "ER02"]
rows = []
for period_name, path in periods.items():
    d = pd.read_csv(path)
    for duid, g in d.groupby("DUID"):
        rows.append({"period": period_name, "DUID": duid,
                     "corr": g["TOTALDEMAND"].corr(g["WEIGHTED_AVG_PRICE"])})
corr_df = pd.DataFrame(rows)

fig, ax = plt.subplots(figsize=(9.5, 5))
fig.suptitle(
    "Bayswater consistently prices against demand; Eraring's pattern is weaker and less stable",
    fontsize=12, fontweight="bold", x=0.02, ha="left", color=INK,
)
n_periods = len(periods)
width = 0.24
x = range(len(duids))
for i, (period_name, color) in enumerate(period_colors.items()):
    vals = [corr_df[(corr_df["DUID"] == d) & (corr_df["period"] == period_name)]["corr"].iloc[0] for d in duids]
    offsets = [xi + (i - (n_periods - 1) / 2) * width for xi in x]
    ax.bar(offsets, vals, width=width * 0.92, label=period_name, color=color, zorder=3)

ax.axhline(0, color=MUTED, linewidth=1)
ax.set_xticks(list(x))
ax.set_xticklabels(duids, fontsize=10)
ax.set_ylabel("corr(regional demand, weighted-avg bid price)", fontsize=9.5, color=INK_SECONDARY)
clean_axes(ax)
ax.legend(frameon=False, fontsize=9, loc="lower left", ncols=1)
ax.tick_params(labelsize=9)

plt.tight_layout(rect=[0, 0, 1, 0.93])
plt.savefig("exhibit3_correlation_by_plant.png", dpi=160)
plt.close()
print("saved exhibit3_correlation_by_plant.png")
