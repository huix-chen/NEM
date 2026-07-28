# NSW1's 5–6pm Problem: Why Naive Scarcity Pricing Won't Predict the Next Price Spike

*A data-driven diagnosis of evening price volatility in Australia's National Electricity Market, built on real AEMO dispatch and bidding data — not assumptions.*

---

## Executive Summary

NSW1 recorded 137 price spikes above $1,000/MWh in 2023. Ninety percent of them landed in a single two-hour window: 5–6pm. This isn't random volatility — it's the evening ramp of the duck curve, and it is going to get worse before it gets better as more coal exits the grid.

We went looking for the mechanism generators use to price into that window, on the assumption that it would look like classic scarcity pricing — price rises as reserve margin falls. **It doesn't.** Using real AEMO bid submissions (not modeled assumptions) across three independent real events, we find that Bayswater's two units consistently price *against* demand — cheaper at the peak, more expensive when demand is merely moderate — while Eraring's units show a materially weaker and less stable version of the same pattern. Any model that assumes a single generic scarcity curve for "coal baseload" will misprice this market, and will misprice it differently once Eraring retires.

**What we recommend:** replace generic scarcity-alpha assumptions with plant-specific, demand-indexed bidding curves estimated directly from historical bid microdata, and validate before using in any policy or investment scenario.

---

## 1. The Problem: Price Spikes Aren't Spread Across the Year — They're Concentrated in a Two-Hour Window

In 2023, NSW1 spent most of the year trading in the $50–150/MWh range. But 137 times, price broke $1,000/MWh — and once, hit the market price cap of $16,599/MWh. Demand at the moment of a spike averaged 10,041 MW, 34% above the annual average of 7,469 MW.

The distribution of *when* these spikes happen is the real story:

![Exhibit 1: spike timing](exhibit1_spike_timing.png)

- **May alone accounts for a third of the year's spikes** — not the hottest month, which rules out simple heatwave-driven summer peak demand as the main story.
- **90% of all spikes occur at 5–6pm** — the exact window where rooftop and utility solar drop off faster than evening demand rises. This is the duck curve's neck, and it is a structural, recurring feature of the market, not a tail event.

## 2. Why It Matters: The Fleet That's Supposed to Fill This Gap Is Shrinking, and We Don't Understand How It Actually Bids

Two things make this more than an academic curiosity:

- **Retailers and consumers are directly exposed.** A handful of 5–6pm intervals each year can dominate a retailer's wholesale cost base for the entire period, and ultimately flow through to retail tariffs and hedging costs.
- **The units expected to cover this window are aging out.** Bayswater and Eraring — the two coal stations behind every DUID in this analysis — together represent close to 3,000 MW of NSW1's dispatchable capacity. Eraring in particular is on a public retirement timeline. Whatever replaces that capacity (storage, gas peakers, demand response) will be sized and dispatched based on models of *how the current fleet behaves under stress.* If those models assume a textbook scarcity curve and the real fleet doesn't bid that way, the resulting capacity and investment signals will be wrong in the years that matter most — precisely as the duck curve deepens and firm capacity gets scarcer.

Getting the *mechanism* right — not just the demand-side symptom — is the difference between a model that predicts the next spike and one that's calibrated to a fiction.

## 3. What We Recommend: Stop Assuming a Generic Scarcity Curve — Estimate Plant-Specific Bidding Behavior from Real Data

We tested the standard assumption directly: pull real `BIDDAYOFFER_D`/`BIDPEROFFER_D` bid submissions for Bayswater (BW01, BW02) and Eraring (ER01, ER02) — the two NSW1 coal stations most exposed to this window — and real AEMO reserve-margin and demand data (`DISPATCHREGIONSUM`), across three independent real weeks chosen specifically to stress-test the relationship:

| Window | What it represents | Reserve margin range |
|---|---|---|
| May 2025 | Typical, uneventful week | 1,290 – 9,581 MW |
| Aug 2024 | Genuinely sustained tight week (day-average RRP $2,145/MWh) | 792 – 8,767 MW |
| Nov 2025 | Classic duck-curve day (RRP swung from –$999 to the $20,300 cap in a single day) | 1,131 – 11,245 MW |

The naive hypothesis — price rises as reserve margin tightens — **failed in all three windows.** What we found instead:

![Exhibit 3: correlation by plant](exhibit3_correlation_by_plant.png)

- **Bayswater (BW01, BW02) consistently prices *against* demand** — correlation between regional demand and its volume-weighted average bid price runs -0.5 to -0.8 in every single window tested, calm or stressed.
- **Eraring's pattern is weaker and unstable** — near zero (even slightly positive) in the calm week, only becoming meaningfully negative in the two stressed windows. Same fuel type, same region, different bidding logic — plausibly linked to Eraring's later position in its own retirement timeline versus Bayswater's.

One real day makes the mechanism concrete. On November 26, 2025:

![Exhibit 2: duck curve day](exhibit2_duckcurve_day.png)

BW01 bid its capacity up to a blended average of ~$9,400/MWh at 9–11am, when demand was a moderate 7,000–9,400 MW — and bid down to the market price floor during the day's *actual* demand peak of 10,760 MW at 5–8pm. That's the opposite of textbook scarcity pricing: the unit prices low exactly when it wants to guarantee dispatch and capture peak volume, and prices its "optional" capacity high when running isn't strictly necessary. This self-preservation logic, not a scarcity markup, is what a replacement model needs to capture — and it needs to capture it per plant, not per fuel type.

