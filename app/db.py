"""SQLite persistence: runs, the per-run event log (audit trail), and the invoice ledger."""
from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone

from . import config
from .utils import norm_invoice_number

_lock = threading.Lock()

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY,
    seq INTEGER,
    created_at TEXT,
    updated_at TEXT,
    filename TEXT,
    file_path TEXT,
    file_hash TEXT,
    source TEXT,
    status TEXT,              -- queued | processing | completed | error
    current_stage TEXT,
    decision TEXT,            -- APPROVE | REVIEW | REJECT (system decision)
    final_status TEXT,        -- what the invoice is now: approved / in_review / rejected / ...
    vendor_name TEXT,
    vendor_id TEXT,
    invoice_number TEXT,
    po_number TEXT,
    total REAL,
    currency TEXT,
    engine TEXT,
    headline TEXT,
    result_json TEXT,
    reviewed_by TEXT,
    review_note TEXT,
    reviewed_at TEXT,
    duration_ms INTEGER
);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT,
    ts TEXT,
    stage TEXT,
    type TEXT,               -- stage_start | stage_done | log | decision | review | error
    status TEXT,
    message TEXT,
    data_json TEXT
);
CREATE INDEX IF NOT EXISTS ix_events_run ON events(run_id, id);
CREATE TABLE IF NOT EXISTS ledger (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    vendor_id TEXT,
    invoice_number TEXT,
    invoice_number_norm TEXT,
    invoice_date TEXT,
    po_number TEXT,
    currency TEXT,
    subtotal REAL,
    tax REAL,
    total REAL,
    status TEXT,
    service_period TEXT,
    lines_json TEXT,
    source TEXT,
    run_id TEXT,
    file_hash TEXT,
    created_at TEXT
);
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def conn() -> sqlite3.Connection:
    c = sqlite3.connect(config.DB_PATH, timeout=15, check_same_thread=False)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA busy_timeout=15000")
    return c


def init(reset: bool = False) -> None:
    with _lock, conn() as c:
        if reset:
            c.executescript("DROP TABLE IF EXISTS runs; DROP TABLE IF EXISTS events; DROP TABLE IF EXISTS ledger;")
        c.executescript(SCHEMA)
        n = c.execute("SELECT COUNT(*) FROM ledger").fetchone()[0]
        if n == 0:
            for row in config.load_json("seed_ledger.json"):
                _insert_ledger(c, row, source="seed (ERP history)")


def _insert_ledger(c, row: dict, source: str, run_id: str | None = None, file_hash: str | None = None):
    c.execute(
        """INSERT INTO ledger (vendor_id, invoice_number, invoice_number_norm, invoice_date, po_number, currency,
           subtotal, tax, total, status, service_period, lines_json, source, run_id, file_hash, created_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (row["vendor_id"], row.get("invoice_number"), norm_invoice_number(row.get("invoice_number")),
         row.get("invoice_date"), row.get("po_number"), row.get("currency"), row.get("subtotal"), row.get("tax"),
         row.get("total"), row.get("status", "approved"), row.get("service_period"),
         json.dumps(row.get("lines", [])), source, run_id, file_hash, now()))


def add_to_ledger(row: dict, source: str, run_id: str, file_hash: str | None):
    with _lock, conn() as c:
        _insert_ledger(c, row, source, run_id, file_hash)


def ledger_rows(vendor_id: str | None = None, po_number: str | None = None) -> list[dict]:
    q, args = "SELECT * FROM ledger WHERE 1=1", []
    if vendor_id:
        q += " AND vendor_id=?"
        args.append(vendor_id)
    if po_number:
        q += " AND po_number=?"
        args.append(po_number)
    with conn() as c:
        rows = [dict(r) for r in c.execute(q + " ORDER BY id", args)]
    for r in rows:
        r["lines"] = json.loads(r.pop("lines_json") or "[]")
    return rows


def recover_interrupted() -> int:
    """Runs left 'queued'/'processing' by a crash or restart can never finish - mark them as errors."""
    with _lock, conn() as c:
        ids = [r[0] for r in c.execute("SELECT id FROM runs WHERE status IN ('queued','processing')")]
        for rid in ids:
            c.execute("UPDATE runs SET status='error', final_status='error', updated_at=?, headline=? WHERE id=?",
                      (now(), "Processing was interrupted by a server restart - resubmit the invoice.", rid))
            c.execute("INSERT INTO events (run_id, ts, stage, type, status, message) VALUES (?,?,?,?,?,?)",
                      (rid, now(), "system", "error", "fail", "Processing interrupted by server restart."))
    return len(ids)


def create_run(run_id: str, filename: str, file_path: str, file_hash: str, source: str) -> None:
    with _lock, conn() as c:
        seq = (c.execute("SELECT COALESCE(MAX(seq),0) FROM runs").fetchone()[0] or 0) + 1
        c.execute("""INSERT INTO runs (id, seq, created_at, updated_at, filename, file_path, file_hash, source, status,
                     current_stage, final_status) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                  (run_id, seq, now(), now(), filename, file_path, file_hash, source, "queued", "intake", "processing"))


