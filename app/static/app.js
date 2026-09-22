"use strict";

const $ = (id) => document.getElementById(id);
const labels = {CLIENT:"Person",EMAIL:"Email",PHONE:"Phone",ADDRESS:"Address",SSN:"SSN",ACCOUNT:"Account",AMOUNT:"Amount"};
let current = null, busy = false, ready = false, devViewer = false, noticeTimer, fileBuffer = null;
const verified = new Set();
const messages = {
  session_required:"Your session expired. Refresh the page and process the document again.",
  txt_only:"Only TXT files are supported.",
  utf8_required:"Please use a UTF-8 encoded file.",
  document_too_large:"This document exceeds the size limit.",
  invalid_document_or_too_many_entities:"Enter 1–100,000 characters with no more than 2,000 detected spans.",
  expected_text_only:"The document format is invalid.",
  document_not_found:"Document not found or unavailable to this session.",
  outbound_blocked_or_unavailable:"Request blocked or local receiver unavailable. No original-text fallback was sent."
};

async function api(path, options = {}) {
  const response = await fetch(path, {...options, credentials:"same-origin", cache:"no-store",
    headers:{"X-Privacy-Wall":"1",...(options.headers || {})}});
  const data = await response.json();
  if (!response.ok) throw new Error(messages[data.detail] || "Request failed: " + (data.detail || response.status));
  return data;
}
function notify(message, error = false) {
  clearTimeout(noticeTimer);
  $("notice").textContent = message;
  $("notice").className = error ? "error" : "";
  $("notice").hidden = false;
  noticeTimer = setTimeout(() => $("notice").hidden = true, 4500);
}
function updateButtons() {
  $("mask-button").disabled = !ready || busy || !$("source").value.trim();
  for (const id of ["masked-tab","restore-button","copy-button","complete-button","embed-button","delete-button"]) {
    $(id).disabled = busy || !current;
  }
  for (const button of document.querySelectorAll("[data-sample]")) button.disabled = busy || !ready;
  $("file-input").disabled = busy || !ready;
  $("source").disabled = busy;
  $("mask-button").setAttribute("aria-busy", String(busy));
}
async function task(action) {
  if (busy) return;
  busy = true;
  updateButtons();
  try { await action(); }
  catch (error) { notify(error.message, true); }
  finally { busy = false; updateButtons(); }
}
function inputChanged() {
  $("char-count").textContent = Array.from($("source").value).length.toLocaleString() + " / 100,000";
  fileBuffer = null;
  if (current) $("result-note").textContent = "Input changed. This is the previous result; mask again to update.";
  updateButtons();
}
function renderText(text, spans, original = false) {
  // Offsets are code points. Source content is always rendered as text, never HTML.
  const chars = Array.from(text), fragment = document.createDocumentFragment();
  let cursor = 0;
  for (const span of spans) {
    const start = original ? span.start : span.masked_start;
    const end = original ? span.end : span.masked_end;
    fragment.append(document.createTextNode(chars.slice(cursor, start).join("")));
    const mark = document.createElement("mark");
    mark.textContent = chars.slice(start, end).join("");
    mark.dataset.kind = span.kind;
    mark.title = (labels[span.kind] || "Source placeholder") + " · " + span.token + " · " + span.source;
    fragment.append(mark);
    cursor = end;
  }
  fragment.append(document.createTextNode(chars.slice(cursor).join("")));
  $("result").replaceChildren(fragment);
  $("result").hidden = false;
  $("empty-state").hidden = true;
  $("masked-tab").classList.toggle("active", !original);
  $("restore-button").classList.toggle("active", original);
  $("result-tag").textContent = original ? "Original · Session only" : "Masked";
}
function resetWire() {
  verified.clear();
  $("metric-wire").textContent = "Not checked";
  $("metric-wire-note").textContent = "Local HTTP receiver";
  $("wire-status").className = "wire-status";
  $("wire-status").textContent = "No requests sent yet. This is a local mock service, not an AI model.";
  $("payload-details").hidden = true;
  $("payload").textContent = "";
  $("payload-hash").textContent = "";
}
function showDocument(doc) {
  current = doc;
  resetWire();
  renderText(doc.masked_text, doc.spans);
  $("metric-total").textContent = Object.values(doc.counts).reduce((sum,n) => sum+n,0);
  $("metric-types").textContent = Object.keys(doc.counts).length + " / 7";
  $("metric-time").textContent = doc.elapsed_ms + " ms";
  $("legend").replaceChildren(...Object.entries(labels).map(([kind,label]) => {
    const item = document.createElement("span");
    item.textContent = label + " " + (doc.counts[kind] || 0);
    return item;
  }));
  $("result-note").textContent = "Encrypted mapping · Session-authorized restore";
}
async function selectFile(file) {
  if (!file) return;
  if (!file.name.toLowerCase().endsWith(".txt")) throw new Error(messages.txt_only);
  if (file.size > 400000) throw new Error(messages.document_too_large);
  const buffer = await file.arrayBuffer();
  let text;
  try { text = new TextDecoder("utf-8", {fatal:true}).decode(buffer); }
  catch { throw new Error(messages.utf8_required); }
  if (Array.from(text).length > 100000) throw new Error(messages.document_too_large);
  $("source").value = text;
  inputChanged();
  fileBuffer = buffer;
  for (const button of document.querySelectorAll("[data-sample]")) button.classList.remove("selected");
  notify("TXT loaded. Select Mask document to process it. File names are not transmitted.");
}
$("source").addEventListener("input", inputChanged);
$("file-input").addEventListener("change", (event) => task(() => selectFile(event.target.files[0])));
$("drop-zone").addEventListener("dragover", (event) => {event.preventDefault(); $("drop-zone").classList.add("drag");});
$("drop-zone").addEventListener("dragleave", () => $("drop-zone").classList.remove("drag"));
$("drop-zone").addEventListener("drop", (event) => {
  event.preventDefault(); $("drop-zone").classList.remove("drag");
  task(() => selectFile(event.dataTransfer.files[0]));
});
for (const button of document.querySelectorAll("[data-sample]")) {
  button.addEventListener("click", () => task(async () => {
    const data = await api("/api/samples/" + button.dataset.sample);
    $("source").value = data.text;
    inputChanged();
    for (const other of document.querySelectorAll("[data-sample]")) other.classList.toggle("selected", other === button);
  }));
}
$("mask-button").addEventListener("click", () => task(async () => {
  if (Array.from($("source").value).length > 100000) throw new Error(messages.document_too_large);
  const doc = fileBuffer
    ? await api("/api/documents/upload", {method:"POST",headers:{"Content-Type":"application/octet-stream","X-File-Extension":".txt"},body:fileBuffer})
    : await api("/api/documents", {method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({text:$("source").value})});
  const previous = current;
  showDocument(doc);
  if (previous) await api("/api/documents/" + previous.document_id, {method:"DELETE"});
  notify("Document masked. Review the output, then verify an outbound request.");
}));
$("masked-tab").addEventListener("click", () => {
  if (current) renderText(current.masked_text,current.spans);
});
$("restore-button").addEventListener("click", () => task(async () => {
  const result = await api("/api/documents/" + current.document_id + "/restore", {method:"POST"});
  renderText(result.text,result.spans,true);
}));
$("copy-button").addEventListener("click", () => task(async () => {
  await navigator.clipboard.writeText(current.masked_text);
  notify("Masked text copied to clipboard.");
}));
for (const operation of ["complete","embed"]) {
  $(operation + "-button").addEventListener("click", () => task(async () => {
    $("wire-status").textContent = "Sending to the local receiver and verifying the request…";
    try {
      const result = await api("/api/documents/" + current.document_id + "/send/" + operation, {method:"POST"});
      verified.add(operation);
      $("metric-wire").textContent = verified.size + " / 2 verified";
      $("metric-wire-note").textContent = "Detected entities only";
      $("wire-status").className = "wire-status success";
      $("wire-status").textContent = (operation === "complete" ? "Completion" : "Embedding") +
        " verified · " + result.body_bytes + " bytes · " + result.transport + " · " +
        result.checked_entity_count + " detected occurrences checked. No known raw values found.";
      $("payload-details").hidden = !devViewer;
      if (devViewer) {
        $("payload").textContent = result.serialized_body;
        $("payload-hash").textContent = "SHA-256 · " + result.body_sha256;
        $("payload-details").open = true;
      } else $("wire-status").textContent += " Payload viewer is disabled.";
    } catch (error) {
      verified.delete(operation);
      $("metric-wire").textContent = verified.size + " / 2 verified";
      $("payload-details").hidden = true;
      $("wire-status").className = "wire-status error";
      $("wire-status").textContent = error.message;
      throw error;
    }
  }));
}
$("delete-button").addEventListener("click", () => task(async () => {
  await api("/api/documents/" + current.document_id, {method:"DELETE"});
  current=null; fileBuffer=null;
  $("source").value=""; $("file-input").value="";
  inputChanged();
  $("result").replaceChildren(); $("result").hidden=true; $("empty-state").hidden=false;
  $("metric-total").textContent="—"; $("metric-types").textContent="— / 7";
  $("metric-time").textContent="—"; $("result-tag").textContent="Awaiting input";
  $("result-note").textContent="Current document deleted";
  $("legend").replaceChildren();
  resetWire();
  notify("Document and encrypted mapping deleted.");
}));
for (const link of document.querySelectorAll(".nav-link")) {
  link.addEventListener("click", () => {
    for (const other of document.querySelectorAll(".nav-link")) other.classList.toggle("active", other === link);
  });
}
api("/api/session", {method:"POST"}).then(data => {
  ready=true; devViewer=data.dev_viewer; updateButtons();
}).catch(error => notify(error.message,true));
