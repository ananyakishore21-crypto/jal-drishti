"use strict";

/* Jal Drishti dashboard. Talks only to the local Jal Drishti API (no government systems). */

const $ = (sel, el = document) => el.querySelector(sel);
const $$ = (sel, el = document) => [...el.querySelectorAll(sel)];
const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const num = (v) => (v == null ? "—" : String(Number(Number(v).toFixed(3))));

// API location: ?api=http://host:port overrides; same origin when served by the backend;
// localhost:8000 when index.html is opened directly from disk.
const API_BASE = (() => {
  const fromQuery = new URLSearchParams(location.search).get("api");
  if (fromQuery) return fromQuery.replace(/\/+$/, "");
  if (window.JAL_API_BASE) return String(window.JAL_API_BASE).replace(/\/+$/, "");
  if (location.protocol === "file:") return "http://localhost:8000";
  return "";
})();

const VISARJAN_DATE = new Date("2026-10-20T00:00:00+05:30"); // Durga visarjan date from the participant guide
const SHORT = { "Dissolved oxygen": "DO", BOD: "BOD", pH: "pH", Conductivity: "Conductivity" };
const PHASE = { pre: "Before", during: "During", after: "1 week after" };

const state = { allYears: [], brief: null, lang: "en", top: 3, ghat: null, loadSeq: 0 };

/* ---------- API ---------- */

async function api(path, params = {}) {
  const qs = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v !== "" && v != null) qs.set(k, v);
  const query = qs.toString();
  const url = `${API_BASE}${path}${query ? `?${query}` : ""}`;
  let res;
  try {
    res = await fetch(url, { headers: { Accept: "application/json" } });
  } catch {
    throw new Error(`Cannot reach the Jal Drishti API at ${API_BASE || location.origin}. Is the backend running?`);
  }
  let body;
  try {
    body = await res.json();
  } catch {
    throw new Error(`Unexpected response (${res.status}) from ${path}.`);
  }
  if (!res.ok) {
    const err = body.error || (body.data && body.data.error) || {};
    throw new Error(err.message || `Request to ${path} failed (${res.status}).`);
  }
  return body;
}

/* ---------- helpers ---------- */

function showError(msg) { const b = $("#banner"); b.textContent = msg; b.hidden = false; }
function clearError() { $("#banner").hidden = true; }
function setLoading(on) {
  $("#loading").hidden = !on;
  document.body.setAttribute("aria-busy", on ? "true" : "false");
}

function currentParams() {
  const checked = $$("#f-years input:checked").map((i) => i.value);
  const params = { festival: $("#f-festival").value, phase: $("#f-phase").value };
  if (checked.length && checked.length < state.allYears.length) params.year = checked.join(",");
  return { params, noYears: checked.length === 0 };
}

function sourceLink(src) {
  if (!src || !src.page) return "—";
  const title = esc(src.report || "Source report");
  if (!src.url) return `<span title="${title}">p. ${src.page}</span>`;
  return `<a href="${esc(`${src.url}#page=${src.page}`)}" target="_blank" rel="noopener" title="${title}">p. ${src.page}</a>`;
}

function valueCell(r) {
  if (r.measurement_status === "measured") {
    return `${num(r.value)}${r.unit_assumed ? ` <span class="unit">${esc(r.unit_assumed)}*</span>` : ""}`;
  }
  if (r.measurement_status === "below_detection") {
    return `<span class="chip chip-bdl" title="Below detection limit: very low, not zero">${esc(r.value_as_printed.trim() || "BDL")}</span>`;
  }
  const printed = r.value_as_printed.trim();
  return `<span class="chip chip-missing" title="Not sampled. Not treated as clean">Missing${printed ? ` (“${esc(printed)}”)` : ""}</span>`;
}

function limitText(cmp) {
  const c = cmp && cmp.criterion;
  if (!c) return "—";
  const op = { min: "≥ ", max: "≤ ", range: "" }[c.limit_type] || "";
  return `${op}${esc(c.limit)}${c.unit ? ` ${esc(c.unit)}` : ""}`;
}

