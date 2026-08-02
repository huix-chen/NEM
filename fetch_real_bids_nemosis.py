"""
Template for pulling real generator bids (BIDDAYOFFER_D / BIDPEROFFER_D) and real
generator output (DISPATCH_UNIT_SCADA) via NEMOSIS.

Requires network access to nemweb.com.au / aemo.com.au, so it must run on a local
machine, not in this sandbox (whose network allowlist excludes both).

Install:
    pip install nemosis

Notes:
    - BIDDAYOFFER_D / BIDPEROFFER_D are missing from AEMO's archive between
      2021-03 and 2024-07 (a known NEMOSIS issue). Pick a window outside that gap.
    - Bid tables are large (0.5-1.5GB compressed per month). Start with a few days
      to a month, not a full year.
    - The first run downloads the raw zip into raw_data_cache and converts it to
      a parquet cache; later runs for the same period read straight from cache.
"""
from nemosis import dynamic_data_compiler

# ---------- Config ----------
RAW_DATA_CACHE = "./nemosis_cache"   # change to any local path
START_TIME = "2025/05/01 00:00:00"   # start with the month with the most spikes (May)
END_TIME = "2025/05/08 00:00:00"     # one week first, widen once it works
# BIDDAYOFFER_D / BIDPEROFFER_D are missing between 2021-03 and 2024-07 (known
# NEMOSIS issue). Pick a window outside that gap or you'll get NoDataToReturn.

# The four units under study (NSW1 coal, Bayswater + Eraring)
PEAKER_DUIDS = ["ER01", "ER02", "BW01", "BW02"]

# ---------- 1. Real bid data (what each unit is willing to sell for) ----------
# BIDDAYOFFER_D: 10-band daily price ladder per DUID
bid_price_bands = dynamic_data_compiler(
    START_TIME, END_TIME, "BIDDAYOFFER_D", RAW_DATA_CACHE,
    filter_cols=["DUID"], filter_values=(PEAKER_DUIDS,),
)
print("BIDDAYOFFER_D sample:")
print(bid_price_bands.head())

# BIDPEROFFER_D: MW available per band per DUID per 5-minute interval
bid_volume_bands = dynamic_data_compiler(
    START_TIME, END_TIME, "BIDPEROFFER_D", RAW_DATA_CACHE,
    filter_cols=["DUID"], filter_values=(PEAKER_DUIDS,),
)
print("\nBIDPEROFFER_D sample:")
print(bid_volume_bands.head())

# ---------- 2. Real output data (what each unit actually generated) ----------
unit_scada = dynamic_data_compiler(
    START_TIME, END_TIME, "DISPATCH_UNIT_SCADA", RAW_DATA_CACHE,
    filter_cols=["DUID"], filter_values=(PEAKER_DUIDS,),
)
print("\nDISPATCH_UNIT_SCADA sample:")
print(unit_scada.head())

# ---------- 3. What this data feeds into next ----------
# a) Merge bid_price_bands + bid_volume_bands on DUID + interval to reconstruct
#    each unit's full 5-minute bid ladder (10 price bands x 10 volume bands).
# b) Join that ladder to system reserve margin (derivable from nsw1_2023.csv)
#    to see the real "tighter reserve margin -> more volume at high price bands"
#    curve, which replaces the hand-tuned alpha formula in nem_mvp.py.
# c) unit_scada checks whether a unit was actually dispatched and how much, for
#    comparison against ABM-simulated dispatch results.
