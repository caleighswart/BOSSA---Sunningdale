"""
Bossa Sunningdale — Bar Stock Dashboard Generator
===================================================
Generates docs/index.html — a static Netlify dashboard showing the
daily bar stock levels in a clean, professional format for managers and owners.

Called by .github/workflows/daily_bar.yml after the bar agent runs.
Requires the same PILOTLIVE_* credentials as main.py.

Usage:
    cd bar && python generate_dashboard.py
"""

import os
import re
import sys
from datetime import datetime, timezone, timedelta
from html import escape

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from analyse import load_data, analyse
from config import CATEGORY_LABELS, CATEGORY_ORDER, CATEGORY_UNITS, SUPPLIERS


# Mirror analyse.py's prefix → category mapping so we can group by category
# in the Admin tab (par-sheet names lack a category attribute on their own).
PREFIX_TO_CAT = {
    "dr": "DRAUGHT", "be": "BEER", "ci": "CIDER", "cb": "CBEV",
    "lq": "LIQUEUR", "px": "PREMIX", "ps": "PORTSHERRY",
    "br": "BRANDY", "ru": "RUM", "wh": "WHISKEY", "ws": "WHITE SPIR",
    "sw": "SWINE", "ww": "WWINE", "rw": "RWINE",
    "pa": "PACKAGING", "waka": "VAPES", "puff": "VAPES",
    "hb": "HBEV", "so": "LIQUEUR", "sj": "HBEV",
}


def _cat_from_par_name(name: str) -> str:
    """Map a par-sheet product name back to its category code via prefix."""
    m = re.match(r"^([a-z]+)\s*-", name.lower())
    if m and m.group(1) in PREFIX_TO_CAT:
        return PREFIX_TO_CAT[m.group(1)]
    return ""


def _unit(cat: str) -> str:
    """Return the display unit for a category (Litres / Bottles / Units)."""
    return CATEGORY_UNITS.get(cat, "Units")


def _cat_from_label(label: str) -> str:
    """Reverse-lookup a category code from its display label."""
    for code, lbl in CATEGORY_LABELS.items():
        if lbl == label:
            return code
    return ""

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
        cls = "pb-fill-crit"
    elif pct < 0.70:
        cls = "pb-fill-low"
    else:
        cls = "pb-fill-ok"
    return (
        f'<div class="pb-wrap">'
        f'<div class="pb-fill {cls}" style="width:{w:.0f}%"></div>'
        f'</div>'
        f'<span class="pb-label">{pct * 100:.0f}%</span>'
    )


def _fmt(v: float) -> str:
    return str(int(v)) if v == int(v) else f"{v:.1f}"


def _stock_table(rows: list, show_status: bool = False, hide_category: bool = False) -> str:
    """Render a list of (label, item[, status]) tuples as an HTML table.

    Each row's category determines the unit label (Litres/Bottles/Units)
    that suffixes the SOH and par numbers. When hide_category is True the
    Category column is dropped (used inside collapsible category sections).
    """
    if not rows:
        return '<p class="empty">Nothing to flag — looking good.</p>'

    cols = ""
    if not hide_category:
        cols += "<th>Category</th>"
    cols += (
        "<th>Product</th>"
        "<th class='num'>SOH</th><th class='num'>Par</th>"
        "<th>Unit</th><th class='fill-col'>Fill</th>"
    )
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
        cat  = _cat_from_label(label)
        unit = _unit(cat)

        row_class = f' class="row-{status}"' if show_status else ""
        html += f"<tr{row_class}>"
        if not hide_category:
            html += f'<td class="cat-cell">{escape(label)}</td>'
        html += f'<td class="name-cell">{name}</td>'
        html += f'<td class="num">{soh}</td>'
        html += f'<td class="num">{par}</td>'
        html += f'<td class="unit-cell">{escape(unit)}</td>'
        html += f'<td class="fill-col">{_pct_bar(pct)}</td>'
        if show_status:
            labels = {"critical": "Critical", "low": "Low", "healthy": "Healthy", "variance": "Variance"}
            html += f'<td><span class="pill pill-{status}">{labels.get(status, status)}</span></td>'
        html += "</tr>"

    html += "</tbody></table>"
    return html


def _cat_section(label: str, count: int, body: str) -> str:
    """Wrap a category's content in a collapsible <details> section."""
    return (
        f'<details class="cat-section" open>'
        f'<summary class="cat-summary">'
        f'<span class="cat-summary-name">{escape(label.upper())}</span>'
        f'<span class="cat-summary-count">{count}</span>'
        f'</summary>'
        f'{body}'
        f'</details>'
    )


def _grouped_stock_table(
    rows: list,
    show_status: bool = False,
    sort_mode: str = "severity",
    empty_msg: str = "Nothing to flag — looking good.",
) -> str:
    """Render rows as collapsible category sections.

    rows: list of (label, item) or (label, item, status) tuples.
    sort_mode: "severity" (worst pct first) or "alphabetical".
    """
    if not rows:
        return f'<p class="empty">{empty_msg}</p>'

    groups: dict[str, list] = {}
    for row in rows:
        groups.setdefault(row[0], []).append(row)

    parts = []
    for label in sorted(groups.keys(), key=lambda x: x.lower()):
        items = groups[label]
        if sort_mode == "alphabetical":
            items.sort(key=lambda r: _nice(r[1]["name"]).lower())
        else:
            items.sort(key=lambda r: r[1].get("pct", 1.0))
        parts.append(
            _cat_section(label, len(items),
                         _stock_table(items, show_status, hide_category=True))
        )
    return "".join(parts)


def _grouped_variance_table(var_items: list) -> str:
    """Render variance items grouped by category.

    var_items: list of (label, name, soh).
    """
    if not var_items:
        return '<p class="empty">No variances to investigate.</p>'

    groups: dict[str, list] = {}
    for label, name, soh in var_items:
        groups.setdefault(label, []).append((name, soh))

    parts = []
    for label in sorted(groups.keys(), key=lambda x: x.lower()):
        items = sorted(groups[label], key=lambda x: x[1])  # worst SOH first
        tbl = (
            '<table class="stock-table"><thead>'
            '<tr><th>Product</th><th class="num">SOH</th></tr>'
            '</thead><tbody>'
        )
        for name, soh in items:
            tbl += (
                '<tr class="row-variance">'
                f'<td class="name-cell">{escape(_nice(name))}</td>'
                f'<td class="num">{soh:.0f}</td>'
                '</tr>'
            )
        tbl += "</tbody></table>"
        parts.append(_cat_section(label, len(items), tbl))
    return "".join(parts)


def _grouped_missing_par(names: list) -> str:
    """Render missing-par product names grouped by category (collapsible)."""
    if not names:
        return ""

    groups: dict[str, list[str]] = {}
    for name in names:
        cat = _cat_from_par_name(name)
        label = CATEGORY_LABELS.get(cat, "Other") if cat else "Other"
        groups.setdefault(label, []).append(name)

    parts = []
    for label in sorted(groups.keys(), key=lambda x: x.lower()):
        items = sorted(groups[label], key=lambda x: x.lower())
        lis = "".join(f"<li>{escape(n)}</li>" for n in items)
        parts.append(
            _cat_section(label, len(items),
                         f'<ul class="admin-list">{lis}</ul>')
        )
    return "".join(parts)


def _grouped_new_products(unmatched: list) -> str:
    """Render new-product unmatched list grouped by category (collapsible).

    unmatched: list of (cat_code, name, soh).
    """
    if not unmatched:
        return ""

    groups: dict[str, list] = {}
    for cat, name, soh in unmatched:
        label = CATEGORY_LABELS.get(cat, cat)
        groups.setdefault(label, []).append((name, soh))

    parts = []
    for label in sorted(groups.keys(), key=lambda x: x.lower()):
        items = sorted(groups[label], key=lambda x: _nice(x[0]).lower())
        tbl = (
            '<table class="stock-table"><thead>'
            '<tr><th>Product</th><th class="num">SOH</th></tr>'
            '</thead><tbody>'
        )
        for name, soh in items:
            tbl += (
                "<tr>"
                f'<td class="name-cell">{escape(_nice(name))}</td>'
                f'<td class="num">{_fmt(soh)}</td>'
                "</tr>"
            )
        tbl += "</tbody></table>"
        parts.append(_cat_section(label, len(items), tbl))
    return "".join(parts)


