"""Stage G - Decision.

The decision is a pure function of the checks: any reject-severity failure -> REJECT, else any
review-severity failure -> REVIEW, else APPROVE. That keeps every outcome explainable: the reasons
are exactly the failed checks, and each failed check maps to a concrete next action and an owner."""
from __future__ import annotations

from datetime import timedelta

from .. import config
from ..utils import fmt_money, to_date

ACTIONS = {
    "A-INTAKE": ("Vendor", "Ask the vendor to resend the invoice as a valid, unprotected PDF."),
    "A-DOCTYPE": ("AP clerk", "File the document for reference; it is not a payable invoice. No payment action."),
    "V-REQ": ("Vendor", "Request a corrected invoice that includes the missing field(s)."),
    "V-CONF": ("AP clerk", "Verify the low-confidence fields against the PDF and correct them before posting."),
    "V-DATE": ("AP clerk", "Confirm the invoice date with the vendor."),
    "V-DUE": ("AP clerk", "Confirm payment terms / due date with the vendor."),
    "V-LINEMATH": ("Vendor", "Return to vendor: line amounts do not reconcile; request a corrected invoice."),
    "V-SUM": ("Vendor", "Return to vendor: line items do not add up to the subtotal; request a corrected invoice."),
    "V-TOTAL": ("Vendor", "Return to vendor: subtotal + tax does not equal the total; request a corrected invoice."),
    "V-TAXRATE": ("Tax team", "Confirm the tax calculation; request a corrected invoice if wrong."),
    "D-FOUND": ("Procurement", "Do not pay. Route to Procurement: onboard the vendor (W-9, bank verification) and raise a PO, or return to sender."),
    "D-STATUS": ("Vendor management", "Do not pay while the vendor is not approved; Vendor Management to resolve the hold first."),
    "D-TAXID": ("Vendor management", "Verify the vendor's tax ID; update master data only with documentary evidence."),
    "D-DOMAIN": ("Treasury", "Verify the sender via the phone number on the vendor master (not contact details on the invoice)."),
    "D-BANK": ("Treasury", "Call-back verification required: confirm the bank change with the vendor using master-file contact details; Treasury approves any change."),
    "D-BANKNOTICE": ("Treasury", "Treat the change-of-bank request as unverified until confirmed by call-back; do not update bank details from the invoice."),
    "D-FRAUD": ("Security / Treasury", "Fraud hold: do not pay and do not reply to the sender. Report to Security and contact the genuine vendor through master-file contacts."),
    "D-CUR": ("AP clerk", "Confirm billing currency with the vendor."),
    "E-REF": ("Buyer", "Ask the requester/buyer for the correct PO number."),
    "E-FIND": ("Buyer", "Buyer to confirm the PO this invoice belongs to (or raise one - no PO, no pay)."),
    "E-VENDOR": ("AP clerk", "Reject: the PO belongs to a different vendor. Ask the vendor for the correct PO."),
    "E-STATUS": ("Buyer", "PO is not open - buyer to confirm whether it should be re-opened or the invoice rejected."),
    "E-CUR": ("Buyer", "Currency differs from the PO - buyer to confirm."),
    "E-LINES": ("Buyer", "Buyer to confirm the un-ordered items or request a credit note."),
    "E-PRICE": ("Buyer", "Buyer to approve the price variance via PO amendment, or request a corrected invoice."),
    "E-QTY": ("Buyer", "Quantity exceeds what is open on the PO - confirm receipt / amend the PO, or short-pay."),
    "E-AMOUNT": ("Buyer", "Amount exceeds the PO balance beyond tolerance - PO amendment or corrected invoice required."),
    "E-ANC": ("Buyer", "Buyer to approve the non-PO charges."),
    "E-TAX": ("Tax team", "Tax rate differs from the PO - confirm the correct rate; request a corrected invoice if the PO rate applies."),
    "F-FILE": ("AP clerk", "Do not pay - this file was already processed. Close as duplicate."),
    "F-INV": ("AP clerk", "Do not pay - duplicate of an invoice already recorded. Notify the vendor of the original's status."),
    "F-FUZZY": ("AP clerk", "Compare with the earlier invoice; if it is the same supply, reject as duplicate."),
}

SEV_ORDER = {"reject": 0, "review": 1}

# Short, human phrasing of each issue for headlines and the dashboard.
ISSUE = {
    "A-INTAKE": "file could not be read", "A-READ": "nothing legible on the document", "A-DOCTYPE": "document is not an invoice",
    "V-REQ": "missing critical fields", "V-CONF": "low-confidence extraction", "V-DATE": "implausible invoice date",
    "V-DUE": "due date before invoice date", "V-LINEMATH": "line arithmetic errors", "V-SUM": "lines do not add up to subtotal",
    "V-TOTAL": "subtotal + tax does not equal total", "V-TAXRATE": "tax does not match stated rate",
    "D-FOUND": "vendor not in vendor master", "D-STATUS": "vendor is not approved", "D-TAXID": "tax ID mismatch",
    "D-DOMAIN": "look-alike sender domain", "D-BANK": "bank account differs from master", "D-BANKNOTICE": "change-of-bank request",
    "D-FRAUD": "possible vendor impersonation", "D-CUR": "currency differs from vendor setup",
    "E-REF": "PO reference not found", "E-FIND": "PO not referenced", "E-VENDOR": "PO belongs to another vendor",
    "E-STATUS": "PO not open", "E-CUR": "currency differs from PO", "E-LINES": "items not on PO", "E-PRICE": "unit price above PO",
    "E-QTY": "quantity exceeds PO", "E-AMOUNT": "amount exceeds PO balance", "E-ANC": "non-PO charges over allowance",
    "E-TAX": "tax rate differs from PO", "F-FILE": "file already processed", "F-INV": "duplicate invoice",
    "F-FUZZY": "possible duplicate",
}


