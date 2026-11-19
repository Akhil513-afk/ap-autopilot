"""Record the 5-minute product demo as a silent screen video (voice-over is added afterwards).

Drives the real app in Google Chrome with Playwright, shows a visible cursor and a scene caption,
and writes demo/timeline.json with the exact second each scene starts, so the narration script can
be timed against the actual recording.

    # app must be running on :8000 (./run.sh)
    .venv/bin/python scripts/record_demo.py
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "demo"
BASE = "http://localhost:8000"
W, H = 1600, 900
FFMPEG_CANDIDATES = [shutil.which("ffmpeg"),
                     "/opt/anaconda3/lib/python3.13/site-packages/imageio_ffmpeg/binaries/ffmpeg-macos-aarch64-v9.0"]

# Visible cursor + click ripple + scene caption, injected into every page (recordings show no OS cursor).
OVERLAY_JS = r"""
(() => {
  const css = `
  #__cur{position:fixed;left:0;top:0;width:22px;height:22px;z-index:2147483647;pointer-events:none;transform:translate(-3px,-2px);transition:transform .05s}
  #__cur svg{width:22px;height:22px;filter:drop-shadow(0 2px 3px rgba(0,0,0,.35))}
  .__rip{position:fixed;width:34px;height:34px;margin:-17px 0 0 -17px;border-radius:50%;border:3px solid rgba(37,99,235,.85);z-index:2147483646;pointer-events:none;animation:__r .55s ease-out forwards}
  @keyframes __r{from{transform:scale(.3);opacity:1}to{transform:scale(1.6);opacity:0}}
  #__cap{position:fixed;top:13px;left:50%;transform:translateX(-50%);z-index:2147483645;pointer-events:none;background:#0b1220;color:#fff;
    font:600 14px Inter,-apple-system,sans-serif;padding:8px 16px;border-radius:999px;box-shadow:0 6px 20px rgba(0,0,0,.25);display:flex;gap:10px;align-items:center;opacity:0;transition:opacity .35s}
  #__cap b{background:#2563eb;border-radius:999px;padding:2px 9px;font-size:12px;letter-spacing:.03em}`;
  const boot = () => {
    if (document.getElementById('__cur')) return;
    const st = document.createElement('style'); st.textContent = css; document.head.appendChild(st);
    const c = document.createElement('div'); c.id = '__cur';
    c.innerHTML = '<svg viewBox="0 0 24 24"><path d="M4 2l16 9.5-7 1.6-3.6 6.9z" fill="#fff" stroke="#0b1220" stroke-width="1.6" stroke-linejoin="round"/></svg>';
    document.body.appendChild(c);
    const cap = document.createElement('div'); cap.id = '__cap'; document.body.appendChild(cap);
    document.addEventListener('mousemove', e => { c.style.left = e.clientX + 'px'; c.style.top = e.clientY + 'px'; }, true);
    document.addEventListener('mousedown', e => { const r = document.createElement('div'); r.className = '__rip'; r.style.left = e.clientX + 'px'; r.style.top = e.clientY + 'px'; document.body.appendChild(r); setTimeout(() => r.remove(), 600); }, true);
    window.__caption = (tag, text) => { cap.innerHTML = (tag ? '<b>' + tag + '</b>' : '') + '<span>' + text + '</span>'; cap.style.opacity = text ? 1 : 0; };
  };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot); else boot();
})();
"""


class Demo:
    def __init__(self, page):
        self.p = page
        self.t0 = time.monotonic()
        self.x, self.y = W / 2, H / 2
        self.timeline: list[dict] = []

    # -- timing ------------------------------------------------------------------------------
    def now(self) -> float:
        return round(time.monotonic() - self.t0, 1)

    def mark(self, key: str, label: str):
        self.timeline.append({"t": self.now(), "key": key, "label": label})
        print(f"  [{self.now():6.1f}s] {key}: {label}")

    def hold(self, s: float):
        time.sleep(s)

    def caption(self, tag: str, text: str):
        self.p.evaluate("([t, x]) => window.__caption && window.__caption(t, x)", [tag, text])

    # -- pointer -----------------------------------------------------------------------------
    def move_to(self, x: float, y: float, dur: float = 0.6):
        steps = max(8, int(dur * 40))
        for i in range(1, steps + 1):
            k = i / steps
            k = k * k * (3 - 2 * k)  # ease in-out
            self.p.mouse.move(self.x + (x - self.x) * k, self.y + (y - self.y) * k)
            time.sleep(dur / steps)
        self.x, self.y = x, y

    def point(self, selector_or_locator, dur: float = 0.6, dx: float = 0.5, dy: float = 0.5):
        loc = self.p.locator(selector_or_locator).first if isinstance(selector_or_locator, str) else selector_or_locator
        loc.scroll_into_view_if_needed()
        b = loc.bounding_box()
        self.move_to(b["x"] + b["width"] * dx, b["y"] + b["height"] * dy, dur)
        return loc

    def click(self, sel, dur: float = 0.6, pause: float = 0.25):
        self.point(sel, dur)
        time.sleep(pause)
        self.p.mouse.down(); time.sleep(0.06); self.p.mouse.up()
        time.sleep(0.35)

    def scroll(self, dy: int, dur: float = 1.2):
        steps = max(6, int(dur * 30))
        for _ in range(steps):
            self.p.mouse.wheel(0, dy / steps)
            time.sleep(dur / steps)

    def scroll_top(self):
        self.p.evaluate("window.scrollTo({top: 0, behavior: 'smooth'})")
        time.sleep(0.7)

    # -- app helpers -------------------------------------------------------------------------
    def nav(self, href: str):
        self.click(f'#nav a[href="{href}"]', dur=0.7)
        time.sleep(0.6)

    def run_sample(self, name: str):
        self.nav("#/new")
        self.p.wait_for_selector(f'[data-run="{name}"]')
        time.sleep(0.6)
        self.click(f'[data-run="{name}"]', dur=0.9, pause=0.4)
        self.p.wait_for_selector(".decision.pending, .decision.APPROVE, .decision.REVIEW, .decision.REJECT", timeout=30000)

    def wait_decision(self):
        self.p.wait_for_selector(".decision.APPROVE, .decision.REVIEW, .decision.REJECT, .decision.error", timeout=120000)
        time.sleep(0.8)

    def tab(self, key: str, hold: float = 0):
        self.click(f"#tab-{key}", dur=0.5)
        time.sleep(0.4 + hold)

    def scroll_to_title(self, text: str, offset: int = 200, dur: float = 1.0):
        y = self.p.evaluate("""([t, o]) => { const e = [...document.querySelectorAll('.section-title')].find(x => x.textContent.trim().startsWith(t));
            return e ? e.getBoundingClientRect().top + window.scrollY - o : null; }""", [text, offset])
        if y is not None:
            self.scroll(int(y - self.p.evaluate("window.scrollY")), dur)

    def scroll_to(self, selector: str, offset: int = 120, dur: float = 1.0):
        y = self.p.evaluate("([s, o]) => { const e = document.querySelector(s); return e ? e.getBoundingClientRect().top + window.scrollY - o : null; }", [selector, offset])
        if y is None:
            return
        cur = self.p.evaluate("window.scrollY")
        self.scroll(int(y - cur), dur)


def script(d: Demo):
    p = d.p

    # 1 - Intro: how it works ------------------------------------------------------------------
    p.goto(f"{BASE}/#/how"); p.wait_for_selector(".pipe .node"); time.sleep(0.8)
    d.mark("intro", "How it works - pipeline overview")
    d.caption("", "AP Autopilot · invoice PDF → explainable decision")
    d.hold(2.5)
    for i, node in enumerate(p.locator(".pipe .node").all()):
        d.point(node.locator(".bub"), dur=0.45); d.hold(0.9)
    d.mark("rules", "Three outcomes")
    for r in p.locator(".rule").all():
        d.point(r, dur=0.4); d.hold(0.9)
    d.mark("edges", "The four designed edge cases")
    for e in p.locator(".ecard").all():
        d.point(e, dur=0.4); d.hold(0.9)

    # 2 - Upload page & scenario library -------------------------------------------------------
    d.mark("upload", "Upload page and scenario library")
    d.caption("", "Upload any PDF - digital or scanned")
    d.nav("#/new"); p.wait_for_selector("[data-run]"); d.hold(1)
    d.point("#drop", dur=0.6); d.hold(1.8)
    d.scroll(260, 1.0); d.hold(1.5)
    d.scroll(-260, 0.8)

    # 3 - Happy path 1 -------------------------------------------------------------------------
    d.mark("happy1", "Happy path - clean invoice, run live")
    d.caption("Happy path", "Clean itemised invoice · Apex Office Supplies")
    d.run_sample("01_happy_apex_office_supplies.pdf")
    d.point(".timeline", dur=0.8, dy=0.3); d.wait_decision()
    d.mark("happy1_decision", "Approved - decision, score, next step")
    d.point(".decision .score", dur=0.7); d.hold(2)
    d.point(".decision .issues2 > div:nth-child(2)", dur=0.7); d.hold(2.5)
    d.tab("extracted"); d.scroll_to(".tab-body", 90); d.hold(2.5)
    d.scroll(380, 1.2); d.hold(2)
    d.mark("happy1_po", "PO match - lines matched")
    d.scroll_top(); d.tab("po"); d.scroll_to(".tab-body", 90); d.hold(2.5)
    d.scroll_to_title("Line matching", 200, 1.2); d.hold(2.5)
    d.scroll_top()

    # 4 - Happy path 2: split PO ----------------------------------------------------------------
    d.mark("happy2", "Split PO - invoice 2 of 3")
    d.caption("Happy path", "Split PO · invoice 2 of 3 · Northwind Logistics")
    d.run_sample("02_happy_northwind_split_po_2of3.pdf"); d.wait_decision()
    d.mark("happy2_po", "PO consumption across instalments")
    d.tab("po"); d.scroll_to(".tab-body", 90); d.point(".bar", dur=0.7); d.hold(3)
    d.scroll_to_title("Previously invoiced", 260, 1.0); d.hold(3)
    d.scroll_top()

    # 5 - Edge case 1: scanned, no PO ------------------------------------------------------------
    d.mark("edge1", "Edge 1 - scanned invoice, no PO reference")
    d.caption("Edge case 1", "Scanned image · no PO reference")
    d.run_sample("03_edge_scanned_no_po_cobalt.pdf"); d.wait_decision()
    d.mark("edge1_decision", "Review - PO inferred, buyer must confirm")
    d.point(".iss summary", dur=0.6); d.hold(2.5)
    d.mark("edge1_doc", "Document tab - scan and OCR text")
    d.tab("doc"); d.scroll_to(".tab-body", 90); d.point("pre.text", dur=0.8); d.hold(3.5)
    d.mark("edge1_po", "PO candidates scored")
    d.scroll_top(); d.tab("po"); d.scroll_to(".tab-body", 90); d.hold(1)
    d.scroll_to_title("Purchase orders considered", 260, 1.4); d.hold(3)
    d.scroll_top()

    # 6 - Edge case 2: duplicate vs recurring -----------------------------------------------------
    d.mark("edge2a", "Edge 2a - disguised duplicate")
    d.caption("Edge case 2", "Disguised duplicate · re-numbered resend")
    d.run_sample("04_edge_disguised_duplicate_apex.pdf"); d.wait_decision()
    d.click(".iss summary", dur=0.6); d.hold(3)
    d.tab("dups"); d.scroll_to(".tab-body", 90); d.hold(2.5)
    d.scroll_top()
    d.mark("edge2b", "Edge 2b - recurring invoice, not a duplicate")
    d.caption("Edge case 2", "Same amount as last month · different period")
    d.run_sample("05_edge_recurring_not_duplicate_summit.pdf"); d.wait_decision()
    d.point(".decision .headline", dur=0.6); d.hold(1.5)
    d.tab("dups"); d.scroll_to(".tab-body", 90); d.point(".tab-body .checks .check:last-child", dur=0.7); d.hold(3.5)
    d.scroll_top()

    # 7 - Edge case 3: split PO over-billing -------------------------------------------------------
    d.mark("edge3", "Edge 3 - split PO over-billing")
    d.caption("Edge case 3", "Final instalment over the agreed rate")
    d.run_sample("06_edge_split_po_overbilling_northwind.pdf"); d.wait_decision()
    d.point(".decision .headline", dur=0.6); d.hold(1.5)
    d.tab("po"); d.scroll_to(".tab-body", 90); d.point(".bar", dur=0.7); d.hold(3)
    d.scroll_to_title("Line matching", 200, 1.0); d.hold(3)
    d.scroll_top()

    # 8 - Edge case 4: vendor impersonation ----------------------------------------------------------
    d.mark("edge4", "Edge 4 - vendor impersonation / bank change")
    d.caption("Edge case 4", "Look-alike vendor · new bank account")
    d.run_sample("07_edge_vendor_impersonation_bank_change.pdf"); d.wait_decision()
    sums = p.locator(".iss summary")
    for i in range(min(2, sums.count())):
        d.click(sums.nth(i), dur=0.5); d.hold(1.6)
    d.hold(1.5)
    d.tab("extracted"); d.scroll_to_title("Vendor", 160, 1.2); d.hold(3.5)
    d.scroll_top()

    # 9 - Human review -------------------------------------------------------------------------------
    d.mark("review", "Review queue - human approves the inferred PO")
    d.caption("Human in the loop", "Reviewer confirms the inferred PO")
    d.nav("#/reviews"); p.wait_for_selector(".qcard"); d.hold(2)
    d.click(p.locator("a.qcard", has_text="Cobalt"), dur=0.7); d.wait_decision(); d.hold(0.8)
    d.click("#rv-note", dur=0.6)
    p.keyboard.type("Buyer D. Okafor confirmed PO-2026-0377 by email", delay=38)
    d.hold(0.6)
    d.click('[data-act="approve"]', dur=0.6); d.hold(2.5)
    d.point(".reviewed", dur=0.6); d.hold(2)

    # 10 - Dashboard ---------------------------------------------------------------------------------
    d.mark("dashboard", "Dashboard - history, KPIs, filters")
    d.caption("", "Every run, its decision and its audit trail")
    d.nav("#/"); p.wait_for_selector(".donut"); d.hold(1.5)
    d.point(".kpis", dur=0.8); d.hold(1.5)
    d.point(".donut", dur=0.7); d.hold(2)
    d.click('[data-f="REJECT"]', dur=0.6); d.hold(2.5)
    d.click('[data-f="all"]', dur=0.5); d.hold(1)
    d.mark("end", "End")
    d.caption("", "AP Autopilot · thank you")
    d.hold(3)


def main():
    OUT.mkdir(exist_ok=True)
    health = json.load(urllib.request.urlopen(f"{BASE}/api/health"))
    print("engine:", health.get("model") or "rule-based", "| pacing:", health["pacing"])
    urllib.request.urlopen(urllib.request.Request(f"{BASE}/api/reset", method="POST"))
    raw = OUT / "raw"
    shutil.rmtree(raw, ignore_errors=True)
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="chrome", headless=True)
        ctx = browser.new_context(viewport={"width": W, "height": H}, device_scale_factor=1, bypass_csp=True,
                                  record_video_dir=str(raw), record_video_size={"width": W, "height": H})
        ctx.add_init_script(OVERLAY_JS)
        page = ctx.new_page()
        d = Demo(page)
        try:
            script(d)
        finally:
            total = d.now()
            video = page.video.path()
            ctx.close(); browser.close()
    (OUT / "timeline.json").write_text(json.dumps({"duration_s": total, "engine": health.get("model"), "scenes": d.timeline}, indent=2))
    print(f"recorded {total:.1f}s -> {video}")

    ff = next((c for c in FFMPEG_CANDIDATES if c and Path(c).exists()), None)
    if not ff:
        print("ffmpeg not found - raw .webm kept at", video); return
    mp4 = OUT / "ap-autopilot-demo.mp4"
    subprocess.run([ff, "-y", "-loglevel", "error", "-i", str(video), "-c:v", "libx264", "-preset", "slow", "-crf", "18",
                    "-pix_fmt", "yuv420p", "-r", "30", "-movflags", "+faststart", "-an", str(mp4)], check=True)
    print("wrote", mp4)


if __name__ == "__main__":
    sys.exit(main())
