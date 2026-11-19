"""Gemini-based document understanding (Google AI Studio free tier works).

The PDF itself (not our OCR text) is sent to Gemini, so scanned pages, odd layouts and
implied references are read the way a person would read them. Output is constrained to a
JSON schema, so the rest of the pipeline gets the same structure as the deterministic
parser. Gemini only *reads* the invoice - every business rule and the final decision stay
in deterministic code."""
from __future__ import annotations

import json
import time

from google import genai
from google.genai import errors as genai_errors
from google.genai import types

from .. import config

NULLABLE_STR = {"type": ["string", "null"]}
NULLABLE_NUM = {"type": ["number", "null"]}

FIELD_KEYS = ["vendor_name", "vendor_address", "vendor_email", "vendor_tax_id", "vendor_bank_account", "vendor_bank_name",
              "invoice_number", "invoice_date", "due_date", "po_number", "currency", "subtotal", "tax_amount", "tax_rate",
              "total", "service_period_start", "service_period_end"]

SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["document_type", "document_type_reason", *FIELD_KEYS, "tax_inclusive", "payment_instruction_change",
                 "line_items", "confidence", "evidence", "warnings"],
    "properties": {
        "document_type": {"type": "string", "enum": ["invoice", "credit_note", "statement", "quote", "purchase_order",
                                                     "delivery_note", "receipt", "unknown"]},
        "document_type_reason": {"type": "string"},
        "vendor_name": NULLABLE_STR, "vendor_address": NULLABLE_STR, "vendor_email": NULLABLE_STR,
        "vendor_tax_id": NULLABLE_STR, "vendor_bank_account": NULLABLE_STR, "vendor_bank_name": NULLABLE_STR,
        "invoice_number": NULLABLE_STR,
        "invoice_date": {"type": ["string", "null"], "description": "ISO yyyy-mm-dd"},
        "due_date": {"type": ["string", "null"], "description": "ISO yyyy-mm-dd"},
        "po_number": {"type": ["string", "null"], "description": "Purchase order reference exactly as printed"},
        "currency": {"type": ["string", "null"], "description": "ISO 4217 code"},
        "subtotal": NULLABLE_NUM, "tax_amount": NULLABLE_NUM,
        "tax_rate": {"type": ["number", "null"], "description": "decimal, e.g. 0.0825"},
        "total": NULLABLE_NUM,
        "service_period_start": {"type": ["string", "null"], "description": "ISO yyyy-mm-dd"},
        "service_period_end": {"type": ["string", "null"], "description": "ISO yyyy-mm-dd"},
        "tax_inclusive": {"type": "boolean"},
        "payment_instruction_change": {"type": "boolean",
                                       "description": "true if the document announces new/changed bank or remittance details"},
        "line_items": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "required": ["description", "quantity", "unit_price", "amount", "is_ancillary_charge"],
            "properties": {"description": {"type": "string"}, "quantity": NULLABLE_NUM, "unit_price": NULLABLE_NUM,
                           "amount": NULLABLE_NUM, "is_ancillary_charge": {"type": "boolean"}}}},
        "confidence": {"type": "object", "additionalProperties": False,
                       "required": ["vendor_name", "invoice_number", "invoice_date", "po_number", "total", "line_items"],
                       "properties": {k: {"type": "number"} for k in
                                      ["vendor_name", "invoice_number", "invoice_date", "po_number", "total", "line_items"]}},
        "evidence": {"type": "object", "additionalProperties": False,
                     "required": ["invoice_number", "invoice_date", "po_number", "total"],
                     "properties": {k: NULLABLE_STR for k in ["invoice_number", "invoice_date", "po_number", "total"]}},
        "warnings": {"type": "array", "items": {"type": "string"}},
    },
}

PROMPT = """You are the document-reading step of an accounts-payable automation for Meridian Home Goods Inc. (the buyer).
Read the attached document and extract what is printed on it. Rules:
- Extract only what the document shows. Use null when a field is absent or illegible; never guess or compute a value
  that is not printed (e.g. do not invent an invoice number, do not derive a total).
- vendor_* fields describe the party issuing the document (the seller), never Meridian Home Goods.
- po_number: copy the purchase-order reference exactly as printed, including odd formats ("PO 2026/0398",
  "Purchase Order 0431"). If no PO reference appears anywhere, null.
- Dates as ISO yyyy-mm-dd. If a numeric date is ambiguous (e.g. 11/12/2026), assume the vendor's local convention
  (US vendors MM/DD) and add a warning saying so.
- Line items: one entry per printed row. A bundled row with only an amount keeps quantity/unit_price null.
  is_ancillary_charge = true only for an add-on fee charged on top of the goods/services being bought
  (e.g. a "Freight & handling" line on a parts invoice, a fuel surcharge). If the purchased service itself is
  freight or logistics (e.g. "Dedicated freight services"), that line is NOT ancillary.
- tax_inclusive = true only if the document states prices include tax.
- confidence: your 0-1 confidence that each value is exactly right (lower it for blur, OCR-like noise, ambiguity).
- evidence: the short verbatim text you read each value from.
- warnings: anything an AP clerk should know (illegible areas, inconsistencies, notes about changed bank details,
  'copy'/'reminder' stamps, ambiguous dates)."""


