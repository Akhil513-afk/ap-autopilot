"""Gemini extraction path, with the Google client mocked (no network, no key needed)."""
import json
import types as pytypes
from pathlib import Path

import pytest
from google.genai import errors as genai_errors

from app.pipeline import extract, extract_llm, reader

SAMPLE = Path(__file__).resolve().parent.parent / "samples" / "03_edge_scanned_no_po_cobalt.pdf"

FAKE = {
    "document_type": "invoice", "document_type_reason": "Titled INVOICE", "vendor_name": "Cobalt Industrial Parts Co.",
    "vendor_address": None, "vendor_email": "orders@cobaltparts.com", "vendor_tax_id": "91-3348210",
    "vendor_bank_account": "302288150077", "vendor_bank_name": "Great Plains Savings Bank", "invoice_number": "CIP-20931",
    "invoice_date": "2026-11-12", "due_date": None, "po_number": None, "currency": "USD", "subtotal": 2026.0,
    "tax_amount": 167.15, "tax_rate": 0.0825, "total": 2193.15, "service_period_start": None, "service_period_end": None,
    "tax_inclusive": False, "payment_instruction_change": False,
    "line_items": [{"description": "Hydraulic hose assembly 3/4 in", "quantity": 20, "unit_price": 38.75, "amount": 775.0, "is_ancillary_charge": False},
                   {"description": "Freight & handling", "quantity": 1, "unit_price": 35.0, "amount": 35.0, "is_ancillary_charge": True}],
    "confidence": {"vendor_name": 0.95, "invoice_number": 0.9, "invoice_date": 0.7, "po_number": 0.9, "total": 0.92, "line_items": 0.9},
    "evidence": {"invoice_number": "Invoice Number: CIP-20931", "invoice_date": "11/12/2026", "po_number": None, "total": "TOTAL USD 2,193.15"},
    "warnings": ["Date 11/12/2026 is ambiguous; assumed MM/DD"],
}


def _resp(payload):
    cand = pytypes.SimpleNamespace(finish_reason="STOP")
    return pytypes.SimpleNamespace(candidates=[cand], text=json.dumps(payload))


def _install(monkeypatch, behaviour):
    calls = []

    class Models:
        def generate_content(self, model, contents, config):
            calls.append({"model": model, "config": config, "contents": contents})
            return behaviour(len(calls), config)

    class Client:
        def __init__(self, *a, **k):
            self.models = Models()

    monkeypatch.setattr(extract_llm.genai, "Client", Client)
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(extract.config, "USE_LLM", True)
    return calls


def _run():
    data = SAMPLE.read_bytes()
    doc = reader.read(data)
    return extract.run(data, doc.text, doc.ocr_confidence, lambda m: None)


def test_gemini_primary_with_parser_cross_check(monkeypatch):
    calls = _install(monkeypatch, lambda n, cfg: _resp(FAKE))
    out = _run()
    assert out["engine"].startswith("llm:gemini")
    assert calls[0]["config"].response_mime_type == "application/json"
    assert calls[0]["config"].response_json_schema is not None          # structured output requested
    assert calls[0]["contents"][0].inline_data.mime_type == "application/pdf"  # the PDF itself is sent
    assert all(c["agree"] for c in out["cross_check"])
    assert out["fields"]["total"]["confidence"] >= 0.97


def test_schema_rejected_falls_back_to_plain_json(monkeypatch):
    def behaviour(n, cfg):
        if n == 1:
            raise genai_errors.ClientError(400, {"error": {"message": "schema not supported", "status": "INVALID_ARGUMENT"}})
        return _resp(FAKE)
    calls = _install(monkeypatch, behaviour)
    out = _run()
    assert len(calls) == 2 and calls[1]["config"].response_json_schema is None
    assert out["engine"].startswith("llm:gemini")


def test_free_tier_quota_exhausted_falls_back_to_parser(monkeypatch):
    def behaviour(n, cfg):
        raise genai_errors.ClientError(429, {"error": {"message": "quota exceeded", "status": "RESOURCE_EXHAUSTED"}})
    _install(monkeypatch, behaviour)
    out = _run()
    assert out["engine"] == "rules"
    assert "Gemini call failed" in out["engine_note"]


def test_busy_primary_model_falls_through_to_next_model(monkeypatch):
    def behaviour(n, cfg):
        if n == 1:
            raise genai_errors.ServerError(503, {"error": {"message": "high demand", "status": "UNAVAILABLE"}})
        return _resp(FAKE)
    calls = _install(monkeypatch, behaviour)
    out = _run()
    assert calls[0]["model"] != calls[1]["model"]
    assert out["engine"] == f"llm:{calls[1]['model']}"
    assert any("busy" in w for w in out["warnings"])


def test_main_service_line_is_never_treated_as_ancillary(monkeypatch):
    payload = {**FAKE, "line_items": [{"description": "Dedicated freight services - November 2026", "quantity": 1,
                                       "unit_price": 16000.0, "amount": 16000.0, "is_ancillary_charge": True}]}
    _install(monkeypatch, lambda n, cfg: _resp(payload))
    out = _run()
    assert out["line_items"][0]["ancillary"] is False


def test_small_freight_addon_stays_ancillary(monkeypatch):
    _install(monkeypatch, lambda n, cfg: _resp(FAKE))  # $35 freight on a $810 invoice
    out = _run()
    assert [i["ancillary"] for i in out["line_items"]] == [False, True]


def test_no_key_uses_parser(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    out = _run()
    assert out["engine"] == "rules" and "GEMINI_API_KEY" in out["engine_note"]
