# PilotLive — Live Stock Data Pull Reference

This document describes how to pull live stock data from PilotLive programmatically.
Use it whenever an agent needs to fetch real-time stock levels for Bossa Sunningdale.

---

## Key Facts

- PilotLive does **not** issue API keys — use the personal login credentials
- Data is served by an **SSRS report server** at `reports.pilotlive.co.za`
- Authentication is **Windows NTLM** (not Basic, not Bearer token)
- No browser or Playwright needed — a single HTTP GET returns all data
- The working format is **XML** — CSV/Excel time out on the server (>3 min)

---

## The One Request That Works

```
GET https://reports.pilotlive.co.za/ReportServer?%2fStock+Management%2fTheoretical+Stock+On+Hand&rs:Command=Render&rs:Format=XML&dclink=8689
Authorization: NTLM
```

- Returns ~200KB of structured XML in ~2 seconds
- `dclink=8689` is the Bossa Sunningdale store ID — this parameter **must** be set (no default)
- All other parameters (`toDate`, `brand`, `region`) default correctly and do not need to be passed

---

## Report Parameters

Discovered via SSRS SOAP `LoadReport` API:

| Parameter | Type    | Required | Value    | Notes                          |
|-----------|---------|----------|----------|--------------------------------|
| `toDate`  | DateTime | No      | auto     | Defaults to yesterday's date   |
| `brand`   | Integer  | No      | `91`     | Bossa brand ID                 |
| `region`  | Integer  | No      | `9`      | South Africa — Western Cape    |
| `dclink`  | Integer  | **Yes** | **`8689`** | Bossa Sunningdale store ID — no default, will error without it |

---

## XML Response Structure

Root element carries the report date in `Textbox74`:
```xml
<Report xmlns="Theoretical_x0020_Stock_x0020_On_x0020_Hand"
        Textbox74="Bossa Sunningdale: 2026-04-08">
  <Tablix1>
    <ExpenseType_Collection>
      <ExpenseType>
        <Category_Collection>
          <Category Category="BEER" StockValue1="5840.18">
            <Details_Collection>
              <Details
                ProductName="be - amstel"
                Cost="11.22"
                OpeningStock="16.000"
                Purchases="24.000"
                TheoreticalUsage="0.000"
                ClosingStock="40.000"
                StockValue="448.80" />
              ...
            </Details_Collection>
          </Category>
```

**XML namespace:** `Theoretical_x0020_Stock_x0020_On_x0020_Hand`

**Key fields per item:**

| XML Attribute      | Meaning                        |
|--------------------|-------------------------------|
| `Category`         | Stock category (BEER, CHICKEN, etc.) |
| `ProductName`      | Item name as stored in Pilot  |
| `Cost`             | Unit cost in ZAR               |
| `OpeningStock`     | Quantity at last stock take    |
| `Purchases`        | Quantity purchased since take  |
| `TheoreticalUsage` | Theoretical usage from sales   |
| `ClosingStock`     | **Current stock on hand**      |
| `StockValue`       | Total value (cost × SOH)       |

---

## Python Implementation

Dependencies:
```
requests==2.32.3
requests-ntlm==1.3.0
```

The complete, production-ready implementation is at:
```
inventory/pilotcloud.py
```

Key function signature:
```python
from pilotcloud import download_stock_data

rows, title = download_stock_data(username, password)
# rows  → list of {"cat", "name", "cost", "soh", "value"} dicts
# title → "Bossa Sunningdale: 2026-04-08"
```

Minimal standalone example:
```python
import requests
from requests_ntlm import HttpNtlmAuth
import xml.etree.ElementTree as ET

SSRS_BASE   = "https://reports.pilotlive.co.za/ReportServer"
REPORT_PATH = "%2fStock+Management%2fTheoretical+Stock+On+Hand"
STORE_ID    = "8689"
NS          = {"r": "Theoretical_x0020_Stock_x0020_On_x0020_Hand"}

url  = f"{SSRS_BASE}?{REPORT_PATH}&rs:Command=Render&rs:Format=XML&dclink={STORE_ID}"
auth = HttpNtlmAuth("0834436203", "<password from secrets>")

r    = requests.get(url, auth=auth, timeout=120)
r.raise_for_status()

root  = ET.fromstring(r.content)
title = root.get("Textbox74")   # "Bossa Sunningdale: 2026-04-08"

rows = []
for cat in root.findall(".//r:Category", NS):
    for detail in cat.findall(".//r:Details", NS):
        rows.append({
            "cat":   cat.get("Category"),
            "name":  detail.get("ProductName"),
            "cost":  float(detail.get("Cost", 0)),
            "soh":   float(detail.get("ClosingStock", 0)),
            "value": float(detail.get("StockValue", 0)),
        })
# ~1,165 rows across 46 categories
```

---

## Credentials

| Secret name          | Value                        |
|----------------------|------------------------------|
| `PILOTLIVE_USERNAME` | `0834436203` (mobile number) |
| `PILOTLIVE_PASSWORD` | Stored in GitHub Secrets only |

Never hardcode the password. Read from environment:
```python
import os
username = os.getenv("PILOTLIVE_USERNAME")
password = os.getenv("PILOTLIVE_PASSWORD")
```

---

## What Does NOT Work (do not re-investigate)

| Approach | Result | Reason |
|---|---|---|
| `rs:Format=CSV` | 500 / timeout | Server-side render times out |
| `rs:Format=EXCELOPENXML` | 500 / timeout | Same |
| `rs:Format=MHTML` | timeout | Same |
| `dclink=1` | 500 Invalid value | Wrong store ID |
| Playwright browser export | Export button not found | BoldReports viewer blocks headless |
| Pilot Cloud REST API (`/api/StockManagementReports/...`) | 500 | Server-side error, no fix found |
| SOAP `LoadReport` with `HistoryID=xsi:nil` | 500 Type mismatch | Must omit `HistoryID` entirely |

---

## GitHub Actions Usage

The daily workflow at `.github/workflows/daily_brief.yml` runs this automatically at 06:00 SAST.
Required secrets in repo Settings → Secrets → Actions:
- `PILOTLIVE_USERNAME`
- `PILOTLIVE_PASSWORD`
- `TELEGRAM_BOT_TOKEN`

---

## Known Issue: SSRS Timeout Kills Workflow

**Observed:** 2026-04-12. No Telegram brief received.

**Root cause:** `reports.pilotlive.co.za` timed out (read timeout=60s) at run time. The "Test SSRS connection" diagnostic step called `sys.exit(1)` on any non-200 response, aborting the entire workflow before the agent ran. The agent itself has a graceful Excel fallback — but it never got to run.

**Fix applied:** `continue-on-error: true` added to the "Test SSRS connection" step in `daily_brief.yml`. A transient SSRS timeout now logs a warning and the workflow continues; the agent falls back to the most recent Excel file in `inventory/data/`.

**How to diagnose future failures:**
1. Go to `github.com/caleighswart/BOSSA---Sunningdale/actions/workflows/daily_brief.yml`
2. Click the failed run
3. Click the job `Analyse stock & send Telegram brief` in the left sidebar (use job URL format: `.../runs/{run_id}/job/{job_id}`)
4. Look for the ❌ step and read the log output

**How to trigger a manual run:**
- GitHub Actions UI → **Run workflow** dropdown → Branch: main → green **Run workflow** button
- Or via API: `POST /repos/caleighswart/BOSSA---Sunningdale/actions/workflows/daily_brief.yml/dispatches` with `{"ref":"main"}`
