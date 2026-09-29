"use strict";

const $ = (sel) => document.querySelector(sel);

const EXAMPLES = [
  { product: "AX-9000", version: "8.1", q: "BGP peer 10.0.0.2 is stuck in Idle after the fibre was repaired. How do I reset the session without dropping routes?" },
  { product: "AX-9000", version: "7.4", q: "BGP peer 10.0.0.2 is stuck in Idle after the fibre was repaired. How do I reset the session without dropping routes?" },
  { product: "AX-9000", version: "8.1", q: "OSPF neighbor stuck in ExStart right after we upgraded one side." },
  { product: "HX-5G-gNB", version: "23.1", q: "Cell 3 is down with no other alarms. How do I restart it?" },
  { product: "HX-5G-gNB", version: "22.3", q: "Site lost PTP sync. How long before cells go down and what do I check?" },
];

const state = { catalog: { products: [] }, product: null, version: null, history: [], busy: false };

// ---------- bootstrapping ----------------------------------------------------------------

async function init() {
  checkHealth();
  try {
    state.catalog = await (await fetch("/api/catalog")).json();
  } catch {
    state.catalog = { products: [] };
  }
  renderProducts();
  renderExamples();
  $("#ask-form").addEventListener("submit", onSubmit);
  $("#question").addEventListener("keydown", (e) => {
    if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) $("#ask-form").requestSubmit();
  });
  $("#new-incident").addEventListener("click", resetIncident);
}

async function checkHealth() {
  const el = $("#health");
  try {
    const h = await (await fetch("/api/health")).json();
    const ready = h.status === "ok" && h.api_key_configured;
    el.textContent = ready ? `${h.indexed_chunks} sections indexed · ${h.chat_model}`
      : h.status !== "ok" ? "Index not built — run scripts/ingest.py" : "GEMINI_API_KEY missing";
    el.className = "health " + (ready ? "ok" : "bad");
  } catch {
    el.textContent = "API unreachable";
    el.className = "health bad";
  }
}

function renderProducts() {
  const select = $("#product");
  select.innerHTML = "";
  if (!state.catalog.products.length) {
    select.innerHTML = "<option>No documentation indexed</option>";
    select.disabled = true;
    return;
  }
  for (const p of state.catalog.products) {
    const opt = document.createElement("option");
    opt.value = p.product;
    opt.textContent = `${p.product} — ${prettyVendor(p.vendor)}`;
    select.appendChild(opt);
  }
  select.onchange = () => selectProduct(select.value);
  selectProduct(state.catalog.products[0].product);
}

function selectProduct(product, version) {
  const p = state.catalog.products.find((x) => x.product === product);
  if (!p) return;
  if (state.product && state.product !== product) resetIncident();
  state.product = product;
  $("#product").value = product;
  const wrap = $("#versions");
  wrap.innerHTML = "";
  const versions = p.versions.map((v) => v.version);
  const chosen = version && versions.includes(version) ? version : versions[versions.length - 1];
  for (const v of p.versions) {
    const b = document.createElement("button");
    b.type = "button";
    b.role = "radio";
    b.textContent = v.version;
    b.title = v.documents.join("\n");
    b.onclick = () => selectVersion(v.version);
    wrap.appendChild(b);
  }
  selectVersion(chosen);
}

function selectVersion(version) {
  if (state.version && state.version !== version && state.history.length) resetIncident();
  state.version = version;
  for (const b of $("#versions").children) b.setAttribute("aria-checked", String(b.textContent === version));
}

function renderExamples() {
  const ul = $("#examples");
  for (const ex of EXAMPLES) {
    if (!state.catalog.products.some((p) => p.product === ex.product)) continue;
    const li = document.createElement("li");
    const b = document.createElement("button");
    b.type = "button";
    b.innerHTML = `${escapeHtml(ex.q)}<small>${escapeHtml(ex.product)} · ${escapeHtml(ex.version)}</small>`;
    b.onclick = () => {
      resetIncident();
      selectProduct(ex.product, ex.version);
      $("#question").value = ex.q;
      $("#ask-form").requestSubmit();
    };
    li.appendChild(b);
    ul.appendChild(li);
  }
}

function resetIncident() {
  state.history = [];
  $("#thread").innerHTML = "";
  $("#sources").innerHTML = '<p class="muted">Cited sections appear here.</p>';
  $("#empty").hidden = false;
  $("#new-incident").hidden = true;
}

// ---------- asking -------------------------------------------------------------------------

async function onSubmit(event) {
  event.preventDefault();
  if (state.busy) return;
  const question = $("#question").value.trim();
  if (question.length < 3) return;

  const docTypes = [...document.querySelectorAll("#doc-types input:checked")].map((i) => i.value);
  const turn = addTurn(question);
  setBusy(true);
  try {
    const res = await fetch("/api/query", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        question,
        product: state.product,
        version: state.version,
        doc_types: docTypes.length === 4 ? null : docTypes,
        history: state.history.slice(-8),
      }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || `Request failed (${res.status})`);
    renderAnswer(turn, data);
    state.history.push({ role: "user", content: question });
    state.history.push({ role: "assistant", content: answerAsText(data) });
    $("#question").value = "";
    $("#new-incident").hidden = false;
  } catch (err) {
    turn.querySelector(".a").innerHTML = `<p class="error">${escapeHtml(err.message)}</p>`;
  } finally {
    setBusy(false);
  }
}

