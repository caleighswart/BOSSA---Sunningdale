// Par-override write endpoint for the Bossa Sunningdale bar dashboard.
//
//   POST /api/set-par   body { product, par }  → records a manager's par level.
//
// The dashboard's Admin → "Missing par levels" section lets a manager fill in
// the par for a product whose value is still null in bar/pars.json. Saving here
// writes { par } to Netlify Blobs (store "par-overrides", key = product name).
//
// The next daily build (bar/merge_par_overrides.mjs, run in daily_bar.yml before
// generate_dashboard.py) merges these overrides into bar/pars.json — so the
// entered par becomes the real par and drives classification, orders and KPIs.
//
// Unlike confirm.mjs there is no GET/scanner two-step: this is a first-party
// manager action from the dashboard, not an email link, so a single POST is the
// right shape. POST is the only accepted method.
//
// Junk or unknown product keys are harmless — the build-time merge only applies
// overrides for keys that already exist in bar/pars.json, and ignores the rest.

import { getStore } from "@netlify/blobs";

export const config = { path: "/api/set-par" };

const STORE_NAME = "par-overrides";
// pars.json keys are lowercase product names like "be - stella" /
// "wh - glenfiddich 12yr". Allow that charset; reject anything longer/odd.
const PRODUCT_RE = /^[a-z0-9 .,'&()/+-]{1,120}$/;
const PAR_MAX = 100000;

function json(body, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: {
      "content-type": "application/json; charset=utf-8",
      "cache-control": "no-store",
    },
  });
}

export default async (req) => {
  if (req.method !== "POST") {
    return json({ ok: false, error: "method-not-allowed" }, 405);
  }

  let payload;
  try {
    payload = await req.json();
  } catch (err) {
    return json({ ok: false, error: "bad-json" }, 400);
  }

  const product = typeof payload?.product === "string" ? payload.product.trim() : "";
  if (!PRODUCT_RE.test(product)) {
    return json({ ok: false, error: "bad-product" }, 400);
  }

  // par: null clears the override; otherwise a finite number in [0, PAR_MAX].
  let par = payload?.par;
  if (par === null || par === undefined || par === "") {
    par = null;
  } else {
    par = Number(par);
    if (!Number.isFinite(par) || par < 0 || par > PAR_MAX) {
      return json({ ok: false, error: "bad-par" }, 400);
    }
  }

  try {
    const store = getStore(STORE_NAME);
    await store.setJSON(product, { par, updated_at: new Date().toISOString() });
  } catch (err) {
    return json({ ok: false, error: "store-error" }, 500);
  }

  return json({ ok: true });
};
