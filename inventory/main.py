#!/usr/bin/env python3
"""
Bossa Sunningdale — Inventory Agent
Entrypoint: loads data, builds brief, sends to all recipients via Telegram.
Run daily at 06:00 SAST via GitHub Actions.
"""

import os
import sys
import json
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta

# Add inventory dir to path for local imports
sys.path.insert(0, os.path.dirname(__file__))

from analyse import load_data, analyse, build_brief
from config import RECIPIENTS

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8562498363:AAHVJRtFXbAdySE9TVEmpsBCF-gsTqSfNIs")

SAST = timezone(timedelta(hours=2))


def get_dates():
    now = datetime.now(SAST)
    brief_date = now.strftime("%Y-%m-%d")
    # Report date is previous day's stock take
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
            "chat_id": chat_id,
            "text": chunk,
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
                    print(f"    [{i}/{len(chunks)}] ✅ sent to chat {chat_id}")
                else:
                    print(f"    [{i}/{len(chunks)}] ❌ error: {resp}")
        except urllib.error.HTTPError as e:
            print(f"    [{i}/{len(chunks)}] ❌ HTTP {e.code}: {e.read().decode()}")


def main():
    print(f"🏪 Bossa Sunningdale Inventory Agent — {datetime.now(SAST).strftime('%a %-d %b %Y %H:%M SAST')}")
    print("─" * 60)

    report_date, brief_date = get_dates()
    print(f"Report date: {report_date}  |  Brief date: {brief_date}")

    print("\nLoading stock data...")
    rows = load_data()
    print(f"  {len(rows)} items loaded")

    print("\nAnalysing stock levels...")
    group_results, total_value = analyse(rows)

    crit_groups = sum(1 for d in group_results.values() if d["critical"])
    low_groups  = sum(1 for d in group_results.values() if d["low"])
    print(f"  {crit_groups} groups critical | {low_groups} groups low | R{total_value:,.0f} total value")

    print("\nBuilding brief...")
    brief = build_brief(group_results, total_value, report_date, brief_date)

    print(f"\nSending to {len(RECIPIENTS)} recipient(s)...")
    for name, chat_id in RECIPIENTS.items():
        if chat_id == "TODO":
            print(f"  ⏭️  Skipping {name} — chat ID not yet configured")
            continue
        print(f"  → {name} ({chat_id})")
        send_telegram(chat_id, brief)

    print("\n✅ Done!")


if __name__ == "__main__":
    main()
