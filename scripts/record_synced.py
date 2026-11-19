"""Record the website demo paced to a recorded narration (demo/narration_targets.json).

Each scene starts at the second the narrator starts talking about it. No caption overlay, only a
visible cursor. Output: demo/raw_synced/*.webm + demo/timeline_synced.json; scripts/sync_video.py
then fine-aligns every scene and overlays the narrator's camera.

    .venv/bin/python scripts/record_synced.py
"""
from __future__ import annotations

import json
import shutil
import sys
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent))
from record_demo import BASE, OVERLAY_JS, Demo  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "demo"
VW, VH, DSF = 1600, 900, 1.2          # CSS viewport; rendered at 1920x1080
TARGETS = json.loads((OUT / "narration_targets.json").read_text())

# Same cursor overlay, but with the scene-caption pill removed entirely.
CURSOR_ONLY_JS = OVERLAY_JS.replace("const cap = document.createElement('div'); cap.id = '__cap'; document.body.appendChild(cap);", "") \
    .replace("window.__caption = (tag, text) => { cap.innerHTML = (tag ? '<b>' + tag + '</b>' : '') + '<span>' + text + '</span>'; cap.style.opacity = text ? 1 : 0; };",
             "window.__caption = () => {};")


class SyncDemo(Demo):
    def __init__(self, page):
        super().__init__(page)
        self.base = None  # wall-clock moment that maps to narration t=0

    def caption(self, tag, text):  # captions are intentionally not shown
        return

    def scene(self, key: str, label: str):
        if self.base is None:
            self.base = time.monotonic()
        else:
            due = self.base + TARGETS[key]
            while time.monotonic() < due - 0.05:   # idle on the current content until the narrator moves on
                time.sleep(min(0.2, due - time.monotonic()))
        self.mark(key, label)

    def hold(self, s: float):  # short holds only; scene() absorbs the rest of the narration time
        time.sleep(min(s, 1.0))


