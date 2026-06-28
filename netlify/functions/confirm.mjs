// Supplier "confirm receipt" endpoint for Bossa Sunningdale orders.
//
// Each order email (built in bar/generate_dashboard.py) contains a link
// https://bossa-sunningdale.netlify.app/confirm?id=<order-uuid>.
//
//   GET  /confirm?id=<uuid>  → a small page with a "Confirm receipt" button.
//   POST /confirm?id=<uuid>  → records the confirmation in Netlify Blobs.
//
// The two-step (GET page, then POST on a real button click) is deliberate:
// email security scanners / link prefetchers issue GETs, and a GET must never
// mutate state — otherwise an automated scan would silently mark orders
// "confirmed". Only a human button click POSTs.
//
// The id is the order's unguessable UUID, so a supplier can only ever confirm
// the one order they were emailed. Writes are idempotent (last click wins).
//
// The dashboard reads these back via /api/order-status (order-status.mjs) and
// auto-advances the matching order from "sent" to "confirmed".

import { getStore } from "@netlify/blobs";

export const config = { path: "/confirm" };

const STORE_NAME = "order-confirmations";
// Accepts crypto.randomUUID() ("xxxx-xxxx-...") and the o_<base36>_<base36>
// fallback id from newOrderId(); rejects anything else.
const ID_RE = /^[A-Za-z0-9_-]{8,64}$/;

function page(title, message, { status = 200, button = "" } = {}) {
  const html = `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>${title} · Bossa Sunningdale</title>
<style>
  :root { --ink:#0F172A; --ink-mute:#64748B; --line:#E2E7EF;
          --accent:#1D5BD8; --accent-hover:#1747AC; --bg:#F2F4F7; --panel:#FFFFFF; }
  * { box-sizing: border-box; }
  body { margin:0; min-height:100vh; display:flex; align-items:center; justify-content:center;
         background:var(--bg); color:var(--ink); padding:24px;
         font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif; }
  .card { background:var(--panel); border:1px solid var(--line); border-radius:12px;
          box-shadow:0 2px 8px rgba(15,23,42,.06); padding:32px 28px; max-width:440px; width:100%;
          text-align:center; }
  .brand { font-weight:700; letter-spacing:.04em; font-size:14px; color:var(--ink); margin-bottom:18px; }
  .brand span { color:var(--ink-mute); font-weight:600; }
  h1 { font-size:20px; margin:0 0 10px; }
  p { color:var(--ink-mute); line-height:1.5; margin:0 0 22px; font-size:15px; }
  button { background:var(--accent); color:#fff; border:0; border-radius:8px;
           padding:12px 24px; font-size:15px; font-weight:600; cursor:pointer; }
  button:hover { background:var(--accent-hover); }
</style>
</head>
<body>
  <main class="card">
    <div class="brand">BOSSA <span>Sunningdale</span></div>
    <h1>${title}</h1>
    <p>${message}</p>
    ${button}
  </main>
</body>
</html>`;
  return new Response(html, {
    status,
    headers: { "content-type": "text/html; charset=utf-8", "cache-control": "no-store" },
  });
}

export default async (req) => {
  const url = new URL(req.url);
  const id = (url.searchParams.get("id") || "").trim();

  if (!ID_RE.test(id)) {
    return page(
      "Link not recognised",
      "This confirmation link is missing or malformed. Please use the link from your order email.",
      { status: 400 }
    );
  }

  if (req.method === "POST") {
    try {
      const store = getStore(STORE_NAME);
      await store.setJSON(id, {
        status: "confirmed",
        confirmed_at: new Date().toISOString(),
      });
    } catch (err) {
      return page(
        "Something went wrong",
        "We couldn't record your confirmation just now. Please try the link again in a moment.",
        { status: 500 }
      );
    }
    return page(
      "Receipt confirmed",
      "Thank you — we've let Bossa Sunningdale know you received this order. You can close this page."
    );
  }

  // GET — show the confirm button. State only changes on the POST below.
  const button = `<form method="POST" action="/confirm?id=${encodeURIComponent(id)}">
      <button type="submit">Confirm receipt</button>
    </form>`;
  return page(
    "Confirm receipt",
    "Please confirm you've received this order from Bossa Sunningdale.",
    { button }
  );
};
