// Server-side UD order sender for the Bossa Sunningdale bar dashboard.
//
//   POST /api/send-order
//     body { order_date: "YYYY-MM-DD",
//            to:        "supplier@ud.co.za",   // supplier (required)
//            cc:        "manager@bossa.co.za", // manager, optional
//            reply_to:  "manager@bossa.co.za", // optional
//            contact:   "Thabo",               // supplier contact name, optional
//            date_nice: "Monday, 27 July 2026",// pretty date for the body, optional
//            items: [{ key, qty }],            // key = a pars.json product name
//            extra: [{ name, unit, qty }]      // ordered SKUs not in the template
//          }
//     → 200 { ok:true, id }              email accepted by the provider
//       503 { ok:false, error:"not-configured" }  RESEND_API_KEY / ORDER_FROM_EMAIL unset
//       4xx/5xx { ok:false, error }       validation / provider failure
//
// Why this exists: a mailto: link CANNOT carry a file attachment, so the old
// "download the .xlsx then open an email for the manager to attach it" flow
// relied on a human remembering to attach the file — and orders were going out
// with no spreadsheet. This function sends the email server-side with the .xlsx
// actually attached. The manager still reviews the order on the dashboard and
// clicks Send (see sendBatchGroup + its confirm() in generate_dashboard.py), so
// the locked "orders stay manager-reviewed before sending" boundary holds — the
// send mechanism changes, the human-review principle does not.
//
// The spreadsheet is built by the shared buildOrderXlsx() (identical to the
// download path). Email goes via Resend's REST API (plain fetch, no SDK). The
// body/subject are generated server-side from a fixed template; the client only
// supplies structured order data + recipients — so this is not a free-form
// open relay. The `from` address is fixed to the verified sender env var.
//
// Activation (owner-only, Netlify env vars — NOT GitHub Secrets, since this
// runs in the Netlify Functions runtime):
//   RESEND_API_KEY    — Resend API key (resend.com → API Keys)
//   ORDER_FROM_EMAIL  — a verified sender on your Resend domain,
//                       e.g. "orders@bossa-sunningdale.co.za"
//   ORDER_FROM_NAME   — optional display name (default "Bossa Sunningdale")
// Until both required vars are set the function returns 503 and the dashboard
// degrades gracefully to the download+mailto flow.

import { buildOrderXlsx } from "./_ud_order.mjs";

export const config = { path: "/api/send-order" };

const RESEND_ENDPOINT = "https://api.resend.com/emails";
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

function json(body, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: {
      "content-type": "application/json; charset=utf-8",
      "cache-control": "no-store",
    },
  });
}

function cleanEmail(v) {
  const s = typeof v === "string" ? v.trim() : "";
  return EMAIL_RE.test(s) ? s : "";
}

export default async (req) => {
  if (req.method !== "POST") {
    return json({ ok: false, error: "method-not-allowed" }, 405);
  }

  const apiKey = (process.env.RESEND_API_KEY || "").trim();
  const fromEmail = (process.env.ORDER_FROM_EMAIL || "").trim();
  const fromName = (process.env.ORDER_FROM_NAME || "Bossa Sunningdale").trim();
  // Not configured yet → let the dashboard fall back to download+mailto.
  if (!apiKey || !fromEmail) {
    return json({ ok: false, error: "not-configured" }, 503);
  }

  let payload;
  try {
    payload = await req.json();
  } catch (err) {
    return json({ ok: false, error: "bad-json" }, 400);
  }

  const to = cleanEmail(payload?.to);
  if (!to) return json({ ok: false, error: "bad-recipient" }, 400);
  const cc = cleanEmail(payload?.cc);
  const replyTo = cleanEmail(payload?.reply_to);
  const contact = typeof payload?.contact === "string" ? payload.contact.trim().slice(0, 80) : "";
  const dateNice = typeof payload?.date_nice === "string" ? payload.date_nice.trim().slice(0, 80) : "";

  // Build the spreadsheet from the same shared builder as the download path.
  let built;
  try {
    built = await buildOrderXlsx(payload);
  } catch (err) {
    return json({ ok: false, error: "template-error" }, 500);
  }

  // Body + subject are server-generated (fixed template) — the client can't
  // inject arbitrary email content, only order data + recipients.
  const subject = "Bossa Sunningdale bar order" + (dateNice ? " — " + dateNice : "");
  const greeting = contact ? "Hi " + contact : "Hi";
  const replyLine = cc ? "\n\nPlease reply to all so " + cc + " stays on the thread." : "";
  const text =
    greeting + ",\n\n" +
    "Please find this week's bar order attached as a spreadsheet" +
    (dateNice ? " (order date: " + dateNice + ")" : "") + ".\n" +
    "The quantities are filled into your usual order schedule." +
    replyLine + "\n\nThanks,\nBossa Sunningdale";
  const htmlBody =
    "<p>" + greeting + ",</p>" +
    "<p>Please find this week's bar order attached as a spreadsheet" +
    (dateNice ? " (order date: " + escapeHtml(dateNice) + ")" : "") + ". " +
    "The quantities are filled into your usual order schedule.</p>" +
    (cc ? "<p>Please reply to all so " + escapeHtml(cc) + " stays on the thread.</p>" : "") +
    "<p>Thanks,<br>Bossa Sunningdale</p>";

  const attachmentB64 = Buffer.from(built.buffer).toString("base64");

  const body = {
    from: `${fromName} <${fromEmail}>`,
    to: [to],
    subject,
    text,
    html: htmlBody,
    attachments: [{ filename: built.filename, content: attachmentB64 }],
  };
  if (cc) body.cc = [cc];
  if (replyTo) body.reply_to = replyTo;

  let resp;
  try {
    resp = await fetch(RESEND_ENDPOINT, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${apiKey}`,
        "content-type": "application/json",
      },
      body: JSON.stringify(body),
    });
  } catch (err) {
    return json({ ok: false, error: "send-network-error" }, 502);
  }

  let result = {};
  try {
    result = await resp.json();
  } catch (err) {
    // Non-JSON provider response — treat by status below.
  }

  if (!resp.ok) {
    const message = result?.message || result?.error || `provider-${resp.status}`;
    return json({ ok: false, error: "send-failed", detail: message }, 502);
  }

  return json({ ok: true, id: result?.id || null }, 200);
};

function escapeHtml(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}
