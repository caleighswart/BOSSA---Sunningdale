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
| **Dashboard health check** | `.github/workflows/health_check.yml` | 11:33 SAST | Verifies `daily_bar.yml` succeeded today and the dashboard timestamp matches today (SAST). **Self-heals two ways:** (1) auto-triggers `daily_bar.yml` via `workflow_dispatch` if both scheduled crons were dropped; (2) POSTs the Netlify build hook if a run succeeded but the live site is stale (Netlify deploy stalled). Also **monitors Netlify build-credit usage** (if `NETLIFY_API_TOKEN` is set): ≥80% → info issue, ≥95% → hard alert — an early warning for the quota-exhaustion failure that caused the Jun 2026 outage. Opens an info issue (no email) on recovery/warning, or a hard-failure issue (with email) on unrecoverable problems. |

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
| Netlify API token | GitHub Secret | `NETLIFY_API_TOKEN` (Netlify → User settings → Applications → Personal access tokens → New access token). Two uses: (1) `health_check.yml` polls account build-minute usage to warn before the monthly quota is exhausted (read-only); (2) `daily_bar.yml`'s par-merge step reads **and deletes** the `par-overrides` Netlify Blobs store (needs `NETLIFY_SITE_ID` too). **Not yet created** — both the usage monitor and the par-merge are skipped silently until it's set. Optional `NETLIFY_ACCOUNT_ID` overrides the auto-discovered account (first account the token can see). |
| Netlify site ID | GitHub Secret | `NETLIFY_SITE_ID` (Netlify → Site settings → General → Site information → Site ID / API ID). Used **only** by `daily_bar.yml`'s par-merge step (`bar/merge_par_overrides.mjs`) to address the `par-overrides` Blobs store from CI — the SDK needs an explicit `siteID` + `token` outside the Functions runtime. **Not yet created** — par-merge no-ops until both this and `NETLIFY_API_TOKEN` are set (saving still works; saved pars just stay inert). See "Admin par editing". |
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
  ud_order_template.xlsx — UD's blank order catalogue (Col A = pars key, Col B = unit);
                           filled by order-xlsx.mjs into the order schedule UD requires
  main.py               — DORMANT: old Telegram-send entrypoint (no longer run)
  requirements.txt

inventory/               — DORMANT: workflow disabled, code untouched
  main.py, analyse.py, pilotcloud.py, config.py, requirements.txt, data/

prep/                    — DORMANT: workflow disabled, code untouched
  main.py, pilotfetch.py, prep_engine.py, prep_config.py, requirements.txt

netlify/functions/       — Serverless endpoints (order confirm-receipt + par editing)
  confirm.mjs            — Supplier "confirm receipt" page (GET) + recorder (POST → Netlify Blobs)
  order-status.mjs       — JSON read-back of confirmations for the dashboard (GET /api/order-status)
  set-par.mjs            — Manager fills a missing par (POST /api/set-par → Netlify Blobs)
  par-overrides.mjs      — JSON read-back of saved pars for the dashboard (GET /api/par-overrides)
  order-xlsx.mjs         — Builds UD's order schedule: fills bar/ud_order_template.xlsx from the
                           batch order (POST /api/order-xlsx → .xlsx download). Uses ExcelJS.
