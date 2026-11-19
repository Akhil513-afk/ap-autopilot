"""Stage E - Purchase-order identification and 2-way matching.

1. Identify the PO: exact reference -> normalised reference ("PO 2026/0398", "Purchase Order 0431")
   -> if absent/unknown, infer from the vendor's open POs by line-item similarity and amount fit.
2. Compute what is still open on the PO from the ledger of previously approved invoices, so a
   PO legitimately split across several invoices is matched against its *remaining* balance.
3. Match invoice lines to PO lines (including bundled lines that cover several PO lines and
   ancillary charges such as freight that are not on the PO), then compare price, quantity,
   amount, tax and currency against policy tolerances."""
from __future__ import annotations

import itertools
import re

from rapidfuzz import fuzz

from .. import config, db
from ..utils import fmt_money
from .checks import check

S = "po_match"
BILLED_STATUSES = ("approved", "paid")


def _alnum(s):
    return re.sub(r"[^A-Z0-9]", "", (s or "").upper())


def _digits(s):
    return re.sub(r"\D", "", s or "")


def _sim(a, b):
    return fuzz.token_set_ratio((a or "").lower(), (b or "").lower()) / 100.0


def locate_by_reference(ref: str, vendor_id: str | None) -> tuple[dict | None, str | None]:
    pos = config.purchase_orders()
    r = (ref or "").strip()
    for po in pos:
        if po["po_number"].upper() == r.upper():
            return po, "exact reference"
    for po in pos:
        if _alnum(po["po_number"]) in (_alnum(r), _alnum("PO" + r)):
            return po, f"normalised reference ('{r}' -> {po['po_number']})"
    d = _digits(r)
    if len(d) >= 3:
        same = [po for po in pos if _digits(po["po_number"]) == d]
        if len(same) == 1:
            return same[0], f"normalised reference ('{r}' -> {same[0]['po_number']})"
        suffix = [po for po in pos if _digits(po["po_number"]).endswith(d)]
        if vendor_id:
            pref = [po for po in suffix if po["vendor_id"] == vendor_id]
            suffix = pref or suffix
        if len(suffix) == 1:
            return suffix[0], f"partial reference ('{r}' matches the sequence number of {suffix[0]['po_number']})"
    return None, None


def po_position(po: dict) -> dict:
    """Ordered vs already-invoiced, per PO line, from the ledger."""
    rows = [r for r in db.ledger_rows(po_number=po["po_number"]) if r["status"] in BILLED_STATUSES]
    lines = [{**ln, "value": round(ln["qty"] * ln["unit_price"], 2), "billed_qty": 0.0} for ln in po["lines"]]
    for r in rows:
        for li in r["lines"]:
            if len(lines) == 1:
                lines[0]["billed_qty"] += li.get("qty") or 0
                continue
            best = max(lines, key=lambda pl: _sim(li["description"], pl["description"]))
            best["billed_qty"] += li.get("qty") or 0
    for ln in lines:
        ln["remaining_qty"] = round(ln["qty"] - ln["billed_qty"], 4)
    po_sub = round(sum(ln["value"] for ln in lines), 2)
    billed = round(sum(r["subtotal"] or 0 for r in rows), 2)
    return {"lines": lines, "po_subtotal": po_sub, "billed_subtotal": billed, "remaining_subtotal": round(po_sub - billed, 2),
            "prior_invoices": [{"invoice_number": r["invoice_number"], "invoice_date": r["invoice_date"],
                                "subtotal": r["subtotal"], "status": r["status"], "source": r["source"],
                                "service_period": r["service_period"]} for r in rows]}


