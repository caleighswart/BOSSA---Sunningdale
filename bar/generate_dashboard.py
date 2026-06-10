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
from config import CATEGORY_LABELS, CATEGORY_ORDER, CATEGORY_UNITS, SUPPLIERS, keg_litres, load_pars


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


def _order_qty(item: dict, cat_code: str) -> tuple[int, str, str, int]:
    """Order quantity for a low/critical item.

    Returns (qty, order_unit, display, keg_litres). Draught is counted in
    litres but ordered by the keg, so its shortfall is rounded up to whole 30L
    kegs and shown as e.g. "1 keg (30L)". Everything else keeps the existing
    litre/bottle/unit top-up (ceil(par - soh)).
    """
    deficit = item["par"] - item["soh"]
    if cat_code == "DRAUGHT":
        kl   = keg_litres(item["name"])
        kegs = max(1, int(deficit / kl + 0.9999))
        word = "keg" if kegs == 1 else "kegs"
        return kegs, "kegs", f"{kegs} {word} ({kegs * kl}L)", kl
    qty = max(0, int(deficit + 0.9999))
    return qty, _unit(cat_code), str(qty), 0


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
    to send into the Place order tab for batch ordering.
    Supplier-level and global "select all" controls are included.
    """
    if not supplier_groups:
        return '<p class="empty">Nothing to order — bar is well stocked.</p>'

    # Settings panel: lets the manager set the United Distributors email +
    # their own email (CC'd on every outgoing order) without editing config.py.
    # Values are persisted to localStorage — see applyEmailOverrides() in JS.
    html = (
        '<details class="email-settings" id="email-settings">'
        '  <summary class="email-settings-summary">'
        '    <span class="email-settings-title">Order email settings</span>'
        '    <span class="email-settings-status" id="email-settings-status"></span>'
        '  </summary>'
        '  <div class="email-settings-body order-form">'
        '    <p class="form-help">Set the recipient address for United Distributors and add the manager\'s email so a copy of every order is CC\'d to them. Saved on this computer only.</p>'
        '    <div class="form-row">'
        '      <label for="set-supplier-email">United Distributors email</label>'
        '      <input type="email" id="set-supplier-email" placeholder="orders@uniteddistributors.co.za" autocomplete="off">'
        '    </div>'
        '    <div class="form-row">'
        '      <label for="set-manager-email">Manager email <span class="form-hint-inline">(CC on every order)</span></label>'
        '      <input type="email" id="set-manager-email" placeholder="manager@bossasunningdale.co.za" autocomplete="off">'
        '      <span class="form-hint">A copy of every order is sent here, and replies from the supplier come back to this address.</span>'
        '    </div>'
        '    <div class="form-actions">'
        '      <button type="button" class="order-btn" onclick="saveEmailSettings()">Save</button>'
        '      <button type="button" class="order-btn order-btn-secondary" onclick="clearEmailSettings()">Reset to defaults</button>'
        '      <span class="email-settings-saved" id="email-settings-saved" hidden>Saved</span>'
        '    </div>'
        '  </div>'
        '</details>'
        '<div class="selection-toolbar">'
        '  <label class="check-row check-row-strong">'
        '    <input type="checkbox" id="select-all-reorder">'
        '    <span>Select all reorder items</span>'
        '  </label>'
        '  <button type="button" class="order-btn order-btn-secondary" '
        '          onclick="sendSelectionToStockOrder()">'
        '    Send selected to Place order'
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
                # Draught orders in kegs; everything else in its stock unit.
                qty, order_unit, qty_display, keg_l = _order_qty(item, cat_code)
                status   = "critical" if pct < 0.30 else "low"
                tbl += (
                    f'<tr class="row-{status}">'
                    f'<td class="check-col">'
                    f'<input type="checkbox" class="reorder-check" '
                    f'data-group="{group_id}" '
                    f'data-name="{name}" '
                    f'data-cat="{escape(_label)}" '
                    f'data-unit="{escape(unit)}" '
                    f'data-order-unit="{escape(order_unit)}" '
                    f'data-keg-litres="{keg_l}" '
                    f'data-soh="{soh}" data-par="{par}" data-needed="{qty}" '
                    f'data-status="{status}" '
                    f'data-supplier="{sup_name_attr}" '
                    f'data-email="{email_attr}" '
                    f'data-email-default="{email_attr}" '
                    f'data-contact="{contact_attr}"></td>'
                    f'<td class="name-cell">{name}</td>'
                    f'<td class="num">{soh}</td>'
                    f'<td class="num">{par}</td>'
                    f'<td class="unit-cell">{escape(unit)}</td>'
                    f'<td class="num order-qty">{escape(qty_display)}</td>'
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
        {f'<span class="supplier-email" data-email-default="{email_attr}">{escape(email)}</span>' if email else ''}
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


def _stock_order_tab(all_rows: list, pars: dict, today_iso: str) -> str:
    """Render the Place order tab.

    Two entry paths:
      1. Ad-hoc: a single-product form for one-off orders (primary, top of tab).
      2. Batch: items selected on the Order selection tab arrive here for review.

    Catalogue is the union of every par-sheet product (pars.json) and every
    product PilotLive returned today — so Sava can order anything in the bar
    catalogue, not just items currently below par.
    """
    catalogue: dict[str, str] = {}
    for par_name in pars:
        nice = _nice(par_name)
        if nice in catalogue:
            continue
        cat_code = _cat_from_par_name(par_name)
        label = CATEGORY_LABELS.get(cat_code, "") if cat_code else ""
        catalogue[nice] = label
    for label, item, _status in all_rows:
        nice = _nice(item["name"])
        if nice not in catalogue:
            catalogue[nice] = label

    products = sorted(catalogue.items(), key=lambda x: x[0].lower())

    options = ""
    for name, label in products:
        hint = f"{escape(name)} &middot; {escape(label)}" if label else escape(name)
        options += f'<option value="{escape(name)}">{hint}</option>\n'

    return f"""
<div class="order-form-card">
  <h3 class="section-title">Place an ad-hoc order</h3>
  <p class="form-help">Order any product in the bar catalogue — opens your email client ready to send. Start typing the product name to search.</p>

  <form id="stock-order-form" class="order-form" onsubmit="submitStockOrder(event)">
    <div class="form-row">
      <label for="order-date">Order date</label>
      <input type="date" id="order-date" name="date" value="{today_iso}" required>
    </div>

    <div class="form-row">
      <label for="order-item">Stock item</label>
      <input type="text" id="order-item" name="item" list="ad-hoc-products" autocomplete="off" placeholder="Type to search…" required>
      <datalist id="ad-hoc-products">
        {options}
      </datalist>
    </div>

    <div class="form-row">
      <label for="order-qty">Quantity</label>
      <input type="number" id="order-qty" name="qty" min="1" step="1" placeholder="e.g. 12" required>
    </div>

    <div class="form-row">
      <label for="order-email">Supplier email</label>
      <input type="email" id="order-email" name="email" value="hello@makematicai.com" data-email-default="hello@makematicai.com" placeholder="supplier@example.com" required>
      <span class="form-hint">Defaults to the address set in <strong>Order email settings</strong> (Order selection tab). The confirmation will open in your email client ready to send.</span>
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
    tracked_count = total_crit + total_low + total_healthy

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
    stock_order_tab = _stock_order_tab(all_rows, load_pars(), brief_date)

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
<link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
/* =========================================================
   BOSSA Sunningdale — Bar Stock Dashboard
   Light, friendly, high-contrast. Built for staff at the bar.
   ========================================================= */