function statusChip(r) {
  const c = r.comparison || {};
  const cls = c.criterion ? c.criterion.cpcb_class : "B";
  switch (c.status) {
    case "meets": return `<span class="chip chip-ok">Meets Class ${esc(cls)}</span>`;
    case "does_not_meet": return `<span class="chip chip-fail">Outside Class ${esc(cls)}</span>`;
    case "missing": return `<span class="chip chip-missing">Not compared (missing)</span>`;
    case "not_compared": return `<span class="chip chip-bdl">Not compared (BDL)</span>`;
    default: return `<span class="chip chip-none">No limit set</span>`;
  }
}

function paramChip(p) {
  const label = SHORT[p.parameter] || p.parameter;
  const c = p.criterion;
  if (p.compared === 0) return `<span class="chip chip-missing">${esc(label)}: no readings (${p.missing} missing)</span>`;
  const unit = c.unit ? ` ${c.unit}` : "";
  const dir = c.limit_type === "min" ? `below ${num(c.lower)}${unit}`
    : c.limit_type === "max" ? `above ${num(c.upper)}${unit}`
    : `outside ${num(c.lower)}–${num(c.upper)}`;
  const missing = p.missing ? ` · ${p.missing} missing` : "";
  return `<span class="chip ${p.does_not_meet ? "chip-fail" : "chip-ok"}" title="${esc(c.description)}">` +
    `${esc(label)} ${esc(dir)}: ${p.does_not_meet} of ${p.compared}${esc(missing)}</span>`;
}

/* ---------- renderers ---------- */

function renderCountdown() {
  const days = Math.ceil((VISARJAN_DATE - new Date()) / 86400000);
  const when = "Durga visarjan: 20 October 2026";
  $("#countdown").innerHTML = days > 0
    ? `<strong>${days}</strong><span>day${days === 1 ? "" : "s"} to go</span><span>${when}</span>`
    : `<span>${when}</span>`;
}

function renderSummary(d) {
  const cov = d.coverage;
  const b = cov.missing_breakdown;
  const cards = [
    ["Ghats in view", d.scope.sites.length, `${d.scope.events.length} festival test round(s)`],
    ["Readings reported", `${cov.reported_readings} / ${cov.expected_readings}`,
      `${Math.round((cov.coverage_ratio || 0) * 100)}% of expected readings`],
    ["Missing readings", cov.missing,
      `${b.not_sampled} not sampled · ${b.no_table_for_site} no table · ${b.row_absent} not printed`],
    ["Below detection (BDL)", d.counts.below_detection, "Very low, but not zero and not missing"],
  ];
  $("#summary-cards").innerHTML = cards.map(([t, v, s]) =>
    `<div class="card"><div class="card-label">${esc(t)}</div><div class="card-value">${esc(v)}</div>` +
    `<div class="card-sub">${esc(s)}</div></div>`).join("");
  $("#headlines").innerHTML = d.headlines.length
    ? d.headlines.map((h) => `<li>${esc(h)}</li>`).join("")
    : "<li>No readings with a CPCB limit in this selection.</li>";
}

function evidenceTable(rows) {
  return `<div class="table-wrap"><table><thead><tr><th>Round</th><th>Phase</th><th>Parameter</th>` +
    `<th>Value</th><th>Limit</th><th>Explanation</th><th>Source</th></tr></thead><tbody>` +
    rows.map((r) => `<tr><td>${esc(r.festival)} ${r.year}</td><td>${esc(PHASE[r.phase])}</td>` +
      `<td>${esc(r.parameter)}</td><td>${valueCell(r)}</td><td>${limitText(r.comparison)}</td>` +
      `<td>${esc(r.comparison && r.comparison.explanation)}</td><td>${sourceLink(r.source)}</td></tr>`).join("") +
    `</tbody></table></div>`;
}

