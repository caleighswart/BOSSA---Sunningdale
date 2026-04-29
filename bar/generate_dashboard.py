"""
Bossa Sunningdale — Bar Stock Dashboard Generator
===================================================
Generates docs/index.html — a static GitHub Pages dashboard showing the
daily bar stock levels in a clean, professional format for managers and owners.

Called by .github/workflows/daily_bar.yml after the bar agent runs.
Requires the same PILOTLIVE_* credentials as main.py.

Usage:
    cd bar && python generate_dashboard.py
"""

import os
import sys
from datetime import datetime, timezone, timedelta
from html import escape

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from analyse import load_data, analyse
from config import CATEGORY_LABELS, CATEGORY_ORDER, SUPPLIERS

SAST = timezone(timedelta(hours=2))
REPO_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
OUTPUT_PATH = os.path.join(REPO_ROOT, "docs", "index.html")


def _nice(name: str) -> str:
    """Strip the 'xx - ' sort prefix and return the product name."""
    parts = name.split(" - ", 1)
    n = parts[-1].strip() if len(parts) > 1 else name
    return (n[0].upper() + n[1:]) if n else n


def _pct_bar(pct: float) -> str:
    w = min(100, max(0, pct * 100))
    if pct < 0.30:
        color = "#dc2626"
    elif pct < 0.70:
        color = "#d97706"
    else:
        color = "#16a34a"
    return (
        f'<div class="pb-wrap">'
        f'<div class="pb-fill" style="width:{w:.0f}%;background:{color}"></div>'
        f'</div>'
        f'<span class="pb-label">{pct * 100:.0f}%</span>'
    )


def _fmt(v: float) -> str:
    return str(int(v)) if v == int(v) else f"{v:.1f}"


def _stock_table(rows: list, show_status: bool = False) -> str:
    """Render a list of (label, item[, status]) tuples as an HTML table."""
    if not rows:
        return '<p class="empty">None — all good ✓</p>'

    cols = "<th>Category</th><th>Product</th><th class='num'>SOH</th><th class='num'>Par</th><th class='fill-col'>Fill</th>"
    if show_status:
        cols += "<th>Status</th>"

    html = f'<table class="stock-table"><thead><tr>{cols}</tr></thead><tbody>'
    for row in rows:
        if show_status:
            label, item, status = row
        else:
            label, item = row
            status = None

        pct  = item.get("pct", 0)
        name = escape(_nice(item["name"]))
        soh  = _fmt(item["soh"])
        par  = _fmt(item["par"])

        row_class = f' class="row-{status}"' if show_status else ""
        html += f"<tr{row_class}>"
        html += f'<td class="cat-cell">{escape(label)}</td>'
        html += f'<td class="name-cell">{name}</td>'
        html += f'<td class="num">{soh}</td>'
        html += f'<td class="num">{par}</td>'
        html += f'<td class="fill-col">{_pct_bar(pct)}</td>'
        if show_status:
            labels = {"critical": "Critical", "low": "Low", "healthy": "Healthy", "variance": "Variance"}
            html += f'<td><span class="pill pill-{status}">{labels.get(status, status)}</span></td>'
        html += "</tr>"

    html += "</tbody></table>"
    return html


def _build_supplier_groups(by_cat: dict) -> list:
    """Return a list of supplier groups for the Orders tab.

    Each group is a dict:
      name, contact, whatsapp, categories (list), critical (list), low (list)

    Categories sharing the same non-empty whatsapp number are merged.
    Categories with no items to order are skipped.
    """
    seen = {}   # whatsapp → group dict (for deduplication)
    order = []  # preserve display order

    for cat in CATEGORY_ORDER:
        b = by_cat.get(cat)
        if not b:
            continue
        if not b["critical"] and not b["low"]:
            continue

        sup     = SUPPLIERS.get(cat, {})
        wa      = sup.get("whatsapp", "").strip()
        sname   = sup.get("name",     "").strip()
        contact = sup.get("contact",  "").strip()
        label   = CATEGORY_LABELS.get(cat, cat)

        gkey = wa if wa else f"__cat_{cat}"   # merge same-WA suppliers

        if gkey not in seen:
            g = {"name": sname, "contact": contact, "whatsapp": wa,
                 "categories": [], "critical": [], "low": []}
            seen[gkey] = g
            order.append(g)
        else:
            g = seen[gkey]
            # Prefer the first non-empty name/contact we encounter
            if not g["name"] and sname:
                g["name"] = sname
            if not g["contact"] and contact:
                g["contact"] = contact

        g["categories"].append(label)
        for item in b["critical"]:
            g["critical"].append((label, item))
        for item in b["low"]:
            g["low"].append((label, item))

    return order


