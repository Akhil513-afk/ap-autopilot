"""Deterministic, layout-agnostic invoice parser.

Works on the plain text produced by the reader (text layer or OCR). It does not rely on
coordinates or a vendor template: it looks for label vocabularies ("Invoice #", "Bill
Number", "Your Order Ref", "Amount Due", ...) and for line-item rows whose trailing numbers
satisfy qty x price = amount in any column order. Every field carries a confidence and
the evidence line it came from, so the UI can show *why* a value was extracted."""
from __future__ import annotations

import re
from typing import Optional

from ..utils import parse_date, parse_money

NUM_RE = re.compile(r"(?<![\w/.\-])[$€£₹]?\d{1,3}(?:,\d{3})+(?:\.\d+)?(?![\w/%])|(?<![\w/.])[$€£₹]?\d+(?:\.\d+)?(?![\w/%])")
MONEY_RE = re.compile(r"\(?-?[$€£₹]?\s?\d{1,3}(?:,\d{3})*\.\d{2}\)?|\(?-?[$€£₹]?\s?\d+\.\d{2}\)?")
EMAIL_RE = re.compile(r"[\w.+-]+@\s?[\w-]+(?:\.[\w-]+)+")

INV_NO_RE = re.compile(
    r"\b(?:invoice\s*(?:no\.?|number|num\.?|#)|inv\.?\s*(?:no\.?|#)|bill\s*(?:no\.?|number|#)|document\s*(?:no\.?|number))"
    r"\s*[:#.]?\s*([A-Z0-9][A-Z0-9\-/_.]{2,})", re.I)
DATE_LABELS = [r"invoice\s*date", r"date\s*of\s*issue", r"bill\s*date", r"issue\s*date", r"issued(?:\s*on)?", r"dated", r"date"]
DUE_RE = re.compile(r"\bdue\s*date\s*[:]?\s*(.+)", re.I)
PO_RE = re.compile(
    r"(?:\bp\.?\s?o\.?(?=[\s:#]|$)\s*(?:number|no\.?|#|ref(?:erence)?)?|\bpurchase\s*order(?:\s*(?:number|no\.?|#|ref))?"
    r"|\byour\s*(?:order\s*)?ref(?:erence)?|\border\s*ref(?:erence)?|\bcustomer\s*po|\bref(?:erence)?)\s*[:#.]?\s*([^\n]+)", re.I)
PO_TOKEN_RE = re.compile(r"\bPO[\s\-#:]*\d{4}[\s\-/]*\d{3,5}\b|\bPO[\s\-#:]*\d{3,8}\b", re.I)
TAXID_RE = re.compile(r"\b(?:fed(?:eral)?\s*tax\s*id|tax\s*id|ein|tin|vat\s*(?:no\.?|number|reg(?:istration)?)|gstin)\s*[:#.]?\s*([A-Z0-9][A-Z0-9\-]{5,})", re.I)
BANK_ACCT_RE = re.compile(r"\b(?:account\s*(?:no\.?|number|#)?|acct\.?|a/c)\s*[:#.]?\s*(\d[\d\- ]{5,}\d)", re.I)
BANK_NAME_RE = re.compile(r"([A-Z][A-Za-z&.]*(?:\s+[A-Z][A-Za-z&.]*){0,4}\s+Bank)\b")
BANK_CHANGE_RE = re.compile(r"(bank(?:ing)?\s*details\s*have\s*changed|new\s*bank(?:ing)?\s*(?:details|account)|updated?\s*(?:our\s*)?bank|change\s*of\s*bank|remit\s*to\s*(?:our\s*)?new)", re.I)
PERIOD_RE = re.compile(r"\b(?:service\s*period|billing\s*period|period(?:\s*covered)?)\s*[:]?\s*(.+)", re.I)

SUBTOTAL_RE = re.compile(r"\b(sub[\s-]?total|net\s*amount|net\s*total|total\s*before\s*tax|taxable\s*amount|amount\s*before\s*tax)\b", re.I)
TAX_RE = re.compile(r"\b(sales\s*tax|tax|vat|gst|hst|igst|cgst|sgst)\b", re.I)
TAX_EXCLUDE_RE = re.compile(r"tax\s*id|fed\s*tax|tax\s*invoice|\btin\b|\bein\b|incl(?:uding|usive|\.)?\s*(?:of\s*)?(?:tax|vat|gst)|tax\s*registration", re.I)
TOTAL_LABELS = [r"grand\s*total", r"total\s*due", r"amount\s*due", r"balance\s*due", r"total\s*payable", r"amount\s*payable",
                r"total\s*amount", r"invoice\s*total", r"total\s*(?:usd|eur|gbp|inr)", r"total"]