function rankCard(r) {
  const pct = r.score == null ? 0 : Math.min(100, (r.score / 2) * 100);
  let warn = "";
  if (!r.assessable) {
    warn = `<p class="warn">Not ranked: no comparable readings in this selection. This is not evidence that the water meets the criteria.</p>`;
  } else if (r.low_coverage_warning) {
    warn = `<p class="warn">Limited data: ${r.readings_compared} of ${r.readings_expected} expected readings (${esc(r.coverage_level)} coverage). ` +
      `Missing readings are not treated as clean, so this result is less certain.</p>`;
  }
  const evidence = r.evidence.length
    ? `<details class="evidence"><summary>Evidence: ${r.evidence.length} readings furthest outside the limits</summary>${evidenceTable(r.evidence)}</details>`
    : "";
  const caveats = r.caveats.length
    ? `<ul class="card-caveats">${r.caveats.map((c) => `<li>${esc(c)}</li>`).join("")}</ul>` : "";
  return `<article class="ghat-card${r.assessable ? "" : " unranked"}">
    <header>
      <div class="rank" aria-label="Rank ${r.rank ?? "none"}">${r.rank ?? "—"}</div>
      <div class="ghat-name">
        <h3>${esc(r.site)}</h3>
        <p class="hi" lang="hi">${esc(r.name_hi)}</p>
        <p class="muted small">${esc(r.water_body)} · site match: ${esc(r.site_match_confidence)}</p>
      </div>
      <div class="score" title="Score 0–2: mean points per compared reading (see 'How the ranking works')">
        <div class="score-num">${r.score == null ? "—" : num(r.score)}<small> / 2</small></div>
        <div class="bar"><span style="width:${pct}%"></span></div>
        <div class="muted small">${r.readings_outside_criteria} of ${r.readings_compared} readings outside limits</div>
      </div>
    </header>
    <div class="chips">${r.parameters.map(paramChip).join("")}</div>
    ${warn}
    <ul class="reasons">${r.reasons.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>
    ${evidence}${caveats}
    <button class="btn-secondary" data-site="${esc(r.site_id)}">All readings for this ghat</button>
  </article>`;
}

function renderMethod(m) {
  $("#method").innerHTML = `<summary>How the ranking works</summary>
    <p>${esc(m.score)}</p><p>${esc(m.phases)}</p><p>${esc(m.missing_data)}</p>
    <p>Ties are broken by: ${esc(m.tie_break.join(" → "))}.</p>
    <p>Not used in the score (no Class ${esc(m.cpcb_class)} limit): ${esc(m.not_scored.join(", "))}.</p>`;
}

function renderRankings(d, scopeLabel) {
  $("#rank-scope").textContent = scopeLabel ? `Selection: ${scopeLabel}.` : "";
  $("#rankings").innerHTML = d.rankings.length ? d.rankings.map(rankCard).join("") : "<p>No ghats in this selection.</p>";
  renderMethod(d.method);
}

function renderCoverage(d) {
  const events = d.scope.events;
  const head = events.map((e) => `<th>${esc(e.festival)} ${e.year}</th>`).join("");
  const rows = d.sites.map((s) => {
    const byKey = Object.fromEntries(s.events.map((e) => [`${e.year}-${e.festival}`, e]));
    const cells = events.map((e) => {
      const ev = byKey[`${e.year}-${e.festival}`];
      if (!ev) return `<td class="cov cov-na">—</td>`;
      const b = ev.missing_breakdown;
      const tip = `${ev.reported_readings} of ${ev.expected_readings} reported. Missing: ${b.not_sampled} not sampled, ` +
        `${b.no_table_for_site} no table, ${b.row_absent} not printed. BDL: ${ev.below_detection}.`;
      const label = ev.status === "no_table_in_report" ? "No table" : `${ev.reported_readings}/${ev.expected_readings}`;
      return `<td class="cov cov-${esc(ev.status)}" title="${esc(tip)}">${label}</td>`;
    }).join("");
    return `<tr><th scope="row"><button class="link" data-site="${esc(s.site_id)}">${esc(s.site)}</button></th>${cells}` +
      `<td>${s.reported_readings}/${s.expected_readings} (${Math.round((s.coverage_ratio || 0) * 100)}%)</td></tr>`;
  }).join("");
  $("#coverage").innerHTML = `<div class="table-wrap"><table><thead><tr><th>Ghat</th>${head}<th>Total</th></tr></thead>` +
    `<tbody>${rows}</tbody></table></div>`;
}

