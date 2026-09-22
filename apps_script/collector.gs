/**
 * Nghe — flag & recording collector (Google Apps Script)
 * =====================================================
 * One web app that does three jobs:
 *   1. Receives flags and recordings POSTed by the Nghe app.
 *   2. Serves a review page (open the /exec URL in a browser): a native speaker
 *      hears the AI original next to the tester's recording and clicks Approve.
 *   3. Exposes the approved-but-not-installed queue as JSON for the GitHub Action
 *      that installs recordings over the AI clips.
 *
 * SETUP: see apps_script/README.md. In short — make a Google Sheet, open
 * Extensions -> Apps Script, paste this in, set KEY below if you want one,
 * Deploy -> New deployment -> Web app -> Execute as: Me, Who has access: Anyone,
 * then paste the /exec URL into index.html's FLAG_ENDPOINT and redeploy the site.
 */

// Optional shared secret. If set, the app must send the same TESTER_KEY, and the
// review page / install queue require ?key=KEY. Leave '' to accept anything.
const KEY = '';

// Where the AI clips live, so the review page can play the original alongside.
const PAGES_BASE = 'https://councilgritter.github.io/nghe/audio';

const FLAGS = 'Flags';
const RECS = 'Recordings';
const REC_HEADERS = ['when', 'clip', 'region', 'syllable', 'by', 'mime', 'fileId', 'approved', 'installed'];
const FLAG_HEADERS = ['when', 'clip', 'region', 'syllable', 'reason'];


/* ---------- collection (POST from the app / the Action) ---------- */
function doPost(e) {
  const data = JSON.parse(e.postData.contents);
  if (KEY && data.key !== KEY) return json({ ok: false, error: 'bad key' });

  if (data.type === 'installed') {          // the Action reports what it installed
    markInstalled(data.rows || []);
    return json({ ok: true });
  }

  if (data.type === 'recording') {
    const folder = recFolder();
    const bytes = Utilities.base64Decode(data.audio);
    const ext = (data.mime || '').indexOf('mp4') >= 0 ? 'm4a' : 'webm';
    const name = `${data.clip}_${data.region}_${Date.now()}.${ext}`;
    const file = folder.createFile(Utilities.newBlob(bytes, data.mime || 'audio/webm', name));
    sheet(RECS, REC_HEADERS).appendRow(
      [data.when || new Date().toISOString(), data.clip, data.region, data.syllable,
       data.by || '', data.mime || '', file.getId(), '', '']);
    return json({ ok: true });
  }

  // otherwise it's a flag (a reason, no audio)
  sheet(FLAGS, FLAG_HEADERS).appendRow(
    [data.when || new Date().toISOString(), data.clip, data.region, data.syllable, data.reason || '']);
  return json({ ok: true });
}


/* ---------- GET: review page, install queue, one recording ---------- */
function doGet(e) {
  const p = e.parameter || {};
  if (KEY && (p.approved || p.rec) && p.key !== KEY) return json({ ok: false, error: 'bad key' });

  if (p.approved === '1') return json(approvedQueue());        // for the install Action
  if (p.rec) return json(recPayload(p.rec));                   // one recording's audio, for the Action
  return reviewPage();                                         // default: the review UI
}


/* ---------- review page (served HTML + google.script.run) ---------- */
function reviewPage() {
  return HtmlService.createHtmlOutputFromFile('review')
    .setTitle('Nghe — review recordings')
    .addMetaTag('viewport', 'width=device-width, initial-scale=1');
}

// called from review.html via google.script.run
function getPending() {
  const sh = sheet(RECS, REC_HEADERS);
  const rows = sh.getDataRange().getValues();
  const out = [];
  for (let i = 1; i < rows.length; i++) {
    const r = rows[i];
    if (r[7] !== '' ) continue;                                // already decided (approved col)
    const fileId = r[6];
    let b64 = '', mime = r[5];
    try {
      const blob = DriveApp.getFileById(fileId).getBlob();
      b64 = Utilities.base64Encode(blob.getBytes());
      mime = blob.getContentType() || mime;
    } catch (err) { b64 = ''; }
    out.push({
      row: i + 1, clip: r[1], region: r[2], syllable: r[3], by: r[4],
      aiUrl: `${PAGES_BASE}/${r[2]}/${r[1]}.mp3`,
      src: b64 ? `data:${mime};base64,${b64}` : ''
    });
  }
  return out;
}

// called from review.html: value true = approve, false = reject
function decide(row, approve) {
  sheet(RECS, REC_HEADERS).getRange(row, 8).setValue(approve ? 'TRUE' : 'REJECTED');
  return true;
}


/* ---------- install queue (for the GitHub Action) ---------- */
function approvedQueue() {
  const rows = sheet(RECS, REC_HEADERS).getDataRange().getValues();
  const out = [];
  for (let i = 1; i < rows.length; i++) {
    const r = rows[i];
    if (String(r[7]).toUpperCase() === 'TRUE' && r[8] === '') {
      out.push({ row: i + 1, clip: r[1], region: r[2], syllable: r[3] });
    }
  }
  return out;
}

function recPayload(row) {
  const r = sheet(RECS, REC_HEADERS).getRange(Number(row), 1, 1, REC_HEADERS.length).getValues()[0];
  const blob = DriveApp.getFileById(r[6]).getBlob();
  return { clip: r[1], region: r[2], mime: blob.getContentType(),
           b64: Utilities.base64Encode(blob.getBytes()) };
}

function markInstalled(rows) {
  const sh = sheet(RECS, REC_HEADERS);
  const now = new Date().toISOString();
  rows.forEach(row => sh.getRange(Number(row), 9).setValue(now));
}


/* ---------- helpers ---------- */
function sheet(name, headers) {
  const ss = SpreadsheetApp.getActive();
  let sh = ss.getSheetByName(name);
  if (!sh) { sh = ss.insertSheet(name); sh.appendRow(headers); }
  return sh;
}

function recFolder() {
  const props = PropertiesService.getScriptProperties();
  let id = props.getProperty('REC_FOLDER');
  if (id) { try { return DriveApp.getFolderById(id); } catch (e) {} }
  const folder = DriveApp.createFolder('Nghe recordings');
  props.setProperty('REC_FOLDER', folder.getId());
  return folder;
}

function json(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj))
    .setMimeType(ContentService.MimeType.JSON);
}