**Concretely, we recommend:**
1. Replace the single hand-tuned "scarcity alpha" parameter in dispatch/price simulation models with plant-specific curves indexed to demand (or a similarly-behaved variable), estimated directly from each unit's bid history.
2. Treat Bayswater and Eraring as behaviorally distinct even though they're the same fuel type and region — pooling them into one "coal baseload" curve erases the signal that matters.
3. Before using any such model for policy or investment scenario work (storage sizing, demand-response targeting, Market Price Cap / Cumulative Price Threshold analysis), validate it against a real historical event where the Cumulative Price Threshold or Market Price Cap was actually triggered.

## 4. Expected Benefit: A Model That's Right About the 5–6pm Window, Not Just Right on Average

A demand-indexed, plant-specific recalibration should materially improve forecast accuracy for exactly the intervals that matter most financially — the narrow, high-stakes evening window that a generic scarcity curve is least equipped to get right, since it's precisely where our data shows the naive assumption breaks hardest.

The practical payoff is decision quality, not just model fit:
- **Investment timing** — sizing and staging storage/peaker capacity against a fleet-behavior model that reflects what these plants actually do, not what a textbook says they should do.
- **Policy calibration** — Market Price Cap and Cumulative Price Threshold settings informed by realistic bidding responses, not an averaged fiction that smooths over the Bayswater/Eraring split.
- **Retirement-readiness** — a model that already treats Eraring and Bayswater as distinct is positioned to answer "what happens to the 5–6pm window when Eraring leaves" without needing to be rebuilt from scratch.

**This is Phase 1 of the project — diagnosis and mechanism, not yet a validated forecasting tool.** The natural next step (Phase 2) is a backtest against a historical date where the Market Price Cap or Cumulative Price Threshold was actually adjusted, freezing the model beforehand and checking whether it correctly anticipates the post-adjustment shift. That's what would turn this from "a data-driven diagnosis" into "a validated analytical tool" — and quantify the forecast-accuracy improvement in dollar terms rather than correlation coefficients.

---

## Appendix: Data & Methodology

All figures in this report are computed from real AEMO market data pulled via [NEMOSIS](https://github.com/UNSW-CEEM/NEMOSIS), not synthetic or assumed data.

| Data | Source table | Used for |
|---|---|---|
| 2023 half-hourly demand & price, NSW1 | `nsw1_2023.csv` (pre-fetched `DISPATCHREGIONSUM`-equivalent) | Exhibit 1 — spike timing diagnosis |
| Bid price ladders | `BIDDAYOFFER_D`, filtered to `BIDTYPE == ENERGY` | 10-band daily price ladder per DUID |
| Bid volume ladders | `BIDPEROFFER_D`, filtered to `BIDTYPE == ENERGY`, deduplicated to the latest rebid in effect per interval | 5-minute volume-per-band per DUID |
| Regional demand & availability | `DISPATCHREGIONSUM` | Reserve margin = `AVAILABLEGENERATION − TOTALDEMAND` (AEMO's own live availability figure, not nameplate capacity) |
| Generator identity | `duid_generator_registry.csv` (AEMO NEM Registration and Exemption List) | Confirmed BW01/BW02 = Bayswater Power Station (660 MW reg cap each), ER01/ER02 = Eraring Power Station (720 MW reg cap each), both NSW1 coal |

**Units analyzed:** BW01, BW02 (Bayswater), ER01, ER02 (Eraring) — the four largest coal DUIDs in NSW1.

**A note on data availability:** `BIDDAYOFFER_D`/`BIDPEROFFER_D` have a known gap in AEMO's archive between March 2021 and July 2024 (documented in NEMOSIS's own release notes). This is why the three test windows above are drawn from May 2025, August 2024, and November 2025 rather than the original 2023 spike period itself — real bid data for 2023 does not exist in the public archive. The spike-timing diagnosis (Exhibit 1) uses 2023 demand/price data directly; the bidding-behavior analysis (Exhibits 2–3) necessarily uses the closest available real bid data, chosen to span a calm week, a genuinely tight week, and a duck-curve week rather than a single arbitrary sample.

**Per-interval bid reconstruction:** `BIDPEROFFER_D` restates every remaining interval's volume bands each time a unit rebids intraday, so a naive join produces many superseded rows per interval. We keep only the most recent rebid actually in effect (`OFFERDATE <= INTERVAL_DATETIME`, latest `OFFERDATE` wins) before computing each unit's volume-weighted average bid price per 5-minute interval.

## Repository Structure

```
spike_diagnostic.py           # 2023 NSW1 spike-timing diagnosis (Exhibit 1 data)
fetch_real_bids_nemosis.py    # Template: pull real bid + SCADA data via NEMOSIS
merge_bid_bands.py            # Merge BIDDAYOFFER_D + BIDPEROFFER_D into a full 10-band ladder
find_real_spike_days.py       # Scan 2024-08 onward for genuine NSW1 price-spike days
scarcity_curve.py             # Core analysis: real bid price vs. real reserve margin / demand
make_exhibits.py              # Generates exhibit1/2/3 PNGs used in this README
nsw1_2023.csv                 # 2023 NSW1 half-hourly demand & price
duid_generator_registry.csv   # AEMO generator registration list
nemosis_cache/                # Cached NEMOSIS downloads (feather format; raw CSVs pruned to save disk)
```

**To reproduce:** `pip install nemosis pandas numpy matplotlib`, then run `fetch_real_bids_nemosis.py` once to populate the cache, followed by `scarcity_curve.py <window_label>` for any of `sustained_2024aug` / `duckcurve_2025nov`, and `make_exhibits.py` to regenerate the charts above.
