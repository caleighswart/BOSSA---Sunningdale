# Bar Stock Agent

The Bar Stock Agent turns Bossa Sunningdale's live PilotLive stock data into a single static
dashboard — the **only consumer surface** for the bar. Every morning it pulls stock-on-hand from
PilotLive's SSRS report server, matches each SKU against Sava's per-product par levels, classifies
everything as critical / low / healthy, and rebuilds the dashboard.

**Live dashboard:** https://bossa-sunningdale.netlify.app/

> This README documents the bar agent specifically. For system-wide operations — cron schedules,
> redundancy, the self-healing health check, GitHub Secrets, and Netlify — see the repo runbook
> [../CLAUDE.md](../CLAUDE.md).

---

## What it does

```
SSRS pull  →  match against pars.json  →  classify  →  rebuild docs/index.html  →  Netlify deploys
```

The job runs daily via [../.github/workflows/daily_bar.yml](../.github/workflows/daily_bar.yml) and
writes a self-contained HTML file to `docs/index.html`, which Netlify auto-deploys on push. The
generator is **idempotent** — running it twice in a day is harmless and produces the same output for
the same data. (See [../CLAUDE.md](../CLAUDE.md) for the redundant-cron and health-check details.)

---

## File map

| File | Role |
|------|------|
| [generate_dashboard.py](generate_dashboard.py) | **ACTIVE entrypoint.** Fetches SSRS data, analyses it, and builds `docs/index.html` via `build_html()`. |
| [analyse.py](analyse.py) | Par matching + bucket classification (`analyse()`). Also holds the now-dormant Telegram brief builder (`build_brief()`). |
| [pilotfetch.py](pilotfetch.py) | SSRS XML fetch (NTLM auth). |
| [config.py](config.py) | Categories, display labels, units, suppliers, thresholds, and the `pars.json` loader. |
| [pars.json](pars.json) | Product → par mapping (keys = PilotLive product names; value = par units or `null`). |
| [build_design_template.py](build_design_template.py) | Offline design fixture — reuses `build_html()` against a tiny dataset to produce a styled template at `/tmp/bossa_dashboard_design_template.html`. No SSRS/credentials needed. |
| [main.py](main.py) | **DORMANT.** Old Telegram-send entrypoint, kept for reference but no longer run. |
| [orders_webhook.gs](orders_webhook.gs) | Google Apps Script web app behind `BOSSA_ORDERS_WEBHOOK` — best-effort sync of sent orders into a Google Sheet for reporting (dashboard localStorage is the source of truth). |
| [_smoke_gen.py](_smoke_gen.py) | Smoke-test generator. |

---

## Data flow

1. **[pilotfetch.py](pilotfetch.py)** authenticates with NTLM and pulls the *Theoretical Stock On Hand*
   XML report (`dclink=8689` = the Bossa Sunningdale store). Returns ~200KB of XML in ~2s when healthy.
2. **[analyse.py](analyse.py)** infers which categories Sava tracks from `pars.json`, normalises each
   product name (`_norm`: lowercase + collapsed whitespace), and looks up its par.
3. Each matched SKU is **classified** into a bucket (below).
4. **[generate_dashboard.py](generate_dashboard.py)** renders the buckets into the static HTML dashboard.

For the exact SSRS request (URL, params, auth, XML namespace), see
[../PILOTLIVE_DATA_PULL.md](../PILOTLIVE_DATA_PULL.md).

---

## Classification model (current)

Classification is by **percentage of each product's own par level**, not days of cover. Source of
truth: [config.py](config.py) (`CRITICAL_PCT`, `LOW_PCT`, `VARIANCE_CUTOFF`) and
[analyse.py](analyse.py) (`analyse()`).

| Status | Rule | Constant |
|--------|------|----------|
| ⚠️ **Variance** | `soh < -5` (likely count error) | `VARIANCE_CUTOFF = -5` |
| 🔴 **Critical** | `0 ≤ soh < 30% of par` → order today | `CRITICAL_PCT = 0.30` |
| 🟡 **Low** | `30% ≤ soh < 70% of par` → watch | `LOW_PCT = 0.70` |
| ✅ **Healthy** | `soh ≥ 70% of par` | — |

Variance is checked first, so a deeply negative count is surfaced as a variance rather than a critical.
Products on the sheet with **no par value** are reported separately under the dashboard's Admin tab as
"par missing"; PilotLive products in a well-tracked category that aren't on the sheet appear as "new
products — add to count sheet".

---

## Configuration knobs

All in [config.py](config.py) unless noted:

- **Par levels** — edit [pars.json](pars.json) (keys are PilotLive product names). Currently 400
  products, 44 of which have no par set yet (these surface in the Admin tab). The next run picks up
  changes automatically.
- **Thresholds** — `CRITICAL_PCT` / `LOW_PCT` / `VARIANCE_CUTOFF`.
- **Categories** — `BAR_CATEGORIES`, plus display `CATEGORY_LABELS`, `CATEGORY_ORDER`, `CATEGORY_UNITS`.
- **Suppliers** — the `SUPPLIERS` dict. Orders are sent by **email** (`mailto:`) from the dashboard's
  **Place order** tab — an ad-hoc single-product form plus per-supplier batch ("Send batch via email").
  Suppliers sharing an `email` are merged into one order card. All addresses are currently the
  `hello@makematicai.com` test address until real ones are confirmed; the `whatsapp` field is retained
  for fallback but is no longer read by the dashboard.

---

## Run & debug locally

Requires **Python 3.10+** ([config.py](config.py) uses `X | None` type annotations). macOS's system
`python3` is 3.9 and will fail with `unsupported operand type(s) for |`.

```bash
cd bar
pip install -r requirements.txt          # requests + requests-ntlm

# Full run against live SSRS (needs credentials):
export PILOTLIVE_USERNAME=0834436203
export PILOTLIVE_PASSWORD=...             # see GitHub Secrets / ../CLAUDE.md
python generate_dashboard.py             # writes ../docs/index.html

# Styled offline template — no SSRS, no credentials:
python build_design_template.py          # writes /tmp/bossa_dashboard_design_template.html
```

For production debugging ("dashboard didn't update", SSRS timeouts, stuck Netlify deploys), follow the
runbook in [../CLAUDE.md](../CLAUDE.md) rather than duplicating it here.

---

## Design decisions

**Usage signal — TheoreticalUsage over the PLU sales report.** The PLU qty sales report uses different
naming conventions to the stock report, so automatic name-matching failed badly (only ~7 of 80 top bar
PLUs matched; draught items were the worst). A manual PLU→stock lookup would break silently whenever
PilotLive renamed a product. PilotLive's own `TheoreticalUsage` field is already present in the stock
report and matches the stock product names by definition, so it was adopted instead.

> **Note on the historical PDF.** The original rationale is captured in
> [../Bar_Stock_Agent_Design_Decision.pdf](../Bar_Stock_Agent_Design_Decision.pdf) (April 2026). That
> document describes a **days-of-cover** classification (`TheoreticalUsage / STOCKTAKE_DAYS`). The live
> dashboard has since moved to the **% -of-par** model documented above — treat the PDF as historical
> for the classification logic.

---

## Related docs

- [../CLAUDE.md](../CLAUDE.md) — system-wide runbook (schedules, secrets, Netlify, health check, the
  dormant inventory/prep agents).
- [../PILOTLIVE_DATA_PULL.md](../PILOTLIVE_DATA_PULL.md) — full SSRS data-pull technical reference.