:root {{
  /* Paper + ink */
  --bg:          #FAF7F1;   /* warm off-white, paper */
  --bg-soft:     #F3EFE6;
  --panel:       #FFFFFF;
  --panel-soft:  #FAF7F1;
  --line:        #E6DFD0;
  --line-strong: #D5CCB8;
  --line-soft:   #EFEADD;

  /* Ink */
  --ink:         #1C1815;   /* warm near-black */
  --ink-soft:    #3B342C;
  --ink-mute:    #6B6155;
  --ink-faint:   #9B917F;

  /* Action — warm cocoa for primary CTAs */
  --action:      #1C1815;
  --action-hover:#2E2820;

  /* Status — bold, accessible */
  --crit:        #B3271C;   /* clear red */
  --crit-bg:     #FBE8E5;
  --crit-line:   #F4C5BF;
  --low:         #C56B00;   /* warm amber/orange */
  --low-bg:      #FCEDD6;
  --low-line:    #F4D199;
  --ok:          #2E7A3D;   /* green */
  --ok-bg:       #E2F1E3;
  --ok-line:     #B7DDB9;
  --info:        #6A4C8F;   /* plum for variances */
  --info-bg:     #ECE4F2;
  --info-line:   #D2C2DE;
  --accent:      #8C5A2B;   /* warm cocoa accent (brand) */
  --accent-bg:   #F4E9DA;

  /* Fonts */
  --sans:   "Plus Jakarta Sans", -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  --mono:   "JetBrains Mono", ui-monospace, "SF Mono", monospace;

  /* Layout */
  --container-max: 1400px;
  --gutter: 36px;
  --radius-s: 4px;
  --radius-m: 8px;
  --radius-l: 12px;
}}

*, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
button {{ font: inherit; color: inherit; background: none; border: none; cursor: pointer; }}
input, select, textarea {{ font: inherit; color: inherit; }}
ul, ol {{ list-style: none; }}
a {{ color: var(--accent); text-decoration: none; font-weight: 600; }}
a:hover {{ text-decoration: underline; }}

body {{
  font-family: var(--sans);
  background: var(--bg);
  color: var(--ink-soft);
  min-height: 100vh;
  font-size: 16px;
  line-height: 1.5;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}}

/* ─── Masthead ───────────────────────────────────────────── */
.masthead {{
  max-width: var(--container-max);
  margin: 0 auto;
  padding: 28px var(--gutter) 22px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 24px;
}}
.brand-mark {{
  font-family: var(--sans);
  font-weight: 800;
  font-size: 22px;
  letter-spacing: 0.18em;
  color: var(--ink);
}}
.brand-loc {{
  font-size: 14px;
  color: var(--ink-mute);
  margin-top: 4px;
  font-weight: 500;
}}
.masthead-meta {{ text-align: right; }}
.masthead-date {{
  font-weight: 600;
  font-size: 16px;
  color: var(--ink);
}}
.masthead-sub {{
  font-size: 13px;
  color: var(--ink-mute);
  margin-top: 4px;
}}

/* ─── Hero: critical-as-headline ─────────────────────────── */
.hero {{
  max-width: var(--container-max);
  margin: 12px auto 0;
  padding: 32px;
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: var(--radius-l);
  box-shadow: 0 1px 0 rgba(28,24,21,0.02);
}}
.hero-eyebrow {{
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  color: var(--crit);
  margin-bottom: 18px;
  display: flex;
  align-items: center;
  gap: 12px;
}}
.hero-eyebrow::before {{
  content: "";
  width: 10px; height: 10px;
  border-radius: 50%;
  background: var(--crit);
  box-shadow: 0 0 0 4px var(--crit-bg);
  animation: pulse 2.4s ease-in-out infinite;
}}
@keyframes pulse {{
  0%, 100% {{ box-shadow: 0 0 0 4px var(--crit-bg); }}
  50%      {{ box-shadow: 0 0 0 6px rgba(179,39,28,0.18); }}
}}
.hero-grid {{
  display: grid;
  grid-template-columns: minmax(0, 1.05fr) minmax(0, 1fr);
  gap: 48px;
  align-items: end;
}}
.hero-figure {{ display: flex; flex-direction: column; gap: 14px; }}
.hero-num {{
  font-family: var(--sans);
  font-weight: 800;
  font-size: clamp(96px, 14vw, 168px);
  line-height: 0.86;
  letter-spacing: -0.045em;
  font-variant-numeric: tabular-nums;
  color: var(--crit);
}}
.hero-figure-label {{
  font-size: 19px;
  color: var(--ink);
  max-width: 36ch;
  line-height: 1.4;
  font-weight: 500;
}}
.hero-figure-label b {{ font-weight: 700; }}
.hero-cta-block {{
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 14px;
  padding-bottom: 18px;
}}
.cta-primary {{
  font-family: var(--sans);
  font-weight: 700;
  font-size: 17px;
  letter-spacing: -0.005em;
  color: #FFFFFF;
  background: var(--action);
  padding: 18px 28px;
  border-radius: var(--radius-m);
  display: inline-flex;
  align-items: center;
  gap: 12px;
  box-shadow: 0 1px 0 rgba(0,0,0,0.04), 0 12px 28px -14px rgba(28,24,21,0.45);
  transition: background 0.15s, transform 0.05s;
}}
.cta-primary:hover {{ background: var(--action-hover); }}
.cta-primary:active {{ transform: translateY(1px); }}
.cta-primary .cta-icon {{ font-size: 20px; line-height: 1; }}
.cta-meta {{
  font-size: 14px;
  color: var(--ink-mute);
  font-weight: 500;
}}
.cta-meta b {{ color: var(--ink); font-weight: 700; }}

.hero-stats {{
  margin-top: 32px;
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 0;
  border-top: 1px solid var(--line);
  padding-top: 22px;
}}
.hero-stat {{
  padding: 0 24px;
  border-left: 1px solid var(--line);
  display: flex;
  flex-direction: column;
  gap: 6px;
}}
.hero-stat:first-child {{ border-left: none; padding-left: 0; }}
.hero-stat b {{
  font-family: var(--sans);
  font-weight: 700;
  font-size: 38px;
  line-height: 1;
  letter-spacing: -0.02em;
  font-variant-numeric: tabular-nums;
  color: var(--ink);
}}
.hero-stat span {{
  font-size: 13px;
  font-weight: 600;
  color: var(--ink-mute);
  letter-spacing: 0.02em;
}}
.hero-stat[data-tone="low"] b {{ color: var(--low); }}
.hero-stat[data-tone="ok"] b  {{ color: var(--ok); }}
.hero-stat[data-tone="val"] b {{ color: var(--ink); }}

/* ─── Primary nav (3 sections) ───────────────────────────── */
.primary-nav {{
  max-width: var(--container-max);
  margin: 28px auto 0;
  padding: 0 var(--gutter);
  display: flex;
  gap: 0;
  border-bottom: 1px solid var(--line);
}}
.prim {{
  font-family: var(--sans);
  font-weight: 600;
  font-size: 16px;
  padding: 14px 4px 14px;
  margin-right: 32px;
  color: var(--ink-mute);
  position: relative;
  transition: color 0.15s;
}}
.prim:hover {{ color: var(--ink); }}
.prim.active {{ color: var(--ink); font-weight: 700; }}
.prim.active::after {{
  content: "";
  position: absolute;
  left: -2px; right: -2px;
  bottom: -1px;
  height: 3px;
  background: var(--action);
  border-radius: 2px;
}}

