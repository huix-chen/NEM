"""
Phase 2: leave-one-window-out backtest of scarcity_curve.py's core claim, that a
plant-specific, demand-indexed bidding curve predicts better than one generic
curve pooled across all four units.

Background: the original plan was to validate against a real AEMO MPC/CPT event
(the 2024-05-08~15 NSW1 Administered Pricing period), but that window falls
inside the gap where AEMO's bid archive has no BIDDAYOFFER_D/BIDPEROFFER_D data,
so it can't be tested. Instead this runs leave-one-window-out cross-validation
over every real window scarcity_curve.py has produced: each window is held out
in turn while the rest train the model. Not the regulatory-event backtest the
README originally described, but still a strict out-of-sample test.

Two models are compared (both use TOTALDEMAND only, trained and tested on
disjoint data):
  Model A "plant-specific": one demand-binned average price curve per DUID
                             (non-parametric, can capture a non-monotonic shape)
  Model B "pooled naive":   one demand-binned average price curve across all
                             four units (the generic "scarcity alpha" approach
                             the README argues against)
  Baseline "constant":      predict the DUID's training-period average price

An earlier version used a straight-line fit (price = a + b*demand). README
Exhibit 2 shows BW01's real behavior is non-monotonic (bids at the floor at the
actual peak, higher at moderate demand, closer to an inverted U), which a line
can't capture and which would understate the value of a plant-specific curve.
This version bins by demand and takes the mean per bin instead, a non-parametric,
regime-based fit that makes no assumption about the curve's shape.

Metrics: out-of-sample MAE and out-of-sample R² (relative to the constant baseline).
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
N_BINS = 8  # ~4000 training rows per unit -> ~500 points per bin, stable without being too coarse
MIN_ROWS_PER_FOLD = 50  # skip a fold if a DUID has fewer rows than this in train or test
MIN_TRAIN_WINDOWS = 3  # need at least this many earlier months before the first test fold


def load_windows():
    """Auto-discovers every scarcity_curve_data_*.parquet under CACHE_DIR.

    Windows are no longer hardcoded: after running fetch_monthly_bids.py, newly
    pulled months are picked up automatically and the fold count grows with them.
    Empty windows (e.g. the current month, not yet fully archived by AEMO) are
    skipped, since corrcoef crashes on an empty array (a known numpy quirk with
    length-0/1 inputs).
    """
    paths = sorted(glob.glob(f"{CACHE_DIR}/scarcity_curve_data_*.parquet"))
    if not paths:
        raise FileNotFoundError(f"No scarcity_curve_data_*.parquet found under {CACHE_DIR}, run scarcity_curve.py first")
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
    print(f"Found {len(data)} windows: {list(data.keys())}")
    if skipped_empty:
        print(f"Skipped {len(skipped_empty)} empty windows (likely not fully archived yet): {skipped_empty}")
    return data


def fit_binned(x, y, n_bins=N_BINS):
    """Bins x (demand) by quantile and takes the mean of y per bin.

    Non-parametric: makes no assumption about the curve's shape, so it can fit a
    non-monotonic relationship (e.g. an inverted U).
    """
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
    """Predicts y for new x values using the bins from fit_binned.

    Args:
        x: array of demand values to predict for
        interior_edges: bin boundaries returned by fit_binned
        bin_means: per-bin means returned by fit_binned

    Returns:
        Predicted value for each x (the mean of whichever bin it falls into).
    """
    bin_idx = np.searchsorted(interior_edges, np.asarray(x), side="right")
    return bin_means[bin_idx]


def mae(actual, pred):
    """Mean absolute error between predicted and actual values, in the same units as the data ($/MWh)."""
    return float(np.mean(np.abs(actual - pred)))


def r2_vs_baseline(actual, pred, baseline_pred):
    """R² of a model relative to a baseline: 1 is a perfect fit, 0 means no better
    than the baseline, negative means worse than the baseline.

    Args:
        actual: true values
        pred: model's predicted values
        baseline_pred: baseline's predicted values (e.g. the historical average)

    Returns:
        R² score, closer to 1 is better.
    """
    ss_res = np.sum((actual - pred) ** 2)
    ss_tot = np.sum((actual - baseline_pred) ** 2)
    return 1 - ss_res / ss_tot if ss_tot > 0 else np.nan


def run_backtest():
    """Runs a walk-forward backtest: windows are sorted chronologically, and each
    test month is only ever predicted from months strictly before it.

    An earlier version trained on "all other windows" regardless of order, which
    let later months leak into predictions for earlier ones, an information
    leak a genuine forecasting use case would never have. Bidding strategy is
    also not stationary (see the Eraring retirement-negotiation timeline), so
    predicting the past from the future would flatter the result.

    Each fold compares three predictors: plant-specific, pooled naive, and a
    constant baseline (the average of everything trained on so far), scored on
    how well they predict the held-out month.

    Returns:
        results: one row per (test window, DUID) fold, as a DataFrame.
        example_fold: BW01's data from one fold, kept for plotting predicted vs. actual.
    """
    data = load_windows()
    all_labels = sorted(data.keys())  # "monthly_YYYYMM" sorts chronologically as strings
    rows = []
    example_fold = None  # keep one fold's detail for the example chart
    last_actual_corr = {}  # per-DUID, the previous month's actual correlation, for the persistence baseline

    for i in range(MIN_TRAIN_WINDOWS, len(all_labels)):
        test_label = all_labels[i]
        train_labels = all_labels[:i]  # only months strictly before the test month
        train_df = pd.concat([data[l] for l in train_labels], ignore_index=True)
        test_df = data[test_label]

        # Model B: pooled, all four units binned together (the naive "one scarcity curve fits all" approach)
        edges_pool, means_pool = fit_binned(train_df["TOTALDEMAND"], train_df["WEIGHTED_AVG_PRICE"])

        for duid in DUIDS:
            train_sub = train_df[train_df["DUID"] == duid]
            test_sub = test_df[test_df["DUID"] == duid].sort_values("INTERVAL_DATETIME")

            # Skip a fold if a DUID has too few points in train or test (e.g. a
            # month with only a few days of data) -- too few to be meaningful,
            # and can crash corrcoef/binning outright.
            if len(train_sub) < MIN_ROWS_PER_FOLD or len(test_sub) < MIN_ROWS_PER_FOLD:
                print(f"Skipping {test_label}/{duid}: {len(train_sub)} train rows, {len(test_sub)} test rows, too few")
                continue

            # Model A: plant-specific
            edges_a, means_a = fit_binned(train_sub["TOTALDEMAND"], train_sub["WEIGHTED_AVG_PRICE"])
            # Baseline: this DUID's training-period average price (constant prediction)
            const_pred_value = train_sub["WEIGHTED_AVG_PRICE"].mean()

            actual = test_sub["WEIGHTED_AVG_PRICE"].to_numpy()
            demand = test_sub["TOTALDEMAND"].to_numpy()
            pred_a = predict_binned(demand, edges_a, means_a)
            pred_b = predict_binned(demand, edges_pool, means_pool)
            pred_const = np.full_like(actual, const_pred_value)

            # Directional check: does the sign of the demand-price relationship
            # learned in training match the sign actually observed in the held-out
            # window? (A binned model has no single "slope", so this compares
            # correlation signs on train vs. test; descriptive only, not used in prediction.)
            train_corr = np.corrcoef(train_sub["TOTALDEMAND"], train_sub["WEIGHTED_AVG_PRICE"])[0, 1]
            train_pool_corr = np.corrcoef(train_df["TOTALDEMAND"], train_df["WEIGHTED_AVG_PRICE"])[0, 1]
            test_corr = np.corrcoef(demand, actual)[0, 1]
            # bool(...) matters: np.sign(...) == np.sign(...) is a numpy.bool_,
            # and storing numpy.bool_ in an object-dtype column makes
            # pandas.Series.mean() silently wrong (verified: with pandas 2.3.3 /
            # numpy 2.2.6, any True in such a column makes .mean() return 1/n
            # regardless of the real proportion). Plain Python bool avoids it.
            plant_specific_sign_match = bool(np.sign(train_corr) == np.sign(test_corr))
            pooled_sign_match = bool(np.sign(train_pool_corr) == np.sign(test_corr))

            # Persistence baseline: predict this month's sign is whatever last
            # month's actual sign was, no model at all. Context for how much the
            # model's direction match rate is actually buying you.
            prev_corr = last_actual_corr.get(duid)
            persistence_sign_match = bool(np.sign(prev_corr) == np.sign(test_corr)) if prev_corr is not None else np.nan
            last_actual_corr[duid] = test_corr

            rows.append({
                "test_window": test_label,
                "DUID": duid,
                "train_corr_plant_specific": train_corr,
                "train_corr_pooled": train_pool_corr,
                "test_actual_demand_price_corr": test_corr,
                "plant_specific_sign_matches_test": plant_specific_sign_match,
                "pooled_sign_matches_test": pooled_sign_match,
                "persistence_sign_matches_test": persistence_sign_match,
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
    """Prints run_backtest's results as a few summary tables.

    Prints, in order: per-fold detail, per-DUID aggregates (how much better
    plant-specific is than pooled), the global average, and the rate at which
    the direction learned in training matched the direction seen in testing.

    Args:
        results: the detail DataFrame returned by run_backtest

    Returns:
        The per-DUID aggregate DataFrame.
    """
    print("=== Per-fold (test_window x DUID) detail ===")
    print(results.round(2).to_string(index=False))

    n_windows = results["test_window"].nunique()
    print(f"\n=== Per-DUID aggregate ({n_windows} folds) ===")
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

    print(f"\n=== Global average (4 DUIDs x {n_windows} folds, n={len(results)}) ===")
    overall = results[[
        "mae_constant", "mae_pooled_naive", "mae_plant_specific",
        "r2_pooled_vs_constant", "r2_plant_specific_vs_constant",
    ]].mean().round(2)
    print(overall.to_string())
    print(f"\nDirection match (training-set demand-price correlation sign vs. test-window actual sign):")
    print(f"  plant-specific model:  {results['plant_specific_sign_matches_test'].mean()*100:.0f}% of folds")
    print(f"  pooled naive model:    {results['pooled_sign_matches_test'].mean()*100:.0f}% of folds")
    persistence = results["persistence_sign_matches_test"].dropna()
    print(f"  persistence baseline:  {persistence.mean()*100:.0f}% of folds (predict this month = last month's actual sign, no model at all, n={len(persistence)})")
    always_negative = (results["test_actual_demand_price_corr"] < 0).mean()
    print(f"  'always guess negative' baseline: {always_negative*100:.0f}% of folds (context: how skewed the sign distribution already is)")

    return agg


def plot_example(example_fold):
    """Plots BW01's real bid price against both models' predictions for one fold, saved as a PNG.

    Args:
        example_fold: the sample data kept by run_backtest; does nothing if None.
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
    print("\nSaved example chart: backtest_example_bw01_duckcurve.png")


if __name__ == "__main__":
    results, example_fold = run_backtest()
    results.to_csv("backtest_results.csv", index=False)
    print("Saved detail: backtest_results.csv\n")
    summarize(results)
    plot_example(example_fold)