def _call(client, model: str, contents, schema: dict | None):
    cfg = dict(response_mime_type="application/json", temperature=0.0, max_output_tokens=8192)
    if schema is not None:
        cfg["response_json_schema"] = schema
    return client.models.generate_content(model=model, contents=contents, config=types.GenerateContentConfig(**cfg))


# Errors that mean "this model can't serve us right now" -> try the next model in the chain.
# 429 quota exhausted, 404 model retired for this key, 5xx overloaded / unavailable (common on the free tier).
_SKIP_MODEL_CODES = {404, 429, 500, 502, 503, 504}


def _call_model(client, model: str, contents):
    try:
        return _call(client, model, contents, SCHEMA)
    except genai_errors.ClientError as e:
        if getattr(e, "code", None) in _SKIP_MODEL_CODES:
            raise
        # Some models reject parts of strict JSON Schema; retry asking for JSON that follows the prompt.
        return _call(client, model, contents + ["Return JSON with exactly these keys: " + ", ".join(SCHEMA["required"])], None)


def extract(pdf_bytes: bytes) -> dict:
    contents = [types.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf"), PROMPT]
    resp, used, failures = None, None, []
    deadline = time.monotonic() + config.LLM_TOTAL_BUDGET_S
    for model in config.gemini_models():
        remaining = deadline - time.monotonic()
        if remaining < 3:
            failures.append("time budget exhausted")
            break
        # A fresh client per attempt so the timeout never exceeds what's left of the budget; SDK retries off -
        # the model chain itself is our retry strategy.
        client = genai.Client(api_key=config.gemini_key(), http_options=types.HttpOptions(
            timeout=int(min(config.LLM_TIMEOUT_S, remaining) * 1000),
            retry_options=types.HttpRetryOptions(attempts=1)))
        try:
            resp, used = _call_model(client, model, contents), model
            break
        except (genai_errors.ClientError, genai_errors.ServerError) as e:
            code = getattr(e, "code", None)
            if code not in _SKIP_MODEL_CODES:
                raise
            failures.append(f"{model}: {code}")
        except Exception as e:  # noqa: BLE001 - network timeouts etc.: move on to the next model
            if "timeout" not in type(e).__name__.lower() and "timed out" not in str(e).lower():
                raise
            failures.append(f"{model}: timeout")
    if resp is None:
        raise RuntimeError("All Gemini models unavailable (" + "; ".join(failures) + ")")
    if not resp.candidates:
        raise RuntimeError("Gemini returned no candidates (request blocked)")
    finish = str(resp.candidates[0].finish_reason or "")
    if "MAX_TOKENS" in finish:
        raise RuntimeError("Extraction output was truncated")
    if "SAFETY" in finish or "RECITATION" in finish or not resp.text:
        raise RuntimeError(f"Gemini did not return content ({finish or 'empty response'})")
    data = json.loads(resp.text)
    for k in SCHEMA["required"]:            # tolerate partial objects from the schema-less retry
        data.setdefault(k, [] if k in ("line_items", "warnings") else {} if k in ("confidence", "evidence") else
                        False if k in ("tax_inclusive", "payment_instruction_change") else
                        "unknown" if k == "document_type" else None)
    out = _to_common(data, used)
    if failures:
        out["warnings"].append(f"Primary model busy ({'; '.join(failures)}); read with {used}.")
    return out


def _to_common(d: dict, model: str) -> dict:
    conf = d.get("confidence") or {}
    ev = d.get("evidence") or {}

    def f(key, default_conf=0.9):
        v = d.get(key)
        c = conf.get(key, default_conf) if v is not None else 0.0
        return {"value": v, "confidence": round(float(c), 2), "evidence": ev.get(key), "method": "llm"}

    fields = {k: f(k) for k in FIELD_KEYS}
    fields["document_type"] = {"value": d["document_type"], "confidence": 0.95, "evidence": d.get("document_type_reason"),
                               "method": "llm"}
    fields["tax_inclusive"] = {"value": d["tax_inclusive"], "confidence": 0.9, "evidence": None, "method": "llm"}
    fields["payment_instruction_change"] = {"value": d["payment_instruction_change"], "confidence": 0.9,
                                            "evidence": None, "method": "llm"}
    li_conf = float(conf.get("line_items", 0.9))
    items = [{"description": it["description"], "quantity": it["quantity"], "unit_price": it["unit_price"],
              "amount": it["amount"], "ancillary": it["is_ancillary_charge"], "confidence": round(li_conf, 2)}
             for it in d.get("line_items", [])]
    return {"engine": f"llm:{model}", "fields": fields, "line_items": items, "warnings": d.get("warnings", [])}
