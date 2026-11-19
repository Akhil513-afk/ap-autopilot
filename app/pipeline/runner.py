"""Runs one invoice through every stage, persisting a step-by-step event log as it goes.

Each stage writes stage_start / log / stage_done events to SQLite. The UI streams these over
SSE, so the live run view and the audit trail are the same data."""
from __future__ import annotations

import time
import traceback

from .. import config, db
from . import decision, duplicates, extract, po_match, reader, validate, vendor as vendor_stage
from .checks import check

STAGES = [
    ("intake", "Intake & file checks"),
    ("read", "Read document"),
    ("extract", "Extract invoice data"),
    ("validation", "Validate data"),
    ("vendor", "Verify vendor"),
    ("po_match", "Match purchase order"),
    ("duplicates", "Detect duplicates"),
    ("decision", "Decision"),
]


def _status_of(checks: list[dict]) -> str:
    if any(c["status"] == "fail" and c["severity"] == "reject" for c in checks):
        return "fail"
    if any(c["status"] == "fail" for c in checks):
        return "review"
    if any(c["status"] == "warn" for c in checks):
        return "warn"
    return "pass"


class Run:
    def __init__(self, run_id: str, data: bytes, filename: str):
        self.id = run_id
        self.data = data
        self.filename = filename
        self.checks: list[dict] = []
        self.result: dict = {"stages": {}}
        self.t0 = time.time()

    def log(self, stage: str, msg: str, data=None):
        db.add_event(self.id, stage, "log", msg, data=data)

    def start(self, stage: str):
        label = dict(STAGES)[stage]
        db.update_run(self.id, current_stage=stage, status="processing")
        db.add_event(self.id, stage, "stage_start", f"{label} started")
        self.result["stages"][stage] = {"status": "running", "started": db.now()}
        self._st = time.time()

    def done(self, stage: str, status: str, summary: str, checks: list[dict] | None = None, data=None):
        checks = checks or []
        self.checks.extend(checks)
        ms = int((time.time() - self._st) * 1000)
        self.result["stages"][stage] = {"status": status, "summary": summary, "ms": ms, "checks": [c["id"] for c in checks]}
        db.add_event(self.id, stage, "stage_done", summary, status=status, data={"checks": checks, "ms": ms, **(data or {})})
        if config.STAGE_PACING:
            time.sleep(config.STAGE_PACING)

    def skip_rest(self, after: str, reason: str):
        names = [s for s, _ in STAGES]
        for s in names[names.index(after) + 1:-1]:
            self.result["stages"][s] = {"status": "skipped", "summary": reason}
            db.add_event(self.id, s, "stage_done", f"Skipped - {reason}", status="skipped")

    # ------------------------------------------------------------------ main flow
    def execute(self):
        try:
            self._execute()
        except Exception as e:  # noqa: BLE001
            tb = traceback.format_exc()
            db.add_event(self.id, "system", "error", f"Unexpected error: {e}", status="fail", data={"traceback": tb})
            db.update_run(self.id, status="error", final_status="error", headline=f"Processing error: {e}",
                          duration_ms=int((time.time() - self.t0) * 1000))

    def _execute(self):
        r = self.result
        # A. Intake
        self.start("intake")
        self.log("intake", f"Received '{self.filename}' ({len(self.data):,} bytes).")
        try:
            meta = reader.intake(self.data, self.filename)
        except reader.IntakeError as e:
            c = check("A-INTAKE", "intake", "File is a readable PDF", "fail", e.message, "reject", code=e.code)
            self.done("intake", "fail", e.message, [c])
            self.skip_rest("intake", "document could not be opened")
            return self._finish({}, None, None)
        r["document"] = meta
        self.log("intake", f"Valid PDF: {meta['pages']} page(s), SHA-256 {meta['sha256'][:16]}...")
        self.done("intake", "pass", f"Valid PDF, {meta['pages']} page(s).",
                  [check("A-INTAKE", "intake", "File is a readable PDF", "pass", f"PDF opened: {meta['pages']} page(s).")])

        # A2. Read (text layer vs OCR)
        self.start("read")
        doc = reader.read(self.data)
        for n in doc.notes:
            self.log("read", n)
        r["document"].update(method=doc.method, ocr_confidence=doc.ocr_confidence, page_methods=doc.page_methods,
                             text=doc.text)
        if not doc.text.strip():
            c = check("A-READ", "read", "Document has legible content", "fail",
                      "No text could be read from the document even with OCR (blank or illegible scan).", "reject")
            self.done("read", "fail", "Nothing legible on the page.", [c])
            self.skip_rest("read", "no legible content")
            return self._finish({}, None, None)
        if doc.method == "text-layer":
            summ = f"Machine-readable PDF - text layer extracted ({len(doc.text):,} chars)."
            rc = check("A-READ", "read", "Document has legible content", "pass", summ)
        else:
            summ = f"Scanned document - OCR applied, mean confidence {doc.ocr_confidence:.0f}%."
            rc = check("A-READ", "read", "Document has legible content",
                       "pass" if (doc.ocr_confidence or 0) >= 70 else "warn", summ)
        self.done("read", rc["status"], summ, [rc], data={"method": doc.method, "ocr_confidence": doc.ocr_confidence,
                                                         "text_preview": doc.text[:1500]})

        # B. Extract
        self.start("extract")
        ext = extract.run(self.data, doc.text, doc.ocr_confidence, lambda m: self.log("extract", m))
        flat = {k: v["value"] for k, v in ext["fields"].items()}
        flat["lines"] = [{"description": i["description"], "qty": i.get("quantity"), "unit_price": i.get("unit_price")}
                         for i in ext["line_items"]]
        r["extraction"] = ext
        r["extracted"] = flat
        db.update_run(self.id, engine=ext["engine"], vendor_name=flat.get("vendor_name"), invoice_number=flat.get("invoice_number"),
                      po_number=flat.get("po_number"), total=flat.get("total"), currency=flat.get("currency"))
        for w in ext.get("warnings", []):
            self.log("extract", "Note: " + w)
        dtype = flat.get("document_type")
        ex_checks = []
        if dtype != "invoice":
            ex_checks.append(check("A-DOCTYPE", "extract", "Document is an invoice", "fail",
                                   f"Document classified as '{(dtype or 'unknown').replace('_', ' ')}', not an invoice "
                                   f"({ext['fields']['document_type'].get('evidence')}). It cannot be processed for payment.",
                                   "reject"))
        else:
            ex_checks.append(check("A-DOCTYPE", "extract", "Document is an invoice", "pass", "Classified as an invoice."))
        n_found = sum(1 for k, v in ext["fields"].items() if v["value"] not in (None, False))
        summ = f"{n_found} fields and {len(ext['line_items'])} line item(s) extracted via {ext['engine']}."
        self.done("extract", _status_of(ex_checks), summ, ex_checks,
                  data={"fields": ext["fields"], "line_items": ext["line_items"], "engine": ext["engine"],
                        "engine_note": ext.get("engine_note"), "cross_check": ext.get("cross_check")})
        if dtype != "invoice":
            self.skip_rest("extract", "document is not an invoice")
            return self._finish(flat, None, None)

        # C. Validate
        self.start("validation")
        vchecks, derived = validate.run(ext)
        r["derived"] = derived
        fails = [c for c in vchecks if c["status"] == "fail"]
        notes = [c for c in vchecks if c["status"] == "warn"]
        self.done("validation", _status_of(vchecks),
                  f"{len(vchecks)} checks: {len(vchecks) - len(fails) - len(notes)} passed"
                  + (f", {len(notes)} note(s)" if notes else "") + (f", {len(fails)} failed" if fails else "") + ".", vchecks)

        # D. Vendor
        self.start("vendor")
        vchecks2, vend = vendor_stage.run(ext)
        r["vendor"] = vend
        if vend:
            db.update_run(self.id, vendor_id=vend["vendor_id"], vendor_name=vend["name"])
            self.log("vendor", f"Matched vendor master record {vend['vendor_id']} - {vend['name']} (status {vend['status']}).",
                     data=vend.get("match"))
        summ = (f"{vend['name']} ({vend['vendor_id']}), status {vend['status']}." if vend
                else f"'{flat.get('vendor_name')}' not found in vendor master.")
        self.done("vendor", _status_of(vchecks2), summ, vchecks2, data={"vendor": vend})

        # E. PO match
        self.start("po_match")
        pchecks, pinfo = po_match.run(ext, vend, derived)
        po = pinfo.get("po")
        r["po_match"] = {k: v for k, v in pinfo.items()}
        if po:
            db.update_run(self.id, po_number=po["po_number"])
            self.log("po_match", f"PO {po['po_number']} identified by {pinfo['method']}.")
        for cnd in pinfo.get("candidates", [])[:4]:
            self.log("po_match", f"Candidate {cnd['po_number']}: score {cnd['score']:.2f} (lines {cnd['line_score']:.0%}, amount {cnd['amount_score']:.0%})")
        summ = f"Matched to {po['po_number']} ({pinfo['method']})." if po else "No purchase order identified."
        self.done("po_match", _status_of(pchecks), summ, pchecks, data={"po_match": pinfo})

        # F. Duplicates
        self.start("duplicates")
        dchecks, dinfo = duplicates.run(ext, vend, self.id, meta["sha256"])
        r["duplicates"] = dinfo
        self.log("duplicates", f"Compared against {dinfo['compared_against']} prior invoice(s) for this vendor.")
        dfail = [c for c in dchecks if c["status"] == "fail"]
        summ = dfail[0]["message"].split(" - ")[0] if dfail else "No duplicate found."
        self.done("duplicates", _status_of(dchecks), summ, dchecks, data={"duplicates": dinfo})

        self._finish(flat, vend, pinfo)

    def _finish(self, flat: dict, vend: dict | None, pinfo: dict | None):
        self.start("decision")
        dec = decision.decide(self.checks, flat or {}, vend, pinfo)
        self.result["decision"] = dec
        self.result["checks"] = self.checks
        final = {"APPROVE": "approved", "REVIEW": "in_review", "REJECT": "rejected"}[dec["outcome"]]
        if dec["outcome"] == "APPROVE" and vend:
            po = (pinfo or {}).get("po") or {}
            db.add_to_ledger({"vendor_id": vend["vendor_id"], "invoice_number": flat.get("invoice_number"),
                              "invoice_date": flat.get("invoice_date"), "po_number": po.get("po_number"),
                              "currency": flat.get("currency"), "subtotal": (self.result.get("derived") or {}).get("subtotal"),
                              "tax": flat.get("tax_amount"), "total": flat.get("total"), "status": "approved",
                              "service_period": f"{flat['service_period_start']} to {flat['service_period_end']}"
                              if flat.get("service_period_start") and flat.get("service_period_end") else None,
                              "lines": flat.get("lines", [])},
                             source=f"auto-approved run", run_id=self.id,
                             file_hash=(self.result.get("document") or {}).get("sha256"))
            self.log("decision", "Recorded in invoice ledger as approved (PO balance updated).")
        doc = self.result.get("document")
        if doc and "text" in doc:
            doc["text"] = doc["text"][:20000]
        db.add_event(self.id, "decision", "decision", dec["headline"], status=dec["outcome"], data=dec)
        self.done("decision", {"APPROVE": "pass", "REVIEW": "review", "REJECT": "fail"}[dec["outcome"]], dec["headline"])
        import json
        db.update_run(self.id, status="completed", current_stage="done", decision=dec["outcome"], final_status=final,
                      headline=dec["headline"], result_json=json.dumps(self.result, default=str),
                      duration_ms=int((time.time() - self.t0) * 1000))


def process(run_id: str, data: bytes, filename: str):
    Run(run_id, data, filename).execute()
