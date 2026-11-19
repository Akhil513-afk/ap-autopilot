"""Stage D - Vendor verification against the vendor master.

Identification uses several independent signals (tax ID, name/aliases, email domain, bank
account). Verification then compares every identity attribute on the invoice with the
master record. The combination matters: a near-identical name with a different tax ID,
domain *and* bank account is the classic impersonation / business-email-compromise pattern,
whereas a single changed bank account on an otherwise consistent invoice is a call-back
verification case."""
from __future__ import annotations

import re

from rapidfuzz import fuzz

from .. import config
from ..utils import norm_company
from .checks import check

S = "vendor"


def _digits(s):
    return re.sub(r"\D", "", s or "")


def _domain(email):
    return email.split("@", 1)[1].lower().strip() if email and "@" in email else None


def identify(f: dict) -> tuple[dict | None, dict]:
    vendors = config.vendors()
    name = f.get("vendor_name")
    tax = _digits(f.get("vendor_tax_id"))
    dom = _domain(f.get("vendor_email"))
    best, best_score, signals_best = None, 0.0, {}
    for v in vendors:
        names = [v["name"], *v.get("aliases", [])]
        name_score = max((fuzz.token_sort_ratio(norm_company(name), norm_company(n)) / 100 for n in names), default=0) if name else 0
        sig = {
            "name_score": round(name_score, 3),
            "tax_id_match": bool(tax) and tax == _digits(v["tax_id"]),
            "domain_match": bool(dom) and dom == v["email_domain"],
            "bank_match": bool(_digits(f.get("vendor_bank_account"))) and _digits(f.get("vendor_bank_account")) == _digits(v["bank_account"]),
        }
        score = max(sig["name_score"], 0.99 if sig["tax_id_match"] else 0)
        score += 0.05 * sig["domain_match"] + 0.05 * sig["bank_match"]
        if score > best_score:
            best, best_score, signals_best = v, score, sig
    if best and (signals_best.get("name_score", 0) >= 0.80 or signals_best.get("tax_id_match")):
        method = "tax ID" if signals_best["tax_id_match"] else f"name similarity {signals_best['name_score']:.0%}"
        return best, {**signals_best, "method": method, "score": round(min(best_score, 1.0), 3)}
    return None, {**signals_best, "nearest": best["name"] if best else None, "score": round(best_score, 3)}


def run(ext: dict) -> tuple[list[dict], dict | None]:
    f = {k: v["value"] for k, v in ext["fields"].items()}
    out = []
    v, sig = identify(f)
    if not v:
        near = f" Closest master record: {sig.get('nearest')} ({sig.get('name_score', 0):.0%} name similarity)." if sig.get("nearest") else ""
        out.append(check("D-FOUND", S, "Vendor exists in vendor master", "fail",
                         f"'{f.get('vendor_name') or 'Unknown'}' is not in the approved vendor master.{near} "
                         "Invoices can only be paid to onboarded vendors.", "reject", signals=sig))
        return out, None

    out.append(check("D-FOUND", S, "Vendor exists in vendor master", "pass",
                     f"Identified as {v['name']} ({v['vendor_id']}) by {sig['method']}.", vendor_id=v["vendor_id"]))

    if v["status"] != "approved":
        out.append(check("D-STATUS", S, "Vendor is approved for payment", "fail",
                         f"Vendor status is '{v['status'].upper()}'. {v.get('status_reason', '')}".strip(), "reject"))
    else:
        out.append(check("D-STATUS", S, "Vendor is approved for payment", "pass", "Vendor status: approved."))

    mismatches = []
    # Legal name
    if f.get("vendor_name"):
        exact = norm_company(f["vendor_name"]) == norm_company(v["name"]) and \
            f["vendor_name"].lower().rstrip(".") == v["name"].lower().rstrip(".")
        if exact or any(f["vendor_name"].lower().rstrip(".") == a.lower().rstrip(".") for a in v.get("aliases", [])):
            out.append(check("D-NAME", S, "Legal name matches master", "pass", f"'{f['vendor_name']}' matches."))
        elif norm_company(f["vendor_name"]) == norm_company(v["name"]):
            mismatches.append("legal name")
            out.append(check("D-NAME", S, "Legal name matches master", "warn",
                             f"Invoice says '{f['vendor_name']}', master says '{v['name']}' - same name, different legal entity suffix."))
        else:
            out.append(check("D-NAME", S, "Legal name matches master", "warn",
                             f"Invoice name '{f['vendor_name']}' differs from master '{v['name']}' ({sig['name_score']:.0%} similar)."))
    # Tax ID
    if f.get("vendor_tax_id"):
        if _digits(f["vendor_tax_id"]) == _digits(v["tax_id"]):
            out.append(check("D-TAXID", S, "Tax ID matches master", "pass", f"Tax ID {f['vendor_tax_id']} matches."))
        else:
            mismatches.append("tax ID")
            out.append(check("D-TAXID", S, "Tax ID matches master", "fail",
                             f"Tax ID on invoice {f['vendor_tax_id']} does not match master {v['tax_id']}.", "review"))
    else:
        out.append(check("D-TAXID", S, "Tax ID matches master", "info", "No tax ID printed on invoice."))
    # Email domain
    dom = _domain(f.get("vendor_email"))
    if dom:
        if dom == v["email_domain"]:
            out.append(check("D-DOMAIN", S, "Sender domain matches master", "pass", f"Domain {dom} matches."))
        else:
            mismatches.append("email domain")
            out.append(check("D-DOMAIN", S, "Sender domain matches master", "fail",
                             f"Invoice uses '{dom}', master record is '{v['email_domain']}' (look-alike domain?).", "review"))
    # Bank account
    acct = _digits(f.get("vendor_bank_account"))
    if acct:
        if acct == _digits(v["bank_account"]):
            out.append(check("D-BANK", S, "Remit-to bank account matches master", "pass",
                             f"Account ending {acct[-4:]} matches master."))
        else:
            mismatches.append("bank account")
            out.append(check("D-BANK", S, "Remit-to bank account matches master", "fail",
                             f"Remit-to account ending {acct[-4:]} ({f.get('vendor_bank_name') or 'unknown bank'}) differs from "
                             f"master account ending {v['bank_account'][-4:]} ({v['bank_name']}). Never pay to changed bank "
                             f"details without call-back verification.", "review"))
    if f.get("payment_instruction_change"):
        out.append(check("D-BANKNOTICE", S, "No change-of-bank instruction", "fail",
                         "Invoice contains a notice that banking details have changed - a common payment-fraud tactic.", "review"))

    # Composite impersonation rule
    hard = [m for m in mismatches if m in ("tax ID", "email domain", "bank account")]
    if len(hard) >= 2:
        out.append(check("D-FRAUD", S, "Vendor identity consistent", "fail",
                         f"Possible vendor impersonation: invoice resembles {v['name']} but {', '.join(mismatches)} do not match "
                         "the vendor master. Do not pay; verify with the vendor using contact details on file "
                         f"({v['contact_phone']}).", "reject", mismatches=mismatches))
    elif mismatches:
        out.append(check("D-FRAUD", S, "Vendor identity consistent", "warn",
                         f"Identity attribute(s) differ from master: {', '.join(mismatches)}."))
    else:
        out.append(check("D-FRAUD", S, "Vendor identity consistent", "pass", "All printed identity attributes agree with the master."))

    if f.get("currency") and f["currency"] != v["currency"]:
        out.append(check("D-CUR", S, "Invoice currency matches vendor currency", "fail",
                         f"Invoice in {f['currency']}, vendor is set up to bill in {v['currency']}.", "review"))
    return out, {**v, "match": sig}