def _build_supplier_groups(by_cat: dict) -> list:
    """Return a list of supplier groups for the Orders tab.

    Each group is a dict:
      name, contact, email, slug, categories (list), critical (list), low (list)

    Categories sharing the same non-empty email are merged.
    Categories with no items to order are skipped.
    """
    seen = {}   # email → group dict (for deduplication)
    order = []  # preserve display order

    for cat in CATEGORY_ORDER:
        b = by_cat.get(cat)
        if not b:
            continue
        if not b["critical"] and not b["low"]:
            continue

        sup     = SUPPLIERS.get(cat, {})
        email   = sup.get("email",   "").strip()
        sname   = sup.get("name",    "").strip()
        contact = sup.get("contact", "").strip()
        label   = CATEGORY_LABELS.get(cat, cat)

        gkey = email if email else f"__cat_{cat}"   # merge same-email suppliers

        if gkey not in seen:
            g = {"name": sname, "contact": contact, "email": email,
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

    # Stable slug for each supplier (used in the tracking pixel URL).
    for g in order:
        slug_src = (g["name"] or g["email"] or "supplier").lower()
        g["slug"] = re.sub(r"[^a-z0-9]+", "-", slug_src).strip("-") or "supplier"
    return order


def _orders_tab(supplier_groups: list, day_str: str, today_iso: str) -> str:
    """Render the Order selection tab HTML.

    Each row has a checkbox so users can hand-pick the items they want
    to send into the Stock Order tab for batch ordering.
    Supplier-level and global "select all" controls are included.
    """
    if not supplier_groups:
        return '<p class="empty">Nothing to order — bar is well stocked.</p>'

    html = (
        '<div class="selection-toolbar">'
        '  <label class="check-row check-row-strong">'
        '    <input type="checkbox" id="select-all-reorder">'
        '    <span>Select all reorder items</span>'
        '  </label>'
        '  <button type="button" class="order-btn order-btn-secondary" '
        '          onclick="sendSelectionToStockOrder()">'
        '    Send selected to Stock Order'
        '  </button>'
        '</div>'
    )

    for gi, g in enumerate(supplier_groups):
        cats_str = " · ".join(g["categories"])
        sup_name = escape(g["name"]) if g["name"] else "<em class='unset'>Supplier not set</em>"
        contact  = escape(g["contact"]) if g["contact"] else ""
        email    = g["email"]
        slug     = g["slug"]
        n_crit   = len(g["critical"])
        n_low    = len(g["low"])
        group_id = f"supplier-{gi}"

        # ── Viewed-by-supplier badge ─────────────────────────────────────────
        # TODO: when an order has actually been sent, replace this placeholder
        # with one of:
        #   <span class="viewed-badge viewed-badge-pending">Sent — awaiting view</span>
        #   <span class="viewed-badge viewed-badge-viewed">Viewed {timestamp}</span>
        # The pending → viewed transition will be driven by a tracking pixel
        # embedded in the outgoing email body, e.g.
        #     <img src="https://bossa-sunningdale.netlify.app/track/{slug}-{today_iso}.png">
        # A Netlify function will log each pixel request against
        # (supplier_slug, date) and, on the next dashboard regeneration, we'll
        # read that log to populate the viewed timestamp here. Slug + date for
        # this card are already wired through as data-* attributes below so
        # the future backend can hydrate without further markup changes.
        viewed_badge = '<span class="viewed-badge viewed-badge-not-sent">Not sent</span>'

        # Group line items by category so each supplier card shows
        # collapsible per-category sections that mirror Critical/Low tabs.
        by_label: dict[str, list] = {}
        label_order: list[str] = []
        for _label, item in g["critical"] + g["low"]:
            if _label not in by_label:
                by_label[_label] = []
                label_order.append(_label)
            by_label[_label].append(item)

        sup_name_attr = escape(g["name"] or "")
        email_attr    = escape(email or "")
        contact_attr  = escape(g["contact"] or "")

        cat_sections = ""
        for _label in label_order:
            items_in_cat = by_label[_label]
            cat_code = _cat_from_label(_label)
            unit     = _unit(cat_code)

            tbl = (
                '<table class="stock-table order-tbl"><thead>'
                '<tr>'
                '<th class="check-col"></th>'
                '<th>Product</th>'
                '<th class="num">SOH</th><th class="num">Par</th>'
                '<th>Unit</th>'
                '<th class="num">Order qty</th><th class="fill-col">Fill</th></tr>'
                '</thead><tbody>'
            )
            for item in items_in_cat:
                pct      = item.get("pct", 0)
                raw_name = _nice(item["name"])
                name     = escape(raw_name)
                soh      = _fmt(item["soh"])
                par      = _fmt(item["par"])
                needed   = max(0, int(item["par"] - item["soh"] + 0.9999))
                status   = "critical" if pct < 0.30 else "low"
                tbl += (
                    f'<tr class="row-{status}">'
                    f'<td class="check-col">'
                    f'<input type="checkbox" class="reorder-check" '
                    f'data-group="{group_id}" '
                    f'data-name="{name}" '
                    f'data-cat="{escape(_label)}" '
                    f'data-unit="{escape(unit)}" '
                    f'data-soh="{soh}" data-par="{par}" data-needed="{needed}" '
                    f'data-status="{status}" '
                    f'data-supplier="{sup_name_attr}" '
                    f'data-email="{email_attr}" '
                    f'data-contact="{contact_attr}"></td>'
                    f'<td class="name-cell">{name}</td>'
                    f'<td class="num">{soh}</td>'
                    f'<td class="num">{par}</td>'
                    f'<td class="unit-cell">{escape(unit)}</td>'
                    f'<td class="num order-qty">{needed}</td>'
                    f'<td class="fill-col">{_pct_bar(pct)}</td>'
                    f'</tr>'
                )
            tbl += "</tbody></table>"
            # Custom cat-section with a per-category "select all" checkbox in
            # the summary. onclick stopPropagation prevents the checkbox click
            # from also toggling the <details> open/close.
            cat_sections += (
                f'<details class="cat-section" open>'
                f'<summary class="cat-summary">'
                f'<input type="checkbox" class="select-all-cat" '
                f'data-group="{group_id}" data-cat="{escape(_label)}" '
                f'onclick="event.stopPropagation()" '
                f'aria-label="Select all in {escape(_label)}">'
                f'<span class="cat-summary-name">{escape(_label.upper())}</span>'
                f'<span class="cat-summary-count">{len(items_in_cat)}</span>'
                f'</summary>'
                f'{tbl}'
                f'</details>'
            )

        # Supplier-level select-all lives in its own toolbar above the
        # category sections (it used to be a <th> inside a single big table).
        select_toolbar = (
            f'<div class="supplier-select-toolbar">'
            f'  <label class="check-row check-row-strong">'
            f'    <input type="checkbox" class="select-all-supplier" data-group="{group_id}">'
            f'    <span>Select all from this supplier</span>'
            f'  </label>'
            f'</div>'
        )

        crit_badge = (
            f'<span class="badge badge-crit">{n_crit} critical</span> ' if n_crit else ""
        )
        low_badge  = (
            f'<span class="badge badge-low">{n_low} low</span>' if n_low else ""
        )

        html += f"""
<div class="supplier-card" data-group="{group_id}" data-supplier-slug="{escape(slug)}" data-order-date="{escape(today_iso)}">
  <div class="supplier-header">
    <div class="supplier-info">
      <div class="supplier-name">{sup_name}</div>
      <div class="supplier-meta">
        {f'<span class="supplier-contact">{contact}</span>' if contact else ''}
        {f'<span class="supplier-email">{escape(email)}</span>' if email else ''}
        <span class="supplier-cats">{escape(cats_str)}</span>
      </div>
    </div>
    <div class="supplier-actions">
      <div class="supplier-badges">{crit_badge}{low_badge}{viewed_badge}</div>
    </div>
  </div>
  <div class="supplier-body">
    {select_toolbar}
    {cat_sections}
  </div>
</div>"""

    return html


def _stock_order_tab(all_rows: list, today_iso: str) -> str:
    """Render the Stock Order tab.

    Two entry paths:
      1. Batch: items selected on the Order selection tab arrive here for review.
      2. Manual: a single-product order form for ad-hoc requests.
    """
    seen = set()
    products = []
    for label, item, _status in all_rows:
        nice = _nice(item["name"])
        if nice in seen:
            continue
        seen.add(nice)
        products.append((nice, label))
    products.sort(key=lambda x: x[0].lower())

    options = '<option value="">Select a product…</option>\n'
    for name, label in products:
        options += (
            f'<option value="{escape(name)}">'
            f'{escape(name)} &middot; {escape(label)}'
            f'</option>\n'
        )

    return f"""
<div class="order-form-card batch-order-card">
  <h3 class="section-title">Review &amp; send selected reorder items</h3>
  <p class="form-help">Items you ticked on the <strong>Order selection</strong> tab show up here. Adjust quantities if needed, then send the batch by email grouped by supplier.</p>

  <div id="batch-empty" class="batch-empty">
    <p>No items selected yet. Open the <strong>Order selection</strong> tab, tick the products you want to order, then come back here.</p>
    <div class="form-actions">
      <button type="button" class="order-btn order-btn-secondary" onclick="goToTab('orders')">Go to Order selection</button>
    </div>
  </div>

  <div id="batch-content" hidden>
    <div class="form-row batch-date-row">
      <label for="batch-order-date">Order date</label>
      <input type="date" id="batch-order-date" name="batch-date" value="{today_iso}" required>
    </div>
    <div class="form-actions batch-toolbar">
      <button type="button" class="order-btn" onclick="useSelectedReorderItems()">Use selected reorder items</button>
      <button type="button" class="order-btn order-btn-secondary" onclick="clearBatchSelection()">Clear selection</button>
    </div>
    <div id="batch-groups"></div>
    <div id="batch-confirmation" class="order-confirmation" hidden>
      <div class="confirmation-title">Batch order ready — email draft opened.</div>
      <p class="confirmation-note" id="batch-conf-note"></p>
      <div class="form-actions">
        <button type="button" class="order-btn order-btn-secondary" onclick="clearBatchSelection()">Place another batch</button>
      </div>
    </div>
  </div>
</div>

<div id="batch-sticky-bar" class="batch-sticky-bar" hidden>
  <div class="batch-sticky-info" id="batch-sticky-info">0 items selected</div>
  <div class="batch-sticky-actions">
    <button type="button" class="order-btn order-btn-secondary" onclick="clearBatchSelection()">Clear selection</button>
    <button type="button" class="order-btn" onclick="sendAllBatchGroups()">Send batch via email</button>
  </div>
</div>

<div class="order-form-card">
  <h3 class="section-title">Place a single ad-hoc order</h3>
  <p class="form-help">Need something not flagged on the Order selection tab? Use this form to submit a one-off order — opens your email client ready to send.</p>

  <form id="stock-order-form" class="order-form" onsubmit="submitStockOrder(event)">
    <div class="form-row">
      <label for="order-date">Order date</label>
      <input type="date" id="order-date" name="date" value="{today_iso}" required>
    </div>

    <div class="form-row">
      <label for="order-item">Stock item</label>
      <select id="order-item" name="item" required>
        {options}
      </select>
    </div>

    <div class="form-row">
      <label for="order-qty">Quantity</label>
      <input type="number" id="order-qty" name="qty" min="1" step="1" placeholder="e.g. 12" required>
    </div>

    <div class="form-row">
      <label for="order-email">Supplier email <span class="form-tag">test</span></label>
      <input type="email" id="order-email" name="email" value="hello@makematicai.com" placeholder="supplier@example.com" required>
      <span class="form-hint">The confirmation message will open in your email client ready to send.</span>
    </div>

    <div class="form-actions">
      <button type="submit" class="order-btn">Submit order</button>
    </div>
  </form>

  <div id="order-confirmation" class="order-confirmation" hidden>
    <div class="confirmation-title">Order submitted — ready to send.</div>
    <div class="confirmation-details">
      <div><span>Date</span><strong id="conf-date"></strong></div>
      <div><span>Item</span><strong id="conf-item"></strong></div>
      <div><span>Quantity</span><strong id="conf-qty"></strong></div>
      <div><span>Sent to</span><strong id="conf-email"></strong></div>
    </div>
    <p class="confirmation-note">An email draft has opened with the order ready to send. Check the recipient is correct, then send.</p>
    <div class="form-actions">
      <button type="button" class="order-btn order-btn-secondary" onclick="resetStockOrder()">Place another order</button>
    </div>
  </div>
</div>
"""


def build_html(result: dict, brief_date: str, pilotlive_title: str) -> str:
    by_cat      = result["by_cat"]
    unmatched   = result["unmatched"]
    missing_par = result["missing_par"]
    total_value = result["total_value"]

    now_str = datetime.now(SAST).strftime("%-d %b %Y, %H:%M SAST")
    day_str = datetime.strptime(brief_date, "%Y-%m-%d").strftime("%-d %B %Y")

    # Optional Google Apps Script Web App URL for syncing order history.
    # Read from GitHub Secret in CI; absent locally — JS treats absence as
    # "localStorage only, no remote sync".
    webhook_url  = os.environ.get("BOSSA_ORDERS_WEBHOOK", "").strip()
    webhook_meta = (
        f'<meta name="bossa-orders-webhook" content="{escape(webhook_url)}">'
        if webhook_url else ""
    )

    total_crit    = sum(len(b["critical"])  for b in by_cat.values())
    total_low     = sum(len(b["low"])       for b in by_cat.values())
    total_healthy = sum(len(b["healthy"])   for b in by_cat.values())
    total_var     = sum(len(b["variance"])  for b in by_cat.values())

    # ── Assemble row lists ────────────────────────────────────────────────────
    crit_rows, low_rows, healthy_rows, all_rows = [], [], [], []
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
            healthy_rows.append((label, item))
            all_rows.append((label, item, "healthy"))
        for item in b["variance"]:
            all_rows.append((label, item, "variance"))

    # Healthy items render best with the lowest-percentage items first so the
    # "watch list" boundary is visible.
    healthy_rows.sort(key=lambda r: r[1].get("pct", 1.0))

    # ── Variance tab ─────────────────────────────────────────────────────────
    var_items: list[tuple[str, str, float]] = []
    for cat in CATEGORY_ORDER:
        b = by_cat.get(cat)
        if not b or not b["variance"]:
            continue
        label = CATEGORY_LABELS.get(cat, cat)
        for item in b["variance"]:
            var_items.append((label, item["name"], item["soh"]))
    var_html = _grouped_variance_table(var_items)

    # ── Admin tab ─────────────────────────────────────────────────────────────
    admin_html = ""
    if missing_par:
        admin_html += (
            f'<h3 class="section-title">Missing par levels '
            f'<span class="badge badge-warn">{len(missing_par)}</span></h3>'
            f'<p class="admin-note">Set par values in <code>bar/pars.json</code> for these products:</p>'
            f'{_grouped_missing_par(missing_par)}'
        )

    if unmatched:
        admin_html += (
            f'<h3 class="section-title" style="margin-top:2rem">New products in PilotLive '
            f'<span class="badge badge-info">{len(unmatched)}</span></h3>'
            f'<p class="admin-note">These products appear in PilotLive but are not on the bar count sheet:</p>'
            f'{_grouped_new_products(unmatched)}'
        )

    if not admin_html:
        admin_html = '<p class="empty">Nothing in admin — all set.</p>'

    # ── Orders tab ────────────────────────────────────────────────────────────
    supplier_groups = _build_supplier_groups(by_cat)
    orders_tab  = _orders_tab(supplier_groups, day_str, brief_date)
    total_order = sum(len(g["critical"]) + len(g["low"]) for g in supplier_groups)

    # ── Stock Order tab ───────────────────────────────────────────────────────
    stock_order_tab = _stock_order_tab(all_rows, brief_date)

    # ── Build tab content strings ─────────────────────────────────────────────
    crit_tab    = _grouped_stock_table(crit_rows, sort_mode="severity")
    low_tab     = _grouped_stock_table(low_rows,  sort_mode="severity")
    healthy_tab = _grouped_stock_table(healthy_rows, sort_mode="alphabetical")
    all_tab     = _grouped_stock_table(all_rows, show_status=True, sort_mode="alphabetical",
                                       empty_msg="No products in scope yet.")

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Bossa Sunningdale — Bar Stock</title>
{webhook_meta}
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
:root {{
  --bossa-ink:        #1A1A1A;
  --bossa-charcoal:   #33373D;
  --bossa-muted:      #6b7280;
  --bossa-cream:      #ECE6D6;
  --bossa-cream-deep: #E0D8C2;
  --bossa-card:       #FFFFFF;
  --bossa-yellow:     #EDCD45;
  --bossa-pink:       #CC3366;
  --bossa-red:        #B91C1C;
  --bossa-amber:      #B45309;
  --bossa-green:      #15803D;
  --body-font:        "Inter", -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
}}

*, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}