bar/merge_par_overrides.mjs — Build-time merge of saved pars into pars.json (+ --clear mode)
netlify.toml            — Netlify config (publish=docs; functions dir; ud_order_template.xlsx in included_files)
package.json            — @netlify/blobs + exceljs deps for the functions (repo's only Node code)

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
| 2026-06-28 | Addressed the *actual* Jun-outage failure mode: Netlify build-credit exhaustion had no early warning — it only surfaced as a 6-day live-site freeze. | Added a **build-credit monitor** to `health_check.yml` (commit `a1da67a`): polls the Netlify account's build-minute usage each run and warns *before* the quota runs out — ≥80% used → info issue (no email), ≥95% → hard failure (email). Account auto-discovered from the token (override via `NETLIFY_ACCOUNT_ID`). Optional + graceful: needs a Netlify PAT in `NETLIFY_API_TOKEN`; skipped silently if unset, and any monitoring-API error is logged but never fails the health check. **Still pending (manual, owner-only):** create the Netlify PAT and set `NETLIFY_API_TOKEN` to activate. Unlike the build-hook self-heal, this targets the failure mode that actually took the site down. |
| 2026-06-28 | **Feature (manager request):** Orders → History showed status only via a manual dropdown the manager set by hand, and the date group headers were small/muted (11px, all-caps, grey). | (a) Restyled the History date headers — sentence-case, 14px/700, dark ink (on-brand vs. the old muted all-caps; uppercase reserved for ≤11px labels per the v3 design system). (b) Added a **confirm-receipt link** to every order email (`/confirm?id=<order-uuid>`). When the *supplier* clicks it and presses "Confirm receipt", a **Netlify Function** (`netlify/functions/confirm.mjs`) records it to **Netlify Blobs**; the dashboard polls `/api/order-status` (`order-status.mjs`) on load + History-tab open and auto-advances that order `sent → confirmed` (shows a "Confirmed <time>" line). **Two-step GET-page→POST** so email link-scanners can't auto-confirm. Keeps the manual mailto send + the dropdown as an override; stays inside the locked order boundaries (manager still sends/reviews; only the supplier's own click flips status). **No new secret** (Blobs is auto-authed in the Functions runtime). Adds the repo's first Node code (`package.json` → `@netlify/blobs`, `netlify/functions/`) but **no extra daily build** and negligible invocations — safe under the build-credit constraint. See "Order Confirm-Receipt" section below. |
| 2026-06-30 | **Feature (manager request):** the Admin tab's "Missing par levels" list was read-only — the only way to set a par was to hand-edit `bar/pars.json` and commit, so the long-standing "fill in missing pars" TODO never moved. | Made each missing-par row **editable from the dashboard** (PR #27). The manager types a par + Save → a **Netlify Function** (`set-par.mjs`, `POST /api/set-par`) writes it to **Netlify Blobs** (store `par-overrides`); `par-overrides.mjs` (`GET /api/par-overrides`) reads saved values back so the inputs persist across reloads. The entered par becomes the **real** par: a new build-time Node step (`bar/merge_par_overrides.mjs`, run in `daily_bar.yml` **before** `generate_dashboard.py`) merges overrides into `pars.json` (only keys already on the sheet — junk-safe), so on the next refresh the product leaves the missing list and drives classification/orders/KPIs. `daily_bar.yml` also commits `pars.json` and clears consumed overrides **only after a successful push** (a mid-run failure never drops an edit — it re-applies next run). Stays inside the locked order boundaries (pars ≠ the display-only prep sheet; orders still manager-reviewed, so an errant par is caught at the order gate). **Latency:** a saved par applies on the next dashboard build, not instantly — UI says "applies on next refresh". **Still pending (manual, owner-only):** set `NETLIFY_API_TOKEN` (already pending for the build-credit monitor) **+ `NETLIFY_SITE_ID`** — until both exist the merge no-ops, so saving works but pars stay inert (CI warns, never fails). The merge step never fails the daily build. See "Admin par editing" section below. |
| 2026-06-30 | **Feature (manager request):** UD (United Distributors) require orders as a filled-in copy of their own Excel catalogue, not a plain-text email body. The Orders tab's "Send batch via email" button only produced a `mailto:` with the order typed into the body. | Made the button build **UD's actual `.xlsx` schedule**. Committed the manager's UD catalogue as a blank template (`bar/ud_order_template.xlsx` — sample quantities/date cleared; full ~370-row product list + per-product units + styling preserved). `sendBatchGroup()` now POSTs the batch order (`{ key, qty }` pairs, where `key` is the `pars.json` product name carried end-to-end as `data-par-key` — sourced from a new `par_key` field in `analyse.py`) to a **Netlify Function** (`order-xlsx.mjs`, `POST /api/order-xlsx`, uses **ExcelJS**). The function fills **Col C** on every template row whose **Col A** matches, writes the date into D2, appends any off-catalogue SKUs under "Additional items", and returns the `.xlsx`. The dashboard **downloads** it and opens a **short** covering email to UD (manager CC'd) for the manager to **attach and send** — stays manager-reviewed (locked order boundaries). **No new secret** (pure transform; template bundled via `included_files`). **No extra daily build**, negligible invocations — build-credit safe. **Graceful fallback** to the legacy plain-text email if the function is unreachable. Ships working on the next Netlify deploy. See "UD order schedule" section below. |
| 2026-07-22 | **Bug (tester report):** the UD order email arrived at the supplier with **no spreadsheet attached and no item list** — orders were effectively going out empty. Root cause: a `mailto:` link **cannot carry a file attachment**, so the 2026-06-30 flow only *downloaded* the `.xlsx` locally and relied on the manager remembering to manually attach it before sending. That manual step was missed (even in testing), and the covering email body deliberately lists no items (the spreadsheet is the order). Backend verified healthy — `/api/order-xlsx` fills the template correctly. | Owner chose **server-side send** (explicit new instruction, overriding the locked `mailto` boundary — the human *review* still holds). Added **`send-order.mjs`** (`POST /api/send-order`): builds the same `.xlsx` (extracted the fill logic into shared **`_ud_order.mjs`**, now used by both `order-xlsx.mjs` and the sender) and **emails it to UD with the file actually attached** via **Resend**, manager CC'd + reply-to, body/subject generated server-side (not an open relay). `sendBatchGroup()` now shows an on-screen **confirm** (review-before-send), POSTs to `/api/send-order`, and **falls back to the old download + `mailto`** on `503 not-configured` or any send error — so nothing regresses before setup. **Pending (owner-only):** set Netlify env vars `RESEND_API_KEY` + a verified `ORDER_FROM_EMAIL` (Resend needs domain verification); until then the send is inert and the manual-attach failure mode persists. The send-first `index.html` goes live on the next `daily_bar.yml` regen. See "UD order schedule" section. |

