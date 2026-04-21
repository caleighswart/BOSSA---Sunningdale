#!/usr/bin/env python3
"""
Bossa Sunningdale — Bar Stock Agent
====================================
Entrypoint: loads live PilotLive data, matches it against Sava's bar count
par levels, and sends the daily bar brief to Caleigh + bar manager via Telegram.

Runs daily at 07:00 SAST via GitHub Actions (.github/workflows/daily_bar.yml).
Can be run manually for testing:
    cd bar && python main.py
"""

import os
import sys
import json
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(__file__))

from analyse import load_data, analyse, build_brief
from config import RECIPIENTS

# Bar bot uses its OWN Telegram bot so messages arrive in a separate chat
# from the inventory/prep bots. Token is stored as GitHub Secret
# TELEGRAM_BAR_BOT_TOKEN — create via @BotFather (see CLAUDE.md).
BOT_TOKEN = os.getenv("TELEGRAM_BAR_BOT_TOKEN", "")

SAST = timezone(timedelta(hours=2))


def get_dates():
    now = datetime.now(SAST)
    brief_date  = now.strftime("%Y-%m-%d")
    report_date = (now - timedelta(days=1)).strftime("%Y-%m-%d")
    return report_date, brief_date


def send_telegram(chat_id, text):
    """Chunk on newlines at 4000 char boundaries and send each chunk."""
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
                    print(f"    [{i}/{len(chunks)}] ✅ sent to chat {chat_id}")
                else:
                    print(f"    [{i}/{len(chunks)}] ❌ error: {resp}")
        except urllib.error.HTTPError as e:
            print(f"    [{i}/{len(chunks)}] ❌ HTTP {e.code}: {e.read().decode()}")
        except Exception as e:
            print(f"    [{i}/{len(chunks)}] ❌ Telegram error: {e}")


def main():
    print(f"🍾 Bossa Sunningdale Bar Agent — {datetime.now(SAST).strftime('%a %-d %b %Y %H:%M SAST')}")
    print("─" * 60)

    if not BOT_TOKEN:
        print("❌ TELEGRAM_BAR_BOT_TOKEN not set.")
        print("   Create a new bot via @BotFather, then add the token as a")
        print("   GitHub Secret named TELEGRAM_BAR_BOT_TOKEN.")
        sys.exit(1)

    report_date, brief_date = get_dates()
    print(f"Report date: {report_date}  |  Brief date: {brief_date}")

    print("\nLoading stock data...")
    rows, title = load_data()
    print(f"  {len(rows)} total items loaded — {title}")

    print("\nAnalysing bar stock levels against par sheet...")
    result = analyse(rows)

    total_crit = sum(len(b["critical"]) for b in result["by_cat"].values())
    total_low  = sum(len(b["low"])      for b in result["by_cat"].values())
    total_var  = sum(len(b["variance"]) for b in result["by_cat"].values())
    print(f"  {total_crit} critical | {total_low} low | {total_var} variances")
    print(f"  {len(result['unmatched'])} unmatched products | "
          f"{len(result['missing_par'])} par-missing products")
    print(f"  R{result['total_value']:,.0f} total bar value")

    print("\nBuilding brief...")
    brief = build_brief(result, report_date, brief_date)

    print(f"\nSending to {len(RECIPIENTS)} recipient(s)...")
    for name, chat_id in RECIPIENTS.items():
        if chat_id in ("TODO", "") or chat_id.startswith("TODO"):
            print(f"  ⏭️  Skipping {name} — chat ID not yet configured")
            continue
        print(f"  → {name} ({chat_id})")
        send_telegram(chat_id, brief)

    print("\n✅ Done!")


if __name__ == "__main__":
    main()
