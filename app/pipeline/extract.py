"""Stage B - Information extraction orchestrator.

Strategy: when Gemini is configured it is the primary reader, and the deterministic parser
runs alongside it as an independent second opinion. Fields where the two engines agree are
marked "confirmed"; fields where they disagree get their confidence cut and are surfaced to
the reviewer. Without an API key the parser runs alone, so the system always works."""
from __future__ import annotations

from .. import config
from ..utils import close, norm_invoice_number
from . import extract_llm, extract_rules

CROSS_CHECK = ["invoice_number", "invoice_date", "po_number", "subtotal", "tax_amount", "total", "vendor_tax_id",
               "vendor_bank_account"]


def _same(key, a, b) -> bool:
    if a is None or b is None:
        return a is None and b is None
    if key in ("subtotal", "tax_amount", "total"):
        return close(float(a), float(b), 0.01)
    if key == "po_number":
        return "".join(ch for ch in str(a) if ch.isdigit()) == "".join(ch for ch in str(b) if ch.isdigit())
    if key in ("invoice_number",):
        return norm_invoice_number(a) == norm_invoice_number(b)
    return str(a).replace(" ", "").replace("-", "").lower() == str(b).replace(" ", "").replace("-", "").lower()


def _guard_ancillary(ext: dict, log) -> None:
    """An add-on charge (freight, handling, surcharge) is by definition secondary to what was bought.
    Never let the model classify the sole line, or a line carrying most of the invoice value, as ancillary -
    that would turn a logistics provider's main service into a 'non-PO charge'."""
    items = ext["line_items"]
    total = sum(abs(i.get("amount") or 0) for i in items) or 0
    for it in items:
        if not it.get("ancillary"):
            continue
        share = abs(it.get("amount") or 0) / total if total else 1
        if len(items) == 1 or share > 0.25:
            it["ancillary"] = False
            log(f"Reclassified '{(it['description'] or '')[:40]}' as a main line, not an add-on charge "
                f"({share:.0%} of invoice value).")


def run(pdf_bytes: bytes, text: str, ocr_confidence: float | None, log) -> dict:
    rules = extract_rules.extract(text, ocr_confidence)
    log(f"Deterministic parser read {sum(1 for f in rules['fields'].values() if f['value'] not in (None, False))} fields "
        f"and {len(rules['line_items'])} line items.")
    if not config.llm_available():
        rules["cross_check"] = None
        rules["engine_note"] = "Gemini not configured (no GEMINI_API_KEY) - deterministic parser used."
        return rules
    try:
        log(f"Sending PDF to Gemini ({config.LLM_MODEL}) for document understanding ...")
        llm = extract_llm.extract(pdf_bytes)
    except Exception as e:  # noqa: BLE001 - any LLM failure degrades gracefully to the parser
        log(f"Gemini extraction unavailable ({e.__class__.__name__}: {str(e)[:120]}); falling back to deterministic parser.")
        rules["cross_check"] = None
        rules["engine_note"] = f"Gemini call failed ({e.__class__.__name__}); deterministic parser used."
        return rules

    checks = []
    for key in CROSS_CHECK:
        a, b = llm["fields"][key]["value"], rules["fields"].get(key, {}).get("value")
        if a is None and b is None:
            continue
        agree = _same(key, a, b)
        checks.append({"field": key, "llm": a, "parser": b, "agree": agree})
        f = llm["fields"][key]
        if agree:
            f["confidence"] = max(f["confidence"], 0.97)
            f["method"] = "llm + parser agree"
        elif a is None and b is not None:
            # Gemini saw nothing, parser did - take parser's value but flag it
            llm["fields"][key] = {**rules["fields"][key], "confidence": min(rules["fields"][key]["confidence"], 0.6),
                                  "method": "parser only (Gemini returned null)"}
        else:
            f["confidence"] = min(f["confidence"], 0.55)
            f["method"] = "engines disagree"
            llm["warnings"].append(f"Engines disagree on {key}: Gemini read '{a}', parser read '{b}'.")
    _guard_ancillary(llm, log)
    llm["cross_check"] = checks
    llm["engine_note"] = "Gemini read the document; deterministic parser cross-checked key fields."
    agree_n = sum(1 for c in checks if c["agree"])
    log(f"Cross-check: {agree_n}/{len(checks)} key fields confirmed by both engines.")
    return llm