function setBusy(busy) {
  state.busy = busy;
  $("#submit").disabled = busy;
  $("#submit").textContent = busy ? "Searching…" : "Find resolution";
}

function addTurn(question) {
  $("#empty").hidden = true;
  const node = $("#tpl-turn").content.firstElementChild.cloneNode(true);
  node.querySelector(".q").textContent = question;
  node.querySelector(".summary").innerHTML = '<span class="loading">Searching the documentation…</span>';
  $("#thread").appendChild(node);
  node.scrollIntoView({ behavior: "smooth", block: "start" });
  return node;
}

function renderAnswer(turn, data) {
  const meta = turn.querySelector(".meta");
  const answered = data.status === "answered";
  meta.innerHTML = [
    `<span class="tag">${escapeHtml(data.product)} ${escapeHtml(data.version)}</span>`,
    data.version_detected ? '<span class="tag warn">version detected from question</span>' : "",
    answered ? '<span class="tag ok">grounded answer</span>' : '<span class="tag bad">no grounded answer</span>',
    `<span class="tag plain">${(data.latency_ms.total / 1000).toFixed(1)} s</span>`,
  ].join("");

  const summary = turn.querySelector(".summary");
  summary.textContent = data.summary;
  if (!answered) summary.classList.add("notfound");

  const steps = turn.querySelector(".steps");
  for (const step of data.steps) {
    const li = document.createElement("li");
    li.innerHTML = escapeHtml(step.instruction) + citeButtons(step.citations);
    if (step.command) {
      const cmd = document.createElement("div");
      cmd.className = "cmd";
      cmd.innerHTML = `<code>${escapeHtml(step.command)}</code><button type="button" class="copy">Copy</button>`;
      cmd.querySelector(".copy").onclick = (e) => copy(step.command, e.target);
      li.appendChild(cmd);
    }
    steps.appendChild(li);
  }

  const warnings = turn.querySelector(".warnings");
  for (const w of data.warnings) {
    const li = document.createElement("li");
    li.innerHTML = "⚠ " + escapeHtml(w.text) + citeButtons(w.citations);
    warnings.appendChild(li);
  }

  turn.querySelectorAll(".cite").forEach((b) => (b.onclick = () => focusSource(b.dataset.id)));
  renderSources(data.citations, answered ? null : data.retrieved);
}

function citeButtons(ids) {
  return ids.map((id) => `<button type="button" class="cite" data-id="${id}" title="Show source ${id}">${id}</button>`).join("");
}

function renderSources(citations, retrieved) {
  const box = $("#sources");
  box.innerHTML = "";
  if (!citations.length) {
    const near = (retrieved || []).slice(0, 3)
      .map((r) => `<li>${escapeHtml(r.title)} — ${escapeHtml(r.section)} <span class="muted">(${r.score})</span></li>`).join("");
    box.innerHTML = `<p class="muted">No section passed the relevance threshold for this release.</p>` +
      (near ? `<p class="muted">Closest sections found:</p><ul class="muted">${near}</ul>` : "");
    return;
  }
  for (const c of citations) {
    const el = document.createElement("div");
    el.className = "source";
    el.id = `src-${c.id}`;
    el.innerHTML = `
      <header><span class="num">[${c.id}]</span><span class="title">${escapeHtml(c.title)}</span></header>
      <div class="where">${escapeHtml(c.product)} <b>${escapeHtml(c.version)}</b> · ${escapeHtml(c.section)}<br>
        ${escapeHtml(c.source_path)} · lines ${c.line_start}–${c.line_end} · relevance ${c.score}</div>
      <pre>${escapeHtml(c.snippet)}</pre>
      ${c.url ? `<a href="${escapeAttr(c.url)}" target="_blank" rel="noopener">Open in vendor portal ↗</a>` : ""}`;
    box.appendChild(el);
  }
}

function focusSource(id) {
  const el = document.getElementById(`src-${id}`);
  if (!el) return;
  el.scrollIntoView({ behavior: "smooth", block: "nearest" });
  el.classList.add("flash");
  setTimeout(() => el.classList.remove("flash"), 1200);
}

// ---------- helpers ------------------------------------------------------------------------

function answerAsText(data) {
  const steps = data.steps.map((s, i) => `${i + 1}. ${s.instruction}${s.command ? ` (${s.command})` : ""}`);
  return [data.summary, ...steps].join("\n");
}

async function copy(text, button) {
  try {
    await navigator.clipboard.writeText(text);
    button.textContent = "Copied";
    setTimeout(() => (button.textContent = "Copy"), 1200);
  } catch {
    button.textContent = "Select & copy";
  }
}

function prettyVendor(v) {
  return v.split("-").map((w) => w[0].toUpperCase() + w.slice(1)).join(" ");
}

function escapeHtml(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function escapeAttr(s) {
  const url = String(s || "");
  return /^https?:\/\//i.test(url) ? escapeHtml(url) : "#";
}

init();
