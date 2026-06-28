// Status read-back endpoint for the Bossa Sunningdale order dashboard.
//
//   GET /api/order-status → { "<order-id>": { status, confirmed_at }, ... }
//
// The dashboard (bar/generate_dashboard.py, syncRemoteStatus) fetches this on
// load and when the Orders/History tab opens, then auto-advances any local
// order it still has as "sent" to "confirmed" once the supplier has clicked
// the confirm-receipt link (recorded by confirm.mjs into Netlify Blobs).
//
// Served same-origin via config.path, so no CORS handling is needed. Volume is
// tiny (one venue), so returning every confirmation is fine; add an ?ids=
// filter here if the store ever grows large.

import { getStore } from "@netlify/blobs";

export const config = { path: "/api/order-status" };

const STORE_NAME = "order-confirmations";

export default async () => {
  const out = {};
  try {
    const store = getStore(STORE_NAME);
    const { blobs } = await store.list();
    for (const b of blobs) {
      const rec = await store.get(b.key, { type: "json" });
      if (rec) out[b.key] = rec;
    }
  } catch (err) {
    // Blobs unavailable — return an empty map. The dashboard treats this as
    // "no confirmations yet" and keeps the manual dropdown working.
  }

  return new Response(JSON.stringify(out), {
    status: 200,
    headers: {
      "content-type": "application/json; charset=utf-8",
      "cache-control": "no-store",
    },
  });
};