TAX_INCLUSIVE_RE = re.compile(r"(incl(?:uding|usive|\.)?\s*(?:of\s*)?(?:all\s*)?(?:tax|taxes|vat|gst))|(prices?\s*include\s*(?:tax|vat|gst))", re.I)
ITEM_HEADER_RE = re.compile(r"(description|item|deliverable|service|particulars)", re.I)
ITEM_HEADER_NUM_RE = re.compile(r"(qty|quantity|units?|hrs|hours)", re.I)
ANCILLARY_RE = re.compile(r"^\s*(freight|shipping|delivery\s*charge|handling|surcharge|fuel\s*surcharge|postage|carriage|courier)", re.I)


def _f(value, conf, evidence=None, method="label"):
    return {"value": value, "confidence": round(conf, 2), "evidence": evidence, "method": method}


def _money_on(line: str) -> list[float]:
    vals = []
    for m in MONEY_RE.finditer(line):
        v = parse_money(m.group(0))
        if v is not None:
            vals.append(v)
    return vals


def _detect_doc_type(text: str) -> tuple[str, str]:
    t = text.lower()
    if re.search(r"statement\s+of\s+account|account\s+statement|not\s+a\s+tax\s+invoice", t):
        return "statement", "Contains 'statement of account' / 'not a tax invoice'"
    if re.search(r"credit\s*(note|memo)", t):
        return "credit_note", "Contains 'credit note/memo'"
    if re.search(r"\b(quotation|quote\s*no|estimate)\b", t) and "invoice" not in t:
        return "quote", "Quotation / estimate wording, no 'invoice'"
    if re.search(r"^\s*purchase\s+order\s*$", t, re.M) and "invoice" not in t:
        return "purchase_order", "Document titled 'Purchase Order'"
    if re.search(r"\b(packing\s+slip|delivery\s+note)\b", t) and "invoice" not in t:
        return "delivery_note", "Packing slip / delivery note"
    if re.search(r"\b(invoice|bill\s*(?:no|number)|tax\s*invoice)\b", t):
        return "invoice", "Contains invoice wording"
    return "unknown", "No invoice wording found"


def _currency(text: str) -> tuple[Optional[str], float, str]:
    codes = re.findall(r"\b(USD|EUR|GBP|INR|CAD|AUD)\b", text)
    if codes:
        return max(set(codes), key=codes.count), 0.95, f"Currency code '{codes[0]}' on document"
    for sym, cur in (("$", "USD"), ("€", "EUR"), ("£", "GBP"), ("₹", "INR")):
        if sym in text:
            return cur, 0.8, f"Currency symbol '{sym}'"
    return None, 0.0, ""


def _label_amount(lines: list[str], regex_list, exclude=None) -> Optional[tuple[float, str]]:
    for pattern in regex_list:
        rx = re.compile(r"\b" + pattern + r"\b", re.I)
        for ln in reversed(lines):  # totals usually live at the bottom
            if rx.search(ln) and not (exclude and exclude.search(ln)):
                if re.search(r"sub[\s-]?total|line\s*total", ln, re.I) and "sub" not in pattern and "line" not in pattern:
                    continue
                vals = _money_on(ln)
                if vals:
                    return vals[-1], ln.strip()
    return None


