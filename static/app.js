/* AP Autopilot - single-page UI. Vanilla JS, no build step, CSP-safe (no inline handlers). */
"use strict";

/* ================================================================== utilities */
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => Array.from(el.querySelectorAll(s));
const main = $("#main");
const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const money = (v, cur = "USD") => {
  if (v == null || Number.isNaN(v)) return "—";
  try { return new Intl.NumberFormat("en-US", { style: "currency", currency: cur || "USD" }).format(v); } catch { return `${Number(v).toFixed(2)} ${cur}`; }
};
const pct = (v, d = 1) => (v == null ? "—" : `${(v * 100).toFixed(d)}%`);
const dt = (iso, opts = { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }) => (iso ? new Date(iso).toLocaleString([], opts) : "");
const clock = (iso) => (iso ? new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" }) + "." + String(new Date(iso).getMilliseconds()).padStart(3, "0") : "");
function ago(iso) {
  if (!iso) return "";
  const s = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  if (s < 45) return "just now";
  if (s < 3600) return `${Math.round(s / 60)} min ago`;
  if (s < 86400) return `${Math.round(s / 3600)} h ago`;
  return dt(iso, { month: "short", day: "numeric" });
}
const secs = (ms) => (ms == null ? "" : ms < 1000 ? `${ms} ms` : `${(ms / 1000).toFixed(1)} s`);
const store = {
  get(k, d) { try { const v = localStorage.getItem("apa:" + k); return v == null ? d : JSON.parse(v); } catch { return d; } },
  set(k, v) { try { localStorage.setItem("apa:" + k, JSON.stringify(v)); } catch { /* storage unavailable */ } },
};

class ApiError extends Error { constructor(msg, status) { super(msg); this.status = status; } }
async function api(url, opts = {}) {
  let r;
  try { r = await fetch(url, opts); } catch { throw new ApiError("Can't reach the server. Check that it's running and try again.", 0); }
  if (!r.ok) {
    let m = r.statusText || "Request failed";
    try { const j = await r.json(); m = typeof j.detail === "string" ? j.detail : (j.detail?.[0]?.msg || m); } catch { /* not JSON */ }
    throw new ApiError(m, r.status);
  }
  return r.json();
}
const post = (url, body) => api(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: body ? JSON.stringify(body) : undefined });

/* ================================================================== icons */
const ICONS = {
  check: '<path d="M20 6 9 17l-5-5"/>',
  x: '<path d="M18 6 6 18M6 6l12 12"/>',
  alert: '<path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/><path d="M12 9v4M12 17h.01"/>',
  bang: '<path d="M12 5v9M12 19h.01"/>',
  info: '<circle cx="12" cy="12" r="10"/><path d="M12 16v-4M12 8h.01"/>',
  dash: '<rect x="3" y="3" width="7" height="9" rx="1"/><rect x="14" y="3" width="7" height="5" rx="1"/><rect x="14" y="12" width="7" height="9" rx="1"/><rect x="3" y="16" width="7" height="5" rx="1"/>',
  upload: '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="m17 8-5-5-5 5M12 3v12"/>',
  flag: '<path d="M4 15s1-1 4-1 5 2 8 2 4-1 4-1V3s-1 1-4 1-5-2-8-2-4 1-4 1z"/><path d="M4 22v-7"/>',
  db: '<ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M3 5v14a9 3 0 0 0 18 0V5"/><path d="M3 12a9 3 0 0 0 18 0"/>',
  book: '<path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"/><path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"/>',
  file: '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6M16 13H8M16 17H8M10 9H8"/>',
  download: '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="m7 10 5 5 5-5M12 15V3"/>',
  refresh: '<path d="M3 12a9 9 0 0 1 15-6.7L21 8"/><path d="M21 3v5h-5"/><path d="M21 12a9 9 0 0 1-15 6.7L3 16"/><path d="M8 16H3v5"/>',
  clock: '<circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/>',
  dollar: '<path d="M12 2v20M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/>',
  shield: '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>',
  play: '<path d="m6 3 14 9-14 9z"/>',
  ext: '<path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6M15 3h6v6M10 14 21 3"/>',
  chev: '<path d="m9 18 6-6-6-6"/>',
  back: '<path d="m15 18-6-6 6-6"/>',
  inbox: '<path d="M22 12h-6l-2 3h-4l-2-3H2"/><path d="M5.5 5.1 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.5-6.9A2 2 0 0 0 16.8 4H7.2a2 2 0 0 0-1.7 1.1z"/>',
  user: '<path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/>',
  printer: '<path d="M6 9V2h12v7M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2"/><rect x="6" y="14" width="12" height="8"/>',
  minus: '<path d="M5 12h14"/>',
  zap: '<path d="M13 2 3 14h9l-1 8 10-12h-9z"/>',
  search: '<circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/>',
};
const ic = (n, cls = "") => `<svg class="icon ${cls}" viewBox="0 0 24 24" aria-hidden="true">${ICONS[n] || ""}</svg>`;

/* ================================================================== domain constants */
const STAGES = [
  ["intake", "Intake & file checks"], ["read", "Read document"], ["extract", "Extract invoice data"], ["validation", "Validate data"],
  ["vendor", "Verify vendor"], ["po_match", "Match purchase order"], ["duplicates", "Detect duplicates"], ["decision", "Decision"],
];
const STAGE_LABEL = Object.fromEntries(STAGES);
const FINAL = {
  processing: ["Processing", "b-info"], approved: ["Approved", "b-ok"], approved_manual: ["Approved · manual", "b-ok"],
  in_review: ["In review", "b-warn"], awaiting_info: ["Awaiting info", "b-warn"], rejected: ["Rejected", "b-bad"],
  rejected_manual: ["Rejected · manual", "b-bad"], error: ["Error", "b-bad"],
};
const OUTCOME = { APPROVE: ["Approve", "b-ok"], REVIEW: ["Manual review", "b-warn"], REJECT: ["Reject", "b-bad"] };
const STATUS_ICON = { pass: "check", warn: "bang", review: "bang", fail: "x", info: "info", skip: "minus", skipped: "minus" };
const badge = (label, cls, plain = false) => `<span class="badge ${cls}${plain ? " plain" : ""}">${esc(label)}</span>`;
const finalBadge = (r) => {
  if (r.status === "error") return badge("Error", "b-bad");
  if (r.status !== "completed") return `<span class="badge b-info plain"><span class="spinner" style="width:10px;height:10px;border-width:1.5px"></span>${esc(r.status === "queued" ? "Queued" : STAGE_LABEL[r.current_stage] || "Processing")}</span>`;
  const [l, c] = FINAL[r.final_status] || [r.final_status, "b-mute"];
  return badge(l, c);
};

/* ================================================================== app state + shell */
const S = { health: null, stats: null, timer: null, es: null, tick: null };
function cleanup() {
  if (S.timer) clearInterval(S.timer);
  if (S.tick) clearInterval(S.tick);
  if (S.es) S.es.close();
  S.timer = S.tick = S.es = null;
}

const NAV = [
  ["dashboard", "#/", "dash", "Dashboard"],
  ["new", "#/new", "upload", "Upload"],
  ["reviews", "#/reviews", "flag", "Review queue"],
  ["reference", "#/reference", "db", "Vendors & POs"],
  ["how", "#/how", "book", "How it works"],
];
function renderNav(active) {
  $("#nav").innerHTML = NAV.map(([k, href, icon, label]) =>
    `<a href="${href}" class="${k === active ? "active" : ""}" ${k === active ? 'aria-current="page"' : ""} title="${esc(label)}">${ic(icon)}<span class="lbl">${esc(label)}</span>${k === "reviews" ? `<span class="count" id="nav-review-count">${S.stats?.open_reviews || ""}</span>` : ""}</a>`).join("");
}
function setCrumbs(parts) {
  $("#crumbs").innerHTML = parts.map((p, i) => (i === parts.length - 1 ? `<b>${esc(p[0])}</b>` : `<a href="${p[1]}">${esc(p[0])}</a>${ic("chev", "sm")}`)).join("");
  document.title = `${parts[parts.length - 1][0]} · AP Autopilot`;
}
async function refreshStats() {
  try { S.stats = await api("/api/stats"); const c = $("#nav-review-count"); if (c) c.textContent = S.stats.open_reviews || ""; } catch { /* non-critical */ }
}
async function loadHealth() {
  try {
    S.health = await api("/api/health");
    const h = S.health;
    $("#engine-status").innerHTML = h.llm
      ? `<div class="engine-pill" title="${esc(h.model)} reads each PDF; a rule-based parser cross-checks it"><span class="dot on"></span>Gemini engine</div>`
      : `<div class="engine-pill" title="Text layer / OCR + rule-based parser. Set GEMINI_API_KEY to enable Gemini."><span class="dot off"></span>Rule-based engine</div>`;
    $("#version").textContent = `v${h.version}`;
    const rb = $("#reset-btn");
    rb.hidden = !h.allow_reset;
    rb.innerHTML = `${ic("refresh", "sm")}<span>Reset demo</span>`;
  } catch {
    $("#engine-status").innerHTML = `<div class="engine-pill"><span class="dot off"></span>Offline</div>`;
    setTimeout(loadHealth, 4000);
  }
}
$("#top-upload").innerHTML = `${ic("upload")}<span class="lbl">Upload</span>`;
$("#global-search").addEventListener("submit", (e) => {
  e.preventDefault();
  Dash.search = $("#global-q").value.trim();
  Dash.filter = "all"; Dash.page = 0;
  if (location.hash === "#/" || location.hash === "") route(); else location.hash = "#/";
});
$("#reset-btn").addEventListener("click", async () => {
  const ok = await confirmModal({ title: "Reset demo data?", body: "This deletes every processing run and uploaded file, and restores the invoice ledger and PO balances to their seeded ERP history. This cannot be undone.", confirm: "Reset everything", danger: true });
  if (!ok) return;
  try { await post("/api/reset"); toast("Demo data reset", "success"); if (location.hash === "#/" || !location.hash) route(); else location.hash = "#/"; } catch (e) { toast(e.message, "error"); }
});

