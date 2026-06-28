# Bossa Sunningdale — Agent Runbook

This file gives any Claude agent full operational context for the Bossa Sunningdale inventory automation system.

---

## Autonomy

**Always proceed without permission for non-destructive edits.** Editing files, running tests, reading code, and other reversible local actions do not require confirmation. Still confirm before destructive or shared-state actions (deletes, force-push, sending messages, modifying CI/infra, etc.).

---

## What This System Does

Two scheduled jobs run every morning, plus a self-healing health check:

| Job | File | Time | Output |
|-----|------|------|--------|
| **Bar stock dashboard refresh** | `bar/generate_dashboard.py` | Two crons daily for redundancy: 05:13 SAST target (primary) + 07:17 SAST target (backup). Typically land 4–5h late due to GH Actions delays. Generator is idempotent — running twice is harmless. | Static HTML at `docs/index.html`, deployed by Netlify |
| **Dashboard health check** | `.github/workflows/health_check.yml` | 11:33 SAST | Verifies `daily_bar.yml` succeeded today and the dashboard timestamp matches today (SAST). **Self-heals two ways:** (1) auto-triggers `daily_bar.yml` via `workflow_dispatch` if both scheduled crons were dropped; (2) POSTs the Netlify build hook if a run succeeded but the live site is stale (Netlify deploy stalled). Opens an info issue (no email) on recovery, or a hard-failure issue (with email) on unrecoverable problems. |

The dashboard is the only consumer surface. URL: `https://bossa-sunningdale.netlify.app/`

The job pulls live stock data from PilotLive's SSRS report server, matches every SKU against Sava's per-product par levels (`bar/pars.json`, 400 products), and rebuilds the dashboard. It classifies each SKU as critical/low/healthy against its own par level and surfaces missing pars, variances, and new products added to PilotLive that Sava hasn't added to her count sheet yet.

### Disabled but kept in the repo

The inventory and prep bots used to send daily Telegram briefs. As of 2026-05-13 they are **disabled** — schedules removed from the workflows; code untouched. They can be re-enabled by restoring the cron in their workflow files. The bar Telegram bot is also disabled (the `bar/main.py` Telegram send step was removed from the workflow; `bar/main.py` itself is left in place).

Telegram secrets (`TELEGRAM_BOT_TOKEN`, `TELEGRAM_BAR_BOT_TOKEN`) can be deleted from GitHub Secrets — nothing references them anymore.

---

## How We Use the Dashboard — Boundaries (locked)

These are hard limits set by the managers (voice note, 2026-06-19). The dashboard is a
**read-only mirror + order assistant** — it never acts on the managers' process. Do not
build anything that crosses these lines without an explicit new instruction:

1. **Front/Back stock is display-only.** The dashboard reflects the managers' own manual
   count back at them; it never writes to, syncs to, or auto-fills the prep sheet. Managers
   keep full ownership of fills, fill-checking, and stock-checking. (Auto-filling the prep
   sheet was explicitly rejected — "it'll make ridiculous errors and management complacency.")
2. **Data flow is one-directional:** managers' manual prep sheet → periodic snapshot →
   `bar/front_back.json` → dashboard display. Never dashboard → prep sheet.
3. **Orders stay human-in-the-loop.** The dashboard may pre-calculate and pre-fill an order,
   but a manager always reviews it before it's sent — "it can do the orders, but it must
   first give you a prompt you can look at before it gets processed." This is already how the
   "Send batch via email" button works (opens a `mailto:` draft the manager sends manually;
   the `BOSSA_ORDERS_WEBHOOK` only logs a copy *after* sending). Keep it that way.

Front/back data is collected by **piggybacking on the managers' existing stock-take** (no new
daily ask) — whenever they do their regular count, they share a snapshot and it's transcribed
into `bar/front_back.json` with an `_as_of` date. See "Front & Back stock" below.

---

## Credentials & Secrets

