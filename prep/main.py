#!/usr/bin/env python3
"""
Bossa Sunningdale — Prep Bot
Sends daily prep variance report to the head chef via Telegram.
Run daily at 08:00 SAST via GitHub Actions.
"""

import os
import sys
import json
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(__file__))

from pilotfetch import fetch_variance_rows
from prep_engine import analyse_variances, build_variance_brief
from prep_config import CHEF_CHAT_ID

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8562498363:AAHVJRtFXbAdySE9TVEmpsBCF-gsTqSfNIs")

SAST = timezone(timedelta(hours=2))


def get_dates():
    now = datetime.now(SAST)
    brief_date  = now.strftime("%Y-%m-%d")
    report_date = (now - timedelta(days=1)).strftime("%Y-%m-%d")
    return report_date, brief_date


def send_telegram(chat_id, text):
    chunks, current = [], ""
    for line in text.splitlines(keepends=True):
        if len(current) + len(line) > 4000:
            if current.strip():
                chunks.append(current.strip())
            current = line
        else:
            current += line
    if current.strip():
        chunks.append(current.strip())

    for i, chunk in enumerate(chunks, 1):
        payload = json.dumps({
            "chat_id":    chat_id,
            "text":       chunk,
            "parse_mode": "HTML",
        }).encode()
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req) as r:
                resp = json.loads(r.read())
                if resp.get("ok"):
                    print(f"  [{i}/{len(chunks)}] ✅ sent to {chat_id}")
                else:
                    print(f"  [{i}/{len(chunks)}] ❌ Telegram error: {resp}")
        except urllib.error.HTTPError as e:
            print(f"  [{i}/{len(chunks)}] ❌ HTTP {e.code}: {e.read().decode()}")


def main():
    print(f"👨‍🍳 Bossa Prep Bot — {datetime.now(SAST).strftime('%a %-d %b %Y %H:%M SAST')}")
    print("─" * 60)

    username = os.getenv("PILOTLIVE_USERNAME")
    password = os.getenv("PILOTLIVE_PASSWORD")
    if not username or not password:
        print("❌ PILOTLIVE_USERNAME / PILOTLIVE_PASSWORD not set")
        sys.exit(1)

    report_date, brief_date = get_dates()
    print(f"Report date: {report_date}  |  Brief date: {brief_date}")

    print("\nFetching variance data from PilotLive...")
    rows, title = fetch_variance_rows(username, password)
    print(f"  {len(rows)} items — {title}")

    print("\nAnalysing prep variances...")
    high, watch, clean = analyse_variances(rows)
    print(f"  {len(high)} high  |  {len(watch)} watch  |  {len(clean)} on target")

    print("\nBuilding brief...")
    brief = build_variance_brief(high, watch, clean, report_date, brief_date)

    print(f"\nSending to chef ({CHEF_CHAT_ID})...")
    send_telegram(CHEF_CHAT_ID, brief)

    print("\n✅ Done!")


if __name__ == "__main__":
    main()