def match_lines(items: list[dict], pos_lines: list[dict], price_tol: float) -> list[dict]:
    used: set[int] = set()
    out = []
    for idx, it in enumerate(items, 1):
        if it.get("ancillary"):
            out.append({"invoice_line": idx, "description": it["description"], "kind": "ancillary", "po_lines": [],
                        "amount": it.get("amount"), "note": "Ancillary charge (freight/handling/surcharge) - not a PO line"})
            continue
        avail = [pl for pl in pos_lines if pl["line"] not in used]
        scored = sorted(((_sim(it["description"], pl["description"]), pl) for pl in avail), key=lambda x: -x[0])
        single = None
        if scored:
            s0, pl0 = scored[0]
            if s0 >= 0.55 or len(pos_lines) == 1:
                single = (s0, pl0)
        price_ok = False
        if single and it.get("unit_price") is not None:
            price_ok = abs(it["unit_price"] - single[1]["unit_price"]) <= price_tol * single[1]["unit_price"]
        # Bundle: a lump-sum line whose amount equals the combined value of 2+ PO lines
        if not price_ok and (it.get("quantity") in (None, 1, 1.0)) and it.get("amount") and len(avail) >= 2:
            for k in range(min(len(avail), 4), 1, -1):
                hit = None
                for combo in itertools.combinations(avail, k):
                    val = sum(c["unit_price"] * min(c["qty"], max(c.get("remaining_qty", c["qty"]), 0) or c["qty"]) for c in combo)
                    if abs(val - it["amount"]) <= max(0.01, 0.005 * val):
                        hit = combo
                        break
                if hit:
                    for c in hit:
                        used.add(c["line"])
                    out.append({"invoice_line": idx, "description": it["description"], "kind": "bundle",
                                "po_lines": [c["line"] for c in hit], "amount": it["amount"],
                                "po_value": round(sum(c["unit_price"] * c["qty"] for c in hit), 2),
                                "note": f"Bundled line covers PO lines {', '.join(str(c['line']) for c in hit)} "
                                        f"({' + '.join(c['description'][:30] for c in hit)})"})
                    break
            if out and out[-1]["invoice_line"] == idx:
                continue
        if single:
            s0, pl = single
            used.add(pl["line"])
            var = None
            if it.get("unit_price") is not None and pl["unit_price"]:
                var = (it["unit_price"] - pl["unit_price"]) / pl["unit_price"]
            out.append({"invoice_line": idx, "description": it["description"], "kind": "matched", "po_lines": [pl["line"]],
                        "po_description": pl["description"], "similarity": round(s0, 2),
                        "inv_qty": it.get("quantity"), "po_qty": pl["qty"], "po_remaining_qty": pl.get("remaining_qty", pl["qty"]),
                        "inv_price": it.get("unit_price"), "po_price": pl["unit_price"],
                        "price_variance_pct": round(var, 4) if var is not None else None, "amount": it.get("amount"),
                        "note": "single-line PO" if len(pos_lines) == 1 and s0 < 0.55 else None})
        else:
            out.append({"invoice_line": idx, "description": it["description"], "kind": "unmatched", "po_lines": [],
                        "amount": it.get("amount"), "note": "No corresponding PO line"})
    return out


def infer_po(vendor_id: str, items: list[dict], inv_sub: float | None) -> tuple[dict | None, list[dict]]:
    cands = []
    core = [it for it in items if not it.get("ancillary")]
    core_sum = sum(it.get("amount") or 0 for it in core) or inv_sub or 0
    for po in config.purchase_orders():
        if po["vendor_id"] != vendor_id or po["status"] not in ("open",):
            continue
        pos = po_position(po)
        m = match_lines(core, pos["lines"], 0.02)
        matched = [x for x in m if x["kind"] in ("matched", "bundle") and (x.get("similarity", 1) >= 0.55)]
        line_score = len(matched) / max(len(core), 1)
        rem = pos["remaining_subtotal"]
        amt_score = max(0.0, 1 - abs(core_sum - rem) / rem) if rem > 0 else 0.0
        score = round(0.6 * line_score + 0.4 * amt_score, 3)
        cands.append({"po_number": po["po_number"], "score": score, "line_score": round(line_score, 2),
                      "amount_score": round(amt_score, 2), "remaining": rem})
    cands.sort(key=lambda c: -c["score"])
    pol = config.policy()
    if cands and cands[0]["score"] >= pol["inferred_po_min_score"] and \
            (len(cands) == 1 or cands[0]["score"] - cands[1]["score"] >= 0.15):
        po = next(p for p in config.purchase_orders() if p["po_number"] == cands[0]["po_number"])
        return po, cands
    return None, cands


