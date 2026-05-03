# Skill: Bar Stock Agent + Dashboard

Reusable template for standing up a daily bar stock brief (Telegram) + live dashboard (Netlify) for a new restaurant branch using PilotLive SSRS data.

---

## What This Skill Builds

| Component | What it does |
|-----------|-------------|
| `bar/pilotfetch.py` | Pulls live stock XML from PilotLive SSRS (NTLM auth) |
| `bar/analyse.py` | Matches PilotLive products against per-SKU par levels, classifies as critical/low/healthy |
| `bar/generate_dashboard.py` | Builds a self-contained HTML dashboard from the same data |
| `bar/main.py` | Orchestrates fetch → analyse → Telegram send |
| `bar/config.py` | Recipients, categories, thresholds, suppliers |
| `bar/pars.json` | Product → par level map (one entry per SKU) |
| `.github/workflows/daily_bar.yml` | Runs the agent daily, commits updated dashboard, Netlify auto-deploys |
| `netlify.toml` | Tells Netlify to serve from `docs/` |
| `docs/index.html` | Auto-generated dashboard output |

---

## Variables to Change Per Branch

These are the only things that differ between branches:

| What | Where | Notes |
|------|-------|-------|
| **PilotLive store ID** | `bar/pilotfetch.py` — `dclink=` param in the SSRS URL | Get from PilotLive admin — each branch has a unique ID |
| **PilotLive username** | GitHub Secret `PILOTLIVE_USERNAME` | Usually the manager's phone number |
| **PilotLive password** | GitHub Secret `PILOTLIVE_PASSWORD` | Never hardcode |
| **Telegram bot token** | GitHub Secret `TELEGRAM_BAR_BOT_TOKEN` | Create a new bot via @BotFather for each branch |
| **Telegram recipient chat IDs** | `bar/config.py` → `RECIPIENTS` dict | `{"name": "chat_id"}` — get chat ID by messaging the bot first |
| **Par levels** | `bar/pars.json` | Keys = PilotLive product names (lowercase, exact match); values = par units. Start by running the agent once and noting what products appear, then populate. |
| **Supplier details** | `bar/config.py` → `SUPPLIERS` dict | Name, contact number, WhatsApp per category |
| **Cron schedule** | `.github/workflows/daily_bar.yml` | UTC time — SAST is UTC+2 |
| **Netlify site** | Create new site in Netlify, connect to the repo/branch | `netlify.toml` stays the same |

---

## How to Stand Up for a New Branch

### 1. Copy the bar agent files
Copy the entire `bar/` directory and `netlify.toml` and `.github/workflows/daily_bar.yml` into the new branch repo.

### 2. Get the PilotLive store ID
Log into PilotLive → switch to the branch → the URL or admin panel will show the store/dclink ID. Update in `bar/pilotfetch.py`:
```python
url = "https://reports.pilotlive.co.za/ReportServer?...&dclink=XXXX"
```

### 3. Create a Telegram bot
1. Open Telegram → message `@BotFather` → `/newbot`
2. Name it (e.g. "Branch Name Bar Bot")
3. Copy the token
4. Search for the bot in Telegram and click **Start** (so it can message you)
5. Send any message to the bot, then call:
   `https://api.telegram.org/bot{TOKEN}/getUpdates` — the `chat.id` in the response is your chat ID

### 4. Add GitHub Secrets
Repo → Settings → Secrets and variables → Actions:
- `PILOTLIVE_USERNAME`
- `PILOTLIVE_PASSWORD`
- `TELEGRAM_BAR_BOT_TOKEN`

### 5. Bootstrap pars.json
Run the agent once with an empty `pars.json` (`{}`). The brief will show every PilotLive product as "unmatched". Use that list to populate `pars.json` with real par levels:
```json
{
  "castle lite 330ml": 48,
  "jack daniels 750ml": 6
}
```
Keys must match PilotLive product names exactly (the agent normalises to lowercase + collapsed whitespace).

### 6. Connect Netlify
1. Netlify → Add new site → Import from Git → select the repo/branch
2. Build command: leave blank
3. Publish directory: `docs`
4. Deploy — the `netlify.toml` handles the rest

### 7. Trigger a test run
GitHub Actions → `daily_bar.yml` → Run workflow. Check Telegram for the brief and the Netlify URL for the dashboard.

---

## Thresholds (change in `bar/config.py`)

| Threshold | Default | Meaning |
|-----------|---------|---------|
| `CRITICAL_PCT` | 0.30 | Below 30% of par → 🔴 Critical |
| `LOW_PCT` | 0.70 | 30–70% of par → 🟡 Low |
| `VARIANCE_CUTOFF` | -5 | SOH below -5 → ⚠️ Variance (likely count error) |

---

## Dashboard Tabs

| Tab | Shows |
|-----|-------|
| Critical | Items below 30% par, worst first |
| Low | Items 30–70% par |
| Orders | Grouped by supplier, pre-calculated order quantities, WhatsApp order button |
| All Products | Full list with colour-coded status + fill bars |
| Variances | Negative SOH items to investigate |
| Admin | Missing par levels + new PilotLive products not yet on the par sheet |

---

## Known Gotchas

- **SSRS timeout**: the SSRS test step has `continue-on-error: true` — the agent still runs even if the connection test fails. If the brief stops arriving, check GitHub Actions logs first.
- **New products**: when PilotLive adds a new SKU, it appears in the Admin tab under "New Products". Add it to `pars.json` to start tracking it.
- **Par name matching**: the agent normalises names (lowercase, collapsed whitespace). If a product doesn't match, check for trailing spaces or special characters in the PilotLive name.
- **Telegram chunking**: briefs over 4000 chars are split across multiple messages automatically.
- **Dashboard deploy loop**: the workflow uses `[skip ci]` on the dashboard commit to prevent triggering itself again.
