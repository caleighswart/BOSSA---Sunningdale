"""
Bossa Sunningdale — Bar Agent Config
=====================================
Configuration for the daily alcohol / bar stock brief.
Par levels live in bar/pars.json (extracted from Sava's bar count sheet).

This agent is SEPARATE from the inventory agent: it tracks PRODUCT-SPECIFIC
par levels for bar stock only, not category-wide pars.
"""

import os
import json

# ── TELEGRAM RECIPIENTS ───────────────────────────────────────────────────────
# Add the bar manager's Telegram chat ID once confirmed.
RECIPIENTS = {
    "caleigh":     "7399544281",   # Caleigh (owner)
    # "bar_manager": "TODO",       # Add the bar manager's Telegram chat ID here
}

# ── PILOTLIVE CATEGORIES IN SCOPE ─────────────────────────────────────────────
# Every category represented in Sava's bar count sheet.
BAR_CATEGORIES = {
    "DRAUGHT", "BEER", "CIDER", "CBEV",
    "LIQUEUR", "PREMIX", "PORTSHERRY",
    "BRANDY", "RUM", "WHISKEY", "WHITE SPIR",
    "SWINE", "WWINE", "RWINE",
    "PACKAGING", "VAPES", "HBEV",
}

# Pretty labels used in the Telegram brief (ordered for display).
CATEGORY_LABELS = {
    "DRAUGHT":     "Draught",
    "BEER":        "Beer",
    "CIDER":       "Cider",
    "SWINE":       "Sparkling Wine",
    "WWINE":       "White Wine",
    "RWINE":       "Red Wine",
    "PORTSHERRY":  "Port/Sherry",
    "WHISKEY":     "Whiskey",
    "BRANDY":      "Brandy",
    "RUM":         "Rum",
    "WHITE SPIR":  "Gin / Vodka / Tequila",
    "LIQUEUR":     "Liqueur",
    "PREMIX":      "Premix",
    "CBEV":        "Cold Bev / Mixers",
    "HBEV":        "Hot Bev",
    "VAPES":       "Vapes",
    "PACKAGING":   "Packaging",
}

# Display order of categories in the brief.
CATEGORY_ORDER = [
    "DRAUGHT", "BEER", "CIDER",
    "SWINE", "WWINE", "RWINE", "PORTSHERRY",
    "WHISKEY", "BRANDY", "RUM", "WHITE SPIR", "LIQUEUR", "PREMIX",
    "CBEV", "HBEV", "VAPES", "PACKAGING",
]

# ── SUPPLIERS ─────────────────────────────────────────────────────────────────
# One entry per category. If multiple categories share a supplier, give them
# the same 'whatsapp' number — they will be merged into one order card.
#
# whatsapp: international format, digits only, no + or spaces (e.g. "27821234567")
# contact:  rep's first name, used in the pre-filled WhatsApp message
#
# Leave name/contact/whatsapp as "" until you have the details — the Orders
# tab will still show the products but the WhatsApp button won't appear.
SUPPLIERS = {
    "DRAUGHT":    {"name": "",  "contact": "",  "whatsapp": ""},
    "BEER":       {"name": "",  "contact": "",  "whatsapp": ""},
    "CIDER":      {"name": "",  "contact": "",  "whatsapp": ""},
    "SWINE":      {"name": "",  "contact": "",  "whatsapp": ""},
    "WWINE":      {"name": "",  "contact": "",  "whatsapp": ""},
    "RWINE":      {"name": "",  "contact": "",  "whatsapp": ""},
    "PORTSHERRY": {"name": "",  "contact": "",  "whatsapp": ""},
    "WHISKEY":    {"name": "",  "contact": "",  "whatsapp": ""},
    "BRANDY":     {"name": "",  "contact": "",  "whatsapp": ""},
    "RUM":        {"name": "",  "contact": "",  "whatsapp": ""},
    "WHITE SPIR": {"name": "",  "contact": "",  "whatsapp": ""},
    "LIQUEUR":    {"name": "",  "contact": "",  "whatsapp": ""},
    "PREMIX":     {"name": "",  "contact": "",  "whatsapp": ""},
    "CBEV":       {"name": "",  "contact": "",  "whatsapp": ""},
    "HBEV":       {"name": "",  "contact": "",  "whatsapp": ""},
    "VAPES":      {"name": "",  "contact": "",  "whatsapp": ""},
    "PACKAGING":  {"name": "",  "contact": "",  "whatsapp": ""},
}

# ── THRESHOLDS ────────────────────────────────────────────────────────────────
# Mirrors inventory agent's thresholds so the chef/bar team see a consistent
# escalation model. Stock on hand expressed as fraction of product's par.
CRITICAL_PCT = 0.30   # <30% of par → 🔴 critical, order today
LOW_PCT      = 0.70   # 30-70% of par → 🟡 low, watch
# (>=70% of par → ✅ healthy)

# Negative variance threshold (likely count error) below which we flag.
VARIANCE_CUTOFF = -5

# ── PAR LEVELS ────────────────────────────────────────────────────────────────
# Loaded from pars.json (keys: PilotLive product names; values: par units, or None)
_PARS_PATH = os.path.join(os.path.dirname(__file__), "pars.json")


def load_pars() -> dict[str, float | None]:
    """Return {product_name: par or None} loaded from pars.json."""
    with open(_PARS_PATH, "r") as f:
        return json.load(f)


# Products where we intentionally want to suppress "missing par" flagging
# (e.g. packaging & vapes that haven't been counted on the sheet).
# Leave empty for now — all missing pars will surface in the brief's
# "Par missing" section.
IGNORE_MISSING_PAR: set[str] = set()
