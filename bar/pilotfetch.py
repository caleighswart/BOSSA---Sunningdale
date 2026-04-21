"""
Bossa Sunningdale — Bar Stock Fetch
====================================
Pulls live stock data from PilotLive SSRS for the bar/alcohol agent.
Uses NTLM auth identical to the inventory and prep bots.

Kept as its own module so the bar bot is independent of the other two —
changes here cannot affect inventory/ or prep/.
"""

import requests
from requests_ntlm import HttpNtlmAuth
import xml.etree.ElementTree as ET

SSRS_BASE   = "https://reports.pilotlive.co.za/ReportServer"
REPORT_PATH = "%2fStock+Management%2fTheoretical+Stock+On+Hand"
STORE_ID    = "8689"   # Bossa Sunningdale


def fetch_bar_rows(username: str, password: str) -> tuple[list[dict], str]:
    """
    Fetch Theoretical Stock On Hand from SSRS and return bar-relevant rows.

    Each row:
        cat     — PilotLive category (e.g. "BEER", "WHISKEY")
        name    — product name (e.g. "be - castle lite")
        cost    — unit cost (ZAR)
        soh     — closing stock on hand
        value   — stock value (ZAR)

    Returns:
        (rows, title) where title e.g. "Bossa Sunningdale: 2026-04-19"
    """
    url = (
        f"{SSRS_BASE}?{REPORT_PATH}"
        f"&rs:Command=Render&rs:Format=XML&dclink={STORE_ID}"
    )
    auth = HttpNtlmAuth(username, password)

    print("  Connecting to SSRS report server...")
    r = requests.get(url, auth=auth, timeout=120)
    r.raise_for_status()
    print(f"  Received {len(r.content):,} bytes of XML data")

    ns   = {"r": "Theoretical_x0020_Stock_x0020_On_x0020_Hand"}
    root = ET.fromstring(r.content)
    title = root.get("Textbox74", "")

    rows = []
    for cat_elem in root.findall(".//r:Category", ns):
        cat_name = cat_elem.get("Category", "")
        for detail in cat_elem.findall(".//r:Details", ns):
            try:
                cost = float(detail.get("Cost", 0))
            except (ValueError, TypeError):
                continue
            if cost <= 0:
                continue
            rows.append({
                "cat":   cat_name,
                "name":  detail.get("ProductName", ""),
                "cost":  cost,
                "soh":   float(detail.get("ClosingStock", 0)),
                "value": float(detail.get("StockValue", 0)),
            })

    return rows, title
