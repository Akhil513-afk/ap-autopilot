"""Stage C - Information validation: completeness, internal arithmetic, plausibility."""
from __future__ import annotations

from datetime import date, timedelta

from .. import config
from ..utils import fmt_money, to_date
from .checks import check

S = "validation"

CRITICAL = {
    "invoice_number": "Invoice number",
    "invoice_date": "Invoice date",
    "total": "Total amount",
    "vendor_name": "Vendor name",
    "currency": "Currency",
}


def today() -> date:
    return to_date(config.AS_OF_DATE) or date.today()


def run(ext: dict) -> tuple[list[dict], dict]:
    pol = config.policy()
    f = {k: v["value"] for k, v in ext["fields"].items()}
    conf = {k: v["confidence"] for k, v in ext["fields"].items()}
    items = ext["line_items"]
    cur = f.get("currency") or "USD"
    out = []
    tol = pol["rounding_tolerance_abs"]

    # Completeness
    missing = [label for k, label in CRITICAL.items() if f.get(k) in (None, "")]
    if missing:
        out.append(check("V-REQ", S, "Critical fields present", "fail",
                         f"Missing critical field(s): {', '.join(missing)}. The invoice cannot be posted without them.",
                         "review", missing=missing))
    else:
        out.append(check("V-REQ", S, "Critical fields present", "pass",
                         "Vendor, invoice number, date, total and currency all present."))

    # Field confidence
    low = [k for k in ("invoice_number", "invoice_date", "total", "po_number", "subtotal")
           if f.get(k) is not None and conf.get(k, 1) < pol["low_confidence_threshold"]]
    if low:
        out.append(check("V-CONF", S, "Extraction confidence", "fail",
                         f"Low-confidence read on: {', '.join(low)}. A person should verify these against the document.",
                         "review", fields={k: {"value": f[k], "confidence": conf[k]} for k in low}))
    else:
        out.append(check("V-CONF", S, "Extraction confidence", "pass",
                         f"All key fields read with confidence >= {pol['low_confidence_threshold']:.0%}."))

    # Dates
    d = to_date(f.get("invoice_date"))
    if d:
        t = today()
        if d > t + timedelta(days=pol["max_future_date_days"]):
            out.append(check("V-DATE", S, "Invoice date plausible", "fail",
                             f"Invoice is dated {d.isoformat()}, in the future relative to {t.isoformat()}.", "review"))
        elif d < t - timedelta(days=pol["max_invoice_age_days"]):
            out.append(check("V-DATE", S, "Invoice date plausible", "fail",
                             f"Invoice dated {d.isoformat()} is older than {pol['max_invoice_age_days']} days - stale or re-sent.",
                             "review"))
        else:
            out.append(check("V-DATE", S, "Invoice date plausible", "pass", f"Dated {d.isoformat()}, within the acceptable window."))
        due = to_date(f.get("due_date"))
        if due and due < d:
            out.append(check("V-DUE", S, "Due date after invoice date", "fail", f"Due date {due} precedes invoice date {d}.", "review"))
    amb = [w for w in ext.get("warnings", []) if "ambiguous" in w.lower()]
    if amb:
        out.append(check("V-DATEFMT", S, "Date format unambiguous", "warn", amb[0]))

    # Line arithmetic
    bad_lines = []
    for i, it in enumerate(items, 1):
        q, p, a = it.get("quantity"), it.get("unit_price"), it.get("amount")
        if q is not None and p is not None and a is not None and abs(q * p - a) > max(tol, 0.005 * abs(a)):
            bad_lines.append({"line": i, "description": it["description"], "qty_x_price": round(q * p, 2), "amount": a})
    if items:
        if bad_lines:
            out.append(check("V-LINEMATH", S, "Line arithmetic (qty x price = amount)", "fail",
                             f"{len(bad_lines)} line(s) where quantity x unit price does not equal the line amount.",
                             "review", lines=bad_lines))
        else:
            out.append(check("V-LINEMATH", S, "Line arithmetic (qty x price = amount)", "pass",
                             f"All {len(items)} line(s) reconcile."))
    else:
        out.append(check("V-LINEMATH", S, "Line items present", "warn", "No line items could be read; matching will rely on totals only."))

    # Subtotal = sum(lines)
    sub, tax, tot = f.get("subtotal"), f.get("tax_amount"), f.get("total")
    line_sum = round(sum((it.get("amount") or 0) for it in items), 2) if items else None
    if f.get("tax_inclusive") and line_sum is not None and tot is not None:
        ok = abs(line_sum - tot) <= tol
        out.append(check("V-SUM", S, "Line items sum to total (tax-inclusive pricing)", "pass" if ok else "fail",
                         f"Lines sum to {fmt_money(line_sum, cur)}; tax-inclusive total {fmt_money(tot, cur)}.", "review"))
    elif line_sum is not None and sub is not None:
        ok = abs(line_sum - sub) <= tol
        out.append(check("V-SUM", S, "Line items sum to subtotal", "pass" if ok else "fail",
                         f"Lines sum to {fmt_money(line_sum, cur)} vs stated subtotal {fmt_money(sub, cur)}"
                         + ("." if ok else f" - difference {fmt_money(abs(line_sum - sub), cur)}."), "review"))
    if sub is None and line_sum is not None and tot is not None:
        sub = line_sum  # derived for downstream use, flagged below
        out.append(check("V-SUBDER", S, "Subtotal stated", "warn", f"No subtotal printed; derived {fmt_money(sub, cur)} from line items."))

    # Subtotal + tax = total
    if sub is not None and tot is not None and not f.get("tax_inclusive"):
        t = tax or 0.0
        ok = abs(sub + t - tot) <= tol
        out.append(check("V-TOTAL", S, "Subtotal + tax = total", "pass" if ok else "fail",
                         f"{fmt_money(sub, cur)} + {fmt_money(t, cur)} tax = {fmt_money(sub + t, cur)}; document total {fmt_money(tot, cur)}"
                         + ("." if ok else f" - off by {fmt_money(abs(sub + t - tot), cur)}."), "review"))
    # Stated tax rate vs amount
    rate = f.get("tax_rate")
    if rate and sub and tax is not None:
        implied = tax / sub if sub else 0
        if abs(implied - rate) > 0.001:
            out.append(check("V-TAXRATE", S, "Tax amount matches stated rate", "fail",
                             f"Stated rate {rate:.2%} but tax {fmt_money(tax, cur)} implies {implied:.2%}.", "review"))
        else:
            out.append(check("V-TAXRATE", S, "Tax amount matches stated rate", "pass",
                             f"Tax {fmt_money(tax, cur)} = {rate:.2%} of subtotal."))

    derived = {"subtotal": sub, "line_sum": line_sum}
    return out, derived