/* ================================================================== toast + modal */
function toast(msg, kind = "info") {
  const t = document.createElement("div");
  t.className = `toast ${kind}`;
  t.innerHTML = `${ic(kind === "error" ? "alert" : kind === "success" ? "check" : "info")}<span>${esc(msg)}</span>`;
  $("#toasts").appendChild(t);
  setTimeout(() => t.remove(), kind === "error" ? 6000 : 3500);
}
function confirmModal({ title, body, confirm = "Confirm", danger = false }) {
  return new Promise((resolve) => {
    const prev = document.activeElement;
    const root = $("#modal-root");
    root.innerHTML = `<div class="modal-back"><div class="modal" role="dialog" aria-modal="true" aria-labelledby="m-title" aria-describedby="m-body">
      <h2 id="m-title">${esc(title)}</h2><p id="m-body">${esc(body)}</p>
      <div class="row"><button class="btn" data-m="cancel">Cancel</button><button class="btn ${danger ? "danger" : "primary"}" data-m="ok">${esc(confirm)}</button></div></div></div>`;
    const close = (v) => { root.innerHTML = ""; document.removeEventListener("keydown", onKey); prev?.focus?.(); resolve(v); };
    const onKey = (e) => {
      if (e.key === "Escape") close(false);
      if (e.key === "Tab") {
        const f = $$("button", root); const i = f.indexOf(document.activeElement);
        if (e.shiftKey && i <= 0) { e.preventDefault(); f[f.length - 1].focus(); } else if (!e.shiftKey && i === f.length - 1) { e.preventDefault(); f[0].focus(); }
      }
    };
    document.addEventListener("keydown", onKey);
    $(".modal-back", root).addEventListener("click", (e) => { if (e.target.classList.contains("modal-back")) close(false); });
    $('[data-m="cancel"]', root).addEventListener("click", () => close(false));
    $('[data-m="ok"]', root).addEventListener("click", () => close(true));
    $('[data-m="ok"]', root).focus();
  });
}

/* ================================================================== shared view helpers */
const emptyState = (icon, title, text, action = "") => `<div class="empty"><div class="ill">${ic(icon, "lg")}</div><b>${esc(title)}</b>${esc(text)}${action}</div>`;
function errorState(err) {
  main.innerHTML = `<div class="panel">${emptyState("alert", err.status === 404 ? "Not found" : "Something went wrong", err.message, `<div><button class="btn" id="retry">${ic("refresh")}Try again</button></div>`)}</div>`;
  $("#retry")?.addEventListener("click", route);
}
const skeletonRows = (n = 6, cols = 6) => Array.from({ length: n }, () => `<tr>${Array.from({ length: cols }, () => `<td><div class="skel" style="height:14px;width:${50 + Math.round(Math.random() * 45)}%"></div></td>`).join("")}</tr>`).join("");

/* ================================================================== router */
async function route() {
  cleanup();
  const h = location.hash.replace(/^#/, "") || "/";
  const [, view, id] = h.split("/");
  renderNav(view === "run" ? "dashboard" : (view || "dashboard"));
  main.focus({ preventScroll: true });
  window.scrollTo(0, 0);
  try {
    if (!view) await viewDashboard();
    else if (view === "new") await viewNew();
    else if (view === "reviews") await viewReviews();
    else if (view === "run" && id) await viewRun(id);
    else if (view === "reference") await viewReference(id);
    else if (view === "how") viewHow();
    else { setCrumbs([["Not found"]]); main.innerHTML = `<div class="panel">${emptyState("file", "Page not found", "That page doesn't exist.", `<div><a class="btn" href="#/">Go to dashboard</a></div>`)}</div>`; }
  } catch (e) { errorState(e); }
  refreshStats();
}
window.addEventListener("hashchange", route);

/* ================================================================== dashboard */
const AV_COLORS = ["#2563eb", "#7c3aed", "#0891b2", "#059669", "#d97706", "#db2777", "#4f46e5", "#0d9488", "#ea580c", "#65a30d"];
function avatar(name, cls = "") {
  const n = (name || "?").replace(/\b(inc|llc|ltd|co|corp)\.?\b/gi, "").trim();
  const ini = n.split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0]).join("").toUpperCase() || "?";
  let h = 0; for (const ch of n) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
  return `<span class="av ${cls}" style="background:${AV_COLORS[h % AV_COLORS.length]}" aria-hidden="true">${esc(ini)}</span>`;
}
const PILL = {
  approved: ["Approved", "ok", "check"], approved_manual: ["Approved", "ok", "user"], in_review: ["In review", "warn", "flag"],
  awaiting_info: ["Awaiting info", "warn", "clock"], rejected: ["Rejected", "bad", "x"], rejected_manual: ["Rejected", "bad", "user"], error: ["Error", "bad", "alert"],
};
function pill(r) {
  if (r.status === "error") return `<span class="pill bad">${ic("alert")}Error</span>`;
  if (r.status !== "completed") return `<span class="pill info"><span class="spinner" style="width:11px;height:11px;border-width:1.5px"></span>${r.status === "queued" ? "Queued" : "Processing"}</span>`;
  const [l, c, i] = PILL[r.final_status] || [r.final_status, "mute", "info"];
  return `<span class="pill ${c}" ${/manual/.test(r.final_status) ? 'title="Decided by a reviewer"' : ""}>${ic(i)}${l}</span>`;
}
/* first issue from the headline, e.g. "Needs manual review - unit price above PO; amount..." -> "unit price above PO" */
function issueOf(r) {
  if (!r.headline || r.decision === "APPROVE") return null;
  const parts = r.headline.split(" - ").slice(1).join(" - ").split(/;\s*/).filter(Boolean);
  if (!parts.length) return null;
  const first = parts[0].replace(/\s*\(\+\d+ more\)$/, "");
  return { text: first.charAt(0).toUpperCase() + first.slice(1), more: parts.length - 1, kind: r.decision === "REJECT" ? "x" : "r" };
}
const issueChip = (r) => { const i = issueOf(r); return i ? `<span class="chip-issue ${i.kind}" title="${esc(r.headline)}">${esc(i.text)}</span>${i.more ? `<span class="more-n">+${i.more}</span>` : ""}` : `<span class="faint">—</span>`; };

