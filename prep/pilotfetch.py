"""
Bossa Sunningdale — PilotLive Prep Variance Fetch
===================================================
Fetches the Theoretical Stock On Hand report and returns full row data
including OpeningStock, Purchases, TheoreticalUsage and ClosingStock
so that prep variance can be calculated.

Does NOT share code with inventory/pilotcloud.py — inventory bot is unchanged.
"""

import os
import requests
from requests_ntlm import HttpNtlmAuth
import xml.etree.ElementTree as ET

SSRS_BASE   = "https://reports.pilotlive.co.za/ReportServer"
REPORT_PATH = "%2fStock+Management%2fTheoretical+Stock+On+Hand"
STORE_ID    = "8689"   # Bossa Sunningdale


def fetch_variance_rows(username: str, password: str) -> tuple[list[dict], str]:
    """
    Pull the SSRS XML report and return full rows for variance analysis.

    Each row contains:
        cat               PilotLive category
        name              Product name
        cost              Unit cost (ZAR)
        opening           Opening stock
        purchases         Purchased since last count
        theoretical_usage Theoretical usage from sales / recipes
        soh               Closing stock on hand
        variance          (opening + purchases - theoretical_usage) - soh
                          Negative = used more than theory (wastage / over-portion)
                          Positive = used less than theory (sales not rung / under-portion)

    Returns (rows, title) where title = "Bossa Sunningdale: YYYY-MM-DD"
    """
    url = (
        f"{SSRS_BASE}?{REPORT_PATH}"
        f"&rs:Command=Render&rs:Format=XML&dclink={STORE_ID}"
    )
    auth = HttpNtlmAuth(username, password)

    print("  Connecting to SSRS report server...")
    r = requests.get(url, auth=auth, timeout=120)
    r.raise_for_status()
    print(f"  Received {len(r.content):,} bytes")

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

            opening   = float(detail.get("OpeningStock",      0))
            purchases = float(detail.get("Purchases",         0))
            theory    = float(detail.get("TheoreticalUsage",  0))
            soh       = float(detail.get("ClosingStock",      0))
            variance  = (opening + purchases - theory) - soh

            rows.append({
                "cat":               cat_name,
                "name":              detail.get("ProductName", ""),
                "cost":              cost,
                "opening":           opening,
                "purchases":         purchases,
                "theoretical_usage": theory,
                "soh":               soh,
                "variance":          variance,
            })

    return rows, title
