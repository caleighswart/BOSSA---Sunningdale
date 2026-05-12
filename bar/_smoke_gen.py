"""Generate a smoke-test dashboard HTML using fixture rows (no SSRS).

Use this to eyeball UI changes locally without live PilotLive creds.
Writes to docs/_smoke.html so it doesn't clobber the live dashboard.
"""
import os
import sys
import types
from datetime import datetime, timezone, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

# Local Python is 3.9 but config.py uses PEP 604 `X | None` annotations that
# only work at runtime on 3.10+. Inject `from __future__ import annotations`
# so type expressions stay strings — purely for local smoke runs.
with open(os.path.join(HERE, "config.py"), "r", encoding="utf-8") as _f:
    _src = "from __future__ import annotations\n" + _f.read()
_config = types.ModuleType("config")
_config.__file__ = os.path.join(HERE, "config.py")
exec(compile(_src, _config.__file__, "exec"), _config.__dict__)
sys.modules["config"] = _config

import analyse as _analyse
import generate_dashboard as gd

SAST = timezone(timedelta(hours=2))


# Load realistic SOH data from Sava's latest stock count Excel so the smoke
# dashboard reflects production-like volumes (407 SKUs, full category coverage).
# Pars still come from the live pars.json — they're already in sync with the sheet.
STOCK_SHEET = os.path.abspath(
    os.path.join(HERE, "April 26 Stock Count This one.xlsx")
)

_PREFIX_TO_CAT = {
    "dr": "DRAUGHT", "be": "BEER", "ci": "CIDER", "cb": "CBEV",
    "lq": "LIQUEUR", "px": "PREMIX", "ps": "PORTSHERRY",
    "br": "BRANDY", "ru": "RUM", "wh": "WHISKEY", "ws": "WHITE SPIR",
    "sw": "SWINE", "ww": "WWINE", "rw": "RWINE",
    "pa": "PACKAGING", "waka": "VAPES", "puff": "VAPES",
    "hb": "HBEV", "so": "LIQUEUR", "sj": "HBEV",
}


def _load_rows_from_sheet():
    """Read the Report tab from Sava's stock count: col A = name, col C = SOH."""
    import openpyxl
    import re
    wb = openpyxl.load_workbook(STOCK_SHEET, data_only=True)
    ws = wb["Report"]
    rows = []
    for r in ws.iter_rows(values_only=True):
        name = r[0]
        if not name or not isinstance(name, str):
            continue
        name = name.strip()
        soh_raw = r[2] if len(r) > 2 else None
        try:
            soh = float(soh_raw) if soh_raw not in (None, "") else 0.0
        except (TypeError, ValueError):
            soh = 0.0
        m = re.match(r"^([a-z]+)\s*-", name.lower())
        cat = _PREFIX_TO_CAT.get(m.group(1)) if m else None
        if not cat:
            continue
        rows.append({"name": name, "cat": cat, "soh": soh, "value": 0.0})
    return rows


def _fake_load_data():
    title = "Bossa Sunningdale (SMOKE — Apr 26 count)"
    return _load_rows_from_sheet(), title


# Patch IO — pars come from the real pars.json via the unpatched load_pars().
_analyse.load_data = _fake_load_data
gd.load_data = _fake_load_data

# Override output path
OUT = os.path.abspath(os.path.join(HERE, "..", "docs", "_smoke.html"))

brief_date = datetime.now(SAST).strftime("%Y-%m-%d")
rows, title = _fake_load_data()
result = _analyse.analyse(rows)
html = gd.build_html(result, brief_date, title)
with open(OUT, "w", encoding="utf-8") as f:
    f.write(html)
print(f"wrote {OUT}")