const Dash = { filter: store.get("dashFilter", "all"), search: "", sort: { key: "seq", dir: -1 }, page: 0, size: 12, runs: [] };
async function viewDashboard() {
  setCrumbs([["Dashboard"]]);
  main.innerHTML = `
    <div class="page-head"><h1>Dashboard</h1><div class="row"><button class="btn" id="export-csv">${ic("download")}Export</button></div></div>
    <div class="grid kpis" id="kpis">${Array.from({ length: 4 }, () => `<div class="panel kpi"><div class="skel" style="width:42px;height:42px;border-radius:12px"></div><div style="flex:1"><div class="skel" style="height:11px;width:60%"></div><div class="skel" style="height:22px;width:40%;margin-top:8px"></div></div></div>`).join("")}</div>
    <div id="dash-upper"></div>
    <div class="panel"><div class="toolbar" id="dash-toolbar"></div><div class="table-wrap"><table><thead id="dash-head"></thead><tbody id="rows">${skeletonRows(6, 6)}</tbody></table></div><div class="table-foot" id="dash-foot"></div></div>`;
  $("#export-csv").addEventListener("click", exportCsv);
  const load = async () => {
    const [stats, runs] = await Promise.all([api("/api/stats"), api("/api/runs")]);
    S.stats = stats; Dash.runs = runs;
    drawKpis(stats); drawUpper(stats, runs); drawTable(false);
    const busy = runs.some((r) => !["completed", "error"].includes(r.status));
    if (busy && !S.timer) S.timer = setInterval(() => load().catch(() => {}), 2500);
    if (!busy && S.timer) { clearInterval(S.timer); S.timer = null; }
  };
  await load();
}
function drawKpis(s) {
  const k = (label, value, icon, cls) => `<div class="panel kpi ${cls}"><div class="ic2">${ic(icon)}</div><div><div class="label">${label}</div><div class="value">${value}</div></div></div>`;
  $("#kpis").innerHTML =
    k("Processed", s.completed, "file", "info") +
    k("Touchless", pct(s.touchless_rate, 0), "zap", "ok") +
    k("In review", s.open_reviews, "flag", "warn") +
    k("Value cleared", money(s.value_approved).replace(/\.00$/, ""), "dollar", "ok") +
    k("Value blocked", money(s.value_blocked).replace(/\.00$/, ""), "shield", "bad");
}
function donut(parts, total) {
  const r = 58, c = 2 * Math.PI * r;
  let off = 0;
  const segs = parts.filter((p) => p.v > 0).map((p) => {
    const len = (p.v / total) * c;
    const s = `<circle cx="74" cy="74" r="${r}" fill="none" stroke="${p.c}" stroke-width="16" stroke-dasharray="${Math.max(0, len - 2)} ${c}" stroke-dashoffset="${-off}" stroke-linecap="butt"/>`;
    off += len; return s;
  }).join("");
  return `<svg viewBox="0 0 148 148" aria-hidden="true"><circle cx="74" cy="74" r="${r}" fill="none" stroke="#eef2f6" stroke-width="16"/>${segs}</svg>`;
}
function drawUpper(s, runs) {
  const total = s.approve + s.review + s.reject;
  if (!total) { $("#dash-upper").innerHTML = ""; return; }
  const parts = [{ l: "Approved", v: s.approve, c: "#059669" }, { l: "Manual review", v: s.review, c: "#f59e0b" }, { l: "Rejected", v: s.reject, c: "#dc2626" }];
  const open = runs.filter((r) => ["in_review", "awaiting_info"].includes(r.final_status)).sort((a, b) => a.seq - b.seq).slice(0, 4);
  $("#dash-upper").innerHTML = `<div class="dash-grid">
    <div class="panel"><div class="panel-head"><h2>Decisions</h2><span class="muted" style="font-size:12.5px">avg ${secs(s.avg_ms)} per invoice</span></div>
      <div class="donut-wrap"><div class="donut" role="img" aria-label="${parts.map((p) => `${p.v} ${p.l}`).join(", ")}">${donut(parts, total)}<div class="ctr"><div><b>${total}</b><span>invoices</span></div></div></div>
        <div class="lg-list">${parts.map((p) => `<div class="lg-row"><i style="background:${p.c}"></i><span>${p.l}</span><span><b>${p.v}</b><span class="p">${pct(p.v / total, 0)}</span></span></div>`).join("")}</div></div></div>
    <div class="panel"><div class="panel-head"><h2>Needs attention</h2>${s.open_reviews ? `<a href="#/reviews" class="btn sm">View all ${s.open_reviews}</a>` : ""}</div>
      ${open.length ? `<div class="attn">${open.map((r) => { const i = issueOf(r); return `<a href="#/run/${r.id}">${avatar(r.vendor_name, "sm")}<div class="mid"><div class="t" style="white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${esc(r.vendor_name || r.filename)}</div><div class="cell-sub" style="white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${esc(i?.text || "")}</div></div><span class="amt">${money(r.total, r.currency)}</span></a>`; }).join("")}</div>`
        : emptyState("check", "All clear", "")}</div></div>`;
}
function filteredRuns() {
  let rs = Dash.runs || [];
  if (Dash.filter !== "all") rs = rs.filter((r) => r.decision === Dash.filter);
  const q = Dash.search.toLowerCase();
  if (q) rs = rs.filter((r) => [r.vendor_name, r.invoice_number, r.po_number, r.filename, r.headline].join(" ").toLowerCase().includes(q));
  const { key, dir } = Dash.sort;
  return [...rs].sort((a, b) => { const x = a[key] ?? "", y = b[key] ?? ""; return (x > y ? 1 : x < y ? -1 : 0) * dir; });
}
function drawTable(keepFocus = true) {
  const runs = Dash.runs || [];
  const count = (f) => (f === "all" ? runs.length : runs.filter((r) => r.decision === f).length);
  const hadFocus = keepFocus && document.activeElement?.id === "q";
  const pos = hadFocus ? document.activeElement.selectionStart : null;
  $("#dash-toolbar").innerHTML = `<div class="chips" role="group" aria-label="Filter">${[["all", "All"], ["APPROVE", "Approved"], ["REVIEW", "Review"], ["REJECT", "Rejected"]]
    .map(([f, l]) => `<button class="chip" data-f="${f}" aria-pressed="${Dash.filter === f}">${l}<span class="n">${count(f)}</span></button>`).join("")}</div>
    <span class="grow"></span><div class="search" style="display:block">${ic("search")}<input type="search" id="q" placeholder="Search" value="${esc(Dash.search)}" aria-label="Filter invoices"></div>`;
  const cols = [["vendor_name", "Vendor"], ["po_number", "PO"], ["total", "Amount", "num"], ["final_status", "Status"], [null, "Issue"], ["created_at", "Received", "num"]];
  $("#dash-head").innerHTML = `<tr>${cols.map(([k, l, c]) => (k
    ? `<th class="sortable ${c || ""} ${Dash.sort.key === k ? "sorted" : ""}" data-k="${k}" tabindex="0" aria-sort="${Dash.sort.key === k ? (Dash.sort.dir > 0 ? "ascending" : "descending") : "none"}">${l}<span class="arrow">${Dash.sort.key === k && Dash.sort.dir > 0 ? "▲" : "▼"}</span></th>`
    : `<th>${l}</th>`)).join("")}</tr>`;
  const rs = filteredRuns();
  const pages = Math.max(1, Math.ceil(rs.length / Dash.size));
  Dash.page = Math.min(Dash.page, pages - 1);
  const slice = rs.slice(Dash.page * Dash.size, (Dash.page + 1) * Dash.size);
  $("#rows").innerHTML = slice.length ? slice.map((r) => `
    <tr class="click" data-id="${r.id}" tabindex="0" aria-label="Open ${esc(r.vendor_name || r.filename)}">
      <td><div class="who">${avatar(r.vendor_name || r.filename)}<div style="min-width:0"><div class="nm">${esc(r.vendor_name || "Unidentified")}</div><div class="sb">${esc(r.invoice_number || "no invoice #")}</div></div></div></td>
      <td class="mono nowrap">${esc(r.po_number || "—")}</td>
      <td class="num" style="font-weight:600">${money(r.total, r.currency)}</td>
      <td>${pill(r)}</td>
      <td>${issueChip(r)}</td>
      <td class="num muted" title="${esc(dt(r.created_at))}">${ago(r.created_at)}</td>
    </tr>`).join("")
    : `<tr><td colspan="6">${runs.length ? emptyState("search", "No matches", "") : emptyState("inbox", "No invoices yet", "", `<div><a class="btn primary" href="#/new">${ic("upload")}Upload invoice</a></div>`)}</td></tr>`;
  $("#dash-foot").innerHTML = rs.length > Dash.size ? `<span>${Dash.page * Dash.size + 1}–${Math.min(rs.length, (Dash.page + 1) * Dash.size)} of ${rs.length}</span>
    <span class="row"><button class="btn sm icon-btn" id="pg-prev" aria-label="Previous page" ${Dash.page === 0 ? "disabled" : ""}>${ic("back")}</button><button class="btn sm icon-btn" id="pg-next" aria-label="Next page" ${Dash.page >= pages - 1 ? "disabled" : ""}>${ic("chev")}</button></span>` : rs.length ? `<span>${rs.length} invoice${rs.length === 1 ? "" : "s"}</span>` : "";
  $$(".chip", $("#dash-toolbar")).forEach((c) => c.addEventListener("click", () => { Dash.filter = c.dataset.f; Dash.page = 0; store.set("dashFilter", Dash.filter); drawTable(); }));
  const q = $("#q");
  q.addEventListener("input", () => { Dash.search = q.value; Dash.page = 0; drawTable(); });
  if (hadFocus) { q.focus(); q.setSelectionRange(pos, pos); }
  $$("th.sortable").forEach((th) => {
    const go = () => { const k = th.dataset.k; Dash.sort = { key: k, dir: Dash.sort.key === k ? -Dash.sort.dir : -1 }; drawTable(); };
    th.addEventListener("click", go);
    th.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); go(); } });
  });
  $$("tr.click").forEach((tr) => {
    tr.addEventListener("click", () => (location.hash = `#/run/${tr.dataset.id}`));
    tr.addEventListener("keydown", (e) => { if (e.key === "Enter") location.hash = `#/run/${tr.dataset.id}`; });
  });
  $("#pg-prev")?.addEventListener("click", () => { Dash.page--; drawTable(); });
  $("#pg-next")?.addEventListener("click", () => { Dash.page++; drawTable(); });
}
function exportCsv() {
  const rs = filteredRuns();
  if (!rs.length) { toast("Nothing to export", "error"); return; }
  const cols = ["seq", "created_at", "filename", "vendor_name", "vendor_id", "invoice_number", "po_number", "currency", "total", "decision", "final_status", "headline", "reviewed_by", "duration_ms"];
  const cell = (v) => { const s = String(v ?? ""); return /[",\n]/.test(s) || /^[=+\-@]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s; };
  const csv = [cols.join(","), ...rs.map((r) => cols.map((c) => cell(r[c])).join(","))].join("\n");
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([csv], { type: "text/csv" }));
  a.download = `ap-invoices-${new Date().toISOString().slice(0, 10)}.csv`;
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  toast(`Exported ${rs.length} invoice${rs.length === 1 ? "" : "s"}`, "success");
}

/* ================================================================== upload / process */
const EXPECT = { APPROVE: ["Approve", "ok", "check"], REVIEW: ["Review", "warn", "flag"], REJECT: ["Reject", "bad", "x"] };
async function viewNew() {
  setCrumbs([["Upload"]]);
  main.innerHTML = `<div class="page-head"><h1>Upload invoices</h1></div>
    <label class="drop compact" id="drop">
      <div class="ill">${ic("upload", "xl")}</div>
      <div><b>Drop PDFs or click to browse</b><div class="hint">Digital or scanned · up to ${S.health?.max_upload_mb || 20} MB</div></div>
      <input type="file" id="file" accept="application/pdf,.pdf" multiple class="sr-only">
    </label>
    <div class="panel queue" id="queue" hidden></div>
    <div id="library"><div class="scen-group"><div class="scen">${Array.from({ length: 6 }, () => `<div class="panel scard"><div class="skel" style="width:44px;height:44px;border-radius:12px"></div><div style="flex:1"><div class="skel" style="height:12px;width:70%"></div><div class="skel" style="height:10px;width:45%;margin-top:7px"></div></div></div>`).join("")}</div></div></div>`;
  const drop = $("#drop"), file = $("#file");
  file.addEventListener("change", () => { uploadMany([...file.files]); file.value = ""; });
  ["dragenter", "dragover"].forEach((ev) => drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.add("over"); }));
  ["dragleave", "drop"].forEach((ev) => drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.remove("over"); }));
  drop.addEventListener("drop", (e) => uploadMany([...e.dataTransfer.files]));

  const samples = await api("/api/samples");
  const groups = [["Happy path", "check"], ["Edge case", "zap"], ["Exception", "alert"]];
  $("#library").innerHTML = groups.map(([g, gi]) => {
    const items = samples.filter((s) => s.group === g);
    if (!items.length) return "";
    return `<section class="scen-group"><h2>${ic(gi, "sm")}${esc(g === "Edge case" ? "Edge cases" : g === "Exception" ? "Exceptions" : g)}</h2><div class="scen">${items.map((s) => {
      const [el, ec, ei] = EXPECT[s.expected] || ["", "mute", "info"];
      return `<article class="panel scard" title="${esc(s.description)}">
        ${avatar(s.vendor === "—" ? "?" : s.vendor, "lg")}
        <div class="mid"><div class="t">${esc(s.title)}</div><div class="v">${esc(s.vendor)}</div></div>
        <div class="acts">${el ? `<span class="pill ${ec}" title="Expected outcome">${ic(ei)}${el}</span>` : ""}
          <a class="btn sm icon-btn" href="/api/samples/${encodeURIComponent(s.name)}/file" target="_blank" rel="noopener" title="View PDF" aria-label="View PDF">${ic("ext")}</a>
          <button class="btn primary sm icon-btn" data-run="${esc(s.name)}" title="Run" aria-label="Run ${esc(s.title)}">${ic("play")}</button></div>
      </article>`; }).join("")}</div></section>`;
  }).join("");
  $$("[data-run]").forEach((b) => b.addEventListener("click", async () => {
    b.disabled = true; b.innerHTML = `<span class="spinner"></span>`;
    try { const { run_id } = await post(`/api/samples/${encodeURIComponent(b.dataset.run)}/run`); location.hash = `#/run/${run_id}`; }
    catch (e) { toast(e.message, "error"); b.disabled = false; b.innerHTML = ic("play"); }
  }));
}
function uploadOne(f, onProgress) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    const fd = new FormData(); fd.append("file", f);
    xhr.open("POST", "/api/runs");
    xhr.upload.onprogress = (e) => e.lengthComputable && onProgress(e.loaded / e.total);
    xhr.onload = () => {
      let j = {}; try { j = JSON.parse(xhr.responseText); } catch { /* ignore */ }
      if (xhr.status < 300) resolve(j); else reject(new Error(typeof j.detail === "string" ? j.detail : `Upload failed (${xhr.status})`));
    };
    xhr.onerror = () => reject(new Error("Network error"));
    xhr.send(fd);
  });
}
async function uploadMany(files) {
  if (!files.length) return;
  const maxMb = S.health?.max_upload_mb || 20;
  const q = $("#queue"); q.hidden = false;
  const items = files.map((f, i) => {
    let err = null;
    if (!/\.pdf$/i.test(f.name) && f.type !== "application/pdf") err = "Not a PDF";
    else if (f.size > maxMb * 1024 * 1024) err = `Over ${maxMb} MB`;
    else if (f.size === 0) err = "Empty file";
    return { f, i, err };
  });
  q.innerHTML = items.map((it) => `<div class="qitem" id="qi-${it.i}"><span class="qic">${it.err ? `<span style="color:var(--bad)">${ic("alert")}</span>` : `<span class="spinner" style="color:var(--brand)"></span>`}</span>
      <div><div class="name">${esc(it.f.name)}</div><div class="cell-sub" id="qs-${it.i}">${it.err ? `<span style="color:var(--bad)">${esc(it.err)}</span>` : `${Math.max(1, Math.round(it.f.size / 1024))} KB`}</div>
      ${it.err ? "" : `<div class="progress"><i id="qp-${it.i}" style="width:0%"></i></div>`}</div><span id="qa-${it.i}"></span></div>`).join("");
  const ok = [];
  for (const it of items.filter((x) => !x.err)) {
    try {
      const { run_id } = await uploadOne(it.f, (p) => { const b = $(`#qp-${it.i}`); if (b) b.style.width = `${p * 100}%`; });
      ok.push(run_id);
      $(`#qi-${it.i} .qic`).innerHTML = `<span style="color:var(--ok-strong)">${ic("check")}</span>`;
      $(`#qs-${it.i}`).textContent = "Processing";
      $(`#qa-${it.i}`).innerHTML = `<a class="btn sm" href="#/run/${run_id}">Open${ic("chev", "sm")}</a>`;
    } catch (e) {
      $(`#qi-${it.i} .qic`).innerHTML = `<span style="color:var(--bad)">${ic("alert")}</span>`;
      $(`#qs-${it.i}`).innerHTML = `<span style="color:var(--bad)">${esc(e.message)}</span>`;
    }
  }
  if (ok.length === 1 && files.length === 1) location.hash = `#/run/${ok[0]}`;
  else if (ok.length) toast(`${ok.length} invoice${ok.length === 1 ? "" : "s"} queued`, "success");
}

