// ============================================================
// agent-handler — GAS Web App
// ============================================================
// Deploy this script from your Google Sheet:
//   1. Open the sheet → Extensions → Apps Script
//   2. Replace the default Code.gs content with this file
//   3. Set API_KEY below to a secret string of your choosing
//   4. Deploy → New deployment → Web app
//        Execute as: Me
//        Who has access: Anyone
//   5. Copy the deployment URL into config.toml as gas_url
//   6. Set gas_api_key in config.toml to the same API_KEY value
// ============================================================

const API_KEY = "<your-secret-key>";

function getSheet(name) {
  return SpreadsheetApp.getActiveSpreadsheet().getSheetByName(name);
}

function jsonOut(data) {
  return ContentService.createTextOutput(JSON.stringify(data))
    .setMimeType(ContentService.MimeType.JSON);
}

function checkAuth(payload) {
  return payload && payload.apiKey === API_KEY;
}

// Columns written by writeHeader and expected by agent-handler.
const HEADER_COLUMNS = [
  "id", "enabled", "host", "cli", "model", "agent", "prompt",
  "project_dir", "schedule_type", "schedule_value", "order",
  "depends_on", "output_dir", "output_format", "output_filename",
  "cli_args"
];

// ------------------------------------------------------------
// GET Handler (no auth — read-only)
//
// ?action=getTasks&sheet=<name>
//     Returns all data rows as a JSON array of objects.
//     The header row is used as keys; values are strings.
//
// ?action=isSheetEmpty&sheet=<name>
//     Returns { empty: true/false }.
//     "Empty" means no rows at all, or only a blank first row.
// ------------------------------------------------------------
function doGet(e) {
  const action    = e.parameter.action;
  const sheetName = e.parameter.sheet || "Sheet1";

  if (action === "getTasks") {
    const sheet = getSheet(sheetName);
    if (!sheet) return jsonOut({ error: "Sheet not found: " + sheetName });

    const data = sheet.getDataRange().getValues();
    if (data.length < 2) return jsonOut([]);

    const headers = data[0].map(h => String(h).trim());
    const objects = data.slice(1).map(row => {
      const obj = {};
      headers.forEach((h, i) => {
        obj[h] = row[i] !== undefined ? String(row[i]) : "";
      });
      return obj;
    });
    return jsonOut(objects);
  }

  if (action === "isSheetEmpty") {
    const sheet = getSheet(sheetName);
    if (!sheet) return jsonOut({ empty: true });
    const data = sheet.getDataRange().getValues();
    const empty = data.length === 0 ||
      (data.length === 1 && data[0].every(c => c === "" || c === null));
    return jsonOut({ empty });
  }

  return jsonOut({ error: "Unknown action" });
}

// ------------------------------------------------------------
// POST Handler (API key required)
//
// Body (JSON): { apiKey, action, sheet, ...params }
//
// Actions:
//   writeHeader   — Write the standard header row to the sheet.
//   appendRow     — { values: [...] } — Append a row.
//   updateRow     — { rowNumber, values: [...] } — Overwrite a row (1-based).
//   clearRow      — { rowNumber } — Blank a row.
//   findRowById   — { taskId } → { rowNumber } (1-based) or { rowNumber: null }.
// ------------------------------------------------------------
function doPost(e) {
  let payload;
  try {
    payload = JSON.parse(e.postData.contents);
  } catch (_) {
    return jsonOut({ success: false, error: "Invalid JSON" });
  }

  if (!checkAuth(payload))
    return jsonOut({ success: false, error: "Unauthorized" });

  const sheetName = payload.sheet || "Sheet1";

  if (payload.action === "writeHeader") {
    const ss     = SpreadsheetApp.getActiveSpreadsheet();
    const target = ss.getSheetByName(sheetName) || ss.getActiveSheet();
    target.appendRow(HEADER_COLUMNS);
    return jsonOut({ success: true });
  }

  const sheet = getSheet(sheetName);

  if (payload.action === "findRowById") {
    if (!sheet) return jsonOut({ success: false, error: "Sheet not found: " + sheetName });
    const data = sheet.getDataRange().getValues();
    for (let i = 1; i < data.length; i++) {
      if (String(data[i][0]).trim() === payload.taskId) {
        return jsonOut({ success: true, rowNumber: i + 1 });
      }
    }
    return jsonOut({ success: true, rowNumber: null });
  }

  if (payload.action === "appendRow") {
    if (!sheet) return jsonOut({ success: false, error: "Sheet not found: " + sheetName });
    sheet.appendRow(payload.values);
    return jsonOut({ success: true });
  }

  if (payload.action === "updateRow") {
    if (!sheet) return jsonOut({ success: false, error: "Sheet not found: " + sheetName });
    const row  = parseInt(payload.rowNumber, 10);
    const vals = payload.values;
    sheet.getRange(row, 1, 1, vals.length).setValues([vals]);
    return jsonOut({ success: true });
  }

  if (payload.action === "clearRow") {
    if (!sheet) return jsonOut({ success: false, error: "Sheet not found: " + sheetName });
    const row = parseInt(payload.rowNumber, 10);
    sheet.getRange(row, 1, 1, HEADER_COLUMNS.length).clearContent();
    return jsonOut({ success: true });
  }

  return jsonOut({ success: false, error: "Unknown action" });
}