---

## TODO (pending confirmation from Sava)

- Fill in missing par levels for the items flagged in the dashboard's "PAR MISSING" admin tab (mix cocktails, Slo Jo syrups, glenfiddich/bushmills range, vapes, etc.). **As of 2026-06-30 this is self-service from the dashboard** — managers type the par into the editable field on the Admin tab and it writes back to `pars.json` on the next build (see "Admin par editing" section below). **Still needs the `NETLIFY_API_TOKEN` + `NETLIFY_SITE_ID` secrets set** before saved pars actually take effect; until then the field saves but the value stays inert.

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

---

## Order Confirm-Receipt (auto-status)

When a manager sends a supplier order, the dashboard records it in `localStorage` with status `sent`,
and the order email now includes a per-order confirm link:
`https://bossa-sunningdale.netlify.app/confirm?id=<order-uuid>`.

Flow:
1. The supplier opens that link → a small branded page with a **Confirm receipt** button.
2. Clicking the button POSTs to a **Netlify Function** (`netlify/functions/confirm.mjs`), which writes
   `{status: 'confirmed', confirmed_at}` to **Netlify Blobs** (key = the order UUID).
3. The dashboard polls `GET /api/order-status` (`netlify/functions/order-status.mjs`) on load and when
   the Orders → History tab opens (`syncRemoteStatus()` in `generate_dashboard.py`), and
   **auto-advances** any local order still marked `sent` to `confirmed` (showing a "Confirmed <time>"
   line). It never overrides a manual `received`/`cancelled`.

Design notes / boundaries:
- **Two-step (GET page → POST button)** on purpose: email link-scanners issue GETs, so a GET never
  mutates state — only a human button click confirms. Prevents false "confirmed".
- The UUID is unguessable, so a supplier can only confirm the one order they were emailed.
- **No new secret** — Netlify Blobs is auto-authed inside the Functions runtime.
- Stays inside the locked order boundaries: the manager still sends every order via mailto and reviews
  first; the manual status dropdown remains as an override. Only the supplier's own click auto-flips.
- **Routing:** each function self-registers its clean path via `export const config = { path }`
  (Netlify Functions v2), served same-origin — so no CORS and no `netlify.toml` redirects needed.
- **Build impact:** adds the repo's first Node code (`package.json` → `@netlify/blobs`) but **no extra
  daily build** and negligible function invocations (well within the free tier) — safe under the
  build-credit constraint that caused the Jun 2026 outage.

**Activation:** ships working on the next deploy — Netlify auto-detects `netlify/functions/` and
installs `@netlify/blobs`. Nothing to configure. Until then the dashboard degrades gracefully: the
`/api/order-status` fetch fails silently and the manual dropdown still works.

**Verify locally** with `netlify dev` (needs the Netlify CLI + site linked): visit
`http://localhost:8888/confirm?id=test-123`, click **Confirm receipt**, then load
`http://localhost:8888/api/order-status` and confirm `test-123` shows `confirmed`.

---

## UD order schedule (Excel, not an email body)

