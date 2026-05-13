/**
 * Bossa Sunningdale — Orders Webhook (Google Apps Script)
 * =======================================================
 *
 * Receives POST requests from the bar stock dashboard whenever an order is
 * sent or its status updated, and appends/updates rows in a "BossaOrders"
 * sheet of the bound Google Spreadsheet.
 *
 * The dashboard's localStorage is the source of truth — this script is a
 * best-effort sync so orders are visible in Sheets for reporting. Failures
 * are silent on the client side.
 *
 * DEPLOY INSTRUCTIONS
 * -------------------
 *   1. Create a new Google Sheet (e.g. "Bossa — Order History").
 *   2. Extensions → Apps Script. Replace the default Code.gs with this file.
 *   3. (Optional) Project Settings → tick "Show appsscript.json" if you want
 *      to lock down the timezone — default is fine.
 *   4. Click "Deploy" → "New deployment".
 *        - Type:           Web app
 *        - Description:    Bossa orders webhook v1
 *        - Execute as:     Me (your Google account)
 *        - Who has access: Anyone
 *   5. Authorise when prompted. Copy the Web App URL.
 *   6. In GitHub → Settings → Secrets and variables → Actions → New secret:
 *        - Name:  BOSSA_ORDERS_WEBHOOK
 *        - Value: <the Web App URL from step 5>
 *
 * On the next scheduled run (or manual trigger of daily_bar.yml), the
 * generated dashboard will include a <meta name="bossa-orders-webhook">
 * tag pointing here, and sent orders will land in this sheet.
 *
 * REDEPLOYING AFTER EDITS
 * ----------------------
 *   Deploy → Manage deployments → pencil icon → Version: "New version"
 *   → Deploy. The URL stays the same — no GitHub Secret update needed.
 *
 * INPUT SCHEMA
 * ------------
 *   POST body is JSON. Two actions:
 *
 *   { action: "create",
 *     id, sent_at, order_date, supplier, supplier_whatsapp,
 *     items: [{name, qty, unit, status}, ...],
 *     status, notes }
 *
 *   { action: "update", id, status?, notes? }
 *
 * RESPONSE
 * --------
 *   200 application/json:  {"ok": true,  "action": "...", "id": "..."}
 *   200 application/json:  {"ok": false, "error": "..."}
 *
 * (Apps Script web apps always return 200 — the ok field signals success.)
 */

const SHEET_NAME = "BossaOrders";
const HEADERS = [
  "id", "sent_at", "order_date", "supplier", "supplier_whatsapp",
  "item_count", "items_json", "status", "notes", "updated_at"
];

function doPost(e) {
  const lock = LockService.getScriptLock();
  try {
    lock.waitLock(10000);
  } catch (err) {
    return _json({ok: false, error: "lock timeout"});
  }

  try {
    if (!e || !e.postData || !e.postData.contents) {
      return _json({ok: false, error: "empty body"});
    }
    const payload = JSON.parse(e.postData.contents);
    const action  = payload.action || "create";
    const sheet   = _sheet();

    if (action === "create") {
      return _handleCreate(sheet, payload);
    }
    if (action === "update") {
      return _handleUpdate(sheet, payload);
    }
    return _json({ok: false, error: "unknown action: " + action});
  } catch (err) {
    return _json({ok: false, error: String(err)});
  } finally {
    lock.releaseLock();
  }
}

function doGet() {
  // Sanity-check endpoint so you can hit the URL in a browser.
  return _json({ok: true, service: "bossa-orders-webhook"});
}

function _handleCreate(sheet, p) {
  if (!p.id) {
    return _json({ok: false, error: "missing id"});
  }
  // Idempotency: if a row with this id already exists, treat as update.
  const existing = _findRowById(sheet, p.id);
  const now = new Date().toISOString();
  const items = Array.isArray(p.items) ? p.items : [];
  const row = [
    p.id,
    p.sent_at           || now,
    p.order_date        || "",
    p.supplier          || "",
    p.supplier_whatsapp || "",
    items.length,
    JSON.stringify(items),
    p.status            || "sent",
    p.notes             || "",
    now
  ];
  if (existing > 0) {
    sheet.getRange(existing, 1, 1, HEADERS.length).setValues([row]);
  } else {
    sheet.appendRow(row);
  }
  return _json({ok: true, action: "create", id: p.id});
}

function _handleUpdate(sheet, p) {
  if (!p.id) {
    return _json({ok: false, error: "missing id"});
  }
  const rowIdx = _findRowById(sheet, p.id);
  if (rowIdx <= 0) {
    return _json({ok: false, error: "id not found", id: p.id});
  }
  if (p.status !== undefined) {
    sheet.getRange(rowIdx, HEADERS.indexOf("status") + 1).setValue(p.status);
  }
  if (p.notes !== undefined) {
    sheet.getRange(rowIdx, HEADERS.indexOf("notes") + 1).setValue(p.notes);
  }
  sheet.getRange(rowIdx, HEADERS.indexOf("updated_at") + 1)
       .setValue(new Date().toISOString());
  return _json({ok: true, action: "update", id: p.id});
}

function _sheet() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  let sheet = ss.getSheetByName(SHEET_NAME);
  if (!sheet) {
    sheet = ss.insertSheet(SHEET_NAME);
    sheet.appendRow(HEADERS);
    sheet.setFrozenRows(1);
    sheet.getRange(1, 1, 1, HEADERS.length).setFontWeight("bold");
  }
  return sheet;
}

function _findRowById(sheet, id) {
  const lastRow = sheet.getLastRow();
  if (lastRow < 2) return -1;
  const ids = sheet.getRange(2, 1, lastRow - 1, 1).getValues();
  for (let i = 0; i < ids.length; i++) {
    if (String(ids[i][0]) === String(id)) {
      return i + 2;  // 1-indexed, plus header row
    }
  }
  return -1;
}

function _json(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj))
    .setMimeType(ContentService.MimeType.JSON);
}
