"""
Bossa Sunningdale — Prep Bot Config
====================================
Defines which items appear on the daily chef prep list and how
they map to PilotLive stock categories.

The prep bot reads current stock levels and tells the head chef
what needs to be prepped before service.
"""

# ── TELEGRAM RECIPIENT ────────────────────────────────────────────────────────
# Head chef's Telegram chat ID — add once chef has messaged the bot
CHEF_CHAT_ID = "7399544281"   # Caleigh — test recipient (swap for head chef's ID when ready)

# ── SERVICE TIMES ─────────────────────────────────────────────────────────────
SERVICE_START = "11:00"
PREP_DEADLINE = "10:30"

# ── PREP ITEMS ────────────────────────────────────────────────────────────────
# Each entry defines a prep task linked to PilotLive stock categories.
#
# Fields:
#   cats        PilotLive category name(s) to watch
#   action      Verb shown on the prep list ("Marinate", "Make", "Portion", etc.)
#   unit        Unit for quantities shown to the chef
#   par         Target quantity to have prepped and ready for service
#   urgent_pct  If stock < this % of par → shows as URGENT (do first)
#   low_pct     If stock < this % of par → shows in TODAY'S PREP
#   note        Optional tip shown alongside the item

PREP_ITEMS = [
    # ── PROTEINS ──────────────────────────────────────────────────────────────
    {
        "label":      "Chicken",
        "cats":       ["CHICKEN"],
        "action":     "Marinate",
        "unit":       "portions",
        "par":        30,
        "urgent_pct": 0.30,
        "low_pct":    0.70,
        "note":       "Peri-peri & lemon herb",
    },
    {
        "label":      "Pork Ribs",
        "cats":       ["PORK"],
        "action":     "Marinate & portion",
        "unit":       "portions",
        "par":        20,
        "urgent_pct": 0.30,
        "low_pct":    0.70,
        "note":       "Overnight minimum — check if yesterday's batch is done",
    },
    {
        "label":      "Beef",
        "cats":       ["MEAT"],
        "action":     "Portion & season",
        "unit":       "portions",
        "par":        15,
        "urgent_pct": 0.30,
        "low_pct":    0.70,
        "note":       None,
    },
    {
        "label":      "Seafood",
        "cats":       ["SEAFOOD"],
        "action":     "Thaw & portion",
        "unit":       "portions",
        "par":        12,
        "urgent_pct": 0.30,
        "low_pct":    0.70,
        "note":       "Check freshness on delivery",
    },

    # ── SAUCES & MISE EN PLACE ────────────────────────────────────────────────
    {
        "label":      "Sauces",
        "cats":       ["SAUCE"],
        "action":     "Make",
        "unit":       "units",
        "par":        8,
        "urgent_pct": 0.30,
        "low_pct":    0.70,
        "note":       "Peri-peri, chimichurri, house dressing",
    },

    # ── FRESH PRODUCE ─────────────────────────────────────────────────────────
    {
        "label":      "Fresh Veg",
        "cats":       ["FVEG"],
        "action":     "Wash & prep",
        "unit":       "kg",
        "par":        5,
        "urgent_pct": 0.30,
        "low_pct":    0.70,
        "note":       "Salads, garnish, sides",
    },

    # ── DAIRY & CHEESE ────────────────────────────────────────────────────────
    {
        "label":      "Dairy",
        "cats":       ["DAIRY"],
        "action":     "Portion",
        "unit":       "units",
        "par":        5,
        "urgent_pct": 0.30,
        "low_pct":    0.70,
        "note":       None,
    },
    {
        "label":      "Cheese",
        "cats":       ["CHEESE"],
        "action":     "Slice & portion",
        "unit":       "units",
        "par":        10,
        "urgent_pct": 0.30,
        "low_pct":    0.70,
        "note":       None,
    },

    # ── CHIPS / SIDES ─────────────────────────────────────────────────────────
    {
        "label":      "Chips",
        "cats":       ["CHIPS"],
        "action":     "Par-fry batch",
        "unit":       "kg",
        "par":        15,
        "urgent_pct": 0.30,
        "low_pct":    0.70,
        "note":       "Par-fry before service rush",
    },
]

# Categories excluded from all prep analysis
EXCLUDE = {
    "CLEANING", "CLOTHING", "CUTLERY & CROCKERY", "DEPOSITS", "EQUIPMENT",
    "STATIONERY", "PACKAGING", "WOOD", "VAPES", "Total", "Expense", "GAS",
    "OWNERS CHOICE", "RECIPE", "SLO JO",
}