/* ================================================================== review queue */
async function viewReviews() {
  setCrumbs([["Review queue"]]);
  main.innerHTML = `<div class="page-head"><h1>Review queue<span class="sub-count" id="qcount"></span></h1></div>
    <div id="qlist" class="qcards">${Array.from({ length: 3 }, () => `<div class="panel" style="padding:18px"><div class="skel" style="height:14px;width:40%"></div><div class="skel" style="height:12px;width:70%;margin-top:10px"></div></div>`).join("")}</div>`;
  const runs = (await api("/api/runs")).filter((r) => ["in_review", "awaiting_info"].includes(r.final_status)).sort((a, b) => a.seq - b.seq);
  const details = await Promise.all(runs.map((r) => api(`/api/runs/${r.id}`).catch(() => r)));
  $("#qcount").textContent = details.length ? `${details.length} open` : "";
  $("#qlist").innerHTML = details.length ? details.map((r) => {
    const d = r.result?.decision || {};
    return `<a class="panel qcard" href="#/run/${r.id}">
      <div class="who">${avatar(r.vendor_name, "lg")}<div style="min-width:0"><div class="nm" style="font-size:15px">${esc(r.vendor_name || r.filename)}</div>
        <div class="row" style="gap:8px;margin-top:3px">${pill(r)}${d.queue ? `<span class="muted" style="font-size:12.5px">${ic("user", "sm")} ${esc(d.queue)}</span>` : ""}<span class="faint" style="font-size:12px">${ago(r.created_at)}</span></div></div></div>
      <div><div class="amt">${money(r.total, r.currency)}</div><div class="muted mono" style="font-size:12px;text-align:right">${esc(r.invoice_number || "")}</div></div>
      <div class="issues">${(d.reasons || []).map((x) => `<span class="issue">${esc((x.issue || x.check).replace(/^./, (c) => c.toUpperCase()))}</span>`).join("")}</div></a>`;
  }).join("") : `<div class="panel">${emptyState("check", "All clear", "No invoices waiting for review.")}</div>`;
}
/* ================================================================== run view */
let RV = null;
function newRunState(run, prevTab) {
  return { run, events: [], lastId: 0, stages: Object.fromEntries(STAGES.map(([k]) => [k, { status: "pending" }])), tab: prevTab || "extracted", stageFilter: null, decision: null, error: null };
}
function applyEvent(st, e) {
  if (e.id <= st.lastId) return;
  st.lastId = e.id; st.events.push(e);
  const s = st.stages[e.stage];
  if (e.type === "stage_start" && s) { s.status = "running"; s.started = e.ts; }
  if (e.type === "stage_done" && s) { s.status = e.status || "pass"; s.summary = e.message; s.ms = e.data?.ms; s.data = e.data || {}; s.checks = e.data?.checks || []; }
  if (e.type === "decision") st.decision = e.data;
  if (e.type === "error") st.error = e.message;
}
async function viewRun(id) {
  setCrumbs([["Dashboard", "#/"], ["Run"]]);
  main.innerHTML = `<div class="skel" style="height:26px;width:40%;margin-bottom:10px"></div><div class="skel" style="height:14px;width:30%;margin-bottom:20px"></div><div class="skel" style="height:72px;border-radius:14px;margin-bottom:16px"></div><div class="skel" style="height:140px;border-radius:14px"></div>`;
  const run = await api(`/api/runs/${id}`);
  RV = newRunState(run, RV?.run?.id === id ? RV.tab : null);
  run.events.forEach((e) => applyEvent(RV, e));
  renderRun();
  if (!["completed", "error"].includes(run.status)) {
    const es = new EventSource(`/api/runs/${id}/stream?after=${RV.lastId}`);
    S.es = es;
    es.addEventListener("step", (m) => { applyEvent(RV, JSON.parse(m.data)); renderRun(); });
    es.addEventListener("end", async () => {
      es.close(); S.es = null;
      if (S.tick) { clearInterval(S.tick); S.tick = null; }
      const full = await api(`/api/runs/${id}`);
      RV.run = full; full.events.forEach((e) => applyEvent(RV, e)); renderRun(); refreshStats();
      const d = full.result?.decision;
      if (d) toast(`${OUTCOME[d.outcome][0]} · ${d.headline}`, d.outcome === "APPROVE" ? "success" : "info");
    });
    S.tick = setInterval(() => { const el = $("#elapsed"); if (el) el.textContent = secs(Date.now() - new Date(RV.run.created_at).getTime()); }, 250);
  }
}
function renderRun() {
  const st = RV, run = st.run, res = run.result || {};
  const dec = st.decision || res.decision;
  const extract = st.stages.extract.data || {};
  const ex = res.extracted || Object.fromEntries(Object.entries(extract.fields || {}).map(([k, v]) => [k, v.value]));
  const cur = ex.currency || "USD";
  const allChecks = res.checks || Object.values(st.stages).flatMap((s) => s.checks || []);
  const fails = allChecks.filter((c) => c.status === "fail").length;
  const title = run.vendor_name || ex.vendor_name || run.filename;
  setCrumbs([["Dashboard", "#/"], [title]]);
  const focusedId = document.activeElement?.id;
  const noteDraft = $("#rv-note")?.value;
  const done = run.status === "completed";

  main.innerHTML = `
    <div class="run-head2">
      ${avatar(title, "lg")}
      <div class="ttl"><h1>${esc(title)} ${done || run.status === "error" ? pill(run) : ""}</h1>
        <div class="meta">${ex.invoice_number ? `<span class="mono">${esc(ex.invoice_number)}</span> · ` : ""}Run #${run.seq} · ${esc(ago(run.created_at))}${run.duration_ms ? ` · ${secs(run.duration_ms)}` : ""}</div></div>
      <div class="acts">
        <a class="btn icon-btn" href="/api/runs/${run.id}/document" target="_blank" rel="noopener" title="Original PDF" aria-label="Original PDF">${ic("file")}</a>
        ${done ? `<a class="btn icon-btn" href="/api/runs/${run.id}/export" title="Export JSON" aria-label="Export JSON">${ic("download")}</a><button class="btn icon-btn" id="print-btn" title="Print" aria-label="Print">${ic("printer")}</button>` : ""}
      </div>
    </div>
    ${keyFacts(run, ex, res, cur)}
    ${decisionBlock(dec, run, allChecks)}
    <div class="run-grid">
      <section class="panel" aria-label="Pipeline"><div class="panel-head"><h2>Pipeline</h2><div class="mini-steps" aria-hidden="true">${STAGES.map(([k]) => `<i class="${st.stages[k].status}"></i>`).join("")}</div></div>
        <ol class="timeline">${STAGES.map(([k, label], i) => stageRow(k, label, i)).join("")}</ol></section>
      <section class="panel" aria-label="Details">
        <div class="tabs" role="tablist" aria-label="Run details">${[["extracted", "Data"], ["po", "PO match"], ["checks", "Checks", allChecks.length ? (fails ? fails : allChecks.length) : "", fails ? "bad" : ""], ["dups", "Duplicates"], ["doc", "Document"], ["log", "Audit log", st.events.length]]
          .map(([k, l, n, c]) => `<button class="tab" role="tab" id="tab-${k}" data-tab="${k}" aria-selected="${st.tab === k}" tabindex="${st.tab === k ? 0 : -1}" aria-controls="tabpanel">${l}${n ? `<span class="n ${c || ""}">${n}</span>` : ""}</button>`).join("")}</div>
        <div class="tab-body" role="tabpanel" id="tabpanel" aria-labelledby="tab-${st.tab}">${renderTab(st.tab, { st, run, res, ex, cur, allChecks })}</div>
      </section>
    </div>`;
  bindRun();
  if (noteDraft && $("#rv-note")) $("#rv-note").value = noteDraft;
  if (focusedId) document.getElementById(focusedId)?.focus();
}
function keyFacts(run, ex, res, cur) {
  const po = res.po_match?.po?.po_number || run.po_number || ex.po_number;
  const f = (k, v, big = false) => `<div class="fact"><div class="k">${k}</div><div class="v ${big ? "big" : ""}" title="${esc(v || "")}">${v ? esc(v) : '<span class="faint">—</span>'}</div></div>`;
  const engine = run.engine ? (run.engine.startsWith("llm") ? "Gemini + parser" : "Rule-based") : "";
  const rd = res.document?.method ? res.document : RV.stages.read.data || {};
  const read = rd.method ? (rd.method === "ocr" ? `OCR · ${Math.round(rd.ocr_confidence)}%` : "Text layer") : "";
  return `<div class="panel grid facts" style="gap:0">${f("Amount", ex.total != null ? money(ex.total, cur) : "", true)}${f("Invoice date", ex.invoice_date)}${f("PO", po)}${f("Vendor ID", run.vendor_id)}${f("Read via", read)}${f("Engine", engine)}</div>`;
}
function stageRow(k, label, i) {
  const s = RV.stages[k];
  const ico = s.status === "running" ? `<span class="spinner" style="width:12px;height:12px"></span>` : s.status === "pending" ? `<span style="font-size:11px;font-weight:700">${i + 1}</span>` : ic(STATUS_ICON[s.status] || "check");
  const statusText = { pass: "passed", warn: "passed with notes", review: "needs review", fail: "failed", running: "running", pending: "pending", skipped: "skipped" }[s.status] || s.status;
  return `<li class="stage ${s.status} ${RV.stageFilter === k ? "selected" : ""} ${["pending", "running"].includes(s.status) ? "" : "done-line"}">
    <button data-stage="${k}" aria-label="${esc(label)}: ${statusText}" title="${esc(s.summary || "")}" ${RV.stageFilter === k ? 'aria-pressed="true"' : ""}>
      <span class="st-ic">${ico}</span>
      <span style="min-width:0"><span class="st-title"><span>${esc(label)}</span><span class="ms">${s.ms != null ? secs(s.ms) : s.status === "running" ? "…" : ""}</span></span>
      ${s.summary ? `<span class="st-sum" style="display:block">${esc(s.summary)}</span>` : ""}</span></button></li>`;
}
const cap = (s) => String(s || "").replace(/^./, (c) => c.toUpperCase());
function decisionBlock(dec, run, allChecks) {
  if (run.status === "error") {
    return `<section class="panel decision error"><div class="dec2"><div class="d-ic">${ic("alert")}</div><div><div class="eyebrow">Error</div><div class="headline">${esc(run.headline || RV.error || "Processing failed")}</div></div></div></section>`;
  }
  if (!dec) {
    const doneN = STAGES.filter(([k]) => !["pending", "running"].includes(RV.stages[k].status)).length;
    const curr = STAGES.find(([k]) => RV.stages[k].status === "running") || STAGES[Math.min(doneN, STAGES.length - 1)];
    return `<section class="panel decision pending" aria-live="polite"><div class="dec2"><div class="d-ic"><span class="spinner" style="width:22px;height:22px;border-width:2.5px;color:#fff"></span></div>
      <div><div class="eyebrow">Processing · ${doneN + 1 > STAGES.length ? STAGES.length : doneN + 1}/${STAGES.length}</div><div class="headline">${run.status === "queued" && !doneN ? "Queued" : esc(curr[1])}…</div></div>
      <div class="score"><b id="elapsed">${secs(Date.now() - new Date(run.created_at).getTime())}</b><span>elapsed</span></div></div>
      <div class="d-progress"><i style="width:${(doneN / STAGES.length) * 100}%"></i></div></section>`;
  }
  const icon = { APPROVE: "check", REVIEW: "bang", REJECT: "x" }[dec.outcome];
  const canReview = run.status === "completed" && ["in_review", "awaiting_info"].includes(run.final_status);
  const canOverride = run.status === "completed" && run.final_status === "rejected";
  const name = (id) => allChecks.find((c) => c.id === id)?.name || id;
  const issueRow = (dot, label, detail) => `<li><details><summary><span class="sdot ${dot}"></span><span>${esc(label)}</span>${detail ? ic("chev", "sm chev") : ""}</summary>${detail ? `<div class="detail">${esc(detail)}</div>` : ""}</details></li>`;
  const left = dec.reasons.length
    ? dec.reasons.map((r) => issueRow(r.severity, cap(r.issue || name(r.check)), r.text)).join("") + dec.notes.map((n) => issueRow("note", name(n.check), n.text)).join("")
    : issueRow("ok", `All ${dec.counts.total} checks passed`, "") + dec.notes.map((n) => issueRow("note", name(n.check), n.text)).join("");
  const acts = dec.next_actions;
  const actRow = (a) => `<div class="next">${avatar(a.owner, "sm")}<div><b style="font-size:12.5px">${esc(a.owner)}</b><div style="color:var(--ink-2);font-size:13px">${esc(a.action)}</div></div></div>`;
  return `<section class="panel decision ${dec.outcome}" aria-label="Decision">
    <div class="dec2 d-head"><div class="d-ic">${ic(icon)}</div>
      <div style="min-width:0"><div class="eyebrow">${OUTCOME[dec.outcome][0]}${dec.queue ? ` · ${esc(dec.queue)}` : ""}</div><div class="headline">${esc(dec.outcome === "APPROVE" ? `Ready for payment${(RV.run.result?.po_match?.po?.po_number) ? ` · ${RV.run.result.po_match.po.po_number}` : ""}` : cap(dec.headline.replace(/^(Needs manual review|Rejected) - /, "")))}</div></div>
      <div class="score"><b>${dec.counts.passed}/${dec.counts.total}</b><span>checks passed</span></div></div>
    <div class="issues2">
      <div><h3>${dec.reasons.length ? "Issues" : "Result"}</h3><ul class="iss">${left}</ul></div>
      <div><h3>Next step</h3>${acts.slice(0, 2).map(actRow).join("")}${acts.length > 2 ? `<details class="more"><summary>+${acts.length - 2} more</summary>${acts.slice(2).map(actRow).join("")}</details>` : ""}</div>
    </div>
    ${canReview || canOverride ? `<form class="rv-inline" id="review-form" novalidate>
      <input type="text" id="rv-note" maxlength="1000" placeholder="${canOverride ? "Reason for overriding…" : "Add a note…"}" aria-label="Review note">
      <input type="text" id="rv-name" maxlength="80" value="${esc(store.get("reviewer", "AP reviewer"))}" aria-label="Reviewer" style="width:150px">
      ${canOverride ? `<button type="button" class="btn danger" data-act="approve">Override</button>`
        : `<button type="button" class="btn ok" data-act="approve">${ic("check", "sm")}Approve</button><button type="button" class="btn danger" data-act="reject">${ic("x", "sm")}Reject</button><button type="button" class="btn" data-act="request_info" title="Request information">${ic("clock", "sm")}Hold</button>`}
      <div class="field-error" id="rv-err" hidden style="width:100%"></div>
    </form>` : ""}
    ${run.reviewed_by ? `<div class="reviewed">${ic("user")}<div><b>${esc(run.reviewed_by)}</b> · ${esc((FINAL[run.final_status] || [run.final_status])[0])} · ${esc(ago(run.reviewed_at))}${run.review_note ? `<div class="muted">“${esc(run.review_note)}”</div>` : ""}</div></div>` : ""}
  </section>`;
}
function bindRun() {
  $$(".tab").forEach((t, i, all) => {
    t.addEventListener("click", () => { RV.tab = t.dataset.tab; if (RV.tab !== "checks") RV.stageFilter = null; renderRun(); $(`#tab-${RV.tab}`)?.focus(); });
    t.addEventListener("keydown", (e) => {
      if (!["ArrowRight", "ArrowLeft", "Home", "End"].includes(e.key)) return;
      e.preventDefault();
      const idx = e.key === "Home" ? 0 : e.key === "End" ? all.length - 1 : (i + (e.key === "ArrowRight" ? 1 : -1) + all.length) % all.length;
      RV.tab = all[idx].dataset.tab; renderRun(); $(`#tab-${RV.tab}`)?.focus();
    });
  });
  $$(".stage button").forEach((b) => b.addEventListener("click", () => { RV.stageFilter = RV.stageFilter === b.dataset.stage ? null : b.dataset.stage; RV.tab = "checks"; renderRun(); }));
  $("#clear-f")?.addEventListener("click", () => { RV.stageFilter = null; renderRun(); });
  $("#print-btn")?.addEventListener("click", () => window.print());
  $$("[data-act]").forEach((b) => b.addEventListener("click", () => submitReview(b.dataset.act, b)));
  $("#review-form")?.addEventListener("submit", (e) => e.preventDefault());
  $("#rv-note")?.addEventListener("input", (e) => {
    if (!e.target.value.trim()) return;
    e.target.classList.remove("invalid");
    e.target.removeAttribute("aria-invalid");
    const er = $("#rv-err");
    if (er) er.hidden = true;
  });
}
async function submitReview(action, btn) {
  const note = $("#rv-note"), name = $("#rv-name"), err = $("#rv-err");
  err.hidden = true; note.classList.remove("invalid"); note.removeAttribute("aria-invalid");
  if (action !== "request_info" && !note.value.trim()) {
    note.classList.add("invalid"); note.setAttribute("aria-invalid", "true");
    err.textContent = "A note is required."; err.hidden = false; note.focus(); return;
  }
  const override = RV.run.final_status === "rejected";
  if (override || action === "reject") {
    const ok = await confirmModal(override
      ? { title: "Override rejection?", body: "This invoice will be approved for payment. Your note is recorded.", confirm: "Override", danger: true }
      : { title: "Reject invoice?", body: "It will be closed and not paid. Your note is recorded.", confirm: "Reject", danger: true });
    if (!ok) return;
  }
  store.set("reviewer", name.value.trim() || "AP reviewer");
  $$("[data-act]").forEach((b) => (b.disabled = true));
  btn.innerHTML = `<span class="spinner"></span>`;
  try {
    const run = await post(`/api/runs/${RV.run.id}/review`, { action, note: note.value.trim(), reviewer: name.value.trim() || "AP reviewer" });
    RV.run = { ...RV.run, ...run }; (run.events || []).forEach((e) => applyEvent(RV, e));
    note.value = "";
    renderRun(); refreshStats();
    toast({ approve: "Approved", reject: "Rejected", request_info: "On hold" }[action], "success");
  } catch (e) { toast(e.message, "error"); renderRun(); }
}