Shipped 2026-06-30. United Distributors (UD) — the single supplier all 18 categories route to
(`config.py`) — require orders as a **filled-in copy of their own Excel catalogue**, not a
plain-text email body. The Orders tab's **Send batch via email** button now produces that `.xlsx`.

Flow:
1. Manager builds the batch order on the Place-order tab and clicks the send button. `sendBatchGroup()`
   (in `generate_dashboard.py`) collects the selected items as `{ key, qty }` pairs — `key` is the raw
   `pars.json` product name, carried end-to-end as `data-par-key` on each order row (sourced from
   `analyse.py`, which now surfaces `par_key`).
2. It POSTs `{ order_date, items, extra }` to **`netlify/functions/order-xlsx.mjs`**
   (`POST /api/order-xlsx`). The function loads the committed blank template
   **`bar/ud_order_template.xlsx`**, writes the date into D2, and fills **Col C (quantity)** on every
   row whose **Col A** product key matches an item. Ordered SKUs with no template row (`extra`, e.g. a
   brand-new vape) are appended under a trailing "Additional items" block so nothing is dropped. It
   returns the `.xlsx` as an attachment download.
3. **Server-side send (added 2026-07-22):** `sendBatchGroup()` first shows an on-screen **confirm**
   ("Send this order to UD (N items)? To/CC …"), then POSTs the order to **`send-order.mjs`**
   (`POST /api/send-order`), which builds the same `.xlsx` (shared `_ud_order.mjs`) and **emails it to
   UD with the spreadsheet actually attached**, manager CC'd + reply-to, via **Resend**. The order
   stays manager-reviewed — the manager reviews the batch and clicks Send; only the send *mechanism*
   changed (a `mailto:` link **cannot** carry an attachment, which is why the old download-then-attach
   flow was shipping orders with no spreadsheet). **Fallback:** if the sender isn't configured yet
   (`503`) or the send fails, it silently degrades to the **old download + `mailto`** path so a manager
   is never blocked.

Design notes / boundaries:
- **`bar/ud_order_template.xlsx`** is the example UD file with the sample quantities + date cleared —
  a reusable blank form. The full ~370-row catalogue, per-product **units** (Col B: `Case`/`Bot`/`50L`
  …, which exist nowhere else in the repo), category headers, fonts and column widths are preserved
  byte-for-byte. To change UD's product list/units, edit this file.
- **Server-side build, not an inline JS library** — keeps `docs/index.html` lean and gives
  byte-faithful format fidelity (it edits the real template). Mirrors the existing functions pattern;
  self-registers its clean path via `export const config = { path }` (Functions v2), same-origin (no
  CORS). **No new secret** — pure transform, no Blobs/token. The template ships with the bundle via
  `included_files` in `netlify.toml`. Adds `exceljs` to `package.json`.
- **Build-credit safe** — no extra daily build, negligible invocations (only on a manager click).
- **Graceful fallback** — if `/api/order-xlsx` is unreachable (function not yet deployed / offline),
  the button falls back to the legacy plain-text order email so a manager is never blocked.
- **Latency:** none — the file is built and downloaded on click (unlike par edits, which apply next build).

**Activation:**
- **Download/build path** — ships working on the next Netlify deploy (auto-detects `netlify/functions/`,
  installs `exceljs`, bundles the template). Nothing to configure.
