# Bossa Sunningdale — Agent Runbook

This file gives any Claude agent full operational context for the Bossa Sunningdale inventory automation system.

---

## What This System Does

Three GitHub Actions bots run automatically every morning:

| Bot | File | Time | Recipient |
|-----|------|------|-----------|
| **Inventory brief** | `inventory/main.py` | 06:00 SAST daily | Caleigh via Telegram |
| **Bar stock brief** | `bar/main.py` | 07:00 SAST daily | Caleigh + bar manager via Telegram |
| **Prep variance** | `prep/main.py` | 08:00 SAST daily | Chef via Telegram |

The bar bot also generates a **static HTML dashboard** at `docs/index.html`, published via GitHub Pages. It shows the same data as the Telegram brief in a clean, tabbed interface for managers to review and place orders. URL: `https://caleighswart.github.io/BOSSA---Sunningdale/`

All three bots pull live stock data from PilotLive's SSRS report server, analyse it, and send a formatted Telegram message.

The **bar bot** is product-specific — it uses per-SKU par levels from Sava's "Bar Bev Count 2025" spreadsheet (stored in `bar/pars.json`, 404 products), unlike the inventory bot which uses category-wide defaults. It classifies every alcohol/mixer SKU as critical/low/healthy against its own par level and also surfaces missing pars, variances, and new products added to PilotLive that Sava hasn't added to her count sheet yet.

---

## Credentials & Secrets

| What | Where | Value |
|------|-------|-------|
| PilotLive username | GitHub Secret + hardcoded reference | `0834436203` |
| PilotLive password | **GitHub Secret only** — never local | `PILOTLIVE_PASSWORD` |
| Telegram bot token (inventory + prep) | GitHub Secret + hardcoded fallback in `main.py` | `TELEGRAM_BOT_TOKEN` |
| Telegram bot token (bar bot — separate chat) | GitHub Secret only | `TELEGRAM_BAR_BOT_TOKEN` |
| Caleigh's Telegram chat ID | `inventory/config.py` / `bar/config.py` `RECIPIENTS` | `7399544281` |
| Sava's Telegram chat ID | `inventory/config.py` — not yet set | `TODO` |

**GitHub Secrets location:** repo → Settings → Secrets and variables → Actions

---

## Repo Structure

```
.github/workflows/
  daily_brief.yml       — Inventory bot: 06:00 SAST (cron: 0 4 * * *)
  daily_bar.yml         — Bar bot:       07:00 SAST (cron: 0 5 * * *); also generates dashboard
  daily_prep.yml        — Prep bot:      08:00 SAST (cron: 0 6 * * *)

docs/
  index.html            — Auto-generated bar stock dashboard (GitHub Pages)

inventory/
  main.py               — Entrypoint: load → analyse → Telegram
  analyse.py            — Stock analysis engine + brief builder
  pilotcloud.py         — SSRS XML download (NTLM auth)
  config.py             — Par levels, groups, recipients, suppliers
  requirements.txt      — pandas, openpyxl, requests, requests-ntlm
  data/                 — Excel fallback files (most recent used if SSRS fails)

bar/
  main.py               — Entrypoint: load → match → analyse → Telegram
  analyse.py            — Per-product par matching + brief builder
  pilotfetch.py         — SSRS fetch (independent of inventory/prep)
  config.py             — Recipients, categories, thresholds
  pars.json             — 404 product → par mapping (from Sava's count sheet)
  requirements.txt

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

## Telegram Bots

Two separate Telegram bots so the bar brief arrives in its own chat,
distinct from the inventory/prep brief chat.

**Inventory + Prep bot:**
- Bot name:   BossaSunningdaleBot
- Bot ID:     `8562498363`
- Token:      `TELEGRAM_BOT_TOKEN` GitHub Secret (hardcoded fallback in `inventory/main.py` and `prep/main.py`)
- Used by:    `inventory/main.py` and `prep/main.py`

**Bar bot:**
- Bot name:   BossaBarBot (create via @BotFather — see setup below)
- Token:      `TELEGRAM_BAR_BOT_TOKEN` GitHub Secret (no hardcoded fallback)
- Used by:    `bar/main.py`

**Setup for the bar bot (one-time):**
1. In Telegram, open a chat with `@BotFather`.
2. Send `/newbot`. Name it (e.g. "Bossa Bar Stock Bot"). BotFather gives you a token.
3. Search for your new bot in Telegram and click "Start". This gives the bot permission to message you.
4. In GitHub repo → Settings → Secrets and variables → Actions → New repository secret:
   - Name: `TELEGRAM_BAR_BOT_TOKEN`
   - Value: the token BotFather gave you
5. Trigger `daily_bar.yml` manually — brief arrives in the new chat.

**Common commands:**
- Test bot is alive:    `GET https://api.telegram.org/bot{TOKEN}/getMe`
- Send test message:    `POST https://api.telegram.org/bot{TOKEN}/sendMessage` with `{"chat_id":"7399544281","text":"test"}`
- All messages use HTML parse mode, chunked at 4000 chars.

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
- Add bar manager's Telegram chat ID to `RECIPIENTS` in `bar/config.py`
- Fill in missing par levels for the 40 items flagged in the bar brief's "PAR MISSING" section (mix cocktails, Slo Jo syrups, glenfiddich/bushmills range, vapes, etc.)

