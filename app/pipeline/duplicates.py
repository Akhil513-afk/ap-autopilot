"""Stage F - Duplicate detection.

Layered, from certain to probabilistic:
  1. Same file (SHA-256) already processed.
  2. Same vendor + same invoice number after normalisation (case, separators, leading zeros,
     'COPY'/'-R' re-send suffixes): 'AOS-047950' == 'AOS47950'.
  3. Same vendor + same amount + near date + same line content but a *different* number:
     a probable re-keyed duplicate - unless the invoices cover different service periods,
     which is the signature of legitimate recurring billing (rent, retainers, monthly services).
Candidates come from the ledger (approved/paid history) and from invoices still awaiting review."""
from __future__ import annotations

from rapidfuzz import fuzz

from .. import config, db
from ..utils import close, fmt_money, norm_invoice_number, to_date
from .checks import check

S = "duplicates"


def _line_sim(a: list[dict], b: list[dict]) -> float:
    if not a or not b:
        return 0.0
    ta = " | ".join(sorted(f"{(x.get('description') or '')} {x.get('qty', x.get('quantity'))} {x.get('unit_price')}" for x in a))
    tb = " | ".join(sorted(f"{(x.get('description') or '')} {x.get('qty', x.get('quantity'))} {x.get('unit_price')}" for x in b))
    return fuzz.token_sort_ratio(ta.lower(), tb.lower()) / 100.0


def _period(start, end):
    return f"{start} to {end}" if start and end else None


def run(ext: dict, vendor: dict | None, run_id: str, file_hash: str) -> tuple[list[dict], dict]:
    pol = config.policy()
    f = {k: v["value"] for k, v in ext["fields"].items()}
    cur = f.get("currency") or "USD"
    out, info = [], {"compared_against": 0, "matches": [], "recurring_recognised": []}

    same_file = db.runs_with_hash(file_hash, run_id)
    if same_file:
        r = same_file[0]
        out.append(check("F-FILE", S, "File not previously submitted", "fail",
                         f"This exact file was already processed in run #{r['seq']} ({r['filename']}, outcome: "
                         f"{(r['final_status'] or r['decision'] or '').replace('_', ' ')}).", "reject", prior_run=r["id"]))
    else:
        out.append(check("F-FILE", S, "File not previously submitted", "pass", "No identical file (SHA-256) seen before."))

    if not vendor:
        out.append(check("F-INV", S, "Invoice not previously recorded", "skip", "Vendor unknown - invoice-number duplicate check not possible."))
        return out, info

    num_norm = norm_invoice_number(f.get("invoice_number"))
    period = _period(f.get("service_period_start"), f.get("service_period_end"))
    inv_date = to_date(f.get("invoice_date"))
    lines = [{"description": i["description"], "qty": i.get("quantity"), "unit_price": i.get("unit_price")} for i in ext["line_items"]]

    candidates = [{"source": f"ledger ({r['status']})", **r} for r in db.ledger_rows(vendor_id=vendor["vendor_id"])]
    for p in db.pending_review_runs(run_id):
        if p["vendor_id"] != vendor["vendor_id"]:
            continue
        e = p["extracted"]
        candidates.append({"source": f"run #{p['seq']} (awaiting review)", "invoice_number": e.get("invoice_number"),
                           "invoice_number_norm": norm_invoice_number(e.get("invoice_number")), "invoice_date": e.get("invoice_date"),
                           "total": e.get("total"), "po_number": e.get("po_number"),
                           "service_period": _period(e.get("service_period_start"), e.get("service_period_end")),
                           "lines": e.get("lines", [])})
    info["compared_against"] = len(candidates)

    exact = [c for c in candidates if num_norm and c.get("invoice_number_norm") == num_norm]
    if exact:
        c = exact[0]
        same_fmt = (c["invoice_number"] or "").upper() == (f.get("invoice_number") or "").upper()
        detail = "identical invoice number" if same_fmt else \
            f"invoice number '{f.get('invoice_number')}' is the same as '{c['invoice_number']}' once formatting is ignored"
        amt = " and the same amount" if close(c.get("total"), f.get("total"), 0.01) else f" (amount {fmt_money(c.get('total'), cur)} vs {fmt_money(f.get('total'), cur)})"
        out.append(check("F-INV", S, "Invoice not previously recorded", "fail",
                         f"Duplicate of {c['invoice_number']} dated {c['invoice_date']} from {c['source']}: {detail}{amt}.",
                         "reject", match=c["invoice_number"]))
        info["matches"].append({"type": "invoice_number", "invoice_number": c["invoice_number"], "source": c["source"],
                                "invoice_date": c["invoice_date"], "total": c.get("total")})
    else:
        out.append(check("F-INV", S, "Invoice not previously recorded", "pass" if num_norm else "skip",
                         f"Invoice number {f.get('invoice_number')} not seen for this vendor ({len(candidates)} prior invoice(s) compared)."
                         if num_norm else "No invoice number to compare."))

    # Fuzzy: same amount, near date, similar content, different number
    fuzzy_hits = []
    for c in candidates:
        if c in exact or not close(c.get("total"), f.get("total"), 0.01):
            continue
        cd = to_date(c.get("invoice_date"))
        days = abs((inv_date - cd).days) if inv_date and cd else None
        sim = _line_sim(lines, c.get("lines") or [])
        c_period = c.get("service_period")
        if period and c_period and period != c_period:
            info["recurring_recognised"].append({"invoice_number": c["invoice_number"], "service_period": c_period,
                                                 "total": c.get("total")})
            continue
        if (days is None or days <= pol["duplicate_fuzzy_window_days"]) and sim >= 0.85:
            fuzzy_hits.append((c, days, sim))
    if fuzzy_hits:
        c, days, sim = fuzzy_hits[0]
        out.append(check("F-FUZZY", S, "No near-duplicate (same amount and content)", "fail",
                         f"Same amount {fmt_money(f.get('total'), cur)} and {sim:.0%} identical line content as {c['invoice_number']} "
                         f"({c['source']}, {days if days is not None else '?'} days apart) under a different invoice number - "
                         "possible re-submitted invoice.", "review", match=c["invoice_number"], similarity=sim))
        info["matches"].append({"type": "fuzzy", "invoice_number": c["invoice_number"], "similarity": sim, "source": c["source"]})
    elif info["recurring_recognised"]:
        r = info["recurring_recognised"]
        out.append(check("F-FUZZY", S, "No near-duplicate (same amount and content)", "pass",
                         f"Same amount as {', '.join(x['invoice_number'] for x in r)} but for a different service period "
                         f"({period} vs {r[0]['service_period']}) - recognised as legitimate recurring billing, not a duplicate."))
    else:
        out.append(check("F-FUZZY", S, "No near-duplicate (same amount and content)", "pass",
                         "No prior invoice with the same amount and content."))
    return out, info