body {{
  font-family: var(--body-font);
  background: var(--bossa-cream);
  color: var(--bossa-charcoal);
  min-height: 100vh;
  -webkit-font-smoothing: antialiased;
}}

/* ── Hero band ────────────────────────────────────────── */
.header {{
  background: var(--bossa-ink);
  padding: 1.4rem 2rem;
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 0.75rem;
  border-bottom: 3px solid var(--bossa-yellow);
}}
.header-left h1 {{
  color: #fff;
  font-size: 1.25rem;
  font-weight: 700;
  letter-spacing: 0.06em;
  text-transform: uppercase;
}}
.header-left p {{
  color: rgba(236, 230, 214, 0.6);
  font-size: 0.78rem;
  margin-top: 0.25rem;
  font-weight: 500;
}}
.header-right {{ text-align: right; }}
.header-right .date-main {{ color: #fff; font-size: 0.95rem; font-weight: 600; }}
.header-right .date-sub  {{ color: rgba(236, 230, 214, 0.55); font-size: 0.72rem; margin-top: 0.15rem; }}

/* ── Summary bar ─────────────────────────────────────── */
.summary-bar {{
  background: var(--bossa-card);
  border-bottom: 1px solid var(--bossa-cream-deep);
  padding: 1.1rem 2rem;
  display: flex;
  gap: 2.5rem;
  flex-wrap: wrap;
  align-items: center;
}}
.stat-value {{
  font-size: 1.75rem;
  font-weight: 700;
  line-height: 1;
  font-variant-numeric: tabular-nums;
}}
.stat-label {{
  font-size: 0.66rem;
  color: var(--bossa-muted);
  text-transform: uppercase;
  letter-spacing: 0.06em;
  font-weight: 600;
  margin-top: 0.25rem;
}}
.s-crit .stat-value {{ color: var(--bossa-red); }}
.s-low  .stat-value {{ color: var(--bossa-amber); }}
.s-ok   .stat-value {{ color: var(--bossa-green); }}
.s-val  .stat-value {{ color: var(--bossa-ink); }}
.divider {{ width: 1px; height: 2.2rem; background: var(--bossa-cream-deep); }}

/* ── Tab nav ─────────────────────────────────────────── */
.tab-nav {{
  background: var(--bossa-card);
  border-bottom: 2px solid var(--bossa-cream-deep);
  padding: 0 2rem;
  display: flex;
  overflow-x: auto;
}}
.tab-btn {{
  font-family: inherit;
  padding: 0.85rem 1.2rem;
  border: none;
  background: none;
  font-size: 0.86rem;
  font-weight: 500;
  color: var(--bossa-muted);
  cursor: pointer;
  border-bottom: 2px solid transparent;
  margin-bottom: -2px;
  white-space: nowrap;
  transition: color 0.15s, border-color 0.15s;
}}
.tab-btn:hover {{ color: var(--bossa-charcoal); }}
.tab-btn.active {{
  color: var(--bossa-ink);
  border-bottom-color: var(--bossa-yellow);
  font-weight: 600;
}}
.tab-btn .count {{
  display: inline-block;
  margin-left: 0.4rem;
  padding: 0.1rem 0.5rem;
  border-radius: 9999px;
  font-size: 0.7rem;
  font-weight: 700;
  line-height: 1.6;
}}
.c-crit  {{ background: #fdecec; color: var(--bossa-red); }}
.c-low   {{ background: #fbf0e1; color: var(--bossa-amber); }}
.c-ok    {{ background: #e8f5ec; color: var(--bossa-green); }}
.c-var   {{ background: #fbe7ee; color: var(--bossa-pink); }}
.c-all   {{ background: var(--bossa-cream); color: var(--bossa-charcoal); }}
.c-order {{ background: #fbf3cc; color: #6b5310; }}
.c-batch {{ background: var(--bossa-ink); color: var(--bossa-yellow); }}

/* ── Content ──────────────────────────────────────────── */
.content {{
  max-width: 1180px;
  margin: 1.5rem auto;
  padding: 0 1.5rem;
}}
.tab-pane        {{ display: none; }}
.tab-pane.active {{ display: block; }}

/* ── Search bar ─────────────────────────────────────── */
.search-bar {{
  background: var(--bossa-card);
  border: 1px solid var(--bossa-cream-deep);
  border-radius: 8px;
  padding: 0.5rem 0.85rem;
  margin-bottom: 1.25rem;
  display: flex;
  align-items: center;
  gap: 0.4rem;
  max-width: 480px;
  box-shadow: 0 1px 3px rgba(26, 26, 26, 0.04);
}}
.search-bar:focus-within {{
  border-color: var(--bossa-yellow);
}}
.search-bar input {{
  font-family: inherit;
  font-size: 0.9rem;
  border: none;
  background: transparent;
  flex: 1;
  outline: none;
  color: var(--bossa-charcoal);
  padding: 0.15rem 0;
}}
.search-bar input::placeholder {{
  color: var(--bossa-muted);
}}
.search-clear {{
  font-family: inherit;
  background: none;
  border: none;
  color: var(--bossa-muted);
  cursor: pointer;
  font-size: 1.15rem;
  line-height: 1;
  padding: 0 0.3rem;
  display: none;
  border-radius: 4px;
}}
.search-clear:hover {{ color: var(--bossa-ink); background: var(--bossa-cream); }}
.search-empty {{
  font-style: italic;
  color: var(--bossa-muted);
  font-size: 0.85rem;
  margin: -0.5rem 0 1rem;
  padding-left: 0.25rem;
  display: none;
}}

/* ── Tables ───────────────────────────────────────────── */
.stock-table {{
  width: 100%;
  border-collapse: separate;
  border-spacing: 0;
  background: var(--bossa-card);
  border-radius: 8px;
  box-shadow: 0 1px 3px rgba(26, 26, 26, 0.06), 0 1px 2px rgba(26, 26, 26, 0.04);
  font-size: 0.875rem;
}}
.stock-table thead {{
  position: sticky;
  top: 0;
  z-index: 2;
}}
.stock-table thead th {{
  background: #faf7ee;
  padding: 0.65rem 1rem;
  text-align: left;
  font-size: 0.7rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--bossa-muted);
  border-bottom: 1px solid var(--bossa-cream-deep);
  position: sticky;
  top: 0;
  z-index: 2;
}}
.stock-table thead th:first-child {{ border-top-left-radius: 8px; }}
.stock-table thead th:last-child  {{ border-top-right-radius: 8px; }}
.stock-table thead th.num,
.stock-table thead th.fill-col {{ text-align: center; }}
.stock-table td {{
  padding: 0.65rem 1rem;
  border-bottom: 1px solid #f4eedd;
  vertical-align: middle;
  color: var(--bossa-charcoal);
}}
.stock-table tbody tr:last-child td {{ border-bottom: none; }}
.stock-table tbody tr:last-child td:first-child {{ border-bottom-left-radius: 8px; }}
.stock-table tbody tr:last-child td:last-child  {{ border-bottom-right-radius: 8px; }}
.stock-table tbody tr:hover {{ background: #fdfaf1; }}

.cat-cell  {{ font-size: 0.74rem; color: var(--bossa-muted); font-weight: 500; width: 140px; white-space: nowrap; }}
.name-cell {{ font-weight: 500; color: var(--bossa-ink); }}
.num       {{ text-align: center; font-variant-numeric: tabular-nums; white-space: nowrap; width: 80px; font-weight: 600; color: var(--bossa-ink); }}
.fill-col  {{ width: 170px; white-space: nowrap; text-align: center; }}
.unit-cell {{ font-size: 0.72rem; color: var(--bossa-muted); font-weight: 500; width: 90px; white-space: nowrap; text-transform: lowercase; letter-spacing: 0.02em; }}
.check-col {{ width: 36px; text-align: center; padding-left: 0.5rem !important; padding-right: 0.3rem !important; }}
.check-col input[type="checkbox"] {{
  width: 16px; height: 16px; cursor: pointer;
  accent-color: var(--bossa-yellow);
  vertical-align: middle;
}}

/* Progress bar */
.pb-wrap {{
  display: inline-block;
  width: 88px;
  height: 6px;
  background: var(--bossa-cream-deep);
  border-radius: 3px;
  overflow: hidden;
  vertical-align: middle;
  margin-right: 0.4rem;
}}
.pb-fill       {{ height: 100%; border-radius: 3px; }}
.pb-fill-crit  {{ background: var(--bossa-red); }}
.pb-fill-low   {{ background: var(--bossa-amber); }}
.pb-fill-ok    {{ background: var(--bossa-green); }}
.pb-label    {{
  font-size: 0.75rem;
  color: var(--bossa-charcoal);
  font-variant-numeric: tabular-nums;
  vertical-align: middle;
  font-weight: 600;
}}

/* Left-border status stripe */
.row-critical td:first-child {{ border-left: 3px solid var(--bossa-red); }}
.row-low      td:first-child {{ border-left: 3px solid var(--bossa-amber); }}
.row-healthy  td:first-child {{ border-left: 3px solid var(--bossa-green); }}
.row-variance td:first-child {{ border-left: 3px solid var(--bossa-pink); }}

/* Status pills */
.pill {{
  display: inline-block;
  padding: 0.18rem 0.6rem;
  border-radius: 9999px;
  font-size: 0.7rem;
  font-weight: 600;
}}
.pill-critical {{ background: #fdecec; color: var(--bossa-red); }}
.pill-low      {{ background: #fbf0e1; color: var(--bossa-amber); }}
.pill-healthy  {{ background: #e8f5ec; color: var(--bossa-green); }}
.pill-variance {{ background: #fbe7ee; color: var(--bossa-pink); }}

/* ── Admin tab ───────────────────────────────────────── */
.section-title {{
  font-size: 0.98rem;
  font-weight: 600;
  color: var(--bossa-ink);
  margin-bottom: 0.55rem;
  display: flex;
  align-items: center;
  gap: 0.55rem;
}}
.badge {{
  display: inline-block;
  padding: 0.15rem 0.6rem;
  border-radius: 9999px;
  font-size: 0.7rem;
  font-weight: 700;
}}
.badge-warn {{ background: #fbf0e1; color: var(--bossa-amber); }}
.badge-info {{ background: #fbe7ee; color: var(--bossa-pink); }}
.admin-note {{
  font-size: 0.82rem;
  color: var(--bossa-muted);
  margin-bottom: 0.75rem;
}}
.admin-list {{
  list-style: none;
  background: var(--bossa-card);
  border-radius: 8px;
  box-shadow: 0 1px 3px rgba(26, 26, 26, 0.06);
  overflow: hidden;
  font-size: 0.86rem;
}}
.admin-list li {{
  padding: 0.55rem 1rem;
  border-bottom: 1px solid #f4eedd;
  color: var(--bossa-charcoal);
}}
.admin-list li:last-child {{ border-bottom: none; }}
.admin-list li.more {{ color: var(--bossa-muted); font-style: italic; }}

.empty {{
  text-align: center;
  padding: 3rem 1rem;
  color: var(--bossa-muted);
  font-size: 0.9rem;
  background: var(--bossa-card);
  border-radius: 8px;
  box-shadow: 0 1px 3px rgba(26, 26, 26, 0.06);
}}

/* ── Orders tab ─────────────────────────────────────── */
.supplier-card {{
  background: var(--bossa-card);
  border-radius: 8px;
  box-shadow: 0 1px 3px rgba(26, 26, 26, 0.06), 0 1px 2px rgba(26, 26, 26, 0.04);
  margin-bottom: 1.25rem;
}}
.supplier-header {{
  padding: 1rem 1.25rem;
  border-bottom: 1px solid var(--bossa-cream-deep);
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 1rem;
  flex-wrap: wrap;
}}
.supplier-name {{
  font-size: 0.98rem;
  font-weight: 700;
  color: var(--bossa-ink);
  margin-bottom: 0.3rem;
}}
.supplier-meta {{
  display: flex;
  gap: 1rem;
  flex-wrap: wrap;
  font-size: 0.8rem;
  color: var(--bossa-muted);
}}
.supplier-meta span {{ white-space: nowrap; }}
.supplier-contact {{ color: var(--bossa-charcoal); font-weight: 500; }}
.supplier-email   {{ color: var(--bossa-charcoal); font-variant-numeric: tabular-nums; }}
.supplier-cats    {{ color: var(--bossa-muted); font-style: italic; }}

/* ── Viewed-by-supplier badge ─────────────────────── */
.viewed-badge {{
  display: inline-block;
  padding: 0.18rem 0.6rem;
  border-radius: 9999px;
  font-size: 0.7rem;
  font-weight: 600;
  letter-spacing: 0.01em;
  border: 1px solid transparent;
}}
.viewed-badge-not-sent {{
  background: var(--bossa-cream);
  color: var(--bossa-muted);
  border-color: var(--bossa-cream-deep);
}}
.viewed-badge-pending {{
  background: #fbf0e1;
  color: var(--bossa-amber);
  border-color: #f4dfb4;
}}
.viewed-badge-viewed {{
  background: #e8f5ec;
  color: var(--bossa-green);
  border-color: #cfe6d6;
}}

/* ── Category sections (collapsible) ──────────────── */
.cat-section {{ margin-bottom: 1rem; }}
.cat-section[open] .cat-summary {{
  border-bottom-left-radius: 0;
  border-bottom-right-radius: 0;
  border-bottom: 1px solid var(--bossa-cream-deep);
}}
.cat-summary {{
  list-style: none;
  cursor: pointer;
  background: var(--bossa-card);
  border-radius: 8px;
  padding: 0.65rem 1rem;
  display: flex;
  align-items: center;
  gap: 0.6rem;
  font-size: 0.78rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--bossa-ink);
  box-shadow: 0 1px 3px rgba(26, 26, 26, 0.06), 0 1px 2px rgba(26, 26, 26, 0.04);
  user-select: none;
  position: relative;
  padding-left: 2rem;
}}
.cat-summary::-webkit-details-marker {{ display: none; }}
.cat-summary::before {{
  content: "";
  position: absolute;
  left: 0.85rem;
  top: 50%;
  width: 0;
  height: 0;
  border-left: 5px solid var(--bossa-muted);
  border-top: 4px solid transparent;
  border-bottom: 4px solid transparent;
  transform: translateY(-50%);
  transition: transform 0.12s ease;
}}
.cat-section[open] > .cat-summary::before {{
  transform: translateY(-25%) rotate(90deg);
}}
.cat-summary:hover {{ background: #fdfaf1; }}
.cat-summary-count {{
  background: var(--bossa-cream);
  color: var(--bossa-charcoal);
  padding: 0.1rem 0.55rem;
  border-radius: 9999px;
  font-size: 0.7rem;
  font-weight: 700;
  letter-spacing: 0.04em;
}}
.cat-section[open] .stock-table,
.cat-section[open] .admin-list {{
  border-top-left-radius: 0;
  border-top-right-radius: 0;
  margin-top: 0;
}}
.cat-section[open] .stock-table thead th:first-child {{ border-top-left-radius: 0; }}
.cat-section[open] .stock-table thead th:last-child  {{ border-top-right-radius: 0; }}
.unset {{ color: var(--bossa-muted); font-style: italic; font-weight: 400; }}
.supplier-actions {{
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 0.5rem;
}}
.supplier-badges {{ display: flex; gap: 0.4rem; flex-wrap: wrap; justify-content: flex-end; }}
.badge-crit {{ background: #fdecec; color: var(--bossa-red); }}
.badge-low  {{ background: #fbf0e1; color: var(--bossa-amber); }}
.order-btn {{
  font-family: inherit;
  display: inline-block;
  padding: 0.55rem 1.1rem;
  background: var(--bossa-ink);
  color: var(--bossa-yellow);
  border: none;
  border-radius: 6px;
  font-size: 0.84rem;
  font-weight: 600;
  cursor: pointer;
  white-space: nowrap;
  transition: background 0.15s, color 0.15s;
}}
.order-btn:hover {{ background: var(--bossa-yellow); color: var(--bossa-ink); }}
.order-tbl .order-qty {{ font-weight: 700; color: var(--bossa-ink); }}

/* Per-supplier body that wraps the category sections + select-all toolbar */
.supplier-body {{
  padding: 0.85rem 1.1rem 1rem;
}}
.supplier-select-toolbar {{
  display: flex;
  align-items: center;
  padding: 0.5rem 0.85rem;
  margin-bottom: 0.85rem;
  background: var(--bossa-cream);
  border: 1px solid var(--bossa-cream-deep);
  border-radius: 8px;
}}
/* Inside a supplier card the cat-summary sits on white, so swap to cream
   to keep the same visual rhythm as the Critical / Low tabs. */
.supplier-card .cat-summary {{
  background: var(--bossa-cream);
  box-shadow: none;
  border: 1px solid var(--bossa-cream-deep);
}}
.supplier-card .cat-summary:hover {{ background: var(--bossa-cream-deep); }}
.supplier-card .cat-section[open] > .cat-summary {{
  border-bottom-color: var(--bossa-cream-deep);
}}
.supplier-card .cat-section:last-child {{ margin-bottom: 0; }}

/* Per-category "select all" checkbox sitting in the cat-summary */
.cat-summary .select-all-cat {{
  width: 16px;
  height: 16px;
  accent-color: var(--bossa-yellow);
  cursor: pointer;
  margin-right: 0.15rem;
}}

/* Selection toolbar (Order selection tab) */
.selection-toolbar {{
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  flex-wrap: wrap;
  background: var(--bossa-card);
  border: 1px solid var(--bossa-cream-deep);
  border-radius: 8px;
  padding: 0.7rem 1rem;
  margin-bottom: 1rem;
  box-shadow: 0 1px 3px rgba(26, 26, 26, 0.04);
}}
.check-row {{
  display: inline-flex;
  align-items: center;
  gap: 0.55rem;
  font-size: 0.86rem;
  color: var(--bossa-charcoal);
  cursor: pointer;
  user-select: none;
}}
.check-row input[type="checkbox"] {{
  width: 16px; height: 16px; cursor: pointer;
  accent-color: var(--bossa-yellow);
}}
.check-row-strong {{ font-weight: 600; color: var(--bossa-ink); }}

/* ── Stock Order tab ────────────────────────────────── */
.order-form-card {{
  background: var(--bossa-card);
  border-radius: 12px;
  box-shadow: 0 1px 3px rgba(26, 26, 26, 0.06), 0 1px 2px rgba(26, 26, 26, 0.04);
  padding: 1.75rem;
  max-width: 640px;
}}
.order-form-card .section-title {{ margin-bottom: 0.5rem; }}
.form-help {{
  font-size: 0.86rem;
  color: var(--bossa-muted);
  line-height: 1.55;
  margin-bottom: 1.6rem;
}}
.order-form .form-row {{
  margin-bottom: 1.15rem;
  display: flex;
  flex-direction: column;
}}
.order-form label {{
  font-size: 0.72rem;
  font-weight: 600;
  color: var(--bossa-charcoal);
  margin-bottom: 0.45rem;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  display: flex;
  align-items: center;
  gap: 0.4rem;
}}
.form-tag {{
  background: var(--bossa-yellow);
  color: var(--bossa-ink);
  font-size: 0.62rem;
  font-weight: 700;
  padding: 0.12rem 0.45rem;
  border-radius: 4px;
  letter-spacing: 0.05em;
}}
.order-form input,
.order-form select {{
  font-family: inherit;
  font-size: 0.92rem;
  padding: 0.6rem 0.75rem;
  border: 1px solid var(--bossa-cream-deep);
  border-radius: 8px;
  background: var(--bossa-cream);
  color: var(--bossa-ink);
  outline: none;
  transition: border-color 0.15s, background 0.15s;
}}
.order-form input:focus,
.order-form select:focus {{
  border-color: var(--bossa-yellow);
  background: #fff;
}}
.form-hint {{
  font-size: 0.74rem;
  color: var(--bossa-muted);
  margin-top: 0.4rem;
  font-style: italic;
  line-height: 1.5;
}}
.form-actions {{
  margin-top: 1.5rem;
  display: flex;
  gap: 0.75rem;
}}
.order-btn-secondary {{
  background: var(--bossa-cream-deep);
  color: var(--bossa-ink);
}}
.order-btn-secondary:hover {{
  background: var(--bossa-yellow);
  color: var(--bossa-ink);
}}
.order-confirmation {{
  border: 2px solid var(--bossa-green);
  background: #f3faf5;
  border-radius: 10px;
  padding: 1.4rem 1.5rem;
}}
.confirmation-title {{
  color: var(--bossa-green);
  font-weight: 700;
  font-size: 0.95rem;
  margin-bottom: 1.1rem;
}}
.confirmation-details {{
  display: grid;
  gap: 0.55rem;
  margin-bottom: 1.1rem;
}}
.confirmation-details > div {{
  display: flex;
  gap: 0.85rem;
  align-items: baseline;
  font-size: 0.9rem;
  border-bottom: 1px solid var(--bossa-cream-deep);
  padding-bottom: 0.55rem;
}}
.confirmation-details > div:last-child {{ border-bottom: none; }}
.confirmation-details span {{
  color: var(--bossa-muted);
  min-width: 100px;
  text-transform: uppercase;
  font-size: 0.7rem;
  letter-spacing: 0.06em;
  font-weight: 600;
}}
.confirmation-details strong {{
  color: var(--bossa-ink);
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}}
.confirmation-note {{
  font-size: 0.85rem;
  color: var(--bossa-charcoal);
  line-height: 1.55;
}}

/* Batch order panel */
.batch-order-card {{
  margin-bottom: 1.5rem;
  max-width: none;
}}
.batch-empty {{
  background: var(--bossa-cream);
  border: 1px dashed var(--bossa-cream-deep);
  border-radius: 8px;
  padding: 1.25rem 1.25rem 1rem;
  color: var(--bossa-muted);
  font-size: 0.86rem;
  line-height: 1.55;
}}
.batch-empty p {{ margin-bottom: 0.75rem; }}
.batch-toolbar {{ margin-top: 0; margin-bottom: 1rem; flex-wrap: wrap; }}
.batch-date-row {{
  display: flex;
  flex-direction: column;
  margin-bottom: 1.15rem;
  max-width: 18rem;
}}
.batch-date-row label {{
  font-size: 0.72rem;
  font-weight: 600;
  color: var(--bossa-charcoal);
  margin-bottom: 0.45rem;
  text-transform: uppercase;
  letter-spacing: 0.06em;
}}
.batch-date-row input {{
  font-family: inherit;
  font-size: 0.92rem;
  padding: 0.6rem 0.75rem;
  border: 1px solid var(--bossa-cream-deep);
  border-radius: 8px;
  background: var(--bossa-cream);
  color: var(--bossa-ink);
}}
.batch-group {{
  border: 1px solid var(--bossa-cream-deep);
  border-radius: 10px;
  background: var(--bossa-cream);
  padding: 1rem 1.1rem;
  margin-bottom: 1rem;
}}
.batch-group-header {{
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  gap: 1rem;
  flex-wrap: wrap;
  margin-bottom: 0.7rem;
}}
.batch-group-title {{
  font-weight: 700;
  color: var(--bossa-ink);
  font-size: 0.95rem;
}}
.batch-group-meta {{
  font-size: 0.78rem;
  color: var(--bossa-muted);
}}
.batch-items {{
  display: grid;
  gap: 0.4rem;
}}
.batch-item {{
  display: grid;
  grid-template-columns: 1fr 90px 90px auto;
  gap: 0.6rem;
  align-items: center;
  background: var(--bossa-card);
  border: 1px solid var(--bossa-cream-deep);
  border-radius: 6px;
  padding: 0.5rem 0.75rem;
  font-size: 0.85rem;
}}
.batch-item-name {{ color: var(--bossa-ink); font-weight: 500; }}
.batch-item-meta {{ color: var(--bossa-muted); font-size: 0.74rem; font-variant-numeric: tabular-nums; text-align: right; }}
.batch-item input[type="number"] {{
  font-family: inherit;
  font-size: 0.86rem;
  padding: 0.35rem 0.5rem;
  border: 1px solid var(--bossa-cream-deep);
  border-radius: 6px;
  background: var(--bossa-cream);
  text-align: center;
  font-variant-numeric: tabular-nums;
  width: 100%;
}}
.batch-item input[type="number"]:focus {{ border-color: var(--bossa-yellow); background: #fff; outline: none; }}
.batch-item-remove {{
  background: none;
  border: none;
  color: var(--bossa-muted);
  font-size: 1.05rem;
  line-height: 1;
  cursor: pointer;
  padding: 0.25rem 0.45rem;
  border-radius: 4px;
}}
.batch-item-remove:hover {{ color: var(--bossa-red); background: var(--bossa-cream); }}
.batch-send-btn {{ margin-top: 0.75rem; }}

/* Sticky action bar — always-visible "Send batch via email" while the
   Stock Order tab is active. position:sticky keeps it pinned to the
   viewport bottom while there's content above; it falls into natural
   flow when scrolled to the end. */
.batch-sticky-bar {{
  position: sticky;
  bottom: 0;
  z-index: 50;
  margin-top: 1.25rem;
  padding: 0.85rem 1.1rem;
  background: var(--bossa-card);
  border: 1px solid var(--bossa-cream-deep);
  border-radius: 10px;
  box-shadow: 0 -4px 16px rgba(26, 26, 26, 0.08), 0 1px 3px rgba(26, 26, 26, 0.04);
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  flex-wrap: wrap;
}}
.batch-sticky-info {{
  font-size: 0.86rem;
  font-weight: 600;
  color: var(--bossa-ink);
}}
.batch-sticky-actions {{
  display: flex;
  gap: 0.6rem;
  flex-wrap: wrap;
  margin-left: auto;
}}
@media (max-width: 540px) {{
  .batch-sticky-bar {{ flex-direction: column; align-items: stretch; }}
  .batch-sticky-actions {{ margin-left: 0; justify-content: flex-end; }}
}}
/* Give the Stock Order tab some breathing room below the sticky bar so
   the box-shadow doesn't crowd the page footer. */
#tab-stock-order {{ padding-bottom: 0.5rem; }}

.batch-no-wa {{
  font-size: 0.75rem;
  color: var(--bossa-muted);
  font-style: italic;
  margin-top: 0.6rem;
}}

/* ── Order History tab ──────────────────────────────── */
.c-hist {{ background: var(--bossa-cream-deep); color: var(--bossa-ink); }}
.history-intro {{ margin-bottom: 1rem; }}
.history-intro .section-title {{ margin-bottom: 0.4rem; }}

.history-date-group {{
  background: var(--bossa-card);
  border-radius: 10px;
  box-shadow: 0 1px 3px rgba(26, 26, 26, 0.06), 0 1px 2px rgba(26, 26, 26, 0.04);
  margin-bottom: 1.25rem;
  overflow: hidden;
}}
.history-date-label {{
  background: #faf7ee;
  padding: 0.55rem 1.1rem;
  font-size: 0.72rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--bossa-muted);
  border-bottom: 1px solid var(--bossa-cream-deep);
}}
.history-order {{
  border-bottom: 1px solid #f4eedd;
}}
.history-order:last-child {{ border-bottom: none; }}
.history-order-summary {{
  display: grid;
  grid-template-columns: 1.4fr 1fr 160px 70px;
  gap: 0.8rem;
  align-items: center;
  padding: 0.75rem 1.1rem;
}}
.history-supplier {{
  font-weight: 600;
  color: var(--bossa-ink);
  font-size: 0.92rem;
}}
.history-supplier-meta {{
  font-size: 0.72rem;
  color: var(--bossa-muted);
  margin-top: 0.15rem;
}}
.history-meta {{
  font-size: 0.8rem;
  color: var(--bossa-charcoal);
}}
.history-meta .history-meta-sub {{
  display: block;
  font-size: 0.7rem;
  color: var(--bossa-muted);
  margin-top: 0.15rem;
}}
.history-status {{
  font-family: inherit;
  font-size: 0.74rem;
  font-weight: 600;
  padding: 0.32rem 0.7rem;
  border: 1px solid var(--bossa-cream-deep);
  border-radius: 9999px;
  background: var(--bossa-cream);
  color: var(--bossa-ink);
  cursor: pointer;
  text-transform: capitalize;
  appearance: none;
  -webkit-appearance: none;
  outline: none;
  background-image:
    linear-gradient(45deg, transparent 50%, currentColor 50%),
    linear-gradient(135deg, currentColor 50%, transparent 50%);
  background-position:
    calc(100% - 14px) 50%,
    calc(100% - 9px) 50%;
  background-size: 5px 5px, 5px 5px;
  background-repeat: no-repeat;
  padding-right: 1.4rem;
}}
.history-status:focus {{ border-color: var(--bossa-yellow); }}
.history-status.status-sent      {{ background-color: #fbf0e1; color: var(--bossa-amber); border-color: #f4dfb4; }}
.history-status.status-confirmed {{ background-color: #e7eefb; color: #1e4ea8; border-color: #cad9ee; }}
.history-status.status-received  {{ background-color: #e8f5ec; color: var(--bossa-green); border-color: #cfe6d6; }}
.history-status.status-cancelled {{ background-color: var(--bossa-cream); color: var(--bossa-muted); border-color: var(--bossa-cream-deep); text-decoration: line-through; }}

.history-view-btn {{
  font-family: inherit;
  background: none;
  border: 1px solid var(--bossa-cream-deep);
  border-radius: 6px;
  padding: 0.32rem 0.65rem;
  font-size: 0.78rem;
  font-weight: 600;
  color: var(--bossa-charcoal);
  cursor: pointer;
}}
.history-view-btn:hover {{ background: var(--bossa-cream); color: var(--bossa-ink); }}
.history-view-btn[aria-expanded="true"] {{ background: var(--bossa-ink); color: var(--bossa-yellow); border-color: var(--bossa-ink); }}

.history-order-details {{
  background: var(--bossa-cream);
  border-top: 1px solid var(--bossa-cream-deep);
  padding: 0.75rem 1.1rem 0.9rem;
  font-size: 0.82rem;
}}
.history-order-details[hidden] {{ display: none; }}
.history-items-list {{
  list-style: none;
  display: grid;
  gap: 0.3rem;
}}
.history-items-list li {{
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 0.6rem;
  padding: 0.3rem 0.55rem;
  background: var(--bossa-card);
  border-radius: 5px;
  border: 1px solid var(--bossa-cream-deep);
}}
.history-item-name {{ color: var(--bossa-ink); font-weight: 500; }}
.history-item-qty  {{ color: var(--bossa-charcoal); font-variant-numeric: tabular-nums; font-weight: 600; }}
.history-item-name .history-item-tag {{
  font-size: 0.68rem;
  color: var(--bossa-muted);
  font-weight: 500;
  margin-left: 0.45rem;
  text-transform: lowercase;
}}

.history-footer {{
  margin-top: 1rem;
  display: flex;
  justify-content: flex-end;
}}

@media (max-width: 640px) {{
  .history-order-summary {{
    grid-template-columns: 1fr auto;
    grid-template-areas:
      "supplier status"
      "meta     view";
    gap: 0.5rem 0.75rem;
    padding: 0.7rem 0.85rem;
  }}
  .history-supplier-block {{ grid-area: supplier; }}
  .history-meta          {{ grid-area: meta; }}
  .history-status        {{ grid-area: status; justify-self: end; }}
  .history-view-btn      {{ grid-area: view;   justify-self: end; }}
  .history-order-details {{ padding: 0.6rem 0.85rem 0.75rem; }}
  .history-date-label    {{ padding: 0.5rem 0.85rem; }}
}}

code {{
  font-family: ui-monospace, SFMono-Regular, "SF Mono", monospace;
  background: var(--bossa-cream);
  padding: 0.1rem 0.4rem;
  border-radius: 4px;
  font-size: 0.88em;
}}

/* ── Footer ──────────────────────────────────────────── */
.footer {{
  text-align: center;
  padding: 2rem;
  color: var(--bossa-muted);
  font-size: 0.74rem;
}}

/* ── Responsive ──────────────────────────────────────── */
@media (max-width: 640px) {{
  .header       {{ padding: 1rem; }}
  .summary-bar  {{ padding: 0.85rem 1rem; gap: 1.5rem; }}
  .stat-value   {{ font-size: 1.45rem; }}
  .content      {{ padding: 0 0.75rem; margin-top: 1rem; }}
  .tab-nav      {{ padding: 0 0.5rem; }}
  .stock-table td, .stock-table th {{ padding: 0.5rem 0.6rem; }}
  .cat-cell     {{ display: none; }}
  .fill-col     {{ width: 110px; }}
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
  <button class="tab-btn" data-tab="healthy">Healthy <span class="count c-ok">{total_healthy}</span></button>
  <button class="tab-btn" data-tab="orders">Order selection <span class="count c-order">{total_order}</span></button>
  <button class="tab-btn" data-tab="stock-order">Stock Order <span class="count c-batch" id="batch-count-badge" hidden>0</span></button>
  <button class="tab-btn" data-tab="history">Order History <span class="count c-hist" id="history-count-badge" hidden>0</span></button>
  <button class="tab-btn" data-tab="all">All Products <span class="count c-all">{len(all_rows)}</span></button>
  <button class="tab-btn" data-tab="variance">Variances <span class="count c-var">{total_var}</span></button>
  <button class="tab-btn" data-tab="admin">Admin</button>
</nav>

<div class="content">
  <div class="search-bar">
    <input type="text" id="product-search" placeholder="Search products…" autocomplete="off">
    <button type="button" class="search-clear" id="search-clear" aria-label="Clear search">&times;</button>
  </div>
  <p class="search-empty" id="search-empty"></p>
  <div class="tab-pane active" id="tab-critical">{crit_tab}</div>
  <div class="tab-pane" id="tab-low">{low_tab}</div>
  <div class="tab-pane" id="tab-healthy">{healthy_tab}</div>
  <div class="tab-pane" id="tab-orders">{orders_tab}</div>
  <div class="tab-pane" id="tab-stock-order">{stock_order_tab}</div>
  <div class="tab-pane" id="tab-history">
    <div class="history-intro">
      <h3 class="section-title">Order history</h3>
      <p class="admin-note">Orders sent by email are saved in this browser. Update each order's status as it moves through the supplier (sent → confirmed → received).</p>
    </div>
    <p class="empty" id="history-empty">No orders sent yet. When you send a batch from the <strong>Stock Order</strong> tab, it'll appear here.</p>
    <div id="history-list"></div>
    <div class="history-footer" id="history-footer" hidden>
      <button type="button" class="order-btn order-btn-secondary" onclick="clearOrderHistory()">Clear local history</button>
    </div>
  </div>
  <div class="tab-pane" id="tab-all">{all_tab}</div>
  <div class="tab-pane" id="tab-variance">{var_html}</div>
  <div class="tab-pane" id="tab-admin">{admin_html}</div>
</div>

<div class="footer">
  Bossa Bar Stock Agent &nbsp;·&nbsp; {escape(pilotlive_title)}
</div>

<script>
  const searchBar   = document.querySelector('.search-bar');
  const searchInput = document.getElementById('product-search');
  const searchClear = document.getElementById('search-clear');
  const searchEmpty = document.getElementById('search-empty');

  function updateSearchVisibility() {{
    const activePane = document.querySelector('.tab-pane.active');
    const hasTables  = !!(activePane && activePane.querySelector('.stock-table'));
    searchBar.style.display = hasTables ? '' : 'none';
    if (!hasTables) {{
      searchEmpty.style.display = 'none';
    }}
  }}

  function goToTab(name) {{
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));
    const btn  = document.querySelector('.tab-btn[data-tab="' + name + '"]');
    const pane = document.getElementById('tab-' + name);
    if (btn)  btn.classList.add('active');
    if (pane) pane.classList.add('active');
    updateSearchVisibility();
    applyFilter();
    if (name === 'stock-order') renderBatchPanel();
    if (name === 'history')     renderHistory();
  }}

  document.querySelectorAll('.tab-btn').forEach(btn => {{
    btn.addEventListener('click', () => goToTab(btn.dataset.tab));
  }});

  // ── Product search/filter ──────────────────────────
  function applyFilter() {{
    const q = searchInput.value.trim().toLowerCase();
    const activePane = document.querySelector('.tab-pane.active');
    searchClear.style.display = q ? 'inline-block' : 'none';
    if (!activePane) return;

    const tables = activePane.querySelectorAll('.stock-table');
    const adminLists = activePane.querySelectorAll('.admin-list');
    if (tables.length === 0 && adminLists.length === 0) {{
      searchEmpty.style.display = 'none';
      return;
    }}

    let visibleCount = 0;
    tables.forEach(table => {{
      let tableVisibleRows = 0;
      table.querySelectorAll('tbody tr').forEach(tr => {{
        const nameCell = tr.querySelector('.name-cell');
        if (!nameCell) return;
        const match = !q || nameCell.textContent.toLowerCase().includes(q);
        tr.style.display = match ? '' : 'none';
        if (match) {{ tableVisibleRows++; visibleCount++; }}
      }});
      const supplierCard = table.closest('.supplier-card');
      if (supplierCard) {{
        supplierCard.style.display = tableVisibleRows ? '' : 'none';
      }}
      const catSection = table.closest('.cat-section');
      if (catSection) {{
        catSection.style.display = tableVisibleRows ? '' : 'none';
      }}
    }});

    // Same treatment for the missing-par admin lists.
    adminLists.forEach(ul => {{
      let visibleLis = 0;
      ul.querySelectorAll('li').forEach(li => {{
        const match = !q || li.textContent.toLowerCase().includes(q);
        li.style.display = match ? '' : 'none';
        if (match) {{ visibleLis++; visibleCount++; }}
      }});
      const catSection = ul.closest('.cat-section');
      if (catSection) {{
        catSection.style.display = visibleLis ? '' : 'none';
      }}
    }});

    if (q && visibleCount === 0) {{
      searchEmpty.textContent = 'No products match \"' + q + '\".';
      searchEmpty.style.display = 'block';
    }} else {{
      searchEmpty.style.display = 'none';
    }}
  }}

  searchInput.addEventListener('input', applyFilter);
  searchClear.addEventListener('click', () => {{
    searchInput.value = '';
    applyFilter();
    searchInput.focus();
  }});

  updateSearchVisibility();

  // ── Stock Order form ───────────────────────────────
  function submitStockOrder(e) {{
    e.preventDefault();
    const date  = document.getElementById('order-date').value;
    const item  = document.getElementById('order-item').value;
    const qty   = document.getElementById('order-qty').value;
    const email = document.getElementById('order-email').value.trim();
    if (!date || !item || !qty || !email) return;

    let dateNice = date;
    try {{
      dateNice = new Date(date + 'T12:00:00').toLocaleDateString('en-GB', {{
        weekday: 'long', day: 'numeric', month: 'long', year: 'numeric'
      }});
    }} catch (err) {{}}

    const subject = 'Bossa Sunningdale order — ' + item + ' — ' + dateNice;
    const body =
      'Hi,\\n\\n' +
      'This is Bossa Sunningdale. Please find our bar stock order below.\\n\\n' +
      'Order date: ' + dateNice + '\\n' +
      'Item: ' + item + '\\n' +
      'Quantity: ' + qty + '\\n\\n' +
      'Please confirm availability and ETA.\\n\\n' +
      'Thanks,\\nBossa Sunningdale';

    const mailto = 'mailto:' + encodeURIComponent(email) +
                   '?subject=' + encodeURIComponent(subject) +
                   '&body='   + encodeURIComponent(body);
    window.location.href = mailto;

    document.getElementById('conf-date').textContent  = dateNice;
    document.getElementById('conf-item').textContent  = item;
    document.getElementById('conf-qty').textContent   = qty;
    document.getElementById('conf-email').textContent = email;

    document.getElementById('stock-order-form').hidden   = true;
    document.getElementById('order-confirmation').hidden = false;
  }}

  function resetStockOrder() {{
    const form = document.getElementById('stock-order-form');
    form.reset();
    document.getElementById('order-date').value = new Date().toISOString().slice(0, 10);
    form.hidden = false;
    document.getElementById('order-confirmation').hidden = true;
  }}

  // \u2500\u2500 Order selection: checkbox state \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
  function reorderChecks() {{
    return Array.from(document.querySelectorAll('.reorder-check'));
  }}

  function selectedReorder() {{
    return reorderChecks().filter(cb => cb.checked);
  }}

  function updateBatchBadge() {{
    const badge = document.getElementById('batch-count-badge');
    if (!badge) return;
    const n = selectedReorder().length;
    if (n > 0) {{
      badge.textContent = n;
      badge.hidden = false;
    }} else {{
      badge.hidden = true;
    }}
  }}

  function updateSupplierAllStates() {{
    document.querySelectorAll('.select-all-supplier').forEach(allCb => {{
      const group = allCb.dataset.group;
      const groupChecks = reorderChecks().filter(cb => cb.dataset.group === group);
      if (groupChecks.length === 0) return;
      const checkedCount = groupChecks.filter(cb => cb.checked).length;
      allCb.checked = (checkedCount === groupChecks.length);
      allCb.indeterminate = (checkedCount > 0 && checkedCount < groupChecks.length);
    }});
    const globalCb = document.getElementById('select-all-reorder');
    if (globalCb) {{
      const all = reorderChecks();
      const checked = all.filter(cb => cb.checked).length;
      globalCb.checked = (all.length > 0 && checked === all.length);
      globalCb.indeterminate = (checked > 0 && checked < all.length);
    }}
  }}

  function updateCatAllStates() {{
    document.querySelectorAll('.select-all-cat').forEach(allCb => {{
      const group = allCb.dataset.group;
      const cat   = allCb.dataset.cat;
      const catChecks = reorderChecks().filter(cb =>
        cb.dataset.group === group && cb.dataset.cat === cat
      );
      if (catChecks.length === 0) return;
      const checkedCount = catChecks.filter(cb => cb.checked).length;
      allCb.checked = (checkedCount === catChecks.length);
      allCb.indeterminate = (checkedCount > 0 && checkedCount < catChecks.length);
    }});
  }}

  function onReorderChange() {{
    updateSupplierAllStates();
    updateCatAllStates();
    updateBatchBadge();
  }}

  document.querySelectorAll('.reorder-check').forEach(cb => {{
    cb.addEventListener('change', onReorderChange);
  }});

  document.querySelectorAll('.select-all-supplier').forEach(allCb => {{
    allCb.addEventListener('change', () => {{
      const group = allCb.dataset.group;
      reorderChecks()
        .filter(cb => cb.dataset.group === group)
        .forEach(cb => {{ cb.checked = allCb.checked; }});
      onReorderChange();
    }});
  }});

  document.querySelectorAll('.select-all-cat').forEach(allCb => {{
    allCb.addEventListener('change', () => {{
      const group = allCb.dataset.group;
      const cat   = allCb.dataset.cat;
      reorderChecks()
        .filter(cb => cb.dataset.group === group && cb.dataset.cat === cat)
        .forEach(cb => {{ cb.checked = allCb.checked; }});
      onReorderChange();
    }});
  }});

  const globalSelect = document.getElementById('select-all-reorder');
  if (globalSelect) {{
    globalSelect.addEventListener('change', () => {{
      reorderChecks().forEach(cb => {{ cb.checked = globalSelect.checked; }});
      onReorderChange();
    }});
  }}

  function sendSelectionToStockOrder() {{
    const picked = selectedReorder();
    if (picked.length === 0) {{
      alert('Tick at least one item to send to the Stock Order tab.');
      return;
    }}
    prefillAdhocFromSelection(picked[0]);
    goToTab('stock-order');
  }}

  function prefillAdhocFromSelection(cb) {{
    if (!cb) return;
    const itemSel  = document.getElementById('order-item');
    const qtyInp   = document.getElementById('order-qty');
    const emailInp = document.getElementById('order-email');
    if (itemSel) {{
      const name = cb.dataset.name || '';
      const label = cb.dataset.cat || '';
      let option = Array.from(itemSel.options).find(o => o.value === name);
      if (!option && name) {{
        option = document.createElement('option');
        option.value = name;
        option.textContent = name + ' · ' + label;
        itemSel.add(option, itemSel.options[1] || null);
      }}
      if (option) {{
        option.selected = true;
        itemSel.value = name;
      }} else {{
        itemSel.value = '';
      }}
    }}
    if (qtyInp) {{
      const needed = parseInt(cb.dataset.needed, 10);
      if (needed > 0) qtyInp.value = needed;
    }}
    if (emailInp && cb.dataset.email) {{
      emailInp.value = cb.dataset.email;
    }}
  }}

  // \u2500\u2500 Stock Order: batch panel \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
  function collectSelectedBySupplier() {{
    const groups = new Map();
    selectedReorder().forEach(cb => {{
      const key = cb.dataset.email || ('__noemail__' + (cb.dataset.supplier || 'unknown'));
      if (!groups.has(key)) {{
        groups.set(key, {{
          email:    cb.dataset.email    || '',
          supplier: cb.dataset.supplier || '',
          contact:  cb.dataset.contact  || '',
          items: []
        }});
      }}
      groups.get(key).items.push({{
        name:    cb.dataset.name,
        cat:     cb.dataset.cat,
        unit:    cb.dataset.unit,
        soh:     cb.dataset.soh,
        par:     cb.dataset.par,
        needed:  parseInt(cb.dataset.needed, 10) || 1,
        status:  cb.dataset.status,
      }});
    }});
    return Array.from(groups.values());
  }}

  function renderBatchPanel() {{
    const empty   = document.getElementById('batch-empty');
    const content = document.getElementById('batch-content');
    const wrap    = document.getElementById('batch-groups');
    const conf    = document.getElementById('batch-confirmation');
    if (!empty || !content || !wrap) return;

    const groups = collectSelectedBySupplier();
    if (groups.length === 0) {{
      empty.hidden   = false;
      content.hidden = true;
      wrap.innerHTML = '';
      if (conf) conf.hidden = true;
      updateBatchStickyBar(0, 0, 0);
      return;
    }}

    empty.hidden   = true;
    content.hidden = false;
    if (conf) conf.hidden = true;

    let html = '';
    let totalItems = 0;
    const totalCats = new Set();
    groups.forEach((g, gi) => {{
      const supLabel = g.supplier ? g.supplier : 'Supplier not set';
      const meta = g.email
        ? ('Email ' + g.email + (g.contact ? ' \u00b7 ' + g.contact : ''))
        : 'No email on file';

      // Group items by category. Keep the original index `ii` so the
      // remove + send handlers still resolve to allGroups[gi].items[ii]
      // after we reorder rows visually.
      const byCat = new Map();
      g.items.forEach((it, ii) => {{
        const cat = (it.cat || 'OTHER').toUpperCase();
        if (!byCat.has(cat)) byCat.set(cat, []);
        byCat.get(cat).push({{ it: it, ii: ii }});
      }});
      const catLabels = Array.from(byCat.keys()).sort((a, b) => a.localeCompare(b));

      let catsHtml = '';
      catLabels.forEach(cat => {{
        totalCats.add(cat);
        const entries = byCat.get(cat);
        // Critical before low, then by name.
        entries.sort((a, b) => {{
          const sevA = a.it.status === 'critical' ? 0 : 1;
          const sevB = b.it.status === 'critical' ? 0 : 1;
          if (sevA !== sevB) return sevA - sevB;
          return (a.it.name || '').localeCompare(b.it.name || '');
        }});
        let itemsHtml = '';
        entries.forEach(({{ it, ii }}) => {{
          const safeName = it.name.replace(/"/g, '&quot;');
          itemsHtml += '' +
            '<div class="batch-item" data-gi="' + gi + '" data-ii="' + ii + '">' +
              '<div class="batch-item-name">' + safeName +
                '<div class="batch-item-meta">have ' + it.soh + ' / par ' + it.par + '</div>' +
              '</div>' +
              '<input type="number" min="1" step="1" value="' + it.needed + '" aria-label="Quantity">' +
              '<div class="batch-item-meta">' + it.unit + '</div>' +
              '<button type="button" class="batch-item-remove" aria-label="Remove">&times;</button>' +
            '</div>';
        }});
        catsHtml += '' +
          '<details class="cat-section" open>' +
            '<summary class="cat-summary">' +
              '<span class="cat-summary-name">' + cat + '</span>' +
              '<span class="cat-summary-count">' + entries.length + '</span>' +
            '</summary>' +
            '<div class="batch-items">' + itemsHtml + '</div>' +
          '</details>';
      }});

      totalItems += g.items.length;
      const sendBtn = g.email
        ? '<button type="button" class="order-btn batch-send-btn" data-gi="' + gi + '" onclick="sendBatchGroup(this)">Send batch via email</button>'
        : '<p class="batch-no-wa">Add an email for this supplier in <code>bar/config.py</code> to enable sending.</p>';
      html += '' +
        '<div class="batch-group" data-gi="' + gi + '">' +
          '<div class="batch-group-header">' +
            '<div><div class="batch-group-title">' + supLabel + '</div>' +
              '<div class="batch-group-meta">' + meta + ' \u00b7 ' + g.items.length + ' item' + (g.items.length === 1 ? '' : 's') + '</div></div>' +
          '</div>' +
          catsHtml +
          sendBtn +
        '</div>';
    }});
    wrap.innerHTML = html;
    wrap.dataset.groups = JSON.stringify(groups);
    updateBatchStickyBar(totalItems, totalCats.size, groups.length);

    wrap.querySelectorAll('.batch-item-remove').forEach(btn => {{
      btn.addEventListener('click', () => {{
        const row = btn.closest('.batch-item');
        const gi  = parseInt(row.dataset.gi, 10);
        const ii  = parseInt(row.dataset.ii, 10);
        const allGroups = JSON.parse(wrap.dataset.groups);
        const removed = allGroups[gi].items[ii];
        // Untick the matching reorder checkbox so state stays in sync.
        const match = reorderChecks().find(cb =>
          cb.dataset.name === removed.name &&
          (cb.dataset.email || '') === (allGroups[gi].email || '')
        );
        if (match) match.checked = false;
        onReorderChange();
        renderBatchPanel();
      }});
    }});
  }}

  function updateBatchStickyBar(itemCount, catCount, groupCount) {{
    const bar  = document.getElementById('batch-sticky-bar');
    const info = document.getElementById('batch-sticky-info');
    if (!bar || !info) return;
    if (itemCount === 0) {{
      bar.hidden = true;
      return;
    }}
    bar.hidden = false;
    const itemWord = itemCount === 1 ? 'item' : 'items';
    const catWord  = catCount === 1 ? 'category' : 'categories';
    const supplierSuffix = groupCount > 1
      ? ' · ' + groupCount + ' suppliers'
      : '';
    info.textContent = itemCount + ' ' + itemWord + ' selected across ' +
                       catCount + ' ' + catWord + supplierSuffix;
  }}

  function sendAllBatchGroups() {{
    const wrap = document.getElementById('batch-groups');
    if (!wrap || !wrap.dataset.groups) return;
    const allGroups = JSON.parse(wrap.dataset.groups);
    const sendable = [];
    allGroups.forEach((g, gi) => {{ if (g.email) sendable.push(gi); }});
    if (sendable.length === 0) {{
      alert('No supplier email set — add one in bar/config.py to enable sending.');
      return;
    }}
    sendable.forEach((gi, idx) => {{
      const btn = wrap.querySelector('.batch-send-btn[data-gi="' + gi + '"]');
      if (!btn) return;
      // Stagger slightly so each mailto handoff settles before the next one.
      if (idx === 0) {{
        btn.click();
      }} else {{
        setTimeout(() => btn.click(), idx * 350);
      }}
    }});
  }}

  function useSelectedReorderItems() {{
    renderBatchPanel();
  }}

  function clearBatchSelection() {{
    reorderChecks().forEach(cb => {{ cb.checked = false; }});
    onReorderChange();
    renderBatchPanel();
  }}

  function sendBatchGroup(btn) {{
    const wrap = document.getElementById('batch-groups');
    if (!wrap || !wrap.dataset.groups) return;
    const allGroups = JSON.parse(wrap.dataset.groups);
    const gi = parseInt(btn.dataset.gi, 10);
    const g  = allGroups[gi];
    if (!g || !g.email) return;

    const groupEl = wrap.querySelector('.batch-group[data-gi="' + gi + '"]');
    const items = [];
    if (groupEl) {{
      groupEl.querySelectorAll('.batch-item').forEach((row) => {{
        const qtyInput = row.querySelector('input[type="number"]');
        const qty = Math.max(1, parseInt(qtyInput.value, 10) || 1);
        const ii  = parseInt(row.dataset.ii, 10);
        const src = g.items[ii];
        if (src) items.push(Object.assign({{}}, src, {{ needed: qty }}));
      }});
    }}
    if (items.length === 0) return;

    const dateInput = document.getElementById('batch-order-date');
    const dateRaw = dateInput ? dateInput.value : '';
    let dateNice = dateRaw;
    if (dateRaw) {{
      try {{
        dateNice = new Date(dateRaw + 'T12:00:00').toLocaleDateString('en-GB', {{
          weekday: 'long', day: 'numeric', month: 'long', year: 'numeric'
        }});
      }} catch (err) {{}}
    }}

    const greeting = g.contact ? 'Hi ' + g.contact : 'Hi';
    let body = greeting + ',\\n\\n';
    body += 'Please can we order the following:\\n\\n';
    // Group items by category in first-seen order so the supplier sees a
    // tidy list with WINE/BEER/WHISKEY headings, not a flat dump.
    const byCat = new Map();
    items.forEach(it => {{
      const cat = (it.cat || 'OTHER').toUpperCase();
      if (!byCat.has(cat)) byCat.set(cat, []);
      byCat.get(cat).push(it);
    }});
    byCat.forEach((catItems, cat) => {{
      body += cat + '\\n';
      catItems.forEach(it => {{
        body += '- ' + it.name + ' \u2014 ' + it.needed + '\\n';
      }});
      body += '\\n';
    }});
    body += 'Thanks,\\nBossa Sunningdale';

    const subject = 'Bossa Sunningdale order \u2014 ' + (g.supplier || 'supplier') +
                    (dateNice ? ' \u2014 ' + dateNice : '');

    // Persist the order locally before opening the mail client — the
    // localStorage row is the source of truth; the optional Apps Script
    // webhook gets a best-effort copy.
    const order = {{
      id:             newOrderId(),
      sent_at:        new Date().toISOString(),
      order_date:     dateRaw,
      supplier:       g.supplier || '',
      supplier_email: g.email    || '',
      items: items.map(it => ({{
        name:   it.name,
        qty:    it.needed,
        unit:   it.unit,
        status: it.status
      }})),
      status: 'sent',
      notes:  ''
    }};
    recordOrder(order);

    const mailto = 'mailto:' + encodeURIComponent(g.email) +
                   '?subject=' + encodeURIComponent(subject) +
                   '&body='   + encodeURIComponent(body);
    window.location.href = mailto;

    const conf = document.getElementById('batch-confirmation');
    const note = document.getElementById('batch-conf-note');
    if (note) {{
      note.textContent = 'Sent ' + items.length + ' item' + (items.length === 1 ? '' : 's') +
                         ' to ' + (g.supplier || 'supplier') + ' (' + g.email + '). ' +
                         'Check your email client and send.';
    }}
    if (conf) conf.hidden = false;
  }}

  // ── Order history (localStorage + optional webhook sync) ──────
  const HISTORY_KEY = 'bossaOrders';
  const HISTORY_STATUSES = ['sent', 'confirmed', 'received', 'cancelled'];

  function getWebhookUrl() {{
    const meta = document.querySelector('meta[name="bossa-orders-webhook"]');
    return meta && meta.content ? meta.content.trim() : '';
  }}

  function newOrderId() {{
    if (window.crypto && typeof window.crypto.randomUUID === 'function') {{
      return window.crypto.randomUUID();
    }}
    return 'o_' + Date.now().toString(36) + '_' + Math.random().toString(36).slice(2, 10);
  }}

  function loadOrders() {{
    try {{
      const raw = localStorage.getItem(HISTORY_KEY);
      if (!raw) return [];
      const parsed = JSON.parse(raw);
      return Array.isArray(parsed) ? parsed : [];
    }} catch (err) {{
      return [];
    }}
  }}

  function saveOrders(arr) {{
    try {{
      localStorage.setItem(HISTORY_KEY, JSON.stringify(arr));
    }} catch (err) {{
      // Storage full or disabled — swallow.
    }}
  }}

  function postToWebhook(payload) {{
    const url = getWebhookUrl();
    if (!url) return;
    try {{
      // text/plain avoids the CORS preflight that Apps Script can't satisfy.
      fetch(url, {{
        method: 'POST',
        mode:   'no-cors',
        headers: {{'Content-Type': 'text/plain;charset=UTF-8'}},
        body: JSON.stringify(payload),
        keepalive: true
      }}).catch(() => {{}});
    }} catch (err) {{
      // localStorage is the source of truth — sync is best-effort.
    }}
  }}

  function recordOrder(order) {{
    const all = loadOrders();
    all.push(order);
    saveOrders(all);
    postToWebhook(Object.assign({{action: 'create'}}, order));
    renderHistory();
    updateHistoryBadge();
  }}

  function updateOrderField(id, patch) {{
    const all = loadOrders();
    const idx = all.findIndex(o => o.id === id);
    if (idx < 0) return;
    all[idx] = Object.assign({{}}, all[idx], patch);
    saveOrders(all);
    postToWebhook(Object.assign({{action: 'update', id: id}}, patch));
  }}

  function onHistoryStatusChange(sel) {{
    const id = sel.dataset.id;
    const status = sel.value;
    HISTORY_STATUSES.forEach(s => sel.classList.remove('status-' + s));
    sel.classList.add('status-' + status);
    updateOrderField(id, {{status: status}});
  }}

  function toggleHistoryView(btn) {{
    const order = btn.closest('.history-order');
    if (!order) return;
    const details = order.querySelector('.history-order-details');
    if (!details) return;
    const expanded = btn.getAttribute('aria-expanded') === 'true';
    btn.setAttribute('aria-expanded', expanded ? 'false' : 'true');
    details.hidden = expanded;
    btn.textContent = expanded ? 'View' : 'Hide';
  }}

  function formatDateLabel(iso) {{
    if (!iso) return 'Undated';
    try {{
      return new Date(iso + 'T12:00:00').toLocaleDateString('en-GB', {{
        weekday: 'long', day: 'numeric', month: 'long', year: 'numeric'
      }});
    }} catch (err) {{
      return iso;
    }}
  }}

  function formatSentAt(iso) {{
    if (!iso) return '';
    try {{
      return new Date(iso).toLocaleString('en-GB', {{
        day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit'
      }});
    }} catch (err) {{
      return iso;
    }}
  }}

  function escapeHtml(s) {{
    return String(s == null ? '' : s)
      .replace(/&/g,  '&amp;')
      .replace(/</g,  '&lt;')
      .replace(/>/g,  '&gt;')
      .replace(/"/g,  '&quot;')
      .replace(/'/g,  '&#39;');
  }}

  function renderHistory() {{
    const empty  = document.getElementById('history-empty');
    const list   = document.getElementById('history-list');
    const footer = document.getElementById('history-footer');
    if (!list || !empty) return;

    const orders = loadOrders();
    if (orders.length === 0) {{
      empty.hidden  = false;
      list.innerHTML = '';
      if (footer) footer.hidden = true;
      return;
    }}
    empty.hidden = true;
    if (footer) footer.hidden = false;

    // Newest first.
    const sorted = orders.slice().sort((a, b) => {{
      return String(b.sent_at || '').localeCompare(String(a.sent_at || ''));
    }});

    // Group by order_date.
    const groupsMap = new Map();
    sorted.forEach(o => {{
      const key = o.order_date || '';
      if (!groupsMap.has(key)) groupsMap.set(key, []);
      groupsMap.get(key).push(o);
    }});

    let html = '';
    groupsMap.forEach((rows, date) => {{
      html += '<div class="history-date-group">' +
        '<div class="history-date-label">' + escapeHtml(formatDateLabel(date)) + '</div>';
      rows.forEach(o => {{
        const items     = Array.isArray(o.items) ? o.items : [];
        const itemCount = items.length;
        const sentNice  = formatSentAt(o.sent_at);
        const supplier  = escapeHtml(o.supplier || 'Supplier not set');
        const supEmail  = o.supplier_email || o.supplier_whatsapp || '';
        const waMeta    = supEmail
          ? 'Email ' + escapeHtml(supEmail)
          : 'No email on file';
        const status    = HISTORY_STATUSES.indexOf(o.status) >= 0 ? o.status : 'sent';

        let optionsHtml = '';
        HISTORY_STATUSES.forEach(s => {{
          optionsHtml += '<option value="' + s + '"' +
            (s === status ? ' selected' : '') + '>' + s + '</option>';
        }});

        let itemRows = '';
        items.forEach(it => {{
          const nm  = escapeHtml(it.name || '');
          const qty = escapeHtml(it.qty != null ? it.qty : '');
          const un  = escapeHtml(it.unit || '');
          const tag = it.status
            ? '<span class="history-item-tag">' + escapeHtml(it.status) + '</span>'
            : '';
          itemRows += '<li>' +
            '<span class="history-item-name">' + nm + tag + '</span>' +
            '<span class="history-item-qty">' + qty + ' ' + un + '</span>' +
            '</li>';
        }});

        html += '<div class="history-order" data-id="' + escapeHtml(o.id) + '">' +
          '<div class="history-order-summary">' +
            '<div class="history-supplier-block">' +
              '<div class="history-supplier">' + supplier + '</div>' +
              '<div class="history-supplier-meta">' + waMeta + '</div>' +
            '</div>' +
            '<div class="history-meta">' + itemCount + ' item' + (itemCount === 1 ? '' : 's') +
              (sentNice ? '<span class="history-meta-sub">Sent ' + escapeHtml(sentNice) + '</span>' : '') +
            '</div>' +
            '<select class="history-status status-' + status + '" data-id="' +
              escapeHtml(o.id) + '" onchange="onHistoryStatusChange(this)">' +
              optionsHtml +
            '</select>' +
            '<button type="button" class="history-view-btn" aria-expanded="false" onclick="toggleHistoryView(this)">View</button>' +
          '</div>' +
          '<div class="history-order-details" hidden>' +
            (itemRows
              ? '<ul class="history-items-list">' + itemRows + '</ul>'
              : '<p class="empty">No items recorded.</p>') +
          '</div>' +
        '</div>';
      }});
      html += '</div>';
    }});

    list.innerHTML = html;
  }}

  function updateHistoryBadge() {{
    const badge = document.getElementById('history-count-badge');
    if (!badge) return;
    const n = loadOrders().length;
    if (n > 0) {{
      badge.textContent = n;
      badge.hidden = false;
    }} else {{
      badge.hidden = true;
    }}
  }}

  function clearOrderHistory() {{
    if (!confirm('Clear all order history from this browser?\\n\\nThis only affects local storage — any synced rows in Google Sheets are kept.')) return;
    try {{
      localStorage.removeItem(HISTORY_KEY);
    }} catch (err) {{}}
    renderHistory();
    updateHistoryBadge();
  }}

  // Initialise on load
  updateBatchBadge();
  updateSupplierAllStates();
  updateCatAllStates();
  updateHistoryBadge();
  renderHistory();
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