def _orders_tab(supplier_groups: list) -> str:
    """Render the Orders tab HTML."""
    import json as _json

    if not supplier_groups:
        return '<p class="empty">Nothing to order — all stock is healthy ✓</p>'

    html = ""
    for g in supplier_groups:
        cats_str   = " · ".join(g["categories"])
        sup_name   = escape(g["name"])   if g["name"]   else "<em class='unset'>Supplier not set</em>"
        contact    = escape(g["contact"]) if g["contact"] else ""
        wa         = g["whatsapp"]
        n_crit     = len(g["critical"])
        n_low      = len(g["low"])

        # Build WhatsApp button or config prompt
        if wa:
            # Encode items for JS
            items_for_js = []
            for _label, item in g["critical"] + g["low"]:
                soh     = item["soh"]
                par     = item["par"]
                needed  = max(0, int(par - soh + 0.9999))  # ceil
                items_for_js.append({
                    "name":   _nice(item["name"]),
                    "soh":    _fmt(soh),
                    "par":    _fmt(par),
                    "needed": needed,
                    "status": "CRITICAL" if item.get("pct", 1) < 0.30 else "low",
                })
            items_json = escape(_json.dumps(items_for_js))
            contact_js = escape(g["contact"])
            sup_js     = escape(g["name"] or "there")
            wa_btn = (
                f'<button class="order-btn" '
                f'onclick="orderViaWA(this)" '
                f'data-phone="{wa}" '
                f'data-supplier="{sup_js}" '
                f'data-contact="{contact_js}" '
                f'data-items="{items_json}">'
                f'&#128242; Place Order via WhatsApp'
                f'</button>'
            )
        else:
            wa_btn = '<span class="order-btn-unset">Add WhatsApp number in bar/config.py to enable ordering</span>'

        # Items table
        all_items = g["critical"] + g["low"]
        tbl = (
            '<table class="stock-table order-tbl"><thead>'
            '<tr><th>Category</th><th>Product</th>'
            '<th class="num">SOH</th><th class="num">Par</th>'
            '<th class="num">Order qty</th><th class="fill-col">Fill</th></tr>'
            '</thead><tbody>'
        )
        for _label, item in all_items:
            pct    = item.get("pct", 0)
            name   = escape(_nice(item["name"]))
            soh    = _fmt(item["soh"])
            par    = _fmt(item["par"])
            needed = max(0, int(item["par"] - item["soh"] + 0.9999))
            status = "critical" if pct < 0.30 else "low"
            tbl += (
                f'<tr class="row-{status}">'
                f'<td class="cat-cell">{escape(_label)}</td>'
                f'<td class="name-cell">{name}</td>'
                f'<td class="num">{soh}</td>'
                f'<td class="num">{par}</td>'
                f'<td class="num order-qty">{needed}</td>'
                f'<td class="fill-col">{_pct_bar(pct)}</td>'
                f'</tr>'
            )
        tbl += "</tbody></table>"

        crit_badge = (
            f'<span class="badge badge-crit">{n_crit} critical</span> ' if n_crit else ""
        )
        low_badge  = (
            f'<span class="badge badge-low">{n_low} low</span>' if n_low else ""
        )

        html += f"""
<div class="supplier-card">
  <div class="supplier-header">
    <div class="supplier-info">
      <div class="supplier-name">{sup_name}</div>
      <div class="supplier-meta">
        {f'<span class="supplier-contact">&#128100; {contact}</span>' if contact else ''}
        {f'<span class="supplier-wa">&#128242; {wa}</span>' if wa else ''}
        <span class="supplier-cats">{escape(cats_str)}</span>
      </div>
    </div>
    <div class="supplier-actions">
      <div class="supplier-badges">{crit_badge}{low_badge}</div>
      {wa_btn}
    </div>
  </div>
  {tbl}
</div>"""

    return html