def _parse_line_items(lines: list[str]) -> tuple[list[dict], list[str]]:
    notes = []
    start = None
    for i, ln in enumerate(lines):
        if ITEM_HEADER_RE.search(ln) and (ITEM_HEADER_NUM_RE.search(ln) or re.search(r"amount|total|price", ln, re.I)) \
                and not _money_on(ln):
            start = i + 1
            break
    end = len(lines)
    # The item table ends at the first totals-block line: subtotal, any total label
    # ("Amount Due", "Balance Due", "Total Payable", ...) or a tax line, matched at line start
    # so item descriptions that merely contain "total" are not cut off.
    totals_start = re.compile(r"^\s*(?:" + "|".join(TOTAL_LABELS) + r"|(?:sales\s*)?tax|vat|gst|hst)\b", re.I)
    for i in range(start or 0, len(lines)):
        if SUBTOTAL_RE.search(lines[i]) or totals_start.search(lines[i]):
            end = i
            break
    if start is None:
        notes.append("No line-item table header found; scanning body rows for qty x price = amount patterns.")
        start = 0
    items = []
    for ln in lines[start:end]:
        toks = [(m.start(), m.group(0)) for m in NUM_RE.finditer(ln)]
        if not toks:
            continue
        nums = [parse_money(t) for _, t in toks]
        has_money = bool(_money_on(ln))
        if not has_money:
            continue
        desc_cut = None
        item = None
        # try last 3 numbers in either qty/price/amount or price/qty/amount order
        if len(nums) >= 3:
            a, b, c = nums[-3:]
            if a and b and c and abs(a * b - c) <= max(0.02, c * 0.0005):
                ta, tb = toks[-3][1], toks[-2][1]
                a_money = "$" in ta or "€" in ta or "£" in ta or "." in ta
                b_money = "$" in tb or "€" in tb or "£" in tb or "." in tb
                if b_money and not a_money:
                    q, p = a, b
                elif a_money and not b_money:
                    q, p = b, a
                else:
                    q, p = (a, b) if a <= b else (b, a)
                item = {"description": None, "quantity": q, "unit_price": p, "amount": c}
                desc_cut = toks[-3][0]
        if item is None and len(nums) >= 2:
            p, c = nums[-2:]
            if p and c and abs(p - c) <= 0.01:
                item = {"description": None, "quantity": 1.0, "unit_price": p, "amount": c, "_qty_inferred": True}
                desc_cut = toks[-2][0]
        if item is None and len(nums) >= 1 and len(ln) > 12:
            c = nums[-1]
            item = {"description": None, "quantity": None, "unit_price": None, "amount": c, "_amount_only": True}
            desc_cut = toks[-1][0]
        if item is None:
            continue
        desc = re.sub(r"[|]+", " ", ln[:desc_cut]).strip(" -|:\t")
        if len(desc) < 3:
            continue
        item["description"] = re.sub(r"\s{2,}", " ", desc)
        items.append(item)
    for it in items:
        if it.pop("_qty_inferred", False):
            notes.append(f"'{it['description'][:40]}': quantity not legible, inferred as 1 because unit price equals amount.")
        if it.pop("_amount_only", False):
            notes.append(f"'{it['description'][:40]}': only an amount is shown (bundled / lump-sum line).")
    return items, notes