def update_run(run_id: str, **fields) -> None:
    if not fields:
        return
    fields["updated_at"] = now()
    cols = ", ".join(f"{k}=?" for k in fields)
    with _lock, conn() as c:
        c.execute(f"UPDATE runs SET {cols} WHERE id=?", (*fields.values(), run_id))


def add_event(run_id: str, stage: str, type_: str, message: str, status: str | None = None, data=None) -> int:
    with _lock, conn() as c:
        cur = c.execute("INSERT INTO events (run_id, ts, stage, type, status, message, data_json) VALUES (?,?,?,?,?,?,?)",
                        (run_id, now(), stage, type_, status, message, json.dumps(data, default=str) if data is not None else None))
        return cur.lastrowid


def events_since(run_id: str, after_id: int = 0) -> list[dict]:
    with conn() as c:
        rows = [dict(r) for r in c.execute("SELECT * FROM events WHERE run_id=? AND id>? ORDER BY id", (run_id, after_id))]
    for r in rows:
        r["data"] = json.loads(r.pop("data_json")) if r.get("data_json") else None
    return rows


def get_run(run_id: str) -> dict | None:
    with conn() as c:
        r = c.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
    if not r:
        return None
    d = dict(r)
    d["result"] = json.loads(d.pop("result_json")) if d.get("result_json") else None
    return d


def list_runs(limit: int = 500) -> list[dict]:
    with conn() as c:
        rows = [dict(r) for r in c.execute(
            """SELECT id, seq, created_at, updated_at, filename, source, status, current_stage, decision, final_status,
               vendor_name, vendor_id, invoice_number, po_number, total, currency, engine, headline, reviewed_by,
               reviewed_at, duration_ms FROM runs ORDER BY seq DESC LIMIT ?""", (limit,))]
    return rows


def runs_with_hash(file_hash: str, exclude: str) -> list[dict]:
    with conn() as c:
        return [dict(r) for r in c.execute(
            "SELECT id, seq, created_at, filename, decision, final_status FROM runs WHERE file_hash=? AND id<>? AND status='completed' ORDER BY seq",
            (file_hash, exclude))]


def pending_review_runs(exclude: str) -> list[dict]:
    """Invoices that are not in the ledger yet but are in flight (awaiting review)."""
    with conn() as c:
        rows = [dict(r) for r in c.execute(
            "SELECT id, seq, result_json FROM runs WHERE final_status='in_review' AND id<>?", (exclude,))]
    out = []
    for r in rows:
        res = json.loads(r["result_json"] or "{}")
        out.append({"run_id": r["id"], "seq": r["seq"], "extracted": res.get("extracted", {}),
                    "vendor_id": (res.get("vendor") or {}).get("vendor_id")})
    return out