const confColor = (c) => (c >= 0.85 ? "var(--ok-strong)" : c >= 0.6 ? "var(--warn-strong)" : "var(--bad-strong)");
const CRIT = ["Invoice number", "Invoice date", "Total", "Vendor name", "Currency"];
function fieldCard(label, f, fmt = (v) => v) {
  if (!f) return "";
  const v = f.value, has = v !== null && v !== undefined && v !== "";
  const c = f.confidence ?? 0;
  return `<div class="fieldc"><div class="k"><span>${label}</span>${has ? `<span title="Confidence (${esc(f.method || "")})" style="color:${confColor(c)}">${Math.round(c * 100)}%</span>` : ""}</div>
    ${has ? `<div class="v">${esc(fmt(v))}</div><div class="conf"><i style="width:${c * 100}%;background:${confColor(c)}"></i></div>` : `<div class="v null ${CRIT.includes(label) ? "crit" : ""}">${CRIT.includes(label) ? "Missing" : "Not on document"}</div>`}
    ${f.evidence ? `<div class="ev" title="${esc(f.evidence)}">“${esc(f.evidence)}”</div>` : ""}</div>`;
}
const pending = (stage) => { const s = RV.stages[stage]; return s?.status === "skipped" ? `<div class="callout">${ic("info")}<span>Skipped: ${esc(s.summary)}</span></div>` : `<div class="muted row"><span class="spinner"></span>Waiting for this stage to run…</div>`; };
const checkRow = (c) => `<div class="check ${c.status} ${c.severity || ""}"><div class="ci">${ic(STATUS_ICON[c.status] || "check")}</div><div><div class="cn">${esc(c.name)}${c.severity ? `<span class="sev ${c.severity}">${c.severity}</span>` : ""}<span class="cid">${esc(c.id)}</span></div><div class="cm">${esc(c.message)}</div></div></div>`;
const logRow = (e) => `<div class="log-row ${e.type}"><span class="t">${clock(e.ts)}</span><span class="s">${esc(e.stage)}</span><span class="m">${["stage_done", "decision"].includes(e.type) && e.status ? `[${esc(e.status)}] ` : ""}${esc(e.message)}</span></div>`;
const tbl = (head, body, cls = "") => `<div class="table-wrap panel" style="box-shadow:none"><table class="${cls}"><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table></div>`;

