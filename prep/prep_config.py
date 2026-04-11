"""
Bossa Sunningdale — Prep Bot Config
=====================================
Configuration for the daily prep variance report sent to the head chef.
"""

# ── TELEGRAM RECIPIENT ────────────────────────────────────────────────────────
# Set to Caleigh for testing — swap for head chef's Telegram chat ID when ready
CHEF_CHAT_ID = "7399544281"

# ── PREP CATEGORIES ───────────────────────────────────────────────────────────
# PilotLive categories relevant to kitchen prep.
# Only items in these categories appear in the chef's variance report.
PREP_CATEGORIES = {
    "CHICKEN", "MEAT", "PORK", "SEAFOOD",
    "SAUCE", "FVEG", "DAIRY", "CHEESE",
    "CHIPS", "GROCERIES", "FLOUR DOUGH",
}

# ── VARIANCE THRESHOLDS ───────────────────────────────────────────────────────
# Variance = (Opening + Purchases − TheoreticalUsage) − ClosingStock
# Negative = used more than theory  |  Positive = used less than theory

# Minimum absolute variance to show (filters rounding noise)
MIN_VARIANCE = 0.5

# % of theoretical usage that triggers HIGH alert
HIGH_VARIANCE_PCT = 0.20   # 20%

# % of theoretical usage that triggers WATCH alert
WATCH_VARIANCE_PCT = 0.10  # 10%