def run(ext: dict, vendor: dict | None, derived: dict) -> tuple[list[dict], dict]:
    pol = config.policy()
    f = {k: v["value"] for k, v in ext["fields"].items()}
    items = ext["line_items"]
    cur = f.get("currency") or "USD"
    inv_sub = derived.get("subtotal")
    out: list[dict] = []
    info: dict = {"reference": f.get("po_number"), "method": None, "po": None, "candidates": [], "comparison": [], "lines": []}

    po, method = (None, None)
    if f.get("po_number"):
        po, method = locate_by_reference(f["po_number"], vendor["vendor_id"] if vendor else None)
        if not po:
            out.append(check("E-REF", S, "PO reference resolves", "fail",
                             f"PO reference '{f['po_number']}' does not exist in procurement records.", "review"))
    if not po and vendor:
        po, cands = infer_po(vendor["vendor_id"], items, inv_sub)
        info["candidates"] = cands
        if po:
            method = "inferred"
            c0 = cands[0]
            out.append(check("E-FIND", S, "Purchase order identified", "fail",
                             f"No PO reference on the invoice. Inferred {po['po_number']} from {vendor['name']}'s open POs "
                             f"(match score {c0['score']:.0%}: {c0['line_score']:.0%} of lines, amount fit {c0['amount_score']:.0%}). "
                             "Policy: an inferred PO must be confirmed by the buyer before payment.", "review",
                             candidates=cands))
        else:
            msg = "No PO reference on the invoice and no open PO for this vendor fits the invoice." if not f.get("po_number") \
                else "Could not infer an alternative PO from the vendor's open POs."
            out.append(check("E-FIND", S, "Purchase order identified", "fail", msg + " Requester must provide a PO (no PO, no pay).",
                             "review", candidates=cands))
    elif not po:
        out.append(check("E-FIND", S, "Purchase order identified", "fail",
                         "No PO could be identified" + (" and vendor is unknown." if not vendor else "."), "review"))
    if not po:
        return out, info

    if method != "inferred":
        out.append(check("E-FIND", S, "Purchase order identified", "pass", f"{po['po_number']} found by {method}."))
    info.update(method=method, po=po)
    pos = po_position(po)
    info["position"] = pos

    # Vendor on PO
    if vendor and po["vendor_id"] != vendor["vendor_id"]:
        owner = next((v["name"] for v in config.vendors() if v["vendor_id"] == po["vendor_id"]), po["vendor_id"])
        out.append(check("E-VENDOR", S, "PO belongs to invoicing vendor", "fail",
                         f"{po['po_number']} was issued to {owner}, not {vendor['name']}.", "reject"))
    elif vendor:
        out.append(check("E-VENDOR", S, "PO belongs to invoicing vendor", "pass", f"{po['po_number']} was issued to {vendor['name']}."))

    # PO status
    if po["status"] != "open":
        out.append(check("E-STATUS", S, "PO is open", "fail", f"{po['po_number']} status is '{po['status'].replace('_', ' ')}'.", "review"))
    else:
        out.append(check("E-STATUS", S, "PO is open", "pass", f"{po['po_number']} is open."))

    if f.get("currency") and f["currency"] != po["currency"]:
        out.append(check("E-CUR", S, "Currency matches PO", "fail", f"Invoice {f['currency']} vs PO {po['currency']}.", "review"))
    else:
        out.append(check("E-CUR", S, "Currency matches PO", "pass", f"Both in {po['currency']}."))

    # Line-level matching
    lm = match_lines(items, pos["lines"], pol["unit_price_tolerance_pct"])
    info["lines"] = lm
    unmatched = [x for x in lm if x["kind"] == "unmatched"]
    bundles = [x for x in lm if x["kind"] == "bundle"]
    if unmatched:
        out.append(check("E-LINES", S, "Invoice lines map to PO lines", "fail",
                         f"{len(unmatched)} invoice line(s) have no corresponding PO line: "
                         + "; ".join(f"'{u['description'][:40]}'" for u in unmatched), "review"))
    else:
        extra = f" ({len(bundles)} bundled line(s) mapped to multiple PO lines)" if bundles else ""
        out.append(check("E-LINES", S, "Invoice lines map to PO lines", "pass",
                         f"All {len([x for x in lm if x['kind'] != 'ancillary'])} goods/service line(s) mapped to the PO{extra}."))
    price_bad = [x for x in lm if x["kind"] == "matched" and x.get("price_variance_pct") is not None
                 and abs(x["price_variance_pct"]) > pol["unit_price_tolerance_pct"]]
    if price_bad:
        out.append(check("E-PRICE", S, f"Unit prices within {pol['unit_price_tolerance_pct']:.0%} of PO", "fail",
                         "; ".join(f"'{x['description'][:60]}' billed at {fmt_money(x['inv_price'], cur)} vs PO "
                                   f"{fmt_money(x['po_price'], cur)} ({x['price_variance_pct']:+.1%})" for x in price_bad), "review"))
    elif any(x["kind"] == "matched" for x in lm):
        out.append(check("E-PRICE", S, f"Unit prices within {pol['unit_price_tolerance_pct']:.0%} of PO", "pass",
                         "All matched lines are priced at the PO rate."))
    qty_bad = [x for x in lm if x["kind"] == "matched" and x.get("inv_qty") is not None and x["inv_qty"] > x["po_remaining_qty"] + 1e-9]
    if qty_bad:
        out.append(check("E-QTY", S, "Quantities within PO remaining quantity", "fail",
                         "; ".join(f"'{x['description'][:60]}' invoices {x['inv_qty']:g} but only {x['po_remaining_qty']:g} of "
                                   f"{x['po_qty']:g} remain un-invoiced on the PO" for x in qty_bad), "review"))
    elif any(x["kind"] == "matched" for x in lm):
        out.append(check("E-QTY", S, "Quantities within PO remaining quantity", "pass", "No line exceeds the quantity still open on the PO."))

    anc = [x for x in lm if x["kind"] == "ancillary"]
    anc_total = round(sum(x["amount"] or 0 for x in anc), 2)

    # Amount vs remaining balance with tolerance
    remaining = pos["remaining_subtotal"]
    if inv_sub is not None:
        tol = min(pol["amount_tolerance_pct"] * max(remaining, pos["po_subtotal"] if remaining <= 0 else remaining),
                  pol["amount_tolerance_abs"])
        over = round(inv_sub - remaining, 2)
        info["tolerance"] = round(tol, 2)
        multi = len(pos["prior_invoices"]) > 0
        if remaining <= 0.005:
            out.append(check("E-AMOUNT", S, "Amount within PO remaining balance", "fail",
                             f"{po['po_number']} is already fully invoiced ({fmt_money(pos['billed_subtotal'], cur)} of "
                             f"{fmt_money(pos['po_subtotal'], cur)}); nothing remains to bill.", "review"))
        elif over > tol:
            out.append(check("E-AMOUNT", S, "Amount within PO remaining balance", "fail",
                             f"Invoice subtotal {fmt_money(inv_sub, cur)} exceeds the remaining PO balance "
                             f"{fmt_money(remaining, cur)} by {fmt_money(over, cur)} ({over / remaining:.1%}); tolerance is "
                             f"{fmt_money(tol, cur)}. Needs a PO amendment or a corrected invoice.", "review"))
        elif over > 0.005:
            out.append(check("E-AMOUNT", S, "Amount within PO remaining balance", "warn",
                             f"Invoice is {fmt_money(over, cur)} ({over / remaining:.2%}) above the PO balance - within tolerance "
                             f"({fmt_money(tol, cur)})" + (f", explained by ancillary charges of {fmt_money(anc_total, cur)}." if anc_total else ".")))
        elif not po.get("allows_partial_invoicing") and over < -tol:
            out.append(check("E-AMOUNT", S, "Amount within PO remaining balance", "warn",
                             f"Partial invoice ({fmt_money(inv_sub, cur)} of {fmt_money(remaining, cur)}) on a PO not flagged for partial billing."))
        else:
            out.append(check("E-AMOUNT", S, "Amount within PO remaining balance", "pass",
                             f"Subtotal {fmt_money(inv_sub, cur)} vs remaining {fmt_money(remaining, cur)} - within tolerance."))
        if multi or po.get("allows_partial_invoicing"):
            after = pos["billed_subtotal"] + inv_sub
            n = len(pos["prior_invoices"]) + 1
            out.append(check("E-SPLIT", S, "Split / partial invoicing tracked", "info",
                             f"Invoice #{n} against {po['po_number']}. Previously invoiced {fmt_money(pos['billed_subtotal'], cur)} "
                             f"across {n - 1} invoice(s); after this one {fmt_money(after, cur)} of {fmt_money(pos['po_subtotal'], cur)} "
                             f"({after / pos['po_subtotal']:.0%}) will be consumed.", prior=pos["prior_invoices"]))

    if anc:
        tol_anc = pol["amount_tolerance_abs"]
        if anc_total <= tol_anc:
            out.append(check("E-ANC", S, "Non-PO charges within allowance", "warn",
                             f"Ancillary charges not on the PO: {fmt_money(anc_total, cur)} - accepted within the "
                             f"{fmt_money(tol_anc, cur)} allowance, noted for the buyer."))
        else:
            out.append(check("E-ANC", S, "Non-PO charges within allowance", "fail",
                             f"Ancillary charges not on the PO total {fmt_money(anc_total, cur)} (> {fmt_money(tol_anc, cur)} allowance).", "review"))

    # Tax rate vs PO
    tax, rate = f.get("tax_amount"), f.get("tax_rate")
    if inv_sub:
        eff = rate if rate is not None else ((tax or 0) / inv_sub)
        if abs(eff - po["tax_rate"]) > 0.0005:
            exp = round(inv_sub * po["tax_rate"], 2)
            out.append(check("E-TAX", S, "Tax rate matches PO", "fail",
                             f"Invoice charges tax at {eff:.2%} ({fmt_money(tax or 0, cur)}); PO tax rate is {po['tax_rate']:.2%} "
                             f"(expected {fmt_money(exp, cur)}, difference {fmt_money((tax or 0) - exp, cur)}).", "review"))
        else:
            out.append(check("E-TAX", S, "Tax rate matches PO", "pass", f"Tax at {po['tax_rate']:.2%} as per PO."))

    # Side-by-side comparison for the UI
    po_tax_on_inv = round((inv_sub or 0) * po["tax_rate"], 2)
    info["comparison"] = [
        {"field": "Vendor", "invoice": f.get("vendor_name"), "po": next((v["name"] for v in config.vendors() if v["vendor_id"] == po["vendor_id"]), po["vendor_id"]),
         "ok": bool(vendor and vendor["vendor_id"] == po["vendor_id"])},
        {"field": "PO reference", "invoice": f.get("po_number") or "(none - inferred)", "po": po["po_number"], "ok": method != "inferred"},
        {"field": "Currency", "invoice": f.get("currency"), "po": po["currency"], "ok": (f.get("currency") or po["currency"]) == po["currency"]},
        {"field": "PO value (subtotal)", "invoice": None, "po": fmt_money(pos["po_subtotal"], cur), "ok": None},
        {"field": "Previously invoiced", "invoice": None, "po": fmt_money(pos["billed_subtotal"], cur), "ok": None},
        {"field": "Subtotal vs remaining", "invoice": fmt_money(inv_sub, cur), "po": fmt_money(remaining, cur),
         "ok": inv_sub is not None and inv_sub - remaining <= info.get("tolerance", 0)},
        {"field": "Tax", "invoice": fmt_money(tax, cur), "po": f"{fmt_money(po_tax_on_inv, cur)} @ {po['tax_rate']:.2%}",
         "ok": tax is not None and abs((tax or 0) - po_tax_on_inv) <= 0.05},
    ]
    return out, info
