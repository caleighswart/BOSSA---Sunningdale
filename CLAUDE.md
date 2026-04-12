# Bossa Sunningdale — Agent Runbook

This file gives any Claude agent full operational context for the Bossa Sunningdale inventory automation system.

---

## What This System Does

Two GitHub Actions bots run automatically every morning:

| Bot | File | Time | Recipient |
|-----|------|------|-----------|
| **Inventory brief** | `inventory/main.py` | 06:00 SAST daily | Caleigh via Telegram |
| **Prep variance** | `prep/main.py` | 08:00 SAST daily | Chef via Telegram |

Both bots pull live stock data from PilotLive's SSRS report server, analyse it, and send a formatted Telegram message.

---

## Credentials & Secrets

| What | Where | Value |
|------|-------|-------|
| PilotLive username | GitHub Secret + hardcoded reference | `0834436203` |
| PilotLive password | **GitHub Secret only** — never local | `PILOTLIVE_PASSWORD` |
| Telegram bot token | GitHub Secret + hardcoded fallback in `main.py` | `TELEGRAM_BOT_TOKEN` |
| Caleigh's Telegram chat ID | `inventory/config.py` `RECIPIENTS` | `7399544281` |
| Sava's Telegram chat ID | `inventory/config.py` — not yet set | `TODO` |

**GitHub Secrets location:** repo → Settings → Secrets and variables → Actions

---

## Repo Structure

```
.github/workflows/
  daily_brief.yml       — Inventory bot: 06:00 SAST (cron: 0 4 * * *)
  daily_prep.yml        — Prep bot: 08:00 SAST (cron: 0 6 * * *)

inventory/
  main.py               — Entrypoint: load → analyse → Telegram
  analyse.py            — Stock analysis engine + brief builder
  pilotcloud.py         — SSRS XML download (NTLM auth)
  config.py             — Par levels, groups, recipients, suppliers
  requirements.txt      — pandas, openpyxl, requests, requests-ntlm
  data/                 — Excel fallback files (most recent used if SSRS fails)

prep/
  main.py               — Entrypoint: fetch variances → Telegram
  pilotfetch.py         — SSRS fetch (same auth as inventory)
  prep_engine.py        — Variance analysis + brief builder
  prep_config.py        — Chef chat ID, prep categories, thresholds
  requirements.txt

PILOTLIVE_DATA_PULL.md  — Full SSRS technical reference
CLAUDE.md               — This file
```

---

## How Data Is Fetched (SSRS)

```
GET https://reports.pilotlive.co.za/ReportServer
    ?%2fStock+Management%2fTheoretical+Stock+On+Hand
    &rs:Command=Render&rs:Format=XML&dclink=8689
Authorization: NTLM (username=0834436203, password=from env)
```

- Returns ~200KB XML in ~2 seconds when healthy
- `dclink=8689` = Bossa Sunningdale store ID (required — no default)
- XML namespace: `Theoretical_x0020_Stock_x0020_On_x0020_Hand`
- Root attribute `Textbox74` = report date string e.g. `"Bossa Sunningdale: 2026-04-11"`
- Full reference: `PILOTLIVE_DATA_PULL.md`

---

## Telegram Bot

- **Bot name:** BossaSunningdaleBot
- **Bot ID:** `8562498363`
- **Token:** stored in `TELEGRAM_BOT_TOKEN` GitHub Secret; also hardcoded as fallback in `main.py`
- **Test the bot is alive:** `GET https://api.telegram.org/bot{TOKEN}/getMe`
- **Send a test message:** `POST https://api.telegram.org/bot{TOKEN}/sendMessage` with `{"chat_id":"7399544281","text":"test"}`
- Messages use HTML parse mode; chunked at 4000 chars if brief is long

---

## Debugging: Bot Didn't Send a Message

**Step 1 — Check GitHub Actions run:**
Go to `github.com/caleighswart/BOSSA---Sunningdale/actions/workflows/daily_brief.yml`
Find today's run. If ❌ failed, click into it → click job in sidebar → read step logs.

**Step 2 — Common failure: SSRS timeout**
Symptom: "Test SSRS connection" step ❌, log shows `Read timed out`.
Fix: already applied (`continue-on-error: true` on that step). If it happens again despite the fix, check the SSRS server is reachable:
```bash
curl -s -o /dev/null -w "%{http_code}" --max-time 10 https://reports.pilotlive.co.za/ReportServer
# Should return 401 (up, needs auth). TIMEOUT or 000 = server down.
```

**Step 3 — Verify Telegram bot is alive:**
```bash
curl -s "https://api.telegram.org/bot{TOKEN}/getMe"
# Should return {"ok":true,...}
```

**Step 4 — Trigger a manual run:**
GitHub Actions UI → "Run workflow" dropdown → Branch: main → green "Run workflow" button.
The run takes ~1m 15s. Check for a new message on Telegram after it completes.

**Step 5 — If workflow ran but no message received:**
The `send_telegram()` function catches errors silently (prints to log, doesn't raise). Check the job log for lines like `❌ HTTP 400` or `❌ Telegram error`. A 400 means parse error in the message HTML.

---

## Known Issues Log

| Date | Issue | Fix |
|------|-------|-----|
| 2026-04-12 | SSRS timed out at 07:54 SAST → "Test SSRS connection" step `sys.exit(1)` → workflow aborted before agent ran → no Telegram sent | Added `continue-on-error: true` to SSRS test step in `daily_brief.yml` |

---

## TODO (pending confirmation from Sava)

- Add Sava's Telegram chat ID to `RECIPIENTS` in `inventory/config.py`
- Confirm par levels in `inventory/config.py` (all currently defaults)
- Fill in supplier names, contacts, and WhatsApp numbers in `inventory/config.py`
- Add chef's Telegram chat ID to `prep/prep_config.py` (currently uses Caleigh's for testing)

---

## Modifying This System

- **Change par levels:** edit `GROUPS` dict in `inventory/config.py`
- **Add a recipient:** add `"name": "chat_id"` to `RECIPIENTS` in `inventory/config.py`
- **Change send time:** edit cron in `.github/workflows/daily_brief.yml` (UTC — SAST is UTC+2)
- **Add a prep category:** add to `PREP_CATEGORIES` in `prep/prep_config.py`
- **Change variance thresholds:** edit `HIGH_VARIANCE_PCT` / `WATCH_VARIANCE_PCT` in `prep/prep_config.py`