---

## Modifying This System

- **Change inventory par levels:** edit `GROUPS` dict in `inventory/config.py`
- **Change bar par levels:** edit `bar/pars.json` (keys = PilotLive product names)
- **Add a recipient:** add `"name": "chat_id"` to `RECIPIENTS` in relevant `config.py`
- **Change send time:** edit cron in `.github/workflows/*.yml` (UTC — SAST is UTC+2)
- **Add a prep category:** add to `PREP_CATEGORIES` in `prep/prep_config.py`
- **Change variance thresholds:** edit `HIGH_VARIANCE_PCT` / `WATCH_VARIANCE_PCT` in `prep/prep_config.py`
- **Change bar stock thresholds:** edit `CRITICAL_PCT` / `LOW_PCT` in `bar/config.py`
- **Add/update supplier details:** edit `SUPPLIERS` dict in `bar/config.py` (name, contact, whatsapp per category; same whatsapp number = merged into one order card)

---

## Bar Stock Dashboard

A static HTML dashboard is generated by `bar/generate_dashboard.py` and published to GitHub Pages automatically at the end of each `daily_bar.yml` run.

**URL:** `https://caleighswart.github.io/BOSSA---Sunningdale/`

**One-time setup (do once after first deploy):**
1. Go to repo → Settings → Pages
2. Source: **Deploy from a branch**
3. Branch: `main` / folder: `/docs`
4. Save — GitHub will show the live URL within ~30 seconds

**What the dashboard shows:**
- Summary bar: critical count, low count, healthy count, total bar value
- **Critical tab** — items below 30% par, sorted worst first
- **Low tab** — items 30–70% par (watch list)
- **Orders tab** — grouped by supplier with contact details, order quantities pre-calculated, and a "Place Order via WhatsApp" button that opens a pre-written order message
- **All Products tab** — full list with colour-coded status pills and fill bars
- **Variances tab** — negative SOH items to investigate
- **Admin tab** — missing par levels + new PilotLive products not on Sava's sheet

**How it's generated:**
- `generate_dashboard.py` fetches fresh SSRS data (separate call from `main.py`) and builds a self-contained HTML file with no external dependencies
- `daily_bar.yml` commits `docs/index.html` to the repo with `[skip ci]` to prevent workflow loops
- GitHub Pages serves it automatically — no server, no credentials exposed at the URL

**Updating the dashboard outside the scheduled run:**
Trigger `daily_bar.yml` manually via GitHub Actions → Run workflow. The dashboard is regenerated as part of that run.

---

## Bar Bot — How It Works

1. `bar/pilotfetch.py` pulls the SSRS XML report (same endpoint as inventory).
2. `bar/analyse.py` infers which categories Sava tracks by scanning `pars.json` prefixes (`be-` → BEER, `wh-` → WHISKEY, etc.).
3. For every PilotLive product in a tracked category, it looks up the matching par by normalised product name (lowercase, collapsed whitespace).
4. It classifies each matched SKU as:
   - 🔴 Critical (soh < 30% par)
   - 🟡 Low (30–70% par)
   - ✅ Healthy (≥70% par)
   - ⚠️ Variance (soh < −5, likely count error)
5. Unmatched products in well-tracked categories (≥3 par entries on Sava's sheet) appear under "🆕 NEW PRODUCTS — Add to bar count sheet".
6. Par-sheet products with no par value appear under "❓ PAR MISSING — Set par levels".
7. Brief is chunked on newline boundaries at 4000 chars and sent to every recipient in `bar/config.py` `RECIPIENTS`.

**Updating bar pars:** open `bar/pars.json`, change the value for the product name, commit. Next run picks it up.