def build_html(result: dict, brief_date: str, pilotlive_title: str) -> str:
    by_cat      = result["by_cat"]
    unmatched   = result["unmatched"]
    missing_par = result["missing_par"]
    total_value = result["total_value"]

    now_str = datetime.now(SAST).strftime("%-d %b %Y, %H:%M SAST")
    day_str = datetime.strptime(brief_date, "%Y-%m-%d").strftime("%-d %B %Y")

    total_crit    = sum(len(b["critical"])  for b in by_cat.values())
    total_low     = sum(len(b["low"])       for b in by_cat.values())
    total_healthy = sum(len(b["healthy"])   for b in by_cat.values())
    total_var     = sum(len(b["variance"])  for b in by_cat.values())

    # ── Assemble row lists ────────────────────────────────────────────────────
    crit_rows, low_rows, all_rows = [], [], []
    for cat in CATEGORY_ORDER:
        b = by_cat.get(cat)
        if not b:
            continue
        label = CATEGORY_LABELS.get(cat, cat)
        for item in b["critical"]:
            crit_rows.append((label, item))
            all_rows.append((label, item, "critical"))
        for item in b["low"]:
            low_rows.append((label, item))
            all_rows.append((label, item, "low"))
        for item in b["healthy"]:
            all_rows.append((label, item, "healthy"))
        for item in b["variance"]:
            all_rows.append((label, item, "variance"))

    # ── Variance tab ─────────────────────────────────────────────────────────
    if total_var > 0:
        var_items = []
        for cat in CATEGORY_ORDER:
            b = by_cat.get(cat)
            if not b or not b["variance"]:
                continue
            label = CATEGORY_LABELS.get(cat, cat)
            for item in b["variance"]:
                var_items.append((label, item["name"], item["soh"]))
        var_items.sort(key=lambda x: x[2])

        var_html = (
            '<table class="stock-table"><thead>'
            '<tr><th>Category</th><th>Product</th><th class="num">SOH</th></tr>'
            '</thead><tbody>'
        )
        for label, name, soh in var_items:
            var_html += (
                f'<tr class="row-variance">'
                f'<td class="cat-cell">{escape(label)}</td>'
                f'<td class="name-cell">{escape(_nice(name))}</td>'
                f'<td class="num">{soh:.0f}</td>'
                f'</tr>'
            )
        var_html += "</tbody></table>"
    else:
        var_html = '<p class="empty">No variances detected ✓</p>'

    # ── Admin tab ─────────────────────────────────────────────────────────────
    admin_html = ""
    if missing_par:
        admin_html += (
            f'<h3 class="section-title">Missing par levels '
            f'<span class="badge badge-warn">{len(missing_par)}</span></h3>'
            f'<p class="admin-note">Set par values in <code>bar/pars.json</code> for these products:</p>'
            f'<ul class="admin-list">'
        )
        for name in missing_par[:40]:
            admin_html += f"<li>{escape(name)}</li>"
        if len(missing_par) > 40:
            admin_html += f'<li class="more">+ {len(missing_par) - 40} more…</li>'
        admin_html += "</ul>"

    if unmatched:
        admin_html += (
            f'<h3 class="section-title" style="margin-top:2rem">New products in PilotLive '
            f'<span class="badge badge-info">{len(unmatched)}</span></h3>'
            f'<p class="admin-note">These products appear in PilotLive but are not on the bar count sheet:</p>'
            f'<table class="stock-table"><thead>'
            f'<tr><th>Category</th><th>Product</th><th class="num">SOH</th></tr>'
            f'</thead><tbody>'
        )
        for cat, name, soh in unmatched:
            label = CATEGORY_LABELS.get(cat, cat)
            admin_html += (
                f"<tr>"
                f'<td class="cat-cell">{escape(label)}</td>'
                f'<td class="name-cell">{escape(_nice(name))}</td>'
                f'<td class="num">{_fmt(soh)}</td>'
                f"</tr>"
            )
        admin_html += "</tbody></table>"

    if not admin_html:
        admin_html = '<p class="empty">No admin items ✓</p>'

    # ── Orders tab ────────────────────────────────────────────────────────────
    supplier_groups = _build_supplier_groups(by_cat)
    orders_tab  = _orders_tab(supplier_groups)
    total_order = sum(len(g["critical"]) + len(g["low"]) for g in supplier_groups)

    # ── Build tab content strings ─────────────────────────────────────────────
    crit_tab = _stock_table(crit_rows)
    low_tab  = _stock_table(low_rows)
    all_tab  = _stock_table(all_rows, show_status=True)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Bossa Sunningdale — Bar Stock</title>
