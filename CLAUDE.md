# Bossa Sunningdale — Agent Runbook

This file gives any Claude agent full operational context for the Bossa Sunningdale inventory automation system.

---

## What This System Does

One scheduled job runs every morning:

| Job | File | Time | Output |
|-----|------|------|--------|
| **Bar stock dashboard refresh** | `bar/generate_dashboard.py` | 05:13 SAST target (typically lands 09:30–10:30 SAST due to GH Actions cron delays) | Static HTML at `docs/index.html`, deployed by Netlify |
| **Dashboard health check** | `.github/workflows/health_check.yml` | 11:33 SAST | Verifies the bar workflow succeeded today and the dashboard timestamp matches today (SAST); opens a deduped GitHub issue on failure |

The dashboard is the only consumer surface. URL: `https://bossa-sunningdale.netlify.app/`

The job pulls live stock data from PilotLive's SSRS report server, matches every SKU against Sava's per-product par levels (`bar/pars.json`, 404 products), and rebuilds the dashboard. It classifies each SKU as critical/low/healthy against its own par level and surfaces missing pars, variances, and new products added to PilotLive that Sava hasn't added to her count sheet yet.

### Disabled but kept in the repo

The inventory and prep bots used to send daily Telegram briefs. As of 2026-05-13 they are **disabled** — schedules removed from the workflows; code untouched. They can be re-enabled by restoring the cron in their workflow files. The bar Telegram bot is also disabled (the `bar/main.py` Telegram send step was removed from the workflow; `bar/main.py` itself is left in place).

Telegram secrets (`TELEGRAM_BOT_TOKEN`, `TELEGRAM_BAR_BOT_TOKEN`) can be deleted from GitHub Secrets — nothing references them anymore.

---

## Credentials & Secrets

| What | Where | Value |
|------|-------|-------|
| PilotLive username | GitHub Secret | `PILOTLIVE_USERNAME` (`0834436203`) |
| PilotLive password | GitHub Secret | `PILOTLIVE_PASSWORD` |
| Orders webhook URL | GitHub Secret | `BOSSA_ORDERS_WEBHOOK` (used by dashboard "Place Order" buttons) |
| ~~Telegram tokens~~ | ~~GitHub Secret~~ | Unused since 2026-05-13 — safe to delete from repo Settings |

**GitHub Secrets location:** repo → Settings → Secrets and variables → Actions

---

## Repo Structure

