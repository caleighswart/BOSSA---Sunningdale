// UD order-schedule builder (download path) for the Bossa Sunningdale bar dashboard.
//
//   POST /api/order-xlsx
//     body { order_date: "YYYY-MM-DD",
//            items: [{ key, qty }],            // key = a pars.json product name
//            extra: [{ name, cat, unit, qty }] // ordered SKUs not in the template
//          }
//     → 200 with the filled-in .xlsx as an attachment download.
//
// This is the download half of the flow: the dashboard fetches the .xlsx and
// saves it locally (used as the graceful fallback when the server-side email
// sender isn't configured — see send-order.mjs). The actual spreadsheet is
// built by the shared buildOrderXlsx() in _ud_order.mjs so this path and the
// email path produce a byte-identical file.
//
// No secret / no Netlify Blobs — this is a pure transform. The template ships
// with the function bundle via `included_files` in netlify.toml.

import { buildOrderXlsx } from "./_ud_order.mjs";

export const config = { path: "/api/order-xlsx" };

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

  let built;
  try {
    built = await buildOrderXlsx(payload);
  } catch (err) {
    return json({ ok: false, error: "template-error" }, 500);
  }

  return new Response(built.buffer, {
    status: 200,
    headers: {
      "content-type":
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
      "content-disposition": `attachment; filename="${built.filename}"`,
      "cache-control": "no-store",
    },
  });
};