<style>
*, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}

body {{
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, sans-serif;
  background: #f0f2f5;
  color: #1f2937;
  min-height: 100vh;
}}

/* ── Header ─────────────────────────────────────────── */
.header {{
  background: #111827;
  padding: 1.4rem 2rem;
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 0.75rem;
}}
.header-left h1 {{
  color: #fff;
  font-size: 1.25rem;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}}
.header-left p {{
  color: #6b7280;
  font-size: 0.78rem;
  margin-top: 0.2rem;
  letter-spacing: 0.02em;
}}
.header-right {{ text-align: right; }}
.header-right .date-main {{ color: #f9fafb; font-size: 0.95rem; font-weight: 600; }}
.header-right .date-sub  {{ color: #6b7280; font-size: 0.72rem; margin-top: 0.15rem; }}

/* ── Summary bar ─────────────────────────────────────── */
.summary-bar {{
  background: #fff;
  border-bottom: 1px solid #e5e7eb;
  padding: 1rem 2rem;
  display: flex;
  gap: 2.5rem;
  flex-wrap: wrap;
  align-items: center;
}}
.stat-value {{ font-size: 1.7rem; font-weight: 700; line-height: 1; }}
.stat-label {{
  font-size: 0.65rem;
  color: #9ca3af;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  margin-top: 0.2rem;
}}
.s-crit .stat-value {{ color: #dc2626; }}
.s-low  .stat-value {{ color: #d97706; }}
.s-ok   .stat-value {{ color: #16a34a; }}
.s-val  .stat-value {{ color: #111827; }}
.divider {{ width: 1px; height: 2.2rem; background: #e5e7eb; }}

/* ── Tab nav ─────────────────────────────────────────── */
.tab-nav {{
  background: #fff;
  border-bottom: 2px solid #e5e7eb;
  padding: 0 2rem;
  display: flex;
  overflow-x: auto;
}}
.tab-btn {{
  padding: 0.85rem 1.2rem;
  border: none;
  background: none;
  font-size: 0.85rem;
  font-weight: 500;
  color: #6b7280;
  cursor: pointer;
  border-bottom: 2px solid transparent;
  margin-bottom: -2px;
  white-space: nowrap;
  transition: color 0.15s, border-color 0.15s;
}}
.tab-btn:hover {{ color: #374151; }}
.tab-btn.active {{ color: #111827; border-bottom-color: #111827; font-weight: 600; }}
.tab-btn .count {{
  display: inline-block;
  margin-left: 0.35rem;
  padding: 0.1rem 0.45rem;
  border-radius: 9999px;
  font-size: 0.68rem;
  font-weight: 700;
  line-height: 1.6;
}}
.c-crit {{ background: #fef2f2; color: #dc2626; }}
.c-low  {{ background: #fffbeb; color: #d97706; }}
.c-var  {{ background: #f5f3ff; color: #7c3aed; }}
.c-all  {{ background: #f3f4f6; color: #374151; }}

/* ── Content ─────────────────────────────────────────── */
.content {{
  max-width: 1140px;
  margin: 1.5rem auto;
  padding: 0 1.5rem;
}}
.tab-pane        {{ display: none; }}
.tab-pane.active {{ display: block; }}

/* ── Tables ──────────────────────────────────────────── */
.stock-table {{
  width: 100%;
  border-collapse: collapse;
  background: #fff;
  border-radius: 0.5rem;
  overflow: hidden;
  box-shadow: 0 1px 3px rgba(0,0,0,0.07), 0 1px 2px rgba(0,0,0,0.04);
  font-size: 0.865rem;
}}
.stock-table thead th {{
  background: #f9fafb;
  padding: 0.6rem 1rem;
  text-align: left;
  font-size: 0.68rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: #9ca3af;
  border-bottom: 1px solid #e5e7eb;
}}
.stock-table td {{
  padding: 0.6rem 1rem;
  border-bottom: 1px solid #f3f4f6;
  vertical-align: middle;
}}
.stock-table tbody tr:last-child td {{ border-bottom: none; }}
.stock-table tbody tr:hover {{ background: #fafafa; }}

.cat-cell  {{ font-size: 0.72rem; color: #9ca3af; font-weight: 500; width: 140px; white-space: nowrap; }}
.name-cell {{ font-weight: 500; color: #111827; }}
.num       {{ text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }}
.fill-col  {{ width: 165px; white-space: nowrap; }}

/* Progress bar */
.pb-wrap {{
  display: inline-block;
  width: 88px;
  height: 6px;
  background: #e5e7eb;
  border-radius: 3px;
  overflow: hidden;
  vertical-align: middle;
  margin-right: 0.4rem;
}}
.pb-fill  {{ height: 100%; border-radius: 3px; }}
.pb-label {{ font-size: 0.75rem; color: #374151; font-variant-numeric: tabular-nums; vertical-align: middle; }}

/* Left-border status stripe */
.row-critical td:first-child {{ border-left: 3px solid #dc2626; }}
.row-low      td:first-child {{ border-left: 3px solid #d97706; }}
.row-healthy  td:first-child {{ border-left: 3px solid #16a34a; }}
.row-variance td:first-child {{ border-left: 3px solid #7c3aed; }}

/* Status pills */
.pill {{
  display: inline-block;
  padding: 0.18rem 0.55rem;
  border-radius: 9999px;
  font-size: 0.68rem;
  font-weight: 600;
}}
.pill-critical {{ background: #fef2f2; color: #dc2626; }}
.pill-low      {{ background: #fffbeb; color: #d97706; }}
.pill-healthy  {{ background: #f0fdf4; color: #16a34a; }}
.pill-variance {{ background: #f5f3ff; color: #7c3aed; }}

/* ── Admin tab ───────────────────────────────────────── */
.section-title {{
  font-size: 0.95rem;
  font-weight: 600;
  color: #111827;
  margin-bottom: 0.5rem;
  display: flex;
  align-items: center;
  gap: 0.5rem;
}}
.badge {{
  display: inline-block;
  padding: 0.15rem 0.55rem;
  border-radius: 9999px;
  font-size: 0.68rem;
  font-weight: 700;
}}
.badge-warn {{ background: #fffbeb; color: #d97706; }}
.badge-info {{ background: #eff6ff; color: #2563eb; }}
.admin-note {{
  font-size: 0.78rem;
  color: #9ca3af;
  margin-bottom: 0.75rem;
}}
.admin-list {{
  list-style: none;
  background: #fff;
  border-radius: 0.5rem;
  box-shadow: 0 1px 3px rgba(0,0,0,0.07);
  overflow: hidden;
  font-size: 0.84rem;
}}
.admin-list li {{
  padding: 0.5rem 1rem;
  border-bottom: 1px solid #f3f4f6;
  color: #374151;
}}
.admin-list li:last-child {{ border-bottom: none; }}
.admin-list li.more {{ color: #9ca3af; font-style: italic; }}

.empty {{
  text-align: center;
  padding: 3rem 1rem;
  color: #9ca3af;
  font-size: 0.875rem;
  background: #fff;
  border-radius: 0.5rem;
  box-shadow: 0 1px 3px rgba(0,0,0,0.07);
}}

/* ── Orders tab ─────────────────────────────────────── */
.supplier-card {{
  background: #fff;
  border-radius: 0.5rem;
  box-shadow: 0 1px 3px rgba(0,0,0,0.07), 0 1px 2px rgba(0,0,0,0.04);
  margin-bottom: 1.25rem;
  overflow: hidden;
}}
.supplier-header {{
  padding: 1rem 1.25rem;
  border-bottom: 1px solid #e5e7eb;
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 1rem;
  flex-wrap: wrap;
}}
.supplier-name {{
  font-size: 0.95rem;
  font-weight: 700;
  color: #111827;
  margin-bottom: 0.3rem;
}}
.supplier-meta {{
  display: flex;
  gap: 1rem;
  flex-wrap: wrap;
  font-size: 0.78rem;
  color: #6b7280;
}}
.supplier-meta span {{ white-space: nowrap; }}
.supplier-contact {{ color: #374151; font-weight: 500; }}
.supplier-wa      {{ color: #374151; }}
.supplier-cats    {{ color: #9ca3af; font-style: italic; }}
.supplier-actions {{
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 0.5rem;
}}
.supplier-badges {{ display: flex; gap: 0.4rem; flex-wrap: wrap; justify-content: flex-end; }}
.badge-crit {{ background: #fef2f2; color: #dc2626; }}
.badge-low  {{ background: #fffbeb; color: #d97706; }}
.order-btn {{
  display: inline-block;
  padding: 0.5rem 1rem;
  background: #16a34a;
  color: #fff;
  border: none;
  border-radius: 0.4rem;
  font-size: 0.82rem;
  font-weight: 600;
  cursor: pointer;
  white-space: nowrap;
  transition: background 0.15s;
}}
.order-btn:hover {{ background: #15803d; }}
.order-btn-unset {{
  display: inline-block;
  padding: 0.35rem 0.75rem;
  background: #f3f4f6;
  color: #9ca3af;
  border-radius: 0.4rem;
  font-size: 0.72rem;
  white-space: nowrap;
}}
.order-tbl .order-qty {{
  font-weight: 700;
  color: #111827;
}}
.c-order {{ background: #f0fdf4; color: #16a34a; }}

/* ── Footer ──────────────────────────────────────────── */
.footer {{
  text-align: center;
  padding: 2rem;
  color: #d1d5db;
  font-size: 0.72rem;
  letter-spacing: 0.02em;
}}

/* ── Responsive ──────────────────────────────────────── */
@media (max-width: 640px) {{
  .header       {{ padding: 1rem; }}
  .summary-bar  {{ padding: 0.75rem 1rem; gap: 1.25rem; }}
  .content      {{ padding: 0 0.75rem; margin-top: 1rem; }}
  .tab-nav      {{ padding: 0 0.5rem; }}
  .stock-table td, .stock-table th {{ padding: 0.5rem 0.6rem; }}
  .cat-cell     {{ display: none; }}
  .fill-col     {{ width: 120px; }}
  .pb-wrap      {{ width: 60px; }}
}}
</style>
</head>
<body>

<header class="header">
  <div class="header-left">
    <h1>Bossa Sunningdale</h1>
    <p>Bar Stock Dashboard</p>
  </div>
  <div class="header-right">
    <div class="date-main">{day_str}</div>
    <div class="date-sub">Updated {now_str}</div>
  </div>
</header>

<div class="summary-bar">
  <div class="s-crit">
    <div class="stat-value">{total_crit}</div>
    <div class="stat-label">Critical</div>
  </div>
  <div class="divider"></div>
  <div class="s-low">
    <div class="stat-value">{total_low}</div>
    <div class="stat-label">Low</div>
  </div>
  <div class="divider"></div>
  <div class="s-ok">
    <div class="stat-value">{total_healthy}</div>
    <div class="stat-label">Healthy</div>
  </div>
  <div class="divider"></div>
  <div class="s-val">
    <div class="stat-value">R{total_value:,.0f}</div>
    <div class="stat-label">Stock Value</div>
  </div>
</div>

<nav class="tab-nav">
  <button class="tab-btn active" data-tab="critical">Critical <span class="count c-crit">{total_crit}</span></button>
  <button class="tab-btn" data-tab="low">Low <span class="count c-low">{total_low}</span></button>
  <button class="tab-btn" data-tab="orders">Orders <span class="count c-order">{total_order}</span></button>
  <button class="tab-btn" data-tab="all">All Products <span class="count c-all">{len(all_rows)}</span></button>
  <button class="tab-btn" data-tab="variance">Variances <span class="count c-var">{total_var}</span></button>
  <button class="tab-btn" data-tab="admin">Admin</button>
</nav>

<div class="content">
  <div class="tab-pane active" id="tab-critical">{crit_tab}</div>
  <div class="tab-pane" id="tab-low">{low_tab}</div>
  <div class="tab-pane" id="tab-orders">{orders_tab}</div>
  <div class="tab-pane" id="tab-all">{all_tab}</div>
  <div class="tab-pane" id="tab-variance">{var_html}</div>
  <div class="tab-pane" id="tab-admin">{admin_html}</div>
</div>

<div class="footer">
  Bossa Bar Stock Agent &nbsp;·&nbsp; {escape(pilotlive_title)}
</div>

<script>
  document.querySelectorAll('.tab-btn').forEach(btn => {{
    btn.addEventListener('click', () => {{
      document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
      document.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));
      btn.classList.add('active');
      document.getElementById('tab-' + btn.dataset.tab).classList.add('active');
    }});
  }});

  function orderViaWA(btn) {{
    const phone    = btn.dataset.phone;
    const contact  = btn.dataset.contact || '';
    const items    = JSON.parse(btn.dataset.items);

    const greeting = contact ? 'Hi ' + contact : 'Hi';
    let msg = greeting + ', this is Bossa Sunningdale.\\n\\nPlacing a bar stock order:\\n\\n';

    items.forEach(item => {{
      const icon = item.status === 'CRITICAL'
        ? String.fromCodePoint(0x1F534)
        : String.fromCodePoint(0x1F7E1);
      msg += icon + ' ' + item.name + ' \u2014 order ' + item.needed +
             ' (have ' + item.soh + ', par ' + item.par + ')\\n';
    }});

    msg += '\\nPlease confirm availability and ETA. Thank you!';

    window.open('https://wa.me/' + phone + '?text=' + encodeURIComponent(msg), '_blank');
  }}
</script>

</body>
</html>"""


def main():
    print(f"📊 Bar Stock Dashboard Generator — {datetime.now(SAST).strftime('%a %-d %b %Y %H:%M SAST')}")
    print("─" * 60)

    brief_date = datetime.now(SAST).strftime("%Y-%m-%d")

    print("Loading stock data...")
    rows, title = load_data()
    print(f"  {len(rows)} items — {title}")

    print("Analysing...")
    result = analyse(rows)

    total_crit = sum(len(b["critical"]) for b in result["by_cat"].values())
    total_low  = sum(len(b["low"])      for b in result["by_cat"].values())
    print(f"  {total_crit} critical | {total_low} low | R{result['total_value']:,.0f} value")

    html = build_html(result, brief_date, title)

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"\n✅ Dashboard written → {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