```
.github/workflows/
  daily_bar.yml         — Bar dashboard refresh: 05:13 SAST target (cron: 13 3 * * *)
  daily_brief.yml       — Inventory bot (DISABLED, manual trigger only)
  daily_prep.yml        — Prep bot       (DISABLED, manual trigger only)

docs/
  index.html            — Auto-generated bar stock dashboard (Netlify)

bar/
  generate_dashboard.py — ACTIVE: SSRS fetch → analyse → write docs/index.html
  analyse.py            — Per-product par matching + brief builder
  pilotfetch.py         — SSRS fetch
  config.py             — Categories, thresholds, suppliers
  pars.json             — 404 product → par mapping (from Sava's count sheet)
  main.py               — DORMANT: old Telegram-send entrypoint (no longer run)
  requirements.txt

inventory/               — DORMANT: workflow disabled, code untouched
  main.py, analyse.py, pilotcloud.py, config.py, requirements.txt, data/

prep/                    — DORMANT: workflow disabled, code untouched
  main.py, pilotfetch.py, prep_engine.py, prep_config.py, requirements.txt

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

## Debugging: Dashboard didn't update

**Step 1 — Check the GitHub Actions run:**
GitHub → Actions → "Bossa Sunningdale — Daily Bar Stock Dashboard" → today's run. If ❌, click into the failing step.

**Step 2 — Common failure: SSRS timeout**
Symptom: "Test SSRS connection" step prints `Read timed out`.
That step is `continue-on-error: true`, so the workflow continues to "Generate dashboard". If `generate_dashboard.py` *also* can't reach SSRS, it will fail and the dashboard won't update. Verify SSRS is up:
```bash
curl -s -o /dev/null -w "%{http_code}" --max-time 10 https://reports.pilotlive.co.za/ReportServer
# Should return 401 (up, needs auth). TIMEOUT or 000 = server down.
```

**Step 3 — Workflow succeeded but Netlify shows old date**
Check whether the "Commit dashboard for Netlify deploy" step actually committed something. If it printed "Dashboard unchanged — nothing to commit", nothing pushed — SSRS likely returned the same data as yesterday. If it *did* push, check Netlify dashboard → Deploys.
Historical bug (2026-05-07): `[skip ci]` in the commit message caused Netlify to ignore commits. Don't reintroduce it.

**Step 4 — Trigger a manual run:**
GitHub Actions UI → workflow → "Run workflow" → main → run. Takes ~1m 15s.

---

## Known Issues Log

| Date | Issue | Fix |
|------|-------|-----|
| 2026-04-12 | SSRS timed out at 07:54 SAST → "Test SSRS connection" step `sys.exit(1)` → workflow aborted before agent ran | Added `continue-on-error: true` to SSRS test step |
| 2026-05-07 | Dashboard at `bossa-sunningdale.netlify.app` stuck on 3 May version. Workflow ran daily and pushed `docs/index.html` updates, but Netlify ignored every commit. Cause: commit message contained `[skip ci]`, which Netlify honors to skip deploys. | Removed `[skip ci]` from the commit message in `daily_bar.yml`. Unblock a stuck deploy via Netlify dashboard → Deploys → "Trigger deploy" → "Clear cache and deploy site". |
| 2026-05-13 | Telegram briefs decommissioned across all three bots — dashboard is the only consumer surface. Bar workflow stripped of Telegram send step; inventory + prep workflows disabled (schedule removed, manual trigger only). | This change. Code for the disabled bots remains in the repo. |
| 2026-05-13 | Dashboard wasn't updated by 08:30 SAST. Cron was `0 5 * * *` (07:00 SAST target) — a peak top-of-hour slot, and GitHub Actions consistently delayed the run by 1h 52m – 3h 24m, so it landed between 08:52 and 10:24 SAST. | Shifted cron to `13 3 * * *` (05:13 SAST target). Off-peak minute; even with typical 1–3h GH delay the run should land before 07:00 SAST. |
| 2026-05-13 | Added daily dashboard health check (`health_check.yml`). First test fired at 09:13 SAST and (correctly) flagged that today's `daily_bar.yml` hadn't completed — empirically GH Actions delays the scheduled cron by 4-5h, not 1-3h, so the bar workflow typically lands 09:30–10:30 SAST. Health check at 09:13 SAST was inside the delay window and produced a false alarm. | Moved health check cron to `33 9 * * *` (11:33 SAST) to give a safe buffer past the worst observed delay. |

---

## TODO (pending confirmation from Sava)

- Fill in missing par levels for the items flagged in the dashboard's "PAR MISSING" admin tab (mix cocktails, Slo Jo syrups, glenfiddich/bushmills range, vapes, etc.)

---

## Modifying This System

- **Change bar par levels:** edit `bar/pars.json` (keys = PilotLive product names)
- **Change refresh time:** edit cron in `.github/workflows/daily_bar.yml` (UTC — SAST is UTC+2)
- **Change bar stock thresholds:** edit `CRITICAL_PCT` / `LOW_PCT` in `bar/config.py`
- **Add/update supplier details:** edit `SUPPLIERS` dict in `bar/config.py` (name, contact, whatsapp per category; same whatsapp number = merged into one order card)
- **Re-enable inventory or prep:** restore `schedule:` block in the relevant workflow file

---

## Bar Stock Dashboard

A static HTML dashboard is generated by `bar/generate_dashboard.py` and deployed to Netlify automatically at the end of each `daily_bar.yml` run.

**URL:** `https://bossa-sunningdale.netlify.app/`

**How deployment works:**
Netlify watches the `main` branch and auto-deploys whenever `docs/index.html` is updated. The `netlify.toml` at the repo root sets `publish = "docs"` so Netlify serves from the right directory. No manual setup needed after the initial Netlify site is connected to the repo.

**What the dashboard shows:**
- Summary bar: critical count, low count, healthy count, total bar value
- **Critical tab** — items below 30% par, sorted worst first
- **Low tab** — items 30–70% par (watch list)
- **Orders tab** — grouped by supplier with contact details, order quantities pre-calculated, and a "Place Order via WhatsApp" button that opens a pre-written order message
- **All Products tab** — full list with colour-coded status pills and fill bars
- **Variances tab** — negative SOH items to investigate
- **Admin tab** — missing par levels + new PilotLive products not on Sava's sheet

**How it's generated:**
- `generate_dashboard.py` fetches fresh SSRS data and builds a self-contained HTML file with no external dependencies
- `daily_bar.yml` commits `docs/index.html` to the repo (no `[skip ci]` — Netlify needs to see the push)
- Netlify serves it automatically — no server, no credentials exposed at the URL

**Updating the dashboard outside the scheduled run:**
Trigger `daily_bar.yml` manually via GitHub Actions → Run workflow. The dashboard is regenerated as part of that run.

---

## How the Dashboard Analysis Works

1. `bar/pilotfetch.py` pulls the SSRS XML report.
2. `bar/analyse.py` infers which categories Sava tracks by scanning `pars.json` prefixes (`be-` → BEER, `wh-` → WHISKEY, etc.).
3. For every PilotLive product in a tracked category, it looks up the matching par by normalised product name (lowercase, collapsed whitespace).
4. It classifies each matched SKU as:
   - 🔴 Critical (soh < 30% par)
   - 🟡 Low (30–70% par)
   - ✅ Healthy (≥70% par)
   - ⚠️ Variance (soh < −5, likely count error)
5. Unmatched products in well-tracked categories (≥3 par entries on Sava's sheet) appear under the dashboard's Admin tab as "new products — add to bar count sheet".
6. Par-sheet products with no par value appear under the Admin tab as "par missing — set par levels".

**Updating bar pars:** open `bar/pars.json`, change the value for the product name, commit. Next run picks it up.
