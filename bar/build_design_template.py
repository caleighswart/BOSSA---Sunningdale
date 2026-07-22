"""
Build a stripped-down dashboard for offline design exploration.

Reuses generate_dashboard.build_html() against a small fixture dataset so the
template is byte-for-byte structurally identical to production (same CSS,
same JS, same markup) but small enough to drop into a Claude artifact.

Output: /tmp/bossa_dashboard_design_template.html
"""

import os
from generate_dashboard import build_html


def _item(name: str, soh: float, par: float) -> dict:
    return {"name": name, "soh": soh, "par": par, "pct": (soh / par) if par else 0}


def _bucket(critical, low, healthy, variance=None) -> dict:
    return {
        "critical": critical,
        "low":      low,
        "healthy":  healthy,
        "variance": variance or [],
    }


FIXTURE = {
    "by_cat": {
        "BEER": _bucket(
            critical=[
                _item("Castle dbl malt",    0,   12),
                _item("Guinness 440ml",     2,   24),
                _item("Heineken 330ml",     6,   48),
            ],
            low=[
                _item("Corona 330ml",      18,   36),
                _item("Windhoek Draught",  10,   24),
                _item("Black Label 750ml", 14,   36),
            ],
            healthy=[
                _item("Castle Lite 330ml", 40,   48),
                _item("Hansa Pilsner",     22,   24),
                _item("Amstel 330ml",      30,   36),
            ],
        ),
        "WWINE": _bucket(
            critical=[
                _item("Nederburg Sauvignon Blanc", 1,   12),
                _item("Two Oceans Chardonnay",    0,    6),
                _item("KWV Chenin Blanc",         2,   18),
            ],
            low=[
                _item("Diemersdal SB",        4,   12),
                _item("Boschendal 1685",      5,   12),
                _item("Mulderbosch Rose",     8,   18),
            ],
            healthy=[
                _item("Backsberg Chardonnay", 11,  12),
                _item("Steenberg Sauv Blanc",  9,  12),
                _item("Spier Signature",      14,  18),
            ],
        ),
        "WHISKEY": _bucket(
            critical=[
                _item("Jameson Standard",       0.5,   6),
                _item("Glenfiddich 12yr",       1,     6),
                _item("Johnnie Walker Black",   1.5,   6),
            ],
            low=[
                _item("Bells Original",         2,     6),
                _item("Jack Daniels",           3,     6),
                _item("Bushmills Original",     2.5,   6),
            ],
            healthy=[
                _item("J&B Rare",               5,     6),
                _item("Famous Grouse",          5.5,   6),
                _item("Chivas Regal 12yr",      4.5,   6),
            ],
            variance=[
                _item("Glenmorangie 10yr",     -7,     6),
            ],
        ),
        "BRANDY": _bucket(
            critical=[
                _item("KWV 3yr",          2.4,  180),
                _item("Hennessy VS",      0.5,   30),
                _item("KWV 20yr",         0.6,   30),
            ],
            low=[
                _item("Klipdrift Premium", 12,    36),
                _item("Richelieu",         15,    36),
                _item("Van Ryn 10yr",       6,    12),
            ],
            healthy=[
                _item("KWV 10yr",          20,    24),
                _item("Klipdrift Export",  18,    24),
                _item("Oude Meester",      15,    18),
            ],
        ),
        "WHITE SPIR": _bucket(
            critical=[
                _item("Gordon's Gin",       1,    12),
                _item("Tanqueray London",   0,     6),
                _item("Smirnoff 1818",      2,    12),
            ],
            low=[
                _item("Bombay Sapphire",    4,    12),
                _item("Absolut Vodka",      5,    12),
                _item("Jose Cuervo Silver", 3,     6),
            ],
            healthy=[
                _item("Hendrick's Gin",     10,   12),
                _item("Inverroche Verdant",  6,    6),
                _item("Olmeca Reposado",     5,    6),
            ],
            variance=[
                _item("Stolichnaya",       -8,    12),
            ],
        ),
    },
    "unmatched": [
        ("WHISKEY",    "Aberlour 12yr",       3.0),
        ("LIQUEUR",    "Aperol Spritz Mix",   5.0),
    ],
    "missing_par": [
        "wh - Glenfiddich 15yr",
        "wh - Bushmills Black Bush",
        "li - Slo Jo Lavender Syrup",
        "li - Slo Jo Rose Syrup",
    ],
    "total_value": 184523.50,
}


def main() -> None:
    out_path = "/tmp/bossa_dashboard_design_template.html"
    html = build_html(
        FIXTURE,
        brief_date="2026-05-27",
        pilotlive_title="Bossa Sunningdale — Design Template",
    )
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
    size_kb = os.path.getsize(out_path) / 1024
    print(f"OK  →  {out_path}  ({size_kb:.1f} KB)")


if __name__ == "__main__":
    main()
