// Merge manager-entered par overrides into bar/pars.json before the dashboard
// is generated.
//
// Flow:
//   1. A manager fills in a missing par on the dashboard Admin tab.
//   2. set-par.mjs writes { par } to the Netlify Blobs store "par-overrides".
//   3. This script (run in daily_bar.yml BEFORE generate_dashboard.py) reads the
//      store and writes each override into bar/pars.json — but ONLY for keys that
//      already exist in pars.json. Then the generator picks them up for free
//      (load_pars() reads pars.json), so the entered par drives classification,
//      orders and KPIs, and the product leaves "Missing par levels".
//
// Two modes:
//   node bar/merge_par_overrides.mjs            → merge overrides into pars.json
//   node bar/merge_par_overrides.mjs --clear    → delete the overrides that are
//                                                 now persisted in pars.json
//
// The --clear pass is run LAST in the workflow (after pars.json is committed and
// pushed) so a mid-run failure can never drop a manager's edit: an unconsumed
// override simply re-applies on the next run.
//
// @netlify/blobs is Node-only, so this lives outside the Python generator. Using
// the SDK from CI (outside the Functions runtime) requires manual siteID + token,
// supplied via the NETLIFY_SITE_ID and NETLIFY_API_TOKEN env vars. If either is
// missing the script no-ops (exit 0) so the build still succeeds — but warns if
// there are pending overrides, so a missing secret is visible rather than silent.

import { getStore } from "@netlify/blobs";
import { readFile, writeFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const STORE_NAME = "par-overrides";
const __dirname = dirname(fileURLToPath(import.meta.url));
const PARS_PATH = join(__dirname, "pars.json");

const CLEAR = process.argv.includes("--clear");

function openStore() {
  const siteID = process.env.NETLIFY_SITE_ID;
  const token = process.env.NETLIFY_API_TOKEN;
  if (!siteID || !token) return null;
  return getStore({ name: STORE_NAME, siteID, token });
}

async function listOverrides(store) {
  const out = {};
  const { blobs } = await store.list();
  for (const b of blobs) {
    const rec = await store.get(b.key, { type: "json" });
    if (rec && typeof rec === "object") out[b.key] = rec.par ?? null;
  }
  return out;
}

async function main() {
  const store = openStore();

  if (!store) {
    // No credentials. Surface pending work so it isn't silently dropped, but
    // don't fail the build.
    console.log(
      "merge_par_overrides: NETLIFY_SITE_ID / NETLIFY_API_TOKEN not set — " +
      "skipping (par overrides won't apply until the secrets exist)."
    );
    return;
  }

  let overrides;
  try {
    overrides = await listOverrides(store);
  } catch (err) {
    // Blobs unreachable — don't fail the daily build over it.
    console.log(`::warning::merge_par_overrides: could not read par overrides (${err.message}). Skipping.`);
    return;
  }

  const keys = Object.keys(overrides);
  if (keys.length === 0) {
    console.log("merge_par_overrides: no par overrides to " + (CLEAR ? "clear" : "merge") + ".");
    return;
  }

  const pars = JSON.parse(await readFile(PARS_PATH, "utf8"));

  if (CLEAR) {
    // Delete only the overrides whose value is now reflected in pars.json, so an
    // override that failed to persist (key absent / value mismatch) is kept and
    // retried next run.
    let cleared = 0;
    for (const key of keys) {
      if (key in pars && pars[key] === overrides[key]) {
        await store.delete(key);
        cleared++;
      }
    }
    console.log(`merge_par_overrides: cleared ${cleared} consumed override(s).`);
    return;
  }

  // Merge: apply overrides only for keys already on the par sheet. Unknown keys
  // (e.g. from a crafted POST) are ignored.
  let applied = 0;
  const skipped = [];
  for (const key of keys) {
    if (key in pars) {
      if (pars[key] !== overrides[key]) {
        pars[key] = overrides[key];
        applied++;
      }
    } else {
      skipped.push(key);
    }
  }

  if (applied > 0) {
    await writeFile(PARS_PATH, JSON.stringify(pars, null, 2) + "\n", "utf8");
  }
  console.log(`merge_par_overrides: applied ${applied} par override(s) to pars.json.`);
  if (skipped.length) {
    console.log(`::warning::merge_par_overrides: ignored ${skipped.length} override(s) for unknown product(s): ${skipped.join(", ")}`);
  }
}

main().catch((err) => {
  // Never fail the daily dashboard build because of the par-merge step.
  console.log(`::warning::merge_par_overrides: unexpected error (${err.message}). Skipping.`);
});