def issue(c: dict, po_info: dict | None = None) -> str:
    if c["id"] == "E-FIND" and (po_info or {}).get("method") == "inferred":
        return f"PO not referenced - {(po_info or {}).get('po', {}).get('po_number')} inferred, needs confirmation"
    if c["id"] == "D-STATUS":
        return "vendor is " + c["message"].split("'")[1].lower() if "'" in c["message"] else ISSUE["D-STATUS"]
    if c["id"] in ("F-INV", "F-FUZZY") and (c.get("evidence") or {}).get("match"):
        return f"{ISSUE[c['id']]} of {c['evidence']['match']}"
    return ISSUE.get(c["id"], c["name"].lower())


def approver_for(amount: float | None) -> str:
    for tier in config.policy()["approval_routing"]:
        if tier["max_amount"] is None or (amount or 0) <= tier["max_amount"]:
            return tier["approver"]
    return "Controller"


def decide(checks: list[dict], extracted: dict, vendor: dict | None, po_info: dict | None) -> dict:
    fails = sorted([c for c in checks if c["status"] == "fail"], key=lambda c: SEV_ORDER.get(c["severity"], 2))
    warns = [c for c in checks if c["status"] == "warn"]
    passed = [c for c in checks if c["status"] == "pass"]
    cur = extracted.get("currency") or "USD"
    total = extracted.get("total")
    po = (po_info or {}).get("po")

    if any(c["severity"] == "reject" for c in fails):
        outcome = "REJECT"
    elif fails:
        outcome = "REVIEW"
    else:
        outcome = "APPROVE"

    actions, seen = [], set()
    for c in fails:
        owner, text = ACTIONS.get(c["id"], ("AP clerk", "Investigate: " + c["message"]))
        if c["id"] == "E-FIND" and po and (po_info or {}).get("method") == "inferred":
            text = f"Buyer {po.get('buyer', '')} to confirm {po['po_number']} is the right PO, then release for approval."
        if c["id"] in ("E-PRICE", "E-AMOUNT", "E-QTY", "E-ANC") and po:
            owner = f"Buyer - {po.get('buyer', 'buyer')}"
        if c["id"] == "D-FRAUD" and vendor:
            text += f" Genuine vendor phone on file: {vendor.get('contact_phone')}."
        if c["id"] == "D-STATUS" and vendor and vendor.get("status_reason"):
            text += f" Hold reason: {vendor['status_reason']}"
        if text not in seen:
            seen.add(text)
            actions.append({"owner": owner, "action": text, "from_check": c["id"]})

    if outcome == "APPROVE":
        appr = approver_for(total)
        terms = (vendor or {}).get("payment_terms", "Net 30")
        days = int("".join(ch for ch in terms if ch.isdigit()) or 30)
        d = to_date(extracted.get("invoice_date"))
        due = (d + timedelta(days=days)).isoformat() if d else None
        actions = [{"owner": appr, "action": f"Release for payment approval ({appr} - amount {fmt_money(total, cur)}).", "from_check": None},
                   {"owner": "AP clerk", "action": f"Post to ERP against {po['po_number'] if po else 'PO'} and schedule payment"
                                                   + (f" for {due} ({terms})." if due else "."), "from_check": None}]

    if outcome == "APPROVE":
        headline = f"Approved for payment - all controls passed" + (f"; matched to {po['po_number']}" if po else "")
        if warns:
            headline += f" ({len(warns)} note{'s' if len(warns) != 1 else ''} for the record)"
    elif outcome == "REVIEW":
        headline = "Needs manual review - " + "; ".join(issue(c, po_info) for c in fails[:3]) + \
            (f" (+{len(fails) - 3} more)" if len(fails) > 3 else "")
    else:
        rej = [c for c in fails if c["severity"] == "reject"]
        headline = "Rejected - " + "; ".join(issue(c, po_info) for c in rej[:2])

    queue = None
    if outcome != "APPROVE":
        queue = actions[0]["owner"] if actions else "AP clerk"
    priority = "high" if any(c["id"].startswith("D-") and c["status"] == "fail" for c in fails) else \
        ("medium" if outcome == "REVIEW" else ("high" if outcome == "REJECT" else "normal"))

    return {
        "outcome": outcome,
        "headline": headline,
        "reasons": [{"check": c["id"], "stage": c["stage"], "severity": c["severity"], "issue": issue(c, po_info),
                     "text": c["message"]} for c in fails],
        "notes": [{"check": c["id"], "text": c["message"]} for c in warns],
        "next_actions": actions,
        "queue": queue,
        "priority": priority,
        "counts": {"passed": len(passed), "warnings": len(warns), "failed": len(fails), "total": len(checks)},
        "approver": approver_for(total) if outcome == "APPROVE" else None,
    }