/* ─── Secondary nav: chip filters ────────────────────────── */
.secondary-nav {{
  max-width: var(--container-max);
  margin: 0 auto;
  padding: 18px var(--gutter) 6px;
}}
.chip-group {{ display: flex; flex-wrap: wrap; gap: 8px; }}
.chip-group[hidden] {{ display: none; }}
.tab-btn.chip {{
  font-family: var(--sans);
  font-weight: 600;
  font-size: 14px;
  padding: 9px 16px;
  border: 1.5px solid var(--line-strong);
  background: var(--panel);
  color: var(--ink-soft);
  border-radius: 999px;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  transition: color 0.15s, border-color 0.15s, background 0.15s;
}}
.tab-btn.chip:hover {{ color: var(--ink); border-color: var(--ink-mute); }}
.tab-btn.chip.active {{
  color: #FFFFFF;
  background: var(--action);
  border-color: var(--action);
}}
.tab-btn.chip.active::after {{ display: none; }}
.tab-btn.chip .count {{
  display: inline-block;
  padding: 1px 8px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  background: var(--bg-soft);
  color: var(--ink-soft);
  border: 1px solid var(--line);
  line-height: 1.5;
}}
.tab-btn.chip .count[hidden] {{ display: none; }}
.tab-btn.chip.active .count {{
  background: rgba(255,255,255,0.18);
  color: #FFFFFF;
  border-color: rgba(255,255,255,0.2);
}}
.c-crit  {{ background: var(--crit-bg) !important; color: var(--crit) !important; border-color: var(--crit-line) !important; }}
.c-low   {{ background: var(--low-bg) !important; color: var(--low) !important; border-color: var(--low-line) !important; }}
.c-ok    {{ background: var(--ok-bg) !important; color: var(--ok) !important; border-color: var(--ok-line) !important; }}
.c-var   {{ background: var(--info-bg) !important; color: var(--info) !important; border-color: var(--info-line) !important; }}
.c-all   {{ background: var(--bg-soft) !important; color: var(--ink) !important; }}
.c-order {{ background: var(--accent-bg) !important; color: var(--accent) !important; border-color: #E4CFB1 !important; }}
.c-batch {{ background: var(--ok) !important; color: #FFFFFF !important; border-color: var(--ok) !important; font-weight: 700; }}
.c-hist  {{ background: var(--panel-soft) !important; color: var(--ink) !important; border-color: var(--line) !important; }}

.tab-btn.chip.active .c-crit,
.tab-btn.chip.active .c-low,
.tab-btn.chip.active .c-ok,
.tab-btn.chip.active .c-var,
.tab-btn.chip.active .c-all,
.tab-btn.chip.active .c-order,
.tab-btn.chip.active .c-hist {{
  background: rgba(255,255,255,0.18) !important;
  color: #FFFFFF !important;
  border-color: rgba(255,255,255,0.25) !important;
}}

/* ─── Content ────────────────────────────────────────────── */
.content {{
  max-width: var(--container-max);
  margin: 22px auto 64px;
  padding: 0 var(--gutter);
}}
.tab-pane        {{ display: none; }}
.tab-pane.active {{ display: block; }}

/* ─── Search ─────────────────────────────────────────────── */
.search-bar {{
  background: var(--panel);
  border: 1.5px solid var(--line-strong);
  border-radius: var(--radius-m);
  padding: 12px 16px;
  margin-bottom: 22px;
  display: flex;
  align-items: center;
  gap: 10px;
  max-width: 480px;
}}
.search-bar:focus-within {{ border-color: var(--ink); box-shadow: 0 0 0 3px rgba(28,24,21,0.08); }}
.search-bar::before {{
  content: "\\2315";
  color: var(--ink-mute);
  font-size: 18px;
  line-height: 1;
}}
.search-bar input {{
  font-family: var(--sans);
  font-size: 16px;
  font-weight: 500;
  border: none;
  background: transparent;
  flex: 1;
  outline: none;
  color: var(--ink);
}}
.search-bar input::placeholder {{ color: var(--ink-faint); font-weight: 500; }}
.search-clear {{
  color: var(--ink-mute);
  font-size: 20px;
  padding: 0 6px;
  display: none;
}}
.search-clear:hover {{ color: var(--ink); }}
.search-empty {{
  color: var(--ink-mute);
  font-size: 15px;
  margin: -8px 0 16px;
  display: none;
}}

/* ─── Tables (clean & readable) ──────────────────────────── */
.stock-table {{
  width: 100%;
  border-collapse: collapse;
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: var(--radius-m);
  overflow: hidden;
}}
.stock-table thead th {{
  background: var(--bg-soft);
  padding: 14px 18px;
  text-align: left;
  font-size: 12px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--ink-mute);
  border-bottom: 1px solid var(--line);
}}
.stock-table thead th.num,
.stock-table thead th.fill-col {{ text-align: center; }}
.stock-table td {{
  padding: 14px 18px;
  border-bottom: 1px solid var(--line-soft);
  vertical-align: middle;
  color: var(--ink);
  font-size: 15px;
}}
.stock-table tbody tr:last-child td {{ border-bottom: none; }}
.stock-table tbody tr:hover td {{ background: var(--bg-soft); }}

.cat-cell {{
  font-size: 12px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--ink-mute);
  width: 170px;
  white-space: nowrap;
}}
.name-cell {{
  color: var(--ink);
  font-weight: 600;
  font-size: 16px;
}}
.num {{
  font-family: var(--mono);
  text-align: center;
  font-variant-numeric: tabular-nums;
  font-weight: 600;
  font-size: 15px;
  color: var(--ink);
  width: 90px;
}}
.fill-col {{ width: 200px; text-align: center; white-space: nowrap; }}
.unit-cell {{
  font-size: 12px;
  font-weight: 600;
  color: var(--ink-mute);
  text-transform: uppercase;
  letter-spacing: 0.04em;
  width: 100px;
}}
.check-col {{ width: 40px; text-align: center; }}
.check-col input[type="checkbox"] {{
  width: 18px; height: 18px;
  accent-color: var(--action);
  cursor: pointer;
}}

.pb-wrap {{
  display: inline-block;
  width: 100px;
  height: 8px;
  background: var(--bg-soft);
  vertical-align: middle;
  margin-right: 10px;
  overflow: hidden;
  border-radius: 4px;
  border: 1px solid var(--line);
}}
.pb-fill {{ height: 100%; }}
.pb-fill-crit {{ background: var(--crit); }}
.pb-fill-low  {{ background: var(--low); }}
.pb-fill-ok   {{ background: var(--ok); }}
.pb-label {{
  font-family: var(--mono);
  font-size: 13px;
  color: var(--ink);
  font-variant-numeric: tabular-nums;
  font-weight: 600;
  vertical-align: middle;
}}

.row-critical td:first-child {{ box-shadow: inset 4px 0 0 var(--crit); }}
.row-low      td:first-child {{ box-shadow: inset 4px 0 0 var(--low); }}
.row-healthy  td:first-child {{ box-shadow: inset 4px 0 0 var(--ok); }}
.row-variance td:first-child {{ box-shadow: inset 4px 0 0 var(--info); }}

.pill {{
  display: inline-block;
  padding: 4px 10px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}}
.pill-critical {{ background: var(--crit-bg); color: var(--crit); }}
.pill-low      {{ background: var(--low-bg); color: var(--low); }}
.pill-healthy  {{ background: var(--ok-bg); color: var(--ok); }}
.pill-variance {{ background: var(--info-bg); color: var(--info); }}

/* ─── Section title + admin ─────────────────────────────── */
.section-title {{
  font-family: var(--sans);
  font-size: 22px;
  font-weight: 700;
  letter-spacing: -0.01em;
  color: var(--ink);
  margin-bottom: 10px;
  display: flex;
  align-items: center;
  gap: 12px;
}}
.badge {{
  display: inline-block;
  padding: 3px 10px;
  border-radius: 999px;
  font-size: 11px;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  font-weight: 700;
}}
.badge-warn {{ background: var(--low-bg); color: var(--low); border: 1px solid var(--low-line); }}
.badge-info {{ background: var(--info-bg); color: var(--info); border: 1px solid var(--info-line); }}
.admin-note {{
  font-size: 16px;
  color: var(--ink-soft);
  margin-bottom: 18px;
  max-width: 60ch;
  line-height: 1.55;
}}
.admin-list {{
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: var(--radius-m);
  overflow: hidden;
  font-size: 15px;
}}
.admin-list li {{
  padding: 12px 18px;
  border-bottom: 1px solid var(--line-soft);
  color: var(--ink);
  font-weight: 500;
}}
.admin-list li:last-child {{ border-bottom: none; }}
.admin-list li.more {{ color: var(--ink-mute); font-style: italic; }}

.empty {{
  text-align: center;
  padding: 60px 20px;
  font-size: 18px;
  color: var(--ink-mute);
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: var(--radius-m);
  font-weight: 500;
}}

/* ─── Supplier cards ─────────────────────────────────────── */
.supplier-card {{
  background: var(--panel);
  border: 1px solid var(--line);
  border-left: 4px solid var(--action);
  border-radius: var(--radius-m);
  margin-bottom: 20px;
  overflow: hidden;
}}
.supplier-header {{
  padding: 20px 22px;
  border-bottom: 1px solid var(--line);
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 18px;
  flex-wrap: wrap;
  background: var(--panel-soft);
}}
.supplier-name {{
  font-size: 22px;
  font-weight: 700;
  letter-spacing: -0.01em;
  color: var(--ink);
  margin-bottom: 8px;
}}
.supplier-meta {{
  display: flex;
  gap: 16px;
  flex-wrap: wrap;
  font-size: 14px;
  color: var(--ink-mute);
  font-weight: 500;
}}
.supplier-contact, .supplier-wa {{ color: var(--ink-soft); font-weight: 600; }}
.supplier-email em {{ font-style: italic; color: var(--ink-mute); font-weight: 500; }}
.supplier-cats {{
  color: var(--ink-mute);
  font-size: 14px;
  font-weight: 500;
}}
.unset {{ color: var(--ink-faint); font-style: italic; font-weight: 500; }}
.supplier-actions {{
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 10px;
}}
.supplier-badges {{ display: flex; gap: 6px; flex-wrap: wrap; justify-content: flex-end; }}
.badge-crit {{ background: var(--crit-bg); color: var(--crit); border: 1px solid var(--crit-line); }}
.badge-low  {{ background: var(--low-bg); color: var(--low); border: 1px solid var(--low-line); }}
.order-btn {{
  font-family: var(--sans);
  padding: 12px 20px;
  background: var(--action);
  color: #FFFFFF;
  border-radius: var(--radius-s);
  font-size: 14px;
  font-weight: 700;
  letter-spacing: -0.005em;
  transition: background 0.15s, transform 0.05s;
  display: inline-flex;
  align-items: center;
  gap: 10px;
}}
.order-btn::after {{ content: "\\2192"; font-weight: 600; }}
.order-btn:hover {{ background: var(--action-hover); }}
.order-btn:active {{ transform: translateY(1px); }}
.order-btn-unset {{
  padding: 10px 16px;
  background: transparent;
  color: var(--ink-mute);
  border: 1.5px dashed var(--line-strong);
  border-radius: var(--radius-s);
  font-size: 13px;
  font-style: italic;
  font-weight: 500;
}}
.order-btn-unset::after {{ display: none; }}
.order-tbl .order-qty {{
  font-family: var(--mono);
  font-weight: 700;
  color: var(--ink);
  font-size: 15px;
  background: var(--accent-bg);
  padding: 4px 10px;
  border-radius: var(--radius-s);
  display: inline-block;
}}

.selection-toolbar {{
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  flex-wrap: wrap;
  background: var(--panel);
  border: 1.5px solid var(--line-strong);
  border-radius: var(--radius-m);
  padding: 14px 18px;
  margin-bottom: 20px;
}}
.check-row {{
  display: inline-flex;
  align-items: center;
  gap: 10px;
  font-size: 15px;
  color: var(--ink);
  user-select: none;
  cursor: pointer;
  font-weight: 500;
}}
.check-row input[type="checkbox"] {{
  width: 18px; height: 18px;
  accent-color: var(--action);
}}
.check-row-strong {{ font-weight: 700; }}

.order-btn-secondary {{
  background: var(--panel);
  color: var(--ink);
  border: 1.5px solid var(--line-strong);
}}
.order-btn-secondary::after {{ color: var(--ink-mute); }}
.order-btn-secondary:hover {{ background: var(--bg-soft); border-color: var(--ink-mute); }}

/* ─── Forms (Stock Order + Batch) ────────────────────────── */
.order-form-card {{
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: var(--radius-m);
  padding: 28px 30px;
  max-width: 720px;
  margin-bottom: 22px;
}}
.order-form-card .section-title {{ margin-bottom: 6px; }}
.form-help {{
  font-size: 16px;
  color: var(--ink-soft);
  margin-bottom: 24px;
  line-height: 1.55;
}}
.order-form .form-row {{
  margin-bottom: 18px;
  display: flex;
  flex-direction: column;
}}
.order-form label {{
  font-size: 13px;
  font-weight: 700;
  color: var(--ink-soft);
  margin-bottom: 8px;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  display: flex;
  align-items: center;
  gap: 8px;
}}
.form-tag {{
  background: var(--accent);
  color: #FFFFFF;
  font-size: 10px;
  font-weight: 700;
  padding: 2px 8px;
  border-radius: 999px;
  letter-spacing: 0.04em;
}}
.order-form input,
.order-form select {{
  font-family: var(--sans);
  font-size: 16px;
  padding: 12px 14px;
  border: 1.5px solid var(--line-strong);
  border-radius: var(--radius-s);
  background: var(--panel);
  color: var(--ink);
  outline: none;
}}
.order-form input:focus,
.order-form select:focus {{
  border-color: var(--ink);
  box-shadow: 0 0 0 3px rgba(28,24,21,0.08);
}}
.order-form select {{
  appearance: none;
  -webkit-appearance: none;
  background-image:
    linear-gradient(45deg, transparent 50%, var(--ink) 50%),
    linear-gradient(135deg, var(--ink) 50%, transparent 50%);
  background-position:
    calc(100% - 18px) 52%,
    calc(100% - 13px) 52%;
  background-size: 6px 6px, 6px 6px;
  background-repeat: no-repeat;
  padding-right: 38px;
  cursor: pointer;
}}
.order-form select optgroup {{
  font-family: var(--sans);
  font-weight: 700;
  font-size: 12px;
  color: var(--ink);
  letter-spacing: 0.06em;
  text-transform: uppercase;
  background: var(--bg-soft);
  padding: 4px 0;
}}
.order-form select option {{
  font-weight: 500;
  font-size: 15px;
  color: var(--ink);
  background: var(--panel);
  padding: 6px 0;
}}
.form-hint {{
  font-size: 13px;
  color: var(--ink-mute);
  margin-top: 6px;
  line-height: 1.5;
}}
.form-actions {{
  margin-top: 22px;
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}}
.order-confirmation {{
  border: 1.5px solid var(--ok);
  background: var(--ok-bg);
  border-radius: var(--radius-m);
  padding: 22px;
}}
.confirmation-title {{
  color: var(--ok);
  font-size: 20px;
  font-weight: 700;
  margin-bottom: 14px;
}}
.confirmation-details {{ display: grid; gap: 8px; margin-bottom: 14px; }}
.confirmation-details > div {{
  display: flex;
  gap: 14px;
  font-size: 15px;
  border-bottom: 1px solid var(--line-soft);
  padding-bottom: 8px;
  align-items: baseline;
}}
.confirmation-details > div:last-child {{ border-bottom: none; }}
.confirmation-details span {{
  color: var(--ink-mute);
  min-width: 120px;
  text-transform: uppercase;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.06em;
}}
.confirmation-details strong {{ color: var(--ink); font-weight: 700; }}
.confirmation-note {{ color: var(--ink-soft); font-size: 15px; line-height: 1.6; }}

.batch-order-card {{ max-width: none; }}
.batch-empty {{
  background: var(--bg-soft);
  border: 2px dashed var(--line-strong);
  border-radius: var(--radius-m);
  padding: 24px;
  color: var(--ink-soft);
  font-size: 16px;
  line-height: 1.55;
}}
.batch-empty p {{ margin-bottom: 12px; }}
.batch-toolbar {{ margin: 0 0 14px; }}
.batch-date-row {{
  display: flex;
  flex-direction: column;
  margin-bottom: 18px;
  max-width: 18rem;
}}
.batch-date-row label {{
  font-size: 13px;
  font-weight: 700;
  color: var(--ink-soft);
  margin-bottom: 8px;
  text-transform: uppercase;
  letter-spacing: 0.06em;
}}
.batch-date-row input {{
  font-family: var(--sans);
  font-size: 16px;
  padding: 12px 14px;
  border: 1.5px solid var(--line-strong);
  border-radius: var(--radius-s);
  background: var(--panel);
  color: var(--ink);
}}
.batch-group {{
  border: 1px solid var(--line);
  border-left: 4px solid var(--accent);
  background: var(--panel);
  border-radius: var(--radius-m);
  padding: 18px 20px;
  margin-bottom: 14px;
}}
.batch-group-header {{ display: flex; justify-content: space-between; align-items: baseline; gap: 14px; flex-wrap: wrap; margin-bottom: 12px; }}
.batch-group-title {{ font-weight: 700; color: var(--ink); font-size: 18px; letter-spacing: -0.005em; }}
.batch-group-meta {{ font-size: 13px; color: var(--ink-mute); font-weight: 500; }}
.batch-items {{ display: grid; gap: 6px; }}
.batch-items-head {{
  display: grid;
  grid-template-columns: 1.6fr 72px 72px 110px 84px 36px;
  gap: 12px;
  align-items: center;
  padding: 10px 14px 8px;
  margin-bottom: 4px;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--ink-mute);
  border-bottom: 1px solid var(--line-soft);
}}
.batch-items-head > div {{ text-align: center; }}
.batch-items-head > div:first-child {{ text-align: left; }}
.batch-item {{
  display: grid;
  grid-template-columns: 1.6fr 72px 72px 110px 84px 36px;
  gap: 12px;
  align-items: center;
  background: var(--bg-soft);
  border: 1px solid var(--line);
  border-radius: var(--radius-s);
  padding: 10px 14px;
  font-size: 15px;
}}
.batch-item-name {{ color: var(--ink); font-weight: 600; }}
.batch-item-meta {{ color: var(--ink-mute); font-size: 12px; text-align: center; font-weight: 500; }}
.batch-item-meta-compact {{
  display: none;
  color: var(--ink-mute);
  font-size: 12px;
  font-weight: 500;
  margin-top: 2px;
}}
.batch-item-stock,
.batch-item-par {{
  font-family: var(--mono);
  font-size: 15px;
  font-weight: 600;
  color: var(--ink);
  text-align: center;
}}
.batch-item-unit {{
  color: var(--ink-mute);
  font-size: 13px;
  font-weight: 500;
  text-align: center;
}}
.batch-item[data-status="critical"] .batch-item-stock {{ color: var(--crit); }}
.batch-item[data-status="low"] .batch-item-stock {{ color: var(--warn, #B47A1F); }}
.batch-item input[type="number"] {{
  font-family: var(--mono);
  font-size: 15px;
  font-weight: 600;
  padding: 8px 10px;
  border: 1.5px solid var(--line-strong);
  border-radius: var(--radius-s);
  background: var(--panel);
  color: var(--ink);
  text-align: center;
  width: 100%;
}}
.batch-item input[type="number"]:focus {{ border-color: var(--ink); outline: none; }}
.batch-item-remove {{
  color: var(--ink-mute);
  font-size: 18px;
  padding: 4px 8px;
  border-radius: var(--radius-s);
}}
.batch-item-remove:hover {{ color: var(--crit); background: var(--crit-bg); }}
.batch-send-btn {{ margin-top: 14px; }}
.batch-no-wa {{ font-size: 13px; color: var(--ink-mute); margin-top: 10px; font-style: italic; }}

/* ─── Order History ──────────────────────────────────────── */
.history-intro {{ margin-bottom: 18px; }}
.history-intro .section-title {{ margin-bottom: 6px; }}
.history-date-group {{
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: var(--radius-m);
  margin-bottom: 18px;
  overflow: hidden;
}}
.history-date-label {{
  background: var(--bg-soft);
  padding: 12px 18px;
  font-size: 12px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--ink-mute);
  border-bottom: 1px solid var(--line);
}}
.history-order {{ border-bottom: 1px solid var(--line-soft); }}
.history-order:last-child {{ border-bottom: none; }}
.history-order-summary {{
  display: grid;
  grid-template-columns: 1.4fr 1fr 180px 90px;
  gap: 14px;
  align-items: center;
  padding: 16px 18px;
}}
.history-supplier {{ font-size: 18px; font-weight: 700; color: var(--ink); }}
.history-supplier-meta {{ font-size: 13px; color: var(--ink-mute); margin-top: 3px; font-weight: 500; }}
.history-meta {{ font-size: 14px; color: var(--ink-soft); font-weight: 500; }}
.history-meta .history-meta-sub {{ display: block; font-size: 12px; color: var(--ink-mute); margin-top: 3px; }}
.history-status {{
  font-family: var(--sans);
  font-size: 12px;
  font-weight: 700;
  padding: 8px 28px 8px 14px;
  border: 1.5px solid var(--line-strong);
  border-radius: var(--radius-s);
  background: var(--panel);
  color: var(--ink);
  cursor: pointer;
  text-transform: uppercase;
  letter-spacing: 0.04em;
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
}}
.history-status:focus {{ border-color: var(--ink); }}
.history-status.status-sent      {{ background-color: var(--low-bg); color: var(--low); border-color: var(--low-line); }}
.history-status.status-confirmed {{ background-color: var(--accent-bg); color: var(--accent); border-color: #E4CFB1; }}
.history-status.status-received  {{ background-color: var(--ok-bg); color: var(--ok); border-color: var(--ok-line); }}
.history-status.status-cancelled {{ background-color: var(--bg-soft); color: var(--ink-mute); border-color: var(--line); text-decoration: line-through; }}
.history-view-btn {{
  font-family: var(--sans);
  background: var(--panel);
  border: 1.5px solid var(--line-strong);
  border-radius: var(--radius-s);
  padding: 8px 14px;
  font-size: 12px;
  font-weight: 700;
  color: var(--ink);
  letter-spacing: 0.04em;
  text-transform: uppercase;
}}
.history-view-btn:hover {{ background: var(--bg-soft); border-color: var(--ink-mute); }}
.history-view-btn[aria-expanded="true"] {{ background: var(--action); color: #FFFFFF; border-color: var(--action); }}
.history-order-details {{
  background: var(--bg-soft);
  border-top: 1px solid var(--line);
  padding: 16px 18px 20px;
  font-size: 14px;
}}
.history-order-details[hidden] {{ display: none; }}
.history-items-list {{ display: grid; gap: 5px; }}
.history-items-list li {{
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 12px;
  padding: 10px 14px;
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: var(--radius-s);
  font-size: 14px;
}}
.history-item-name {{ color: var(--ink); font-weight: 600; }}
.history-item-qty {{ font-family: var(--mono); font-weight: 700; color: var(--ink); }}
.history-item-name .history-item-tag {{ font-size: 11px; font-weight: 600; color: var(--ink-mute); margin-left: 8px; text-transform: uppercase; letter-spacing: 0.04em; }}
.history-footer {{ margin-top: 16px; display: flex; justify-content: flex-end; }}

code {{
  font-family: var(--mono);
  background: var(--bg-soft);
  padding: 2px 7px;
  border-radius: 3px;
  font-size: 13px;
  color: var(--accent);
  border: 1px solid var(--line);
  font-weight: 600;
}}

.footer {{
  text-align: center;
  padding: 28px var(--gutter);
  color: var(--ink-faint);
  font-size: 12px;
  font-weight: 500;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  max-width: var(--container-max);
  margin: 0 auto;
}}

/* ─── Responsive ─────────────────────────────────────────── */
@media (max-width: 980px) {{
  :root {{ --gutter: 22px; }}
  .hero {{ padding: 24px; margin: 8px auto 0; border-radius: var(--radius-m); }}
  .hero-grid {{ grid-template-columns: 1fr; gap: 24px; align-items: start; }}
  .hero-cta-block {{ padding-bottom: 0; }}
  .hero-stats {{ grid-template-columns: repeat(2, 1fr); gap: 14px 0; }}
  .hero-stat {{ padding: 0 0 0 18px; }}
  .hero-stat:nth-child(odd) {{ border-left: none; padding-left: 0; padding-right: 18px; }}
  .hero-stat:nth-child(3),
  .hero-stat:nth-child(4) {{ padding-top: 14px; border-top: 1px solid var(--line); }}
  .history-order-summary {{ grid-template-columns: 1fr 110px; gap: 10px; }}
  .history-order-summary .history-meta {{ grid-column: 1 / -1; }}
  .history-order-summary .history-status {{ grid-column: 1; }}
  .history-order-summary .history-view-btn {{ grid-column: 2; justify-self: end; }}
  .batch-items-head {{ grid-template-columns: 1.4fr 60px 60px 96px 70px 30px; font-size: 10.5px; gap: 8px; }}
  .batch-item {{ grid-template-columns: 1.4fr 60px 60px 96px 70px 30px; gap: 8px; }}
}}
@media (max-width: 720px) {{
  .batch-items-head {{ display: none; }}
  .batch-item {{ grid-template-columns: 1fr 96px auto; gap: 10px; }}
  .batch-item .batch-item-stock,
  .batch-item .batch-item-par,
  .batch-item .batch-item-unit {{ display: none; }}
  .batch-item .batch-item-meta-compact {{ display: block; }}
}}
@media (max-width: 720px) {{
  :root {{ --gutter: 16px; }}
  .masthead {{ padding: 20px var(--gutter) 14px; flex-direction: column; align-items: flex-start; gap: 8px; }}
  .masthead-meta {{ text-align: left; }}
  .hero {{ padding: 22px 20px; }}
  .hero-num {{ font-size: 96px; }}
  .hero-figure-label {{ font-size: 17px; }}
  .hero-stats {{ grid-template-columns: 1fr 1fr; }}
  .hero-stat b {{ font-size: 32px; }}
  .prim {{ margin-right: 22px; padding: 12px 4px; font-size: 15px; }}
  .content {{ padding: 0 var(--gutter); }}
  .cat-cell {{ display: none; }}
  .fill-col {{ width: 140px; }}
  .pb-wrap {{ width: 78px; }}
  .stock-table td, .stock-table th {{ padding: 12px 14px; font-size: 14px; }}
  .name-cell {{ font-size: 15px; }}
  .order-form-card {{ padding: 20px 18px; }}
  .selection-toolbar {{ padding: 14px; }}
  .supplier-header {{ padding: 16px; }}
  .supplier-actions {{ width: 100%; align-items: stretch; }}
  .order-btn {{ justify-content: center; }}
  .tab-pane > .stock-table, .supplier-card > .stock-table {{ display: block; overflow-x: auto; }}
  .tab-pane > .stock-table thead, .supplier-card > .stock-table thead {{ display: table-header-group; }}
  .tab-pane > .stock-table tbody, .supplier-card > .stock-table tbody {{ display: table-row-group; }}
  .tab-pane > .stock-table tr, .supplier-card > .stock-table tr {{ display: table-row; }}
  .tab-pane > .stock-table td, .supplier-card > .stock-table td {{ display: table-cell; }}
}}
@media (max-width: 520px) {{
  .hero-num {{ font-size: 80px; }}
  .hero-stats {{ grid-template-columns: 1fr 1fr; gap: 12px 0; }}
  .hero-stat b {{ font-size: 28px; }}
  .cta-primary {{ width: 100%; justify-content: center; font-size: 15px; padding: 14px 18px; }}
  .history-order-summary {{ grid-template-columns: 1fr; }}
  .history-order-summary .history-view-btn {{ justify-self: start; }}
}}

/* ─── Collapsible category sections ─────────────────── */
.cat-sections-wrap {{ display: block; }}
.cat-section {{
  margin-bottom: 12px;
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: var(--radius-m);
  overflow: hidden;
}}
.cat-section:last-child {{ margin-bottom: 0; }}
.cat-summary {{
  list-style: none;
  cursor: pointer;
  padding: 14px 18px 14px 38px;
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: 13px;
  font-weight: 700;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--ink);
  background: var(--bg-soft);
  border-bottom: 1px solid transparent;
  user-select: none;
  position: relative;
  transition: background 0.15s;
}}
.cat-summary::-webkit-details-marker {{ display: none; }}
.cat-summary::before {{
  content: "";
  position: absolute;
  left: 18px;
  top: 50%;
  width: 0; height: 0;
  border-left: 6px solid var(--ink-mute);
  border-top: 5px solid transparent;
  border-bottom: 5px solid transparent;
  transform: translateY(-50%);
  transition: transform 0.15s ease;
}}
.cat-section[open] > .cat-summary {{
  border-bottom-color: var(--line);
}}
.cat-section[open] > .cat-summary::before {{
  transform: translateY(-50%) rotate(90deg);
}}
.cat-summary:hover {{ background: var(--panel-soft); }}
.cat-summary-name {{ flex: 1; }}
.cat-summary-count {{
  padding: 2px 10px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.02em;
  background: var(--bg);
  color: var(--ink-soft);
  border: 1px solid var(--line-strong);
  text-transform: none;
}}
.cat-summary .select-all-cat {{
  width: 18px;
  height: 18px;
  accent-color: var(--action);
  cursor: pointer;
  margin-right: 4px;
}}
/* Inside a cat-section, the inner table loses its outer chrome */
.cat-section .stock-table {{
  border: none;
  border-radius: 0;
  background: var(--panel);
}}
.cat-section .stock-table thead th {{
  background: var(--panel-soft);
  padding: 9px 18px;
  font-size: 11px;
}}
.cat-section .stock-table tbody tr:first-child td {{ padding-top: 12px; }}
.cat-section .stock-table .cat-cell {{ display: none; }}
.cat-section .stock-table .cat-header {{ display: none; }}
/* When inside a supplier-card, swap the chrome to keep visual rhythm */
.supplier-card .cat-section {{
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: var(--radius-s);
  margin-bottom: 10px;
}}
.supplier-card .cat-section > .cat-summary {{
  background: var(--panel-soft);
}}
.supplier-card .cat-section > .cat-summary:hover {{
  background: var(--bg-soft);
}}

/* ─── Email settings panel ──────────────────────────── */
.email-settings {{
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: var(--radius-m);
  margin-bottom: 18px;
  overflow: hidden;
}}
.email-settings-summary {{
  list-style: none;
  cursor: pointer;
  padding: 14px 18px 14px 40px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  font-size: 15px;
  font-weight: 700;
  color: var(--ink);
  position: relative;
  user-select: none;
  transition: background 0.15s;
}}
.email-settings-summary::-webkit-details-marker {{ display: none; }}
.email-settings-summary::before {{
  content: "";
  position: absolute;
  left: 18px; top: 50%;
  width: 0; height: 0;
  border-left: 6px solid var(--ink-mute);
  border-top: 5px solid transparent;
  border-bottom: 5px solid transparent;
  transform: translateY(-50%);
  transition: transform 0.15s ease;
}}
.email-settings[open] > .email-settings-summary::before {{
  transform: translateY(-50%) rotate(90deg);
}}
.email-settings-summary:hover {{ background: var(--bg-soft); }}
.email-settings-title {{ flex: 1; }}
.email-settings-status {{
  font-size: 13px;
  color: var(--ink-mute);
  font-weight: 500;
}}
.email-settings-status b {{ color: var(--ink); font-weight: 700; }}
.email-settings-body {{
  padding: 6px 18px 20px;
  border-top: 1px solid var(--line);
}}
.email-settings-body .form-help {{ margin: 14px 0 16px; }}
.email-settings-body .form-row {{ margin-bottom: 14px; }}
.form-hint-inline {{
  font-size: 12px;
  font-weight: 500;
  color: var(--ink-mute);
  text-transform: none;
  letter-spacing: 0;
}}
.email-settings-saved {{
  color: var(--ok);
  font-size: 13px;
  font-weight: 700;
  align-self: center;
}}

/* ─── Viewed badge on supplier cards ────────────────── */
.viewed-badge {{
  display: inline-block;
  padding: 4px 10px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.02em;
  border: 1px solid transparent;
  text-transform: none;
}}
.viewed-badge-not-sent {{
  background: var(--bg-soft);
  color: var(--ink-mute);
  border-color: var(--line-strong);
}}
.viewed-badge-pending {{
  background: var(--low-bg);
  color: var(--low);
  border-color: var(--low-line);
}}
.viewed-badge-viewed {{
  background: var(--ok-bg);
  color: var(--ok);
  border-color: var(--ok-line);
}}

/* ─── Supplier-email display ────────────────────────── */
.supplier-email {{
  color: var(--ink-soft);
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}}
.supplier-email em {{ color: var(--ink-mute); font-style: italic; font-weight: 500; }}

/* ─── Sticky batch action bar ───────────────────────── */
.batch-sticky-bar {{
  position: sticky;
  bottom: 0;
  z-index: 50;
  margin-top: 18px;
  padding: 14px 18px;
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: var(--radius-m);
  box-shadow: 0 -8px 24px rgba(28,24,21,0.10), 0 1px 3px rgba(28,24,21,0.05);
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  flex-wrap: wrap;
}}
.batch-sticky-info {{
  font-size: 15px;
  font-weight: 700;
  color: var(--ink);
}}
.batch-sticky-actions {{ display: flex; gap: 10px; flex-wrap: wrap; margin-left: auto; }}
@media (max-width: 540px) {{
  .batch-sticky-bar {{ flex-direction: column; align-items: stretch; }}
  .batch-sticky-actions {{ margin-left: 0; justify-content: stretch; }}
  .batch-sticky-actions .order-btn {{ flex: 1; justify-content: center; }}
}}
#tab-stock-order {{ padding-bottom: 8px; }}

</style>
</head>
<body>

<header class="masthead">
  <div class="brand">
    <div class="brand-mark">BOSSA</div>
    <div class="brand-loc">Sunningdale · Bar Stock</div>
  </div>
  <div class="masthead-meta">
    <div class="masthead-date">{day_str}</div>
    <div class="masthead-sub">Updated {now_str}</div>
  </div>
</header>

<section class="hero">
  <div class="hero-eyebrow">Tonight's open floor</div>
  <div class="hero-grid">
    <div class="hero-figure">
      <div class="hero-num">{total_crit}</div>
      <div class="hero-figure-label">Critical items — stock at or near zero. Action before doors open.</div>
    </div>
    <div class="hero-cta-block">
      <button type="button" class="cta-primary" onclick="goToTab('orders')">
        <span class="cta-icon">→</span>
        Review &amp; send supplier orders
      </button>
      <div class="cta-meta"><b>{total_order}</b> items queued · grouped by supplier email</div>
    </div>
  </div>
  <div class="hero-stats">
    <div class="hero-stat" data-tone="low"><b>{total_low}</b><span>Low</span></div>
    <div class="hero-stat" data-tone="ok"><b>{total_healthy}</b><span>Healthy</span></div>
    <div class="hero-stat"><b>{tracked_count}</b><span>Products tracked</span></div>
    <div class="hero-stat" data-tone="val"><b>R{total_value:,.0f}</b><span>Stock value</span></div>
  </div>
</section>

<nav class="primary-nav">
  <button type="button" class="prim active" data-section="stock">Stock</button>
  <button type="button" class="prim" data-section="orders">Orders</button>
  <button type="button" class="prim" data-section="admin">Admin</button>
</nav>

<nav class="secondary-nav">
  <div class="chip-group" data-section="stock">
    <button class="tab-btn chip active" data-tab="critical">Critical <span class="count c-crit">{total_crit}</span></button>
    <button class="tab-btn chip" data-tab="low">Low <span class="count c-low">{total_low}</span></button>
    <button class="tab-btn chip" data-tab="healthy">Healthy <span class="count c-ok">{total_healthy}</span></button>
    <button class="tab-btn chip" data-tab="all">All products <span class="count c-all">{tracked_count}</span></button>
    <button class="tab-btn chip" data-tab="variance">Variances <span class="count c-var">{total_var}</span></button>
  </div>
  <div class="chip-group" data-section="orders" hidden>
    <button class="tab-btn chip" data-tab="orders">By supplier <span class="count c-order">{total_order}</span></button>
    <button class="tab-btn chip" data-tab="stock-order">Place order <span class="count c-batch" id="batch-count-badge" hidden>0</span></button>
    <button class="tab-btn chip" data-tab="history">History <span class="count c-hist" id="history-count-badge" hidden>0</span></button>
  </div>
  <div class="chip-group" data-section="admin" hidden>
    <button class="tab-btn chip" data-tab="admin">Pars &amp; suppliers</button>
  </div>
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
    <p class="empty" id="history-empty">No orders sent yet. When you send an order from the <strong>Place order</strong> tab, it'll appear here.</p>
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

  // Tab → primary section (Stock / Orders / Admin).
  const TAB_SECTION = {{
    critical:    'stock',
    low:         'stock',
    healthy:     'stock',
    all:         'stock',
    variance:    'stock',
    orders:      'orders',
    'stock-order': 'orders',
    history:     'orders',
    admin:       'admin',
  }};

  function setActiveSection(section) {{
    document.querySelectorAll('.prim').forEach(p => {{
      p.classList.toggle('active', p.dataset.section === section);
    }});
    document.querySelectorAll('.chip-group').forEach(g => {{
      if (g.dataset.section === section) g.removeAttribute('hidden');
      else                                g.setAttribute('hidden', '');
    }});
  }}

  function goToTab(name) {{
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));
    const btn  = document.querySelector('.tab-btn[data-tab="' + name + '"]');
    const pane = document.getElementById('tab-' + name);
    if (btn)  btn.classList.add('active');
    if (pane) pane.classList.add('active');
    const section = TAB_SECTION[name];
    if (section) setActiveSection(section);
    updateSearchVisibility();
    applyFilter();
    if (name === 'stock-order') renderBatchPanel();
    if (name === 'history')     renderHistory();
  }}

  document.querySelectorAll('.tab-btn').forEach(btn => {{
    btn.addEventListener('click', () => goToTab(btn.dataset.tab));
  }});

  // Primary nav clicks reveal that section's chip group and activate its first chip.
  document.querySelectorAll('.prim').forEach(p => {{
    p.addEventListener('click', () => {{
      const section = p.dataset.section;
      setActiveSection(section);
      const firstChip = document.querySelector('.chip-group[data-section="' + section + '"] .tab-btn');
      if (firstChip) goToTab(firstChip.dataset.tab);
    }});
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

  // ── Email settings (persisted to localStorage) ──────────
  // Only United Distributors is overridable today. Other suppliers (if added
  // later) keep their config.py defaults.
  const EMAIL_OVERRIDE_NAME = 'United Distributors';
  const SUPPLIER_EMAIL_KEY  = 'bossa.suppliers.united.email';
  const MANAGER_EMAIL_KEY   = 'bossa.manager.email';

  function getSupplierEmailOverride() {{
    try {{ return (localStorage.getItem(SUPPLIER_EMAIL_KEY) || '').trim(); }}
    catch (e) {{ return ''; }}
  }}
  function getManagerEmail() {{
    try {{ return (localStorage.getItem(MANAGER_EMAIL_KEY) || '').trim(); }}
    catch (e) {{ return ''; }}
  }}

  function applyEmailOverrides() {{
    const override = getSupplierEmailOverride();

    // 1. Reorder checkboxes (data-email feeds collectSelectedBySupplier).
    document.querySelectorAll('.reorder-check[data-email-default]').forEach(cb => {{
      const def = cb.dataset.emailDefault || '';
      const isUnited = (cb.dataset.supplier || '') === EMAIL_OVERRIDE_NAME;
      cb.dataset.email = (override && isUnited) ? override : def;
    }});

    // 2. Visible supplier-email pill on each supplier card.
    document.querySelectorAll('.supplier-email[data-email-default]').forEach(span => {{
      const def = span.dataset.emailDefault || '';
      const card = span.closest('.supplier-card');
      const supName = card ? (card.querySelector('.supplier-name')?.textContent || '').trim() : '';
      span.textContent = (override && supName === EMAIL_OVERRIDE_NAME) ? override : def;
    }});

    // 3. Manual order form prefilled email. Called on init + on save —
    //    both legitimate moments to refresh the default. A user editing
    //    the form mid-session keeps their input because we don't re-run.
    const manualInp = document.getElementById('order-email');
    if (manualInp && manualInp.dataset.emailDefault !== undefined) {{
      const def = manualInp.dataset.emailDefault || '';
      manualInp.value = override || def;
    }}

    // 4. Update the status line in the settings panel summary.
    updateEmailSettingsStatus();

    // 5. If the Stock Order tab is currently rendered, refresh it so the
    //    batch-groups JSON picks up the new email.
    const stockPane = document.getElementById('tab-stock-order');
    if (stockPane && stockPane.classList.contains('active')) {{
      try {{ renderBatchPanel(); }} catch (e) {{}}
    }}
  }}

  function updateEmailSettingsStatus() {{
    const el = document.getElementById('email-settings-status');
    if (!el) return;
    const supEmail = getSupplierEmailOverride();
    const mgrEmail = getManagerEmail();
    const parts = [];
    parts.push(supEmail ? ('Supplier: ' + supEmail) : 'Supplier: default');
    if (mgrEmail) parts.push('Manager CC: ' + mgrEmail);
    el.textContent = parts.join(' · ');
  }}

  function saveEmailSettings() {{
    const sup = (document.getElementById('set-supplier-email').value || '').trim();
    const mgr = (document.getElementById('set-manager-email').value || '').trim();
    try {{
      if (sup) localStorage.setItem(SUPPLIER_EMAIL_KEY, sup);
      else     localStorage.removeItem(SUPPLIER_EMAIL_KEY);
      if (mgr) localStorage.setItem(MANAGER_EMAIL_KEY, mgr);
      else     localStorage.removeItem(MANAGER_EMAIL_KEY);
    }} catch (e) {{}}
    applyEmailOverrides();
    const saved = document.getElementById('email-settings-saved');
    if (saved) {{
      saved.hidden = false;
      setTimeout(() => {{ saved.hidden = true; }}, 2000);
    }}
  }}

  function clearEmailSettings() {{
    try {{
      localStorage.removeItem(SUPPLIER_EMAIL_KEY);
      localStorage.removeItem(MANAGER_EMAIL_KEY);
    }} catch (e) {{}}
    const supInp = document.getElementById('set-supplier-email');
    const mgrInp = document.getElementById('set-manager-email');
    if (supInp) supInp.value = '';
    if (mgrInp) mgrInp.value = '';
    applyEmailOverrides();
  }}

  // Returns "&cc=..." for appending to a mailto URL, or "" if no manager set.
  function ccParam() {{
    const mgr = getManagerEmail();
    return mgr ? ('&cc=' + encodeURIComponent(mgr)) : '';
  }}

  // Returns a body suffix asking the supplier to reply-all so the manager
  // stays on the thread. Empty string if no manager email set.
  function replyToBodyLine() {{
    const mgr = getManagerEmail();
    return mgr ? ('\\nPlease reply to all so ' + mgr + ' stays on the thread.\\n') : '';
  }}

  // Populate the settings inputs from localStorage on load.
  (function initEmailSettingsForm() {{
    const supInp = document.getElementById('set-supplier-email');
    const mgrInp = document.getElementById('set-manager-email');
    if (supInp) supInp.value = getSupplierEmailOverride();
    if (mgrInp) mgrInp.value = getManagerEmail();
  }})();
  applyEmailOverrides();

  // ── Stock Order form ─────────────────────
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
      'Please confirm availability and ETA.\\n' +
      replyToBodyLine() +
      '\\nThanks,\\nBossa Sunningdale';

    const mailto = 'mailto:' + encodeURIComponent(email) +
                   '?subject=' + encodeURIComponent(subject) +
                   '&body='   + encodeURIComponent(body) +
                   ccParam();
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
      alert('Tick at least one item to send to the Place order tab.');
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
      itemSel.value = cb.dataset.name || '';
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
        name:      cb.dataset.name,
        cat:       cb.dataset.cat,
        unit:      cb.dataset.unit,
        orderUnit: cb.dataset.orderUnit || cb.dataset.unit,
        kegLitres: parseInt(cb.dataset.kegLitres, 10) || 0,
        soh:       cb.dataset.soh,
        par:       cb.dataset.par,
        needed:    parseInt(cb.dataset.needed, 10) || 1,
        status:    cb.dataset.status,
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
          const statusAttr = it.status ? ' data-status="' + it.status + '"' : '';
          itemsHtml += '' +
            '<div class="batch-item" data-gi="' + gi + '" data-ii="' + ii + '"' + statusAttr + '>' +
              '<div class="batch-item-name">' + safeName +
                '<div class="batch-item-meta-compact">' + it.soh + ' / ' + it.par + ' ' + it.unit + '</div>' +
              '</div>' +
              '<div class="batch-item-stock" aria-label="In stock">' + it.soh + '</div>' +
              '<div class="batch-item-par" aria-label="Par">' + it.par + '</div>' +
              '<input type="number" min="1" step="1" value="' + it.needed + '" aria-label="Order quantity">' +
              '<div class="batch-item-unit">' + (it.kegLitres ? (it.orderUnit + ' (' + (it.needed * it.kegLitres) + 'L)') : it.orderUnit) + '</div>' +
              '<button type="button" class="batch-item-remove" aria-label="Remove">&times;</button>' +
            '</div>';
        }});
        const headerRow = '' +
          '<div class="batch-items-head" aria-hidden="true">' +
            '<div>Product</div>' +
            '<div>In stock</div>' +
            '<div>Par</div>' +
            '<div>Order qty</div>' +
            '<div>Unit</div>' +
            '<div></div>' +
          '</div>';
        catsHtml += '' +
          '<details class="cat-section" open>' +
            '<summary class="cat-summary">' +
              '<span class="cat-summary-name">' + cat + '</span>' +
              '<span class="cat-summary-count">' + entries.length + '</span>' +
            '</summary>' +
            headerRow +
            '<div class="batch-items">' + itemsHtml + '</div>' +
          '</details>';
      }});

      totalItems += g.items.length;
      const sendBtn = g.email
        ? '<button type="button" class="order-btn batch-send-btn" data-gi="' + gi + '" onclick="sendBatchGroup(this)">Send batch via email</button>'
        : '<p class="batch-no-wa">Add an email for this supplier in <strong>Order email settings</strong> on the Order selection tab.</p>';
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

    // Draught is ordered in kegs — keep the "(NL)" litre total beside the qty
    // input in sync as the keg count is edited.
    const liveGroups = JSON.parse(wrap.dataset.groups);
    wrap.querySelectorAll('.batch-item').forEach(row => {{
      const gi = parseInt(row.dataset.gi, 10);
      const ii = parseInt(row.dataset.ii, 10);
      const it = liveGroups[gi] && liveGroups[gi].items[ii];
      if (!it || !it.kegLitres) return;
      const input    = row.querySelector('input[type="number"]');
      const unitCell = row.querySelector('.batch-item-unit');
      if (!input || !unitCell) return;
      input.addEventListener('input', () => {{
        const k = Math.max(1, parseInt(input.value, 10) || 1);
        unitCell.textContent = it.orderUnit + ' (' + (k * it.kegLitres) + 'L)';
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
      alert('No supplier email set — open Order email settings on the Order selection tab and add the supplier address.');
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
        // Draught is ordered by the keg \u2014 spell out kegs + litre total.
        const qtyStr = it.kegLitres
          ? (it.needed + ' keg' + (it.needed === 1 ? '' : 's') + ' (' + (it.needed * it.kegLitres) + 'L)')
          : it.needed;
        body += '- ' + it.name + ' \u2014 ' + qtyStr + '\\n';
      }});
      body += '\\n';
    }});
    body += replyToBodyLine();
    body += '\\nThanks,\\nBossa Sunningdale';

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
        unit:   it.orderUnit || it.unit,
        status: it.status
      }})),
      status: 'sent',
      notes:  ''
    }};
    recordOrder(order);

    const mailto = 'mailto:' + encodeURIComponent(g.email) +
                   '?subject=' + encodeURIComponent(subject) +
                   '&body='   + encodeURIComponent(body) +
                   ccParam();
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