| What | Where | Value |
|------|-------|-------|
| PilotLive username | GitHub Secret | `PILOTLIVE_USERNAME` (`0834436203`) |
| PilotLive password | GitHub Secret | `PILOTLIVE_PASSWORD` |
| Orders webhook URL | GitHub Secret | `BOSSA_ORDERS_WEBHOOK` (receives a best-effort copy of sent orders for the dashboard's order-history sync to a Google Sheet) |
| Netlify build hook | GitHub Secret | `NETLIFY_BUILD_HOOK_URL` (Netlify → Site settings → Build & deploy → Build hooks, branch `main`). POSTed by `health_check.yml` only, on a stale-live recovery, to force a deploy independent of Netlify's Git webhook. **Not yet created** — until the hook exists and this secret is set, the health-check self-heal is inert (a stale event still alerts, just can't auto-redeploy). Optional — degrades to Git auto-deploy if unset. (`daily_bar.yml`'s per-push hook is deliberately **not** shipped — it would double build-credit burn.) |
| ~~Telegram tokens~~ | ~~GitHub Secret~~ | Unused since 2026-05-13 — safe to delete from repo Settings |

**GitHub Secrets location:** repo → Settings → Secrets and variables → Actions

---

## Repo Structure

```
.github/workflows/
  daily_bar.yml         — Bar dashboard refresh: 05:13 + 07:17 SAST targets (crons: 13 3 / 17 5 * * *)
  daily_brief.yml       — Inventory bot (DISABLED, manual trigger only)
  daily_prep.yml        — Prep bot       (DISABLED, manual trigger only)

docs/
  index.html            — Auto-generated bar stock dashboard (Netlify)

bar/
  generate_dashboard.py — ACTIVE: SSRS fetch → analyse → write docs/index.html
  analyse.py            — Per-product par matching + brief builder
  pilotfetch.py         — SSRS fetch
  config.py             — Categories, thresholds, suppliers
  pars.json             — 400 product → par mapping (from Sava's count sheet)
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
| 2026-05-13 | GitHub silently dropped the scheduled `daily_bar.yml` cron entirely — no run fired at 03:13 UTC; by 10:05 SAST nothing was queued or in-progress for the day. Client needs the dashboard live every morning, so a single dropped cron = an outage. | (a) Added a backup cron at `17 5 * * *` (07:17 SAST target) so two independent slots have to be dropped to miss a day. (b) Extended `health_check.yml` to auto-trigger `daily_bar.yml` via `workflow_dispatch` when no successful run is found for today — opens an info issue (no email) on recovery so we still see when GH drops crons, but the dashboard self-heals by ~11:40 SAST in the worst case. |
| 2026-06-19 | `health_check.yml` false-failed 7 days straight (issues #9–#15, daily emails) while the dashboard itself was fine. The v3 redesign (2026-06-11) changed the footer the freshness regex was reading, silently breaking the monitor. | (a) Generator emits a hidden `<meta name="dashboard-generated">` ISO-timestamp marker; health check parses that, not the visible footer (decoupled from the visual template). (b) Added a "Verify freshness marker present" step to `daily_bar.yml` that fails the run if the marker is ever dropped — catches a future redesign regression the same morning instead of days later. (c) Gave `health_check.yml` a redundant backup cron (`33 11 * * *` = 13:33 SAST) so GitHub dropping one cron no longer skips the day's check. |
| 2026-06-22 | Live dashboard stuck on the 20 Jun build for ~2 days. **Not a generator/workflow fault** — SSRS was up, `daily_bar.yml` succeeded daily and pushed fresh `docs/index.html` to `main` through today; **Netlify's Git auto-deploy silently stalled** after the 20 Jun 09:09 SAST build, so the live site never picked up the pushes. `health_check.yml` correctly flagged it (issue #16) but couldn't fix it: its only recovery was re-dispatching `daily_bar.yml`, which just re-pushes to a Netlify that isn't deploying — the self-heal was blind to Netlify-side failures. | Added a **Netlify build hook** (`NETLIFY_BUILD_HOOK_URL` secret) — a URL that forces a deploy from latest `main` independent of the Git webhook. (a) `daily_bar.yml` POSTs it after every real push (belt-and-suspenders). (b) `health_check.yml` POSTs it when a run succeeded today but the live marker is stale, and treats that as an auto-recovery (info issue, no email) instead of a hard failure. **Immediate unblock is still manual:** Netlify → Deploys → check auto-publish isn't locked / repo still connected → "Clear cache and deploy site". Degrades gracefully if the secret is unset (Git auto-deploy only). **⚠️ Correction (2026-06-26): this fix was never actually deployed** — the `daily_bar.yml`/`health_check.yml` edits were left *uncommitted* in the working tree and the `NETLIFY_BUILD_HOOK_URL` secret was never created, so CI kept running the old code. The "Git auto-deploy stalled" diagnosis was also incomplete: the true cause was Netlify **build-credit exhaustion** (see 2026-06-26 row), which a build hook can't fix anyway. |
| 2026-06-26 | Live dashboard still frozen on the 20 Jun build — **6 days stale**, same continuous outage as the 2026-06-22 row (never actually resolved). Upstream all healthy: SSRS up (401), `daily_bar.yml` succeeded daily and `origin/main` had today's `docs/index.html`; `health_check.yml` failed every day (issues #16–#20, daily emails) but its build-hook self-heal was uncommitted + secretless, so it could only detect-and-fail. **Real root cause (per manager): Netlify monthly build credits exhausted — builds suspended at the quota, so no push deploys regardless of Git webhook or build hook.** Credits reset 27 Jun. | Operational, not a code fix. (a) Wait for the 27 Jun credit reset — the next `daily_bar.yml` push then deploys and the live site catches up; if not, trigger one manual deploy in Netlify. (b) Closed the false-failure issues #16–#20 with a root-cause note. (c) Did **not** ship the uncommitted build-hook edits: `daily_bar.yml`'s per-push hook fires a *second* Netlify build per push on top of Git auto-deploy, doubling credit burn — exactly the wrong move under a quota cap. (d) Follow-up after reset: keep Netlify build usage under the monthly quota (deploy once-per-day-on-change, avoid double-triggering) before re-attempting any build-hook self-heal. |
| 2026-06-27 | **Recovery confirmed** — the 2026-06-26 outage resolved itself on the credit reset exactly as predicted, no manual intervention needed. | Verified healthy: live `dashboard-generated` marker advanced to `2026-06-27T10:06 SAST` (was frozen on 2026-06-20 for 6 days) and matches `origin/main`; `daily_bar.yml` succeeded twice; `health_check.yml` ran green at 11:10 SAST — first pass in 5 days, no new issue/email. Closed the last leftover false-failure (issue #21, opened 26 Jun pre-reset) with a root-cause note. Confirms the diagnosis (Netlify build-credit exhaustion, not a code/generator/webhook fault). **Still open — structural:** the monthly quota ran out in the first place (likely early-June redesign deploys + redundant triggers, not the daily cron); keep deploys to one-per-day-on-change and avoid double-triggering (don't run Git auto-deploy *and* a per-push build hook) so it doesn't recur. The uncommitted per-push build-hook edits in `daily_bar.yml`/`health_check.yml` remain unshipped by design. |
| 2026-06-28 | Finished the build-hook self-heal *properly* — the deferred half of the 2026-06-27 structural follow-up. | Shipped **only** the `health_check.yml` staleness-only path (commit `4f7cedf`): on a stale-live event it POSTs `NETLIFY_BUILD_HOOK_URL`, auto-recovers (info issue, no email), and falls back to a hard-fail alert if the POST errors. Fires rarely (only on detected staleness) so it adds **no** per-day credit burn. `daily_bar.yml`'s per-push hook stays **unshipped by design** (it would double credit burn). **Still pending (manual, owner-only):** create the build hook in the Netlify UI and set the `NETLIFY_BUILD_HOOK_URL` secret — until then the self-heal is inert and degrades gracefully (a stale event hard-fails with a "set the secret" message, same alert behaviour as before). ⚠️ Scope: this guards a genuine *Git-webhook stall* (the 2026-06-22 theory) — it does **not** help against Netlify **build-credit exhaustion** (the actual cause of the Jun outage), which only a usage/quota fix prevents. |

---

## TODO (pending confirmation from Sava)

- Fill in missing par levels for the items flagged in the dashboard's "PAR MISSING" admin tab (mix cocktails, Slo Jo syrups, glenfiddich/bushmills range, vapes, etc.)

---

## Modifying This System

- **Change bar par levels:** edit `bar/pars.json` (keys = PilotLive product names)
- **Change refresh time:** edit cron in `.github/workflows/daily_bar.yml` (UTC — SAST is UTC+2)
- **Change bar stock thresholds:** edit `CRITICAL_PCT` / `LOW_PCT` in `bar/config.py`
- **Add/update supplier details:** edit `SUPPLIERS` dict in `bar/config.py` (name, contact, email per category; same email = merged into one order card)
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
- **Place order tab** — an ad-hoc single-product order form plus per-supplier batch ordering with quantities pre-calculated; a "Send batch via email" button opens a pre-filled email to the supplier
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