def script(d: SyncDemo):
    p = d.p
    p.goto(f"{BASE}/#/how"); p.wait_for_selector(".pipe .node"); time.sleep(0.6)

    d.scene("intro", "How it works")
    for node in p.locator(".pipe .node").all():
        d.point(node.locator(".bub"), dur=0.5); time.sleep(1.1)
    d.scene("rules", "Three outcomes")
    for r in p.locator(".rule").all():
        d.point(r, dur=0.5); time.sleep(1.3)
    d.scene("edges", "Four edge cases")
    for e in p.locator(".ecard").all():
        d.point(e, dur=0.5); time.sleep(1.0)

    d.scene("upload", "Upload page")
    d.nav("#/new"); p.wait_for_selector("[data-run]"); time.sleep(0.6)
    d.point("#drop", dur=0.6); time.sleep(2.0)
    d.scroll(300, 1.2); time.sleep(1.5)

    d.scene("happy1", "Happy path - clean invoice")
    d.scroll_top()
    d.run_sample("01_happy_apex_office_supplies.pdf")
    d.point(".timeline", dur=0.8, dy=0.35); d.wait_decision()
    d.scene("happy1_decision", "Approved")
    d.point(".decision .score", dur=0.7); time.sleep(2.5)
    d.point(".decision .issues2 > div:nth-child(2)", dur=0.7); time.sleep(3.0)
    d.tab("extracted"); d.scroll_to(".tab-body", 90); time.sleep(1.5)
    d.scroll(380, 1.2)
    d.scene("happy1_po", "PO match")
    d.scroll_top(); d.tab("po"); d.scroll_to(".tab-body", 90); time.sleep(3.0)
    d.scroll_to_title("Line matching", 200, 1.2)

    d.scene("happy2", "Split PO 2 of 3")
    d.scroll_top()
    d.run_sample("02_happy_northwind_split_po_2of3.pdf"); d.wait_decision()
    d.point(".decision .headline", dur=0.6)
    d.scene("happy2_po", "PO consumption")
    d.tab("po"); d.scroll_to(".tab-body", 90); d.point(".bar", dur=0.7); time.sleep(4.0)
    d.scroll_to_title("Previously invoiced", 260, 1.0)

    d.scene("edge1", "Edge 1 - scanned, no PO")
    d.scroll_top()
    d.run_sample("03_edge_scanned_no_po_cobalt.pdf"); d.wait_decision()
    d.scene("edge1_decision", "Manual review")
    d.point(".iss summary", dur=0.6)
    d.scene("edge1_doc", "Scan and OCR text")
    d.tab("doc"); d.scroll_to(".tab-body", 90); d.point("pre.text", dur=0.8)
    d.scene("edge1_po", "PO candidates")
    d.scroll_top(); d.tab("po"); d.scroll_to(".tab-body", 90); time.sleep(0.8)
    d.scroll_to_title("Purchase orders considered", 260, 1.4)

    d.scene("edge2a", "Edge 2a - disguised duplicate")
    d.scroll_top()
    d.run_sample("04_edge_disguised_duplicate_apex.pdf"); d.wait_decision()
    d.click(".iss summary", dur=0.6); time.sleep(4.0)
    d.tab("dups"); d.scroll_to(".tab-body", 90)

    d.scene("edge2b", "Edge 2b - recurring, not duplicate")
    d.scroll_top()
    d.run_sample("05_edge_recurring_not_duplicate_summit.pdf"); d.wait_decision()
    d.point(".decision .headline", dur=0.6); time.sleep(3.0)
    d.tab("dups"); d.scroll_to(".tab-body", 90); d.point(".tab-body .checks .check:last-child", dur=0.7)

    d.scene("edge3", "Edge 3 - split PO over-billing")
    d.scroll_top()
    d.run_sample("06_edge_split_po_overbilling_northwind.pdf"); d.wait_decision()
    d.point(".decision .headline", dur=0.6); time.sleep(5.0)
    d.tab("po"); d.scroll_to(".tab-body", 90); d.point(".bar", dur=0.7); time.sleep(8.0)
    d.scroll_to_title("Line matching", 200, 1.0); d.point(".tab-body table tbody tr", dur=0.7)

    d.scene("edge4", "Edge 4 - vendor impersonation")
    d.scroll_top()
    d.run_sample("07_edge_vendor_impersonation_bank_change.pdf"); d.wait_decision()
    sums = p.locator(".iss summary")
    for i in range(min(2, sums.count())):
        d.click(sums.nth(i), dur=0.5); time.sleep(3.0)
    d.tab("extracted"); d.scroll_to_title("Vendor", 160, 1.2)

    d.scene("review", "Human review")
    d.scroll_top()
    d.nav("#/reviews"); p.wait_for_selector(".qcard"); time.sleep(1.5)
    d.click(p.locator("a.qcard", has_text="Cobalt"), dur=0.7); d.wait_decision(); time.sleep(0.6)
    d.click("#rv-note", dur=0.6)
    p.keyboard.type("Buyer D. Okafor confirmed PO-2026-0377 by email", delay=45)
    time.sleep(0.6)
    d.click('[data-act="approve"]', dur=0.6); time.sleep(2.0)
    d.point(".reviewed", dur=0.6)

    d.scene("dashboard", "Dashboard")
    d.nav("#/"); p.wait_for_selector(".donut"); time.sleep(1.5)
    d.point(".kpis", dur=0.8); time.sleep(2.0)
    d.point(".donut", dur=0.7); time.sleep(2.5)
    d.click('[data-f="REJECT"]', dur=0.6); time.sleep(3.0)
    d.click('[data-f="all"]', dur=0.5)
    d.scene("end", "End")
    time.sleep(1.0)


def main():
    OUT.mkdir(exist_ok=True)
    health = json.load(urllib.request.urlopen(f"{BASE}/api/health"))
    print("engine:", health.get("model") or "rule-based", "| pacing:", health["pacing"])
    urllib.request.urlopen(urllib.request.Request(f"{BASE}/api/reset", method="POST"))
    raw = OUT / "raw_synced"
    shutil.rmtree(raw, ignore_errors=True)
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="chrome", headless=True)
        ctx = browser.new_context(viewport={"width": VW, "height": VH}, device_scale_factor=DSF, bypass_csp=True,
                                  record_video_dir=str(raw), record_video_size={"width": int(VW * DSF), "height": int(VH * DSF)})
        ctx.add_init_script(CURSOR_ONLY_JS)
        page = ctx.new_page()
        d = SyncDemo(page)
        try:
            script(d)
        finally:
            total = d.now()
            video = page.video.path()
            ctx.close(); browser.close()
    (OUT / "timeline_synced.json").write_text(json.dumps({"duration_s": total, "video": str(video), "scenes": d.timeline}, indent=2))
    print(f"recorded {total:.1f}s -> {video}")


if __name__ == "__main__":
    main()
