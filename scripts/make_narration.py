"""Build the narration script (Markdown) and a teleprompter subtitle file (SRT) from demo/timeline.json.

Each line is anchored to a scene mark recorded during scripts/record_demo.py, so the timestamps match
the final video. Re-run after re-recording:  .venv/bin/python scripts/make_narration.py
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEMO = ROOT / "demo"
WPM = 150  # comfortable speaking pace

# (scene key the line starts at, on-screen cue, what to say)
LINES = [
    ("intro", "‘How it works’ page: the 8-step pipeline",
     "Hi, I'm [your name]. This is AP Autopilot, my solution to problem statement one: invoice processing, from PDF to decision. "
     "Every invoice goes through eight stages, from intake to a final decision."),
    ("rules", "Approve / Review / Reject cards, then the four edge-case cards",
     "Gemini reads the document; fixed rules decide: approve, review, or reject. I designed four edge cases, and I'll run each one live."),
    ("upload", "Upload page and scenario library",
     "Drop in any PDF, digital or scanned, or pick a prepared scenario: two happy paths, four edge cases, six exceptions."),
    ("happy1", "Clean Apex invoice runs; pipeline fills in live",
     "Let's start with a clean invoice from Apex Office Supplies. Watch the pipeline on the left: it checks the file, reads the text layer, and extracts every field."),
    ("happy1_decision", "Green ‘Approve’ banner, 29/29 checks, Data tab",
     "Approved: all twenty-nine checks passed, and the next step is routed to the AP supervisor, with payment scheduled on Net 30. "
     "Every field shows a confidence score and the text it came from."),
    ("happy1_po", "PO match tab: line matching",
     "In the PO match tab, every invoice line maps to the purchase order. Quantity, price and tax are all within tolerance: a clean two-way match."),
    ("happy2", "Northwind ‘invoice 2 of 3’ runs",
     "Second happy path: Northwind bills one PO in three monthly instalments. The PO number is written oddly and the dates are day-first, but it still resolves."),
    ("happy2_po", "PO consumption bar and prior invoice",
     "It matches against what's left on the PO, not the full value. This is invoice two of three, so it's approved, and the PO is now sixty-seven percent used."),
    ("edge1", "Edge case 1: scanned Cobalt invoice runs, then amber ‘Manual review’",
     "Edge case one: a scanned invoice with no PO number at all. There's no text layer, so it runs OCR, at ninety-three percent confidence, "
     "and then it has to work out which purchase order this belongs to. It goes to manual review."),
    ("edge1_doc", "Document tab: scan next to OCR text",
     "Here's the original scan beside the text the system read."),
    ("edge1_po", "PO candidates table",
     "It scored Cobalt's open POs: a hundred percent match versus sixteen. Strong, but an inferred PO still needs the buyer's confirmation."),
    ("edge2a", "Edge case 2: Apex ‘payment reminder’ copy, red ‘Reject’",
     "Edge case two is about duplicates. Apex re-sent an invoice we already paid, as a payment reminder, with a new date and the number re-formatted with a leading zero. "
     "Normalised, it's the same invoice, so it's rejected before it can be paid twice."),
    ("edge2b", "Summit monthly invoice approved; Duplicates tab",
     "But the opposite mistake is just as costly. Summit bills the same four thousand five hundred dollars every month, so a naive check would block it. "
     "The system sees a different service period, recognises recurring billing, and approves it."),
    ("edge3", "Edge case 3: Northwind final instalment; PO match bar",
     "Edge case three: Northwind's final instalment. The agreed rate is sixteen thousand a month, but this invoice says nineteen and a half thousand, with a surcharge bundled in. "
     "The bar shows earlier invoices in grey, this one in amber, and the overrun in red. That's a twenty-one point nine percent price variance, "
     "so it goes to the buyer, by name, for a PO amendment or a corrected invoice."),
    ("edge4", "Edge case 4: impersonation; issues expand; vendor fields",
     "Edge case four is the expensive one: vendor impersonation. The PO and the amounts are perfect. But it says Limited instead of Inc, the tax ID digits are swapped, "
     "the email domain is a look-alike, and it asks us to pay a new bank account. Two or more identity mismatches mean a fraud hold: don't pay, "
     "and call the vendor on the number we already have on file."),
    ("review", "Review queue; note typed; Approve",
     "Back to the scanned invoice in the review queue. The buyer has confirmed the PO, so I add a note and approve. "
     "My name, the decision and the reason all go into the audit trail."),
    ("dashboard", "Dashboard: KPIs, donut, ‘Rejected’ filter",
     "Finally, the dashboard: every invoice, its decision and why, with the value cleared and the value blocked. "
     "Gemini reads, rules decide, and every outcome can be explained. Thanks for watching."),
]


def mmss(t: float) -> str:
    return f"{int(t // 60)}:{int(t % 60):02d}"


def srt_ts(t: float) -> str:
    ms = int(round(t * 1000))
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"


def main():
    tl = json.loads((DEMO / "timeline.json").read_text())
    at = {s["key"]: s.get("t_final", s["t"]) for s in tl["scenes"]}
    end = tl.get("final_duration_s", tl["duration_s"])
    rows = []
    for i, (key, cue, text) in enumerate(LINES):
        start = at[key]
        stop = at[LINES[i + 1][0]] if i + 1 < len(LINES) else end
        words = len(text.split())
        need = words / WPM * 60
        rows.append({"start": start, "stop": stop, "cue": cue, "text": text, "words": words, "need": need, "have": stop - start})

    md = ["# AP Autopilot · demo narration script", "",
          f"Video: `demo/ap-autopilot-demo.mp4` · **{mmss(end)}** · 1600×900 · silent (add your voice).", "",
          "Read each line when the video reaches its timestamp. The lines are timed for a relaxed pace "
          f"(~{WPM} words/min), so you'll have a breath of slack in most scenes. "
          "Replace **[your name]** in the first line.", "",
          "| Time | On screen | Say | Words · fits in |", "|---|---|---|---|"]
    for r in rows:
        md.append(f"| **{mmss(r['start'])}–{mmss(r['stop'])}** | {r['cue']} | {r['text']} | {r['words']} · {r['need']:.0f}s of {r['have']:.0f}s |")
    md += ["", "## Plain script (for reading aloud)", ""]
    for r in rows:
        md.append(f"**[{mmss(r['start'])}]** {r['text']}  ")
        md.append("")
    (DEMO / "NARRATION_SCRIPT.md").write_text("\n".join(md))

    srt = []
    for i, r in enumerate(rows, 1):
        srt += [str(i), f"{srt_ts(r['start'])} --> {srt_ts(max(r['start'] + 1.5, r['stop'] - 0.2))}", r["text"], ""]
    (DEMO / "narration.srt").write_text("\n".join(srt))

    tight = [r for r in rows if r["need"] > r["have"] - 0.5]
    print(f"{len(rows)} lines, video {mmss(end)}")
    for r in rows:
        print(f"  {mmss(r['start'])}  need {r['need']:5.1f}s / have {r['have']:5.1f}s  {'TIGHT' if r in tight else ''}")


if __name__ == "__main__":
    main()
