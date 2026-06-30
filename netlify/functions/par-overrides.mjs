// Par-override read-back endpoint for the Bossa Sunningdale bar dashboard.
//
//   GET /api/par-overrides → { "<product>": <par|null>, ... }
//
// The dashboard (bar/generate_dashboard.py, fetchParOverrides) fetches this on
// load and when the Admin tab opens, then reflects any par a manager has already
// saved back into the matching input under "Missing par levels" (showing it as
// "Saved — applies on next refresh"). The values are written by set-par.mjs into
// Netlify Blobs and consumed by the daily build (bar/merge_par_overrides.mjs).
//
// Served same-origin via config.path, so no CORS handling is needed. Volume is
// tiny (one venue), so returning every override is fine.

import { getStore } from "@netlify/blobs";

export const config = { path: "/api/par-overrides" };

const STORE_NAME = "par-overrides";

export default async () => {
  const out = {};
  try {
    const store = getStore(STORE_NAME);
    const { blobs } = await store.list();
    for (const b of blobs) {
      const rec = await store.get(b.key, { type: "json" });
      // Flatten { par, updated_at } down to the par value the client needs.
      if (rec && typeof rec === "object") out[b.key] = rec.par ?? null;
    }
  } catch (err) {
    // Blobs unavailable — return an empty map. The dashboard treats this as
    // "no saved pars" and the inputs stay blank.
  }

  return new Response(JSON.stringify(out), {
    status: 200,
    headers: {
      "content-type": "application/json; charset=utf-8",
      "cache-control": "no-store",
    },
  });
};