function renderTab(tab, { st, run, res, cur, allChecks }) {
  if (tab === "extracted") {
    const d = st.stages.extract.data;
    if (!d || !d.fields) return pending("extract");
    const F = d.fields, yes = (v) => (v ? "Yes" : "No"), m = (v) => money(v, cur), rate = (v) => pct(v, 2);
    const items = d.line_items || [], xc = d.cross_check;
    return `<div class="section-title">Invoice</div><div class="fields">
        ${fieldCard("Document type", F.document_type, (v) => String(v).replace("_", " "))}${fieldCard("Invoice number", F.invoice_number)}${fieldCard("Invoice date", F.invoice_date)}
        ${fieldCard("PO reference (as printed)", F.po_number)}${fieldCard("Currency", F.currency)}${fieldCard("Due date", F.due_date)}
        ${F.service_period_start?.value ? fieldCard("Service period", { ...F.service_period_start, value: `${F.service_period_start.value} → ${F.service_period_end?.value}` }) : ""}</div>
      <div class="section-title">Amounts</div><div class="fields">
        ${fieldCard("Subtotal", F.subtotal, m)}${fieldCard("Tax", F.tax_amount, m)}${fieldCard("Tax rate", F.tax_rate, rate)}${fieldCard("Total", F.total, m)}${fieldCard("Prices include tax", F.tax_inclusive, yes)}</div>
      <div class="section-title">Vendor</div><div class="fields">
        ${fieldCard("Vendor name", F.vendor_name)}${fieldCard("Tax ID", F.vendor_tax_id)}${fieldCard("Email", F.vendor_email)}
        ${fieldCard("Remit-to account", F.vendor_bank_account)}${fieldCard("Bank", F.vendor_bank_name)}${fieldCard("Change-of-bank notice", F.payment_instruction_change, yes)}</div>
      <div class="section-title">Line items · ${items.length}</div>
      ${items.length ? tbl(`<th>#</th><th>Description</th><th class="num">Qty</th><th class="num">Unit price</th><th class="num">Amount</th><th>Type</th><th class="num">Conf.</th>`,
        items.map((it, i) => `<tr><td class="muted">${i + 1}</td><td>${esc(it.description)}</td><td class="num">${it.quantity ?? "—"}</td><td class="num">${money(it.unit_price, cur)}</td><td class="num">${money(it.amount, cur)}</td><td>${it.ancillary ? `<span class="tag ancillary">ancillary</span>` : it.quantity == null ? `<span class="tag bundle">lump sum</span>` : ""}</td><td class="num" style="color:${confColor(it.confidence)}">${Math.round(it.confidence * 100)}%</td></tr>`).join(""))
        : `<div class="muted">No line items could be read.</div>`}
      ${xc?.length ? `<div class="section-title">Cross-check</div>${tbl(`<th>Field</th><th>Gemini</th><th>Parser</th><th>Result</th>`,
        xc.map((c) => `<tr><td>${esc(c.field.replace(/_/g, " "))}</td><td class="mono">${esc(c.llm)}</td><td class="mono">${esc(c.parser)}</td><td>${c.agree ? badge("agree", "b-ok") : badge("differ", "b-warn")}</td></tr>`).join(""))}` : ""}`;
  }
  if (tab === "po") {
    const d = st.stages.po_match.data?.po_match || res.po_match;
    if (!d) return pending("po_match");
    const po = d.po;
    const cand = d.candidates?.length ? `<div class="section-title">Purchase orders considered</div>${tbl(`<th>PO</th><th class="num">Score</th><th class="num">Line match</th><th class="num">Amount fit</th><th class="num">Open balance</th>`,
      d.candidates.map((c, i) => `<tr><td class="mono">${esc(c.po_number)} ${i === 0 && po?.po_number === c.po_number ? badge("selected", "b-info", true) : ""}</td><td class="num"><b>${pct(c.score, 0)}</b></td><td class="num">${pct(c.line_score, 0)}</td><td class="num">${pct(c.amount_score, 0)}</td><td class="num">${money(c.remaining, cur)}</td></tr>`).join(""))}` : "";
    if (!po) return `<div class="callout warn">${ic("alert")}<span>No purchase order could be identified${d.reference ? ` for the reference “${esc(d.reference)}”` : ": the invoice carries no PO reference and no open PO for this vendor fits"}.</span></div>${cand}`;
    const p = d.position, inv = res.derived?.subtotal ?? res.extracted?.subtotal ?? 0;
    const prior = p.billed_subtotal, total = p.po_subtotal, over = Math.max(0, prior + inv - total), bad = over > (d.tolerance || 0);
    const scale = Math.max(total, prior + inv) || 1, w = (v) => `${Math.max(0, Math.min(100, (v / scale) * 100))}%`;
    return `<div class="po-head"><div><div class="pn">${esc(po.po_number)}</div><div class="muted" style="font-size:12.5px">Identified by <b>${esc(d.method)}</b> · buyer ${esc(po.buyer)} · ${esc(po.cost_center)} · issued ${esc(po.issue_date)}</div></div>
        <div class="row">${badge(po.status.replace("_", " "), po.status === "open" ? "b-ok" : "b-mute")}${po.allows_partial_invoicing ? badge("partial invoicing allowed", "b-info", true) : ""}</div></div>
      <div class="section-title">PO consumption</div>
      <div class="bar" role="img" aria-label="Previously invoiced ${money(prior, cur)}, this invoice ${money(inv, cur)}, PO value ${money(total, cur)}"><i style="width:${w(prior)};background:#94a3b8"></i><i style="width:${w(Math.min(inv, Math.max(0, total - prior)))};background:${bad ? "#f59e0b" : "var(--brand)"}"></i><i style="width:${w(over)};background:var(--bad-strong)"></i></div>
      <div class="legend"><span style="--c:#94a3b8">Previously invoiced ${money(prior, cur)}</span><span style="--c:${bad ? "#f59e0b" : "var(--brand)"}">This invoice ${money(inv, cur)}</span>${over ? `<span style="--c:var(--bad-strong)">Over PO by ${money(over, cur)}</span>` : ""}<span style="--c:#e2e8f0">PO value ${money(total, cur)} · tolerance ${money(d.tolerance, cur)}</span></div>
      <div class="section-title">Invoice vs purchase order</div>
      ${tbl(`<th>Check</th><th>Invoice</th><th>Purchase order</th><th></th>`, d.comparison.map((c) => `<tr><td>${esc(c.field)}</td><td class="mono">${esc(c.invoice ?? "")}</td><td class="mono">${esc(c.po)}</td><td class="${c.ok === true ? "ok" : c.ok === false ? "bad" : ""}">${c.ok === true ? ic("check") : c.ok === false ? ic("x") : ""}</td></tr>`).join(""), "cmp")}
      <div class="section-title">Line matching</div>
      ${tbl(`<th>Invoice line</th><th>Match</th><th>PO line</th><th class="num">Qty inv / open</th><th class="num">Price inv / PO</th><th class="num">Variance</th>`,
        d.lines.map((l) => `<tr><td>${l.invoice_line}. ${esc(l.description)}</td><td><span class="tag ${l.kind}">${l.kind}</span>${l.similarity != null ? `<div class="cell-sub">${pct(l.similarity, 0)} text match</div>` : ""}</td>
          <td>${l.po_lines.length ? `${l.po_lines.map((n) => `#${n}`).join(" + ")} ${l.po_description ? `<span class="muted">${esc(l.po_description)}</span>` : ""}` : `<span class="muted">${esc(l.note || "")}</span>`}${l.kind === "bundle" ? `<div class="cell-sub">${esc(l.note)}</div>` : ""}</td>
          <td class="num">${l.inv_qty != null ? `${l.inv_qty} / ${l.po_remaining_qty}` : "—"}</td>
          <td class="num">${l.inv_price != null ? `${money(l.inv_price, cur)} / ${money(l.po_price, cur)}` : l.kind === "bundle" ? `${money(l.amount, cur)} / ${money(l.po_value, cur)}` : money(l.amount, cur)}</td>
          <td class="num" style="${l.price_variance_pct && Math.abs(l.price_variance_pct) > 0.02 ? "color:var(--bad-strong);font-weight:700" : ""}">${l.price_variance_pct != null ? (l.price_variance_pct >= 0 ? "+" : "") + pct(l.price_variance_pct) : ""}</td></tr>`).join(""))}
      ${p.prior_invoices.length ? `<div class="section-title">Previously invoiced against this PO</div>${tbl(`<th>Invoice</th><th>Date</th><th>Service period</th><th class="num">Subtotal</th><th>Status</th><th>Source</th>`,
        p.prior_invoices.map((x) => `<tr><td class="mono">${esc(x.invoice_number)}</td><td class="nowrap">${esc(x.invoice_date)}</td><td>${esc(x.service_period || "—")}</td><td class="num">${money(x.subtotal, cur)}</td><td>${badge(x.status, x.status === "paid" ? "b-ok" : "b-info")}</td><td class="muted">${esc(x.source)}</td></tr>`).join(""))}` : ""}
      ${cand}`;
  }
  if (tab === "checks") {
    if (!allChecks.length) return pending("intake");
    const order = ["intake", "read", "extract", "validation", "vendor", "po_match", "duplicates"];
    const groups = order.filter((g) => !st.stageFilter || g === st.stageFilter).map((g) => [g, allChecks.filter((c) => c.stage === g)]).filter(([, cs]) => cs.length);
    const logs = st.stageFilter ? st.events.filter((e) => e.stage === st.stageFilter && e.type === "log") : [];
    return `${st.stageFilter ? `<div class="callout">${ic("info")}<span>Showing <b>${esc(STAGE_LABEL[st.stageFilter])}</b> only. <button class="link-btn" style="color:var(--brand-ink);padding:0;font-size:13px" id="clear-f">Show all stages</button></span></div>` : ""}
      ${groups.map(([g, cs]) => `<div class="section-title">${esc(STAGE_LABEL[g] || g)}</div><div class="checks">${cs.map(checkRow).join("")}</div>`).join("") || `<div class="muted">No checks recorded for this stage.</div>`}
      ${logs.length ? `<div class="section-title">Stage log</div><div class="log">${logs.map(logRow).join("")}</div>` : ""}`;
  }
  if (tab === "dups") {
    const d = st.stages.duplicates.data?.duplicates || res.duplicates;
    const cs = allChecks.filter((c) => c.stage === "duplicates");
    if (!d && !cs.length) return pending("duplicates");
    return `<div class="muted" style="font-size:12.5px;margin-bottom:12px">Compared with ${d ? d.compared_against : 0} earlier invoice${d?.compared_against === 1 ? "" : "s"} from this vendor</div>
      <div class="checks">${cs.map(checkRow).join("")}</div>
      ${d?.recurring_recognised?.length ? `<div class="section-title">Same amount, different service period · not duplicates</div>${tbl(`<th>Invoice</th><th>Service period</th><th class="num">Total</th>`, d.recurring_recognised.map((x) => `<tr><td class="mono">${esc(x.invoice_number)}</td><td>${esc(x.service_period)}</td><td class="num">${money(x.total, cur)}</td></tr>`).join(""))}` : ""}`;
  }
  if (tab === "doc") {
    const rd = st.stages.read.data || {};
    const text = res.document?.text || rd.text_preview || "";
    return `<div class="doc-wrap"><div><div class="section-title">Original document</div><iframe title="Invoice PDF" src="/api/runs/${run.id}/document#toolbar=0&view=FitH"></iframe></div>
      <div><div class="section-title">Extracted text ${rd.method ? `· ${rd.method === "ocr" ? `OCR, ${Math.round(rd.ocr_confidence)}% confidence` : "PDF text layer"}` : ""}</div><pre class="text">${esc(text) || "—"}</pre></div></div>`;
  }
  if (tab === "log") return st.events.length ? `<div class="log">${st.events.map(logRow).join("")}</div>` : `<div class="muted">No events yet.</div>`;
  return "";
}

/* ================================================================== reference */
async function viewReference(sub) {
  const tab = ["policy", "vendors", "pos", "ledger"].includes(sub) ? sub : "pos";
  setCrumbs([["Vendors & POs"]]);
  main.innerHTML = `<div class="page-head"><h1>Vendors &amp; POs</h1></div>
    <div class="subtabs" role="tablist">${[["pos", "Purchase orders"], ["vendors", "Vendor master"], ["ledger", "Invoice ledger"], ["policy", "AP policy"]]
      .map(([k, l]) => `<button role="tab" aria-selected="${k === tab}" data-sub="${k}">${l}</button>`).join("")}</div>
    <div id="ref-body"><div class="panel" style="padding:20px"><div class="skel" style="height:200px"></div></div></div>`;
  $$("[data-sub]").forEach((b) => b.addEventListener("click", () => (location.hash = `#/reference/${b.dataset.sub}`)));
  const ref = await api("/api/reference");
  const vname = (id) => ref.vendors.find((v) => v.vendor_id === id)?.name || id;
  const p = ref.policy;
  const body = {
    policy: () => `<div class="panel"><div class="panel-body"><div class="policy">
      ${[["PO amount tolerance", `${pct(p.amount_tolerance_pct, 0)} or ${money(p.amount_tolerance_abs)}, whichever is lower`], ["Unit price tolerance", pct(p.unit_price_tolerance_pct, 0)],
        ["Non-PO charges allowance", money(p.amount_tolerance_abs)], ["Duplicate look-back window", `${p.duplicate_fuzzy_window_days} days`], ["Invoice age limit", `${p.max_invoice_age_days} days`],
        ["Future-dated tolerance", `${p.max_future_date_days} days`], ["Low-confidence threshold", pct(p.low_confidence_threshold, 0)], ["Inferred PO", `Min. score ${pct(p.inferred_po_min_score, 0)}; buyer must confirm`],
        ["Approval routing", p.approval_routing.map((t) => `${t.max_amount ? "≤ " + money(t.max_amount) : "Above"} → ${esc(t.approver)}`).join("<br>")]]
        .map(([k, v]) => `<div class="item"><div class="k">${k}</div><div class="v">${v}</div></div>`).join("")}</div></div></div>`,
    vendors: () => `<div class="panel">${tbl(`<th>Vendor</th><th>Status</th><th>Tax ID</th><th>Email domain</th><th>Bank on file</th><th>Terms</th>`,
      ref.vendors.map((v) => `<tr><td><div class="cell-title">${esc(v.name)}</div><div class="cell-sub">${esc(v.vendor_id)} · ${esc(v.category)} · aka ${esc(v.aliases.join(", "))}</div></td>
        <td>${badge(v.status, v.status === "approved" ? "b-ok" : "b-bad")}${v.status_reason ? `<div class="cell-sub" style="max-width:260px">${esc(v.status_reason)}</div>` : ""}</td>
        <td class="mono">${esc(v.tax_id)}</td><td class="mono">${esc(v.email_domain)}</td><td>${esc(v.bank_name)} <span class="mono muted">••${esc(v.bank_account.slice(-4))}</span></td><td>${esc(v.payment_terms)}</td></tr>`).join(""))}</div>`,
    pos: () => `<div class="panel">${tbl(`<th>PO</th><th>Vendor</th><th>Status</th><th>Lines</th><th class="num">Value</th><th style="min-width:220px">Invoiced</th>`,
      ref.purchase_orders.map((po) => { const ps = po.position, used = ps.po_subtotal ? ps.billed_subtotal / ps.po_subtotal : 0; return `<tr>
        <td><div class="cell-title mono">${esc(po.po_number)}</div><div class="cell-sub">${esc(po.buyer)}</div></td><td>${esc(po.vendor_name)}</td>
        <td>${badge(po.status.replace("_", " "), po.status === "open" ? "b-ok" : "b-mute")}${po.allows_partial_invoicing ? `<div class="cell-sub">partial billing OK</div>` : ""}</td>
        <td style="font-size:12.5px">${po.lines.map((l) => `${l.qty} × ${esc(l.description)} @ ${money(l.unit_price)}`).join("<br>")}</td>
        <td class="num">${money(ps.po_subtotal)}<div class="cell-sub">+ tax ${pct(po.tax_rate, 2)}</div></td>
        <td><div class="bar" style="margin:3px 0 4px"><i style="width:${Math.min(100, used * 100)}%;background:${used > 1.0001 ? "var(--bad-strong)" : "var(--brand)"}"></i></div><span class="cell-sub">${money(ps.billed_subtotal)} invoiced · ${money(ps.remaining_subtotal)} open</span></td></tr>`; }).join(""))}</div>`,
    ledger: () => `<div class="panel">
      ${tbl(`<th>Vendor</th><th>Invoice #</th><th>Normalised</th><th>Date</th><th>PO</th><th>Service period</th><th class="num">Total</th><th>Status</th><th>Source</th>`,
      ref.ledger.map((l) => `<tr><td>${esc(vname(l.vendor_id))}</td><td class="mono">${esc(l.invoice_number || "—")}</td><td class="mono muted">${esc(l.invoice_number_norm)}</td><td class="nowrap">${esc(l.invoice_date)}</td><td class="mono">${esc(l.po_number || "—")}</td><td>${esc(l.service_period || "—")}</td><td class="num">${money(l.total)}</td><td>${badge(l.status, l.status === "paid" ? "b-ok" : "b-info")}</td><td class="muted">${l.run_id ? `<a href="#/run/${l.run_id}">${esc(l.source)}</a>` : esc(l.source)}</td></tr>`).join(""))}</div>`,
  };
  $("#ref-body").innerHTML = body[tab]();
}

/* ================================================================== how it works */
function viewHow() {
  setCrumbs([["How it works"]]);
  const node = (icon, t, s) => `<div class="node"><div class="bub">${ic(icon)}</div><b>${t}</b><span>${s}</span></div>`;
  const rule = (color, icon, t, s) => `<div class="panel rule"><div class="bub" style="background:${color}">${ic(icon)}</div><div><b>${t}</b><span>${s}</span></div></div>`;
  const ecard = (icon, t, p, out) => { const [l, c, i] = EXPECT[out]; return `<div class="panel ecard"><div class="top"><div class="bub">${ic(icon)}</div><span class="pill ${c}">${ic(i)}${l}</span></div><b>${t}</b><p>${p}</p></div>`; };
  main.innerHTML = `<div class="page-head"><h1>How it works</h1></div>
    <div class="panel" style="padding:26px 18px 22px;margin-bottom:22px"><div class="pipe">
      ${node("upload", "Intake", "PDF checks")}${node("file", "Read", "Text or OCR")}${node("zap", "Extract", "Gemini + parser")}${node("check", "Validate", "Fields & maths")}
      ${node("user", "Vendor", "Identity & status")}${node("db", "PO match", "Lines & balance")}${node("search", "Duplicates", "3-layer check")}${node("flag", "Decide", "Explained outcome")}
    </div></div>
    <div class="rules">
      ${rule("var(--ok-strong)", "check", "Approve", "Every control passed")}
      ${rule("var(--warn-strong)", "bang", "Manual review", "Any review-level issue")}
      ${rule("var(--bad-strong)", "x", "Reject", "Any reject-level issue")}
    </div>
    <h2 style="font-size:13px;text-transform:uppercase;letter-spacing:.06em;color:var(--muted);margin-bottom:10px">Designed edge cases</h2>
    <div class="ecards">
      ${ecard("file", "Scanned, no PO", "OCR, then the PO is inferred from the vendor's open POs. A buyer confirms it.", "REVIEW")}
      ${ecard("search", "Duplicate vs recurring", "A re-numbered resend is caught; a monthly invoice for a new period is not.", "REJECT")}
      ${ecard("db", "Split PO over-billing", "Prior invoices are tracked; the overrun and +21.9% rate are flagged.", "REVIEW")}
      ${ecard("shield", "Vendor impersonation", "Look-alike name, wrong tax ID, new bank: fraud hold.", "REJECT")}
    </div>`;
}

/* ================================================================== boot */
document.addEventListener("keydown", (e) => {
  if (e.key === "/" && !/input|textarea|select/i.test(document.activeElement?.tagName || "")) { e.preventDefault(); $("#global-q")?.focus(); }
});
loadHealth().then(route);
