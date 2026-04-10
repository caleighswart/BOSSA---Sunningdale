"""
Bossa Sunningdale — SSRS Stock Report Download
===============================================
Fetches the Theoretical Stock On Hand report directly from the
PilotLive SSRS report server using NTLM authentication and XML format.

No browser automation needed — a single HTTP GET returns structured data.

Credentials are read from environment variables:
  PILOTLIVE_USERNAME — your Pilot Cloud phone number / username
  PILOTLIVE_PASSWORD — your Pilot Cloud password
"""

import requests
from requests_ntlm import HttpNtlmAuth
import xml.etree.ElementTree as ET

SSRS_BASE   = "https://reports.pilotlive.co.za/ReportServer"
REPORT_PATH = "%2fStock+Management%2fTheoretical+Stock+On+Hand"
STORE_ID    = "8689"   # Bossa Sunningdale


def download_stock_data(username: str, password: str) -> tuple[list[dict], str]:
    """
    Fetch Theoretical Stock On Hand from SSRS as XML,
    parse into list of dicts matching the existing analysis pipeline:

    Returns:
        (rows, title) where rows = [{"cat", "name", "cost", "soh", "value"}, ...]
        and title = report header string e.g. "Bossa Sunningdale: 2026-04-08"
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

    # Parse the SSRS XML report
    ns = {"r": "Theoretical_x0020_Stock_x0020_On_x0020_Hand"}
    root = ET.fromstring(r.content)

    # Extract report date from title attribute  e.g. "Bossa Sunningdale: 2026-04-08"
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
