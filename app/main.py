"""HTTP API + static UI.

    .venv/bin/uvicorn app.main:app --port 8000
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import config, db
from .pipeline import po_match, runner
from .pipeline.reader import sha256

logging.basicConfig(level=config.LOG_LEVEL, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("ap")

app = FastAPI(title="AP Autopilot - Invoice PDF to Decision", version=config.VERSION,
              docs_url="/api/docs", redoc_url=None, openapi_url="/api/openapi.json")
app.add_middleware(GZipMiddleware, minimum_size=1024)

db.init()
_recovered = db.recover_interrupted()
if _recovered:
    log.warning("Marked %d interrupted run(s) as error after restart", _recovered)

# Bounded worker pool: OCR and LLM calls are heavy, so we cap concurrency and queue the rest.
POOL = ThreadPoolExecutor(max_workers=config.WORKERS, thread_name_prefix="invoice-worker")

# name -> (group, short title, expected outcome, vendor, one-line description used as a tooltip)
SAMPLE_INFO = {
    "01_happy_apex_office_supplies.pdf": ("Happy path", "Clean itemised invoice", "APPROVE", "Apex Office Supplies", "Digital PDF, explicit PO, exact 2-way match."),
    "02_happy_northwind_split_po_2of3.pdf": ("Happy path", "Split PO · invoice 2 of 3", "APPROVE", "Northwind Logistics", "Second instalment on a 3-month PO; odd PO format, DD/MM dates."),
    "03_edge_scanned_no_po_cobalt.pdf": ("Edge case", "Scanned, no PO reference", "REVIEW", "Cobalt Industrial Parts", "OCR, then the PO is inferred from the vendor's open POs."),
    "04_edge_disguised_duplicate_apex.pdf": ("Edge case", "Disguised duplicate", "REJECT", "Apex Office Supplies", "Paid invoice re-sent with a re-formatted number."),
    "05_edge_recurring_not_duplicate_summit.pdf": ("Edge case", "Recurring, not a duplicate", "APPROVE", "Summit Facilities", "Same amount as last month, different service period."),
    "06_edge_split_po_overbilling_northwind.pdf": ("Edge case", "Split PO over-billing", "REVIEW", "Northwind Logistics", "Final instalment above the agreed rate and PO balance."),
    "07_edge_vendor_impersonation_bank_change.pdf": ("Edge case", "Vendor impersonation", "REJECT", "Apex Office Supplies Ltd.", "Look-alike vendor, wrong tax ID, new bank account."),
    "08_extra_bundled_no_invoice_number_brightpath.pdf": ("Exception", "Bundled lines, no invoice #", "REVIEW", "BrightPath IT Services", "Bundled line covers two PO lines; wrong tax rate."),
    "09_extra_suspended_vendor_vertex.pdf": ("Exception", "Suspended vendor", "REJECT", "Vertex Consulting", "Vendor is on compliance hold."),
    "10_extra_unknown_vendor_greenleaf.pdf": ("Exception", "Unknown vendor", "REJECT", "Greenleaf Catering", "Vendor not onboarded; no PO."),
    "11_extra_not_an_invoice_statement.pdf": ("Exception", "Not an invoice", "REJECT", "Northwind Logistics", "Statement of account."),
    "12_extra_corrupted_file.pdf": ("Exception", "Corrupted file", "REJECT", "—", "Truncated PDF."),
}

CSP = ("default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
       "font-src 'self' https://fonts.gstatic.com; script-src 'self'; "
       "frame-src 'self'; object-src 'self'; connect-src 'self'; base-uri 'self'; form-action 'self'; frame-ancestors 'self'")


@app.middleware("http")
async def headers(request: Request, call_next):
    resp = await call_next(request)
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    resp.headers.setdefault("Referrer-Policy", "same-origin")
    resp.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    p = request.url.path
    if resp.headers.get("content-type", "").startswith("text/html") and not p.startswith("/api/"):
        resp.headers["Content-Security-Policy"] = CSP
        resp.headers["Cache-Control"] = "no-cache"
    elif p.startswith("/static"):
        resp.headers["Cache-Control"] = "no-cache"  # revalidate (ETag) so deploys show up immediately
    return resp


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):
    log.exception("Unhandled error on %s", request.url.path)
    return JSONResponse({"detail": "Internal server error"}, status_code=500)


def _safe_name(filename: str) -> str:
    name = Path(filename or "").name
    name = re.sub(r"[^A-Za-z0-9._\- ]", "_", name).strip()[:120]
    return name or "invoice.pdf"


def _start(data: bytes, filename: str, source: str) -> str:
    run_id = uuid.uuid4().hex[:12]
    safe = _safe_name(filename)
    path = config.UPLOADS / f"{run_id}_{safe}"
    path.write_bytes(data)
    db.create_run(run_id, safe, str(path), sha256(data), source)
    db.add_event(run_id, "intake", "log", f"Invoice submitted via {source}; queued for processing.")
    POOL.submit(runner.process, run_id, data, safe)
    log.info("Queued run %s (%s, %d bytes, %s)", run_id, safe, len(data), source)
    return run_id


def _get(run_id: str) -> dict:
    if not re.fullmatch(r"[0-9a-f]{12}", run_id or ""):
        raise HTTPException(404, "Run not found")
    r = db.get_run(run_id)
    if not r:
        raise HTTPException(404, "Run not found")
    return r


# ----------------------------------------------------------------------------- system
@app.get("/api/health")
def health():
    return {"ok": True, "version": config.VERSION, "llm": config.llm_available(),
            "model": config.LLM_MODEL if config.llm_available() else None, "pacing": config.STAGE_PACING,
            "as_of": config.AS_OF_DATE, "workers": config.WORKERS, "allow_reset": config.ALLOW_RESET,
            "max_upload_mb": config.MAX_UPLOAD_MB}


# ----------------------------------------------------------------------------- intake
@app.post("/api/runs", status_code=202)
async def upload(file: UploadFile = File(...)):
    limit = config.MAX_UPLOAD_MB * 1024 * 1024
    chunks, size = [], 0
    while chunk := await file.read(1024 * 1024):
        size += len(chunk)
        if size > limit:
            raise HTTPException(413, f"File exceeds the {config.MAX_UPLOAD_MB} MB limit.")
        chunks.append(chunk)
    if size == 0:
        raise HTTPException(400, "The uploaded file is empty.")
    # Non-PDFs are deliberately still accepted: the pipeline rejects them at intake with an audit trail.
    return {"run_id": _start(b"".join(chunks), file.filename or "upload.pdf", "upload")}


@app.get("/api/samples")
def samples():
    out = []
    for p in sorted(config.SAMPLES.glob("*.pdf")):
        group, title, expected, vendor, desc = SAMPLE_INFO.get(p.name, ("Sample", p.stem, None, "", ""))
        out.append({"name": p.name, "group": group, "tag": group, "title": title, "expected": expected,
                    "vendor": vendor, "description": desc, "size": p.stat().st_size})
    return out


def _sample(name: str) -> Path:
    p = config.SAMPLES / Path(name).name
    if not p.exists() or p.suffix.lower() != ".pdf":
        raise HTTPException(404, "Sample not found")
    return p


@app.post("/api/samples/{name}/run", status_code=202)
def run_sample(name: str):
    p = _sample(name)
    return {"run_id": _start(p.read_bytes(), p.name, "sample library")}


@app.get("/api/samples/{name}/file")
def sample_file(name: str):
    return FileResponse(_sample(name), media_type="application/pdf", headers={"Content-Disposition": "inline"})


# ----------------------------------------------------------------------------- runs
@app.get("/api/runs")
def runs(limit: int = Query(500, ge=1, le=5000)):
    return db.list_runs(limit)


@app.get("/api/runs/{run_id}")
def run_detail(run_id: str):
    r = _get(run_id)
    r["events"] = db.events_since(run_id)
    return r


@app.get("/api/runs/{run_id}/export")
def run_export(run_id: str):
    r = _get(run_id)
    r["events"] = db.events_since(run_id)
    if r.get("result") and r["result"].get("document"):
        r["result"]["document"].pop("text", None)
    body = json.dumps(r, indent=2, default=str)
    name = f"invoice-run-{r['seq']}-{run_id}.json"
    return HTMLResponse(body, media_type="application/json",
                        headers={"Content-Disposition": f'attachment; filename="{name}"'})


@app.get("/api/runs/{run_id}/document")
def run_document(run_id: str):
    r = _get(run_id)
    p = Path(r["file_path"])
    if not p.exists():
        raise HTTPException(404, "Document no longer available")
    return FileResponse(p, media_type="application/pdf", headers={"Content-Disposition": "inline"})


@app.get("/api/runs/{run_id}/stream")
async def stream(run_id: str, request: Request, after: int = 0):
    _get(run_id)

    async def gen():
        last, idle, beats = after, 0, 0
        yield "retry: 2000\n\n"
        while True:
            if await request.is_disconnected():
                break
            evs = db.events_since(run_id, last)
            for e in evs:
                last = e["id"]
                yield f"id: {e['id']}\nevent: step\ndata: {json.dumps(e, default=str)}\n\n"
            r = db.get_run(run_id)
            if r["status"] in ("completed", "error") and not evs:
                idle += 1
                if idle > 2:
                    yield f"event: end\ndata: {json.dumps({'status': r['status']})}\n\n"
                    break
            beats += 1
            if beats % 60 == 0:
                yield ": keep-alive\n\n"
            await asyncio.sleep(0.15)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


class ReviewIn(BaseModel):
    action: str = Field(pattern="^(approve|reject|request_info)$")
    reviewer: str = Field("AP reviewer", min_length=1, max_length=80)
    note: str = Field("", max_length=1000)


REVIEWABLE = ("in_review", "awaiting_info", "rejected")


@app.post("/api/runs/{run_id}/review")
def review(run_id: str, body: ReviewIn):
    r = _get(run_id)
    if r["status"] != "completed" or r["final_status"] not in REVIEWABLE:
        raise HTTPException(409, f"This invoice is '{r['final_status']}' and can no longer be reviewed.")
    if body.action == "request_info" and r["final_status"] == "rejected":
        raise HTTPException(409, "A rejected invoice can only be overridden (approve) or left rejected.")
    if body.action != "request_info" and not body.note.strip():
        raise HTTPException(422, "A justification note is required to approve or reject.")
    final = {"approve": "approved_manual", "reject": "rejected_manual", "request_info": "awaiting_info"}[body.action]
    res = r["result"] or {}
    ex = res.get("extracted") or {}
    vend = res.get("vendor")
    if body.action == "approve":
        if not vend:
            raise HTTPException(422, "Cannot approve: the vendor is not in the vendor master. Onboard the vendor first.")
        po = ((res.get("po_match") or {}).get("po") or {})
        db.add_to_ledger({"vendor_id": vend["vendor_id"], "invoice_number": ex.get("invoice_number"), "invoice_date": ex.get("invoice_date"),
                          "po_number": po.get("po_number"), "currency": ex.get("currency"),
                          "subtotal": (res.get("derived") or {}).get("subtotal"), "tax": ex.get("tax_amount"), "total": ex.get("total"),
                          "status": "approved",
                          "service_period": f"{ex['service_period_start']} to {ex['service_period_end']}" if ex.get("service_period_start") else None,
                          "lines": ex.get("lines", [])}, source=f"manual approval by {body.reviewer}", run_id=run_id,
                         file_hash=r["file_hash"])
    db.update_run(run_id, final_status=final, reviewed_by=body.reviewer.strip(), review_note=body.note.strip(), reviewed_at=db.now())
    verb = {"approve": "approved", "reject": "rejected", "request_info": "sent back for information"}[body.action]
    db.add_event(run_id, "review", "review",
                 f"{body.reviewer} {verb} the invoice (system decision was {r['decision']}). Note: {body.note.strip() or '-'}",
                 status=body.action, data=body.model_dump())
    log.info("Run %s reviewed: %s by %s", run_id, body.action, body.reviewer)
    out = db.get_run(run_id)
    out["events"] = db.events_since(run_id)
    return out


# ----------------------------------------------------------------------------- reference & stats
@app.get("/api/reference")
def reference():
    vendors = config.vendors()
    pos = []
    for po in config.purchase_orders():
        pos.append({**po, "position": po_match.po_position(po),
                    "vendor_name": next((v["name"] for v in vendors if v["vendor_id"] == po["vendor_id"]), po["vendor_id"])})
    return {"vendors": vendors, "purchase_orders": pos, "policy": config.policy(), "ledger": db.ledger_rows()}


@app.get("/api/stats")
def stats():
    rows = db.list_runs(100000)
    done = [r for r in rows if r["status"] == "completed"]
    by = lambda k: sum(1 for r in done if r["decision"] == k)  # noqa: E731
    return {
        "total": len(rows), "completed": len(done), "processing": sum(1 for r in rows if r["status"] in ("queued", "processing")),
        "errors": sum(1 for r in rows if r["status"] == "error"),
        "approve": by("APPROVE"), "review": by("REVIEW"), "reject": by("REJECT"),
        "open_reviews": sum(1 for r in done if r["final_status"] in ("in_review", "awaiting_info")),
        "value_approved": round(sum(r["total"] or 0 for r in done if r["final_status"] in ("approved", "approved_manual")), 2),
        "value_blocked": round(sum(r["total"] or 0 for r in done if r["final_status"] in ("rejected", "rejected_manual")), 2),
        "value_in_review": round(sum(r["total"] or 0 for r in done if r["final_status"] in ("in_review", "awaiting_info")), 2),
        "avg_ms": int(sum(r["duration_ms"] or 0 for r in done) / len(done)) if done else 0,
        "touchless_rate": round(by("APPROVE") / len(done), 3) if done else 0,
    }


@app.post("/api/reset")
def reset():
    if not config.ALLOW_RESET:
        raise HTTPException(403, "Reset is disabled in this environment.")
    db.init(reset=True)
    for p in config.UPLOADS.glob("*"):
        if p.is_file():
            p.unlink()
    log.warning("Demo data reset")
    return {"ok": True}


# ----------------------------------------------------------------------------- UI
app.mount("/static", StaticFiles(directory=config.STATIC), name="static")


@app.get("/", response_class=HTMLResponse)
def index():
    return (config.STATIC / "index.html").read_text()


@app.get("/{path:path}", include_in_schema=False)
def spa_fallback(path: str):
    if path.startswith("api/"):
        raise HTTPException(404, "Not found")
    return HTMLResponse((config.STATIC / "index.html").read_text())