function renderBrief() {
  const b = state.brief;
  if (!b) return;
  const part = b[state.lang];
  $("#brief-title").textContent = part.title;
  const body = $("#brief-body");
  body.lang = state.lang;
  body.innerHTML = part.lines.map((l) => `<p>${esc(l)}</p>`).join("");
  $$(".tab").forEach((t) => t.setAttribute("aria-selected", String(t.dataset.lang === state.lang)));
}

function renderCaveats(list) {
  $("#caveats").innerHTML = [...new Set(list)].map((c) => `<li>${esc(c)}</li>`).join("");
}

/* ---------- ghat detail dialog ---------- */

async function openGhat(siteId) {
  const dlg = $("#ghat-dialog");
  const { params } = currentParams();
  $("#ghat-title").textContent = "Loading…";
  $("#ghat-body").innerHTML = "<p>Loading readings…</p>";
  if (!dlg.open) dlg.showModal();
  try {
    const res = await api(`/api/ghats/${encodeURIComponent(siteId)}/readings`, params);
    renderGhat(res.data);
  } catch (e) {
    $("#ghat-title").textContent = "Could not load ghat";
    $("#ghat-body").innerHTML = `<p class="banner">${esc(e.message)}</p>`;
  }
}

function renderGhat(d) {
  state.ghat = d;
  const g = d.ghat;
  const a = d.assessment;
  const params = [...new Set(d.readings.map((r) => r.parameter))];
  $("#ghat-title").textContent = g.site;
  $("#ghat-body").innerHTML = `
    <p class="hi" lang="hi">${esc(g.name_hi)}</p>
    <p class="muted small">${esc(g.water_body)} · site match: ${esc(g.site_match_confidence)} ·
      printed in reports as: ${g.names_as_printed.map(esc).join(" | ")}</p>
    ${g.caveats.length ? `<ul class="card-caveats">${g.caveats.map((c) => `<li>${esc(c)}</li>`).join("")}</ul>` : ""}
    ${a ? `<h3>Against CPCB Class B (this selection)</h3>
      <div class="chips">${a.parameters.map(paramChip).join("")}</div>
      <ul class="reasons">${a.reasons.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>` : ""}
    <h3>Coverage by test round</h3>
    <div class="chips">${d.coverage.events.map((e) =>
      `<span class="chip cov-${esc(e.status)}">${esc(e.festival)} ${e.year}: ${e.status === "no_table_in_report"
        ? "no table in report" : `${e.reported_readings}/${e.expected_readings} reported`}</span>`).join("")}</div>
    <h3>Readings</h3>
    <div class="dialog-filters">
      <label>Parameter
        <select id="g-param"><option value="">All parameters</option>
          ${params.map((p) => `<option value="${esc(p)}">${esc(p)}</option>`).join("")}</select>
      </label>
      <label class="chk"><input type="checkbox" id="g-flagged"> Only readings outside limits or missing</label>
    </div>
    <div id="g-table"></div>
    <p class="muted small">* Units are assumed because the reports print none. BDL = below detection limit (very low, not zero).</p>`;
  $("#g-param").addEventListener("change", renderGhatTable);
  $("#g-flagged").addEventListener("change", renderGhatTable);
  renderGhatTable();
}

function renderGhatTable() {
  const d = state.ghat;
  if (!d) return;
  const p = $("#g-param").value;
  const flagged = $("#g-flagged").checked;
  const rows = d.readings.filter((r) => (!p || r.parameter === p) &&
    (!flagged || r.measurement_status === "missing" || (r.comparison && r.comparison.status === "does_not_meet")));
  $("#g-table").innerHTML = rows.length
    ? `<div class="table-wrap"><table><thead><tr><th>Round</th><th>Phase</th><th>Parameter</th><th>Value</th>` +
      `<th>Status</th><th>Explanation</th><th>Source</th></tr></thead><tbody>` +
      rows.map((r) => `<tr><td>${esc(r.festival)} ${r.year}</td><td>${esc(PHASE[r.phase])}</td>` +
        `<td>${esc(r.parameter)}${r.parameter_as_printed && r.parameter_as_printed !== r.parameter
          ? ` <span class="unit">(${esc(r.parameter_as_printed)})</span>` : ""}</td>` +
        `<td>${valueCell(r)}</td><td>${statusChip(r)}</td>` +
        `<td>${esc(r.comparison && r.comparison.explanation)}</td><td>${sourceLink(r.source)}</td></tr>`).join("") +
      `</tbody></table></div>`
    : "<p>No readings match these filters.</p>";
}

/* ---------- actions ---------- */

async function copyText(text, buttonSel) {
  if (!text) return;
  const btn = $(buttonSel);
  const original = btn.textContent;
  try {
    await navigator.clipboard.writeText(text);
  } catch {
    const ta = document.createElement("textarea");
    ta.value = text;
    document.body.appendChild(ta);
    ta.select();
    document.execCommand("copy");
    ta.remove();
  }
  btn.textContent = "Copied ✓";
  setTimeout(() => { btn.textContent = original; }, 1500);
}

function downloadBrief() {
  const b = state.brief;
  if (!b) return;
  const text = `${b.en.text}\n\n${b.hi.text}\n`;
  const url = URL.createObjectURL(new Blob([text], { type: "text/plain;charset=utf-8" }));
  const a = document.createElement("a");
  a.href = url;
  a.download = `jal-drishti-brief-${new Date().toISOString().slice(0, 10)}.txt`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

/* ---------- loading ---------- */

async function load() {
  const { params, noYears } = currentParams();
  if (noYears) { showError("Select at least one year."); return; }
  clearError();
  const seq = ++state.loadSeq;
  setLoading(true);
  try {
    const [summary, rankings, coverage, brief] = await Promise.all([
      api("/api/summary", params),
      api("/api/rankings", params),
      api("/api/coverage", params),
      api("/api/brief", { ...params, top: state.top }),
    ]);
    if (seq !== state.loadSeq) return; // a newer filter change is in flight
    state.brief = brief.data;
    renderSummary(summary.data);
    renderRankings(rankings.data, brief.data.scope.label_en);
    renderCoverage(coverage.data);
    renderBrief();
    renderCaveats(rankings.meta.caveats);
  } catch (e) {
    if (seq === state.loadSeq) showError(e.message);
  } finally {
    if (seq === state.loadSeq) setLoading(false);
  }
}

async function loadBrief() {
  const { params, noYears } = currentParams();
  if (noYears) return;
  try {
    const b = await api("/api/brief", { ...params, top: state.top });
    state.brief = b.data;
    renderBrief();
  } catch (e) {
    showError(e.message);
  }
}

function bindEvents() {
  $("#f-festival").addEventListener("change", load);
  $("#f-phase").addEventListener("change", load);
  $("#brief-top").addEventListener("change", (e) => { state.top = Number(e.target.value); loadBrief(); });
  $$(".tab").forEach((t) => t.addEventListener("click", () => { state.lang = t.dataset.lang; renderBrief(); }));
  $("#copy-brief").addEventListener("click", () => copyText(state.brief && state.brief[state.lang].text, "#copy-brief"));
  $("#copy-both").addEventListener("click", () =>
    state.brief && copyText(`${state.brief.en.text}\n\n${state.brief.hi.text}`, "#copy-both"));
  $("#download-brief").addEventListener("click", downloadBrief);
  const dlg = $("#ghat-dialog");
  $("#ghat-close").addEventListener("click", () => dlg.close());
  dlg.addEventListener("click", (e) => { if (e.target === dlg) dlg.close(); });
  document.addEventListener("click", (e) => {
    const btn = e.target.closest("[data-site]");
    if (btn) openGhat(btn.dataset.site);
  });
}

async function init() {
  renderCountdown();
  bindEvents();
  try {
    const health = await api("/api/health");
    state.allYears = [...new Set(health.data.events.map((e) => e.year))].sort();
    $("#f-years").innerHTML = state.allYears.map((y) =>
      `<label class="chk"><input type="checkbox" value="${y}" checked> ${y}</label>`).join("");
    $("#f-years").addEventListener("change", load);
  } catch (e) {
    showError(e.message);
    return;
  }
  load();
}

document.addEventListener("DOMContentLoaded", init);
