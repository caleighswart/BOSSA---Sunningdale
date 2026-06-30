// UD order-schedule builder for the Bossa Sunningdale bar dashboard.
//
//   POST /api/order-xlsx
//     body { order_date: "YYYY-MM-DD",
//            items: [{ key, qty }],            // key = a pars.json product name
//            extra: [{ name, cat, unit, qty }] // ordered SKUs not in the template
//          }
//     → 200 with the filled-in .xlsx as an attachment download.
//
// United Distributors require their order as a filled-in copy of their own
// Excel catalogue, not a text email body. This function loads the committed
// blank template (bar/ud_order_template.xlsx — the manager's UD count sheet
// with quantities cleared), writes the order date into D2, and fills Col C
// (quantity) on every row whose Col A product key matches an item. Anything in
// `extra` (a brand-new SKU with no template row) is appended in a trailing
// "Additional items" block so nothing is silently dropped. The dashboard
// downloads the result and opens a short email for the manager to attach it to
// and send — the order stays manager-reviewed (see CLAUDE.md order boundaries).
//
// No secret / no Netlify Blobs — this is a pure transform. The template ships
// with the function bundle via `included_files` in netlify.toml.

import ExcelJS from "exceljs";
import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import path from "node:path";

export const config = { path: "/api/order-xlsx" };

// The template is bundled relative to the repo root (netlify.toml
// included_files). Try the repo-root paths first (cwd is the repo root in the
// Netlify runtime and under `netlify dev`), then an import.meta.url-relative
// fallback, so it resolves across environments. If none resolve, the handler
// 500s and the dashboard degrades to the plain-text email.
const HERE = path.dirname(fileURLToPath(import.meta.url));
const TEMPLATE_CANDIDATES = [
  path.join(process.cwd(), "bar", "ud_order_template.xlsx"),
  path.join(process.cwd(), "ud_order_template.xlsx"),
  path.join(HERE, "..", "..", "bar", "ud_order_template.xlsx"),
];

const QTY_MAX = 100000;
// pars.json keys look like "be - black label" / "dr - castle lite draught".
const KEY_MAX = 160;

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

// "2026-06-27" → "27 Jun 2026". Falls back to the raw string if it doesn't
// match YYYY-MM-DD. No Date object — avoids any timezone day-shift.
function formatOrderDate(s) {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(s);
  if (!m) return s;
  const [, y, mo, d] = m;
  const name = MONTHS[Number(mo) - 1];
  if (!name) return s;
  return `${Number(d)} ${name} ${y}`;
}

function json(body, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: {
      "content-type": "application/json; charset=utf-8",
      "cache-control": "no-store",
    },
  });
}

// Accept only a sane integer quantity; anything else drops the line.
function cleanQty(q) {
  const n = Number(q);
  if (!Number.isFinite(n)) return null;
  const i = Math.round(n);
  return i >= 1 && i <= QTY_MAX ? i : null;
}

async function loadTemplate() {
  let lastErr;
  for (const p of TEMPLATE_CANDIDATES) {
    try {
      const buf = await readFile(p);
      const wb = new ExcelJS.Workbook();
      await wb.xlsx.load(buf);
      return wb;
    } catch (err) {
      lastErr = err;
    }
  }
  throw lastErr || new Error("template-not-found");
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

  const orderDate = typeof payload?.order_date === "string" ? payload.order_date.trim() : "";
  const items = Array.isArray(payload?.items) ? payload.items : [];
  const extra = Array.isArray(payload?.extra) ? payload.extra : [];

  // Map of product key → quantity (last write wins; junk keys are harmless —
  // they simply won't match a template row below).
  const qtyByKey = new Map();
  for (const it of items) {
    const key = typeof it?.key === "string" ? it.key.trim() : "";
    const qty = cleanQty(it?.qty);
    if (key && key.length <= KEY_MAX && qty !== null) qtyByKey.set(key, qty);
  }

  let wb;
  try {
    wb = await loadTemplate();
  } catch (err) {
    return json({ ok: false, error: "template-error" }, 500);
  }

  const ws = wb.worksheets[0];
  if (!ws) return json({ ok: false, error: "template-empty" }, 500);

  // Order date → D2 (keeps the template's bold styling on that cell). Written
  // as an unambiguous formatted string ("27 Jun 2026"), not a JS Date — a Date
  // round-trips through the runtime timezone and can land Excel on the wrong
  // calendar day. Parse the YYYY-MM-DD parts directly, no Date involved.
  if (orderDate) {
    ws.getCell("D2").value = formatOrderDate(orderDate);
  }

  // Fill Col C for each matched product key. Col A holds the raw pars.json key.
  ws.eachRow((row) => {
    const a = row.getCell(1).value;
    const key = typeof a === "string" ? a.trim() : "";
    if (key && qtyByKey.has(key)) {
      row.getCell(3).value = qtyByKey.get(key);
    }
  });

  // Append any ordered SKUs that had no template row, so nothing is dropped.
  const extraRows = extra
    .map((e) => ({
      name: typeof e?.name === "string" ? e.name.trim() : "",
      unit: typeof e?.unit === "string" ? e.unit.trim() : "",
      qty: cleanQty(e?.qty),
    }))
    .filter((e) => e.name && e.qty !== null);

  if (extraRows.length) {
    ws.addRow([]); // spacer
    const header = ws.addRow(["Additional items", "Units", null]);
    header.getCell(1).font = { bold: true, size: 16 };
    header.getCell(2).font = { bold: true, size: 16 };
    for (const e of extraRows) {
      ws.addRow([e.name, e.unit, e.qty]);
    }
  }

  let buffer;
  try {
    buffer = await wb.xlsx.writeBuffer();
  } catch (err) {
    return json({ ok: false, error: "write-error" }, 500);
  }

  const safeDate = orderDate || "order";
  const filename = `Bossa Sunningdale - ${safeDate}.xlsx`;

  return new Response(buffer, {
    status: 200,
    headers: {
      "content-type":
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
      "content-disposition": `attachment; filename="${filename}"`,
      "cache-control": "no-store",
    },
  });
};