def extract(text: str, ocr_confidence: float | None = None) -> dict:
    lines = [ln for ln in text.splitlines() if ln.strip()]
    ocr_factor = 1.0 if ocr_confidence is None else max(0.4, min(1.0, ocr_confidence / 100.0))
    fields: dict = {}
    warnings: list[str] = []

    doc_type, why = _detect_doc_type(text)
    fields["document_type"] = _f(doc_type, 0.9 if doc_type != "unknown" else 0.4, why, "keywords")

    # Vendor: first meaningful header line (letterhead), skipping the document title
    vendor = None
    for ln in lines[:6]:
        s = ln.strip()
        s = re.split(r"\s{2,}|\binvoice\b", s, flags=re.I)[0].strip(" -|—_:").strip()
        if len(s) < 3 or re.fullmatch(r"(tax\s*)?invoice|statement.*|bill", s, re.I) or EMAIL_RE.search(s) or re.search(r"\d{3,}", s):
            continue
        vendor = s
        break
    fields["vendor_name"] = _f(vendor, 0.75 * ocr_factor, lines[0] if lines else None, "letterhead") if vendor else _f(None, 0)

    m = EMAIL_RE.search(text)
    email = m.group(0).replace(" ", "") if m else None
    fields["vendor_email"] = _f(email, 0.9 * ocr_factor if email else 0, email)
    m = TAXID_RE.search(text)
    fields["vendor_tax_id"] = _f(m.group(1).strip(".") if m else None, 0.9 * ocr_factor if m else 0, m.group(0) if m else None)
    m = BANK_ACCT_RE.search(text)
    fields["vendor_bank_account"] = _f(re.sub(r"[\s-]", "", m.group(1)) if m else None, 0.9 * ocr_factor if m else 0, m.group(0) if m else None)
    m = BANK_NAME_RE.search(text)
    fields["vendor_bank_name"] = _f(m.group(1).strip() if m else None, 0.7 if m else 0, m.group(0) if m else None)
    m = BANK_CHANGE_RE.search(text)
    fields["payment_instruction_change"] = _f(bool(m), 0.9, m.group(0) if m else None, "keywords")

    m = INV_NO_RE.search(text)
    if m and not re.fullmatch(r"date|number|no", m.group(1), re.I):
        fields["invoice_number"] = _f(m.group(1).strip("."), 0.95 * ocr_factor, m.group(0).strip())
    else:
        fields["invoice_number"] = _f(None, 0, None, "not found")
        warnings.append("No invoice number label found on the document.")

    inv_date, amb, ev = None, None, None
    for lab in DATE_LABELS:
        rx = re.compile(r"\b" + lab + r"\b\s*[:]?\s*(.{6,40})", re.I)
        for ln in lines:
            if re.search(r"due\s*date|statement\s*date|ship\s*date|delivery\s*date", ln, re.I) and lab == "date":
                continue
            mm = rx.search(ln)
            if mm:
                iso, amb = parse_date(mm.group(1))
                if iso:
                    inv_date, ev = iso, mm.group(0).strip()
                    break
        if inv_date:
            break
    fields["invoice_date"] = _f(inv_date, (0.7 if amb else 0.95) * ocr_factor if inv_date else 0, ev)
    if amb:
        warnings.append(f"Invoice date {amb}.")
    m = DUE_RE.search(text)
    due = parse_date(m.group(1))[0] if m else None
    fields["due_date"] = _f(due, 0.9 if due else 0, m.group(0) if m else None)

    # PO reference
    po_raw, po_ev, po_conf = None, None, 0.0
    m = PO_TOKEN_RE.search(text)
    if m:
        po_raw, po_ev, po_conf = m.group(0).strip(), m.group(0), 0.95
    else:
        for ln in lines:
            mm = PO_RE.search(ln)
            if mm:
                cand = mm.group(1).strip()
                tok = re.search(r"(?:\bPO[\s\-#/:]*)?\d[\d\-/ ]{2,}\d", cand, re.I)
                if tok and not re.search(r"packing|slip|invoice|account", mm.group(0), re.I):
                    po_raw, po_ev, po_conf = tok.group(0).strip(), mm.group(0).strip(), 0.75
                    break
    fields["po_number"] = _f(po_raw, po_conf * ocr_factor, po_ev, "label" if po_raw else "not found")

    period_raw = None
    m = PERIOD_RE.search(text)
    if m:
        period_raw = m.group(1).strip()
        parts = re.split(r"\s+(?:-|–|to|through|until)\s+", period_raw, maxsplit=1)
        if len(parts) == 2:
            s, _ = parse_date(parts[0], prefer_dmy=True)
            e, _ = parse_date(parts[1], prefer_dmy=True)
            fields["service_period_start"] = _f(s, 0.85 if s else 0, m.group(0))
            fields["service_period_end"] = _f(e, 0.85 if e else 0, m.group(0))
    fields.setdefault("service_period_start", _f(None, 0))
    fields.setdefault("service_period_end", _f(None, 0))

    cur, cconf, cev = _currency(text)
    fields["currency"] = _f(cur, cconf, cev, "symbol/code")

    sub = _label_amount(lines, [r"sub[\s-]?total", r"net\s*amount", r"net\s*total", r"total\s*before\s*tax", r"taxable\s*amount"])
    fields["subtotal"] = _f(sub[0] if sub else None, 0.95 * ocr_factor if sub else 0, sub[1] if sub else None)

    tax_val, tax_ev, tax_rate = None, None, None
    for ln in reversed(lines):
        if TAX_RE.search(ln) and not TAX_EXCLUDE_RE.search(ln):
            if re.search(r"exempt|n/?a\b|nil", ln, re.I) and not _money_on(ln):
                tax_val, tax_ev = 0.0, ln.strip()
                break
            vals = _money_on(ln)
            if vals:
                tax_val, tax_ev = vals[-1], ln.strip()
                rm = re.search(r"(\d+(?:\.\d+)?)\s?%", ln)
                if rm:
                    tax_rate = float(rm.group(1)) / 100.0
                break
    fields["tax_amount"] = _f(tax_val, 0.9 * ocr_factor if tax_val is not None else 0, tax_ev)
    fields["tax_rate"] = _f(tax_rate, 0.9 if tax_rate is not None else 0, tax_ev)

    tot = _label_amount(lines, TOTAL_LABELS)
    fields["total"] = _f(tot[0] if tot else None, 0.95 * ocr_factor if tot else 0, tot[1] if tot else None)
    if not tot:
        warnings.append("No total / amount due found.")

    m = TAX_INCLUSIVE_RE.search(text)
    fields["tax_inclusive"] = _f(bool(m), 0.85, m.group(0) if m else None, "keywords")

    items, notes = _parse_line_items(lines)
    warnings.extend(notes)
    for it in items:
        it["confidence"] = round(0.9 * ocr_factor if it.get("quantity") is not None else 0.6 * ocr_factor, 2)
        it["ancillary"] = bool(ANCILLARY_RE.search(it["description"] or ""))

    return {"engine": "rules", "fields": fields, "line_items": items, "warnings": warnings}
