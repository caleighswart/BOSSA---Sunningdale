"""
Bossa Sunningdale — Inventory Agent Config
==========================================
Fill in PAR levels and supplier details once confirmed with Sava.
All placeholder values marked with TODO.
"""

# ── TELEGRAM ──────────────────────────────────────────────────────────────────
# Set these as GitHub Secrets: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
# Sava's chat ID to be added once he installs the bot
RECIPIENTS = {
    "caleigh": "7399544281",          # Caleigh (test/owner)
    # "sava": "TODO",                 # Add Sava's Telegram chat ID here
}

# ── PILOTLIVE CLOUD ───────────────────────────────────────────────────────────
# Credentials stored as GitHub Secrets: PILOTLIVE_USERNAME, PILOTLIVE_PASSWORD
# The agent logs into cloud.pilotlive.co.za and downloads the report automatically.
# Set PILOTLIVE_DEBUG=1 locally to enable screenshots for troubleshooting.

# ── SUPPLIERS ─────────────────────────────────────────────────────────────────
# TODO: Fill in supplier details once confirmed with Sava
SUPPLIERS = {
    "protein": {
        "name":     "TODO — Protein Supplier",
        "contact":  "TODO — Name",
        "whatsapp": "TODO — +27XXXXXXXXX",
        "email":    "TODO — email@supplier.co.za",
        "categories": ["CHICKEN", "MEAT", "PORK", "SEAFOOD"],
    },
    "beer_cider": {
        "name":     "TODO — Beer & Cider Supplier",
        "contact":  "TODO — Name",
        "whatsapp": "TODO — +27XXXXXXXXX",
        "email":    "TODO — email@supplier.co.za",
        "categories": ["BEER", "CIDER", "DRAUGHT"],
    },
    "wine": {
        "name":     "TODO — Wine Supplier",
        "contact":  "TODO — Name",
        "whatsapp": "TODO — +27XXXXXXXXX",
        "email":    "TODO — email@supplier.co.za",
        "categories": ["RWINE", "WWINE", "SWINE", "PORTSHERRY"],
    },
    "spirits": {
        "name":     "TODO — Spirits Supplier",
        "contact":  "TODO — Name",
        "whatsapp": "TODO — +27XXXXXXXXX",
        "email":    "TODO — email@supplier.co.za",
        "categories": ["WHISKEY", "WHITE SPIR", "BRANDY", "RUM", "LIQUEUR", "PREMIX"],
    },
    "dry_goods": {
        "name":     "TODO — Dry Goods Supplier",
        "contact":  "TODO — Name",
        "whatsapp": "TODO — +27XXXXXXXXX",
        "email":    "TODO — email@supplier.co.za",
        "categories": ["SAUCE", "GROCERIES", "SPICE", "OIL", "FLOUR DOUGH"],
    },
    "fresh": {
        "name":     "TODO — Fresh Produce Supplier",
        "contact":  "TODO — Name",
        "whatsapp": "TODO — +27XXXXXXXXX",
        "email":    "TODO — email@supplier.co.za",
        "categories": ["FVEG", "DAIRY", "CHEESE"],
    },
    "beverage": {
        "name":     "TODO — Soft Drink Supplier",
        "contact":  "TODO — Name",
        "whatsapp": "TODO — +27XXXXXXXXX",
        "email":    "TODO — email@supplier.co.za",
        "categories": ["CBEV", "HBEV"],
    },
    "chips": {
        "name":     "TODO — Chips / Frozen Supplier",
        "contact":  "TODO — Name",
        "whatsapp": "TODO — +27XXXXXXXXX",
        "email":    "TODO — email@supplier.co.za",
        "categories": ["CHIPS"],
    },
}

# ── PAR LEVELS ────────────────────────────────────────────────────────────────
# Logical groups: group_name -> (PilotLive categories, default_par, unit)
# TODO: Replace default_par values with Sava's confirmed par levels
GROUPS = {
    "Chicken":     (["CHICKEN"],            30,  "portions"),  # TODO: confirm with Sava
    "Meat":        (["MEAT"],               15,  "portions"),  # TODO: confirm with Sava
    "Pork":        (["PORK"],               20,  "portions"),  # TODO: confirm with Sava
    "Beer":        (["BEER"],               24,  "bottles"),   # TODO: confirm with Sava
    "Cider":       (["CIDER"],              12,  "bottles"),   # TODO: confirm with Sava
    "Draught":     (["DRAUGHT"],            20,  "kegs"),      # TODO: confirm with Sava
    "Red Wine":    (["RWINE"],               6,  "bottles"),   # TODO: confirm with Sava
    "White Wine":  (["WWINE"],               6,  "bottles"),   # TODO: confirm with Sava
    "Sparkling":   (["SWINE"],               6,  "bottles"),   # TODO: confirm with Sava
    "Whiskey":     (["WHISKEY"],            0.5, "bottles"),   # TODO: confirm with Sava
    "Gin & Vodka": (["WHITE SPIR"],         0.5, "bottles"),   # TODO: confirm with Sava
    "Brandy":      (["BRANDY"],             0.5, "bottles"),   # TODO: confirm with Sava
    "Rum":         (["RUM"],                0.5, "bottles"),   # TODO: confirm with Sava
    "Liqueur":     (["LIQUEUR", "PREMIX"],  0.5, "bottles"),   # TODO: confirm with Sava
    "Sauces":      (["SAUCE"],               5,  "units"),     # TODO: confirm with Sava
    "Fresh Veg":   (["FVEG"],               5,  "kg"),        # TODO: confirm with Sava
    "Dairy":       (["DAIRY"],              5,  "units"),     # TODO: confirm with Sava
    "Cheese":      (["CHEESE"],             10, "units"),     # TODO: confirm with Sava
    "Hot Bev":     (["HBEV"],              24,  "units"),     # TODO: confirm with Sava
    "Cold Bev":    (["CBEV"],              24,  "units"),     # TODO: confirm with Sava
    "Chips":       (["CHIPS"],             15,  "kg"),        # TODO: confirm with Sava
}

# Categories excluded from stock alerts
EXCLUDE = {
    "CLEANING", "CLOTHING", "CUTLERY & CROCKERY", "DEPOSITS", "EQUIPMENT",
    "STATIONERY", "PACKAGING", "WOOD", "VAPES", "Total", "Expense", "GAS",
    "OWNERS CHOICE", "RECIPE", "SLO JO",
}