- **Server-side send (owner-only, to make the email actually carry the attachment):** set two
  **Netlify environment variables** (Netlify → Site settings → Environment variables — **NOT** GitHub
  Secrets; the function runs in the Netlify Functions runtime):
  - `RESEND_API_KEY` — a [Resend](https://resend.com) API key.
  - `ORDER_FROM_EMAIL` — a **verified** sender on your Resend domain (e.g. `orders@<yourdomain>`).
    Resend requires domain verification (DNS records) before it will deliver to arbitrary recipients.
  - `ORDER_FROM_NAME` — optional display name (default `Bossa Sunningdale`).
  Until both required vars are set, `/api/send-order` returns `503` and the dashboard **falls back to
  the download + `mailto`** flow — so it degrades gracefully, exactly as before. **⚠️ Until this is
  set, the manager must still manually attach the downloaded file** (the failure mode that prompted
  this change). The new `index.html` (with the send-first button) only goes live once
  `daily_bar.yml` regenerates it — trigger a manual run or wait for the morning cron.

**Verify locally** with `netlify dev`: build a batch order on the dashboard, click **Send batch via
email** → confirm the review dialog. With `RESEND_API_KEY`/`ORDER_FROM_EMAIL` set it sends via Resend;
unset, it falls back to a `.xlsx` download with the on-screen quantities filled on the right rows (and
D2 = the order date) and a short email draft opens. Or hit the function directly:
`curl -X POST localhost:8888/api/order-xlsx -H 'content-type: application/json' -d '{"order_date":"2026-06-27","items":[{"key":"be - black label","qty":1},{"key":"dr - castle lite draught","qty":2}],"extra":[]}' -o out.xlsx`
then open `out.xlsx`.

---

## Admin par editing (fill missing pars from the dashboard)

Shipped 2026-06-30 (PR #27). The Admin tab's "Missing par levels" list is editable: each row has
a par input + **Save**. A saved par becomes the **real** par — it writes back to `bar/pars.json`
and drives classification, orders and KPIs on the next refresh. This is the self-service path for
the long-standing "fill in missing pars" TODO.

Flow:
1. Manager types a par into the row and clicks **Save** → `savePar()` POSTs `{product, par}` to
   `set-par.mjs` (`POST /api/set-par`), which writes `{par}` to **Netlify Blobs** (store
   `par-overrides`, key = the raw `pars.json` product name). Empty input → `par: null` (clears it).
2. On load + Admin-tab open, `fetchParOverrides()` reads `par-overrides.mjs` (`GET
   /api/par-overrides`) and reflects saved values back into the inputs ("Saved — applies on next
   refresh"), so an entry persists across reloads even before the next build.
3. The next `daily_bar.yml` run executes `bar/merge_par_overrides.mjs` **before**
   `generate_dashboard.py`: it reads the overrides and writes each into `pars.json` — **only for
   keys already on the sheet** (unknown/crafted keys are ignored). The generator then reads the
   merged `pars.json` via `load_pars()`, so the product leaves "Missing par levels" and classifies
   normally. `pars.json` is committed alongside `docs/index.html`.
4. **After** a successful commit/push, a final step runs `merge_par_overrides.mjs --clear`, deleting
   only the overrides whose value is now reflected in `pars.json`.

Design notes / boundaries:
- **Server-authoritative, not localStorage** — the entered value is the real par (the manager owns
  their stock pars), so it must reach the source of truth, not sit as a per-browser note.
- **Stays inside the locked order boundaries** — `pars.json` is the managers' own count-sheet data
  (≠ the display-only front/back prep sheet), and orders are still manager-reviewed before sending,
  so an errant par is caught at the order-review gate, never auto-sent.
- **Mid-run safety (the one ordering subtlety):** the clear step has **no `if: always()`** — it only
  runs when merge + generate + commit/push all succeeded. If an earlier step fails (e.g. SSRS down),
  the merge's on-disk `pars.json` edit is discarded uncommitted **and** the override is *not* cleared,
  so it simply re-applies next run. Never lose an edit.
- **Never fails the daily build** — `merge_par_overrides.mjs` swallows its own errors and exits 0;
  the critical dashboard refresh is unaffected if Blobs is unreachable.
- `@netlify/blobs` is **Node-only**, so the merge is a Node step (not Python). Addressing Blobs from
  CI (outside the Functions runtime) needs an explicit `siteID` + `token` — hence `NETLIFY_SITE_ID`
  + `NETLIFY_API_TOKEN`.
- **Latency:** a saved par takes full effect on the next build (~05:13 / 07:17 SAST, or a manual
  `workflow_dispatch`) — surfaced honestly in the UI as "applies on next refresh".

**Activation (pending, owner-only):** set the `NETLIFY_API_TOKEN` + `NETLIFY_SITE_ID` GitHub
Secrets. Until both exist the merge no-ops and the daily build logs a `::warning::` listing pending
pars — saving still works (Blobs is auto-authed in the Functions runtime), but the value stays inert
until the merge can run. The functions themselves deploy automatically on the next Netlify build.

**Verify locally** with `netlify dev`: open Admin → Missing par levels, type a par, **Save** → state
shows "Saved"; reload → value persists (via `/api/par-overrides`); `GET /api/par-overrides` shows
`{ "<product>": <par> }`. Then with `NETLIFY_SITE_ID`/`NETLIFY_API_TOKEN` exported, run
`node bar/merge_par_overrides.mjs` and confirm `pars.json` gained the par (key order + other nulls
preserved).
