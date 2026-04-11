#!/usr/bin/env python3
"""
Bossa Sunningdale — Prep Bot
Sends the daily prep list to the head chef via Telegram.
Run daily at 08:00 SAST via GitHub Actions (before morning prep session).
"""

import os
import sys
import json
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta

# Add inventory dir to path so we can reuse pilotcloud + analyse loaders
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "inventory"))
sys.path.insert(0, os.path.dirname(__file__))

from analyse import load_data
from prep_engine import analyse_prep, build_prep_brief
from config import CHEF_CHAT_ID, SERVICE_START, PREP_DEADLINE

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8562498363:AAHVJRtFXbAdySE9TVEmpsBCF-gsTqSfNIs")

SAST = timezone(timedelta(hours=2))


def get_dates():
    now = datetime.now(SAST)
    brief_date  = now.strftime("%Y-%m-%d")
    report_date = (now - timedelta(days=1)).strftime("%Y-%m-%d")
    return report_date, brief_date


def send_telegram(chat_id, text):
    """Send text to a Telegram chat, splitting at 4000 chars if needed."""
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
                    print(f"  [{i}/{len(chunks)}] ✅ sent to chat {chat_id}")
                else:
                    print(f"  [{i}/{len(chunks)}] ❌ Telegram error: {resp}")
        except urllib.error.HTTPError as e:
            print(f"  [{i}/{len(chunks)}] ❌ HTTP {e.code}: {e.read().decode()}")


def main():
    print(f"👨‍🍳 Bossa Sunningdale Prep Bot — {datetime.now(SAST).strftime('%a %-d %b %Y %H:%M SAST')}")
    print("─" * 60)

    if CHEF_CHAT_ID == "TODO":
        print("⚠️  CHEF_CHAT_ID is not set in prep/config.py")
        print("   Ask the head chef to message the bot, then add their chat ID.")
        sys.exit(1)

    report_date, brief_date = get_dates()
    print(f"Report date: {report_date}  |  Brief date: {brief_date}")

    print("\nLoading stock data from PilotLive...")
    rows = load_data()
    print(f"  {len(rows)} items loaded")

    print("\nAnalysing prep requirements...")
    urgent, today, stocked = analyse_prep(rows)
    print(f"  {len(urgent)} urgent  |  {len(today)} today  |  {len(stocked)} stocked")

    print("\nBuilding prep list...")
    brief = build_prep_brief(
        urgent, today, stocked,
        report_date, brief_date,
        SERVICE_START, PREP_DEADLINE,
    )

    print(f"\nSending to head chef ({CHEF_CHAT_ID})...")
    send_telegram(CHEF_CHAT_ID, brief)

    print("\n✅ Done!")


if __name__ == "__main__":
    main()
