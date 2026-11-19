"""End-to-end regression: every sample invoice through the real API, asserting the decision.

Run:  .venv/bin/python -m pytest -q
"""
import time

import pytest
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

client = TestClient(app)

# Order matters where the ledger carries state between invoices (split PO, duplicates).
EXPECTED = [
    ("01_happy_apex_office_supplies.pdf", "APPROVE", None),
    ("02_happy_northwind_split_po_2of3.pdf", "APPROVE", None),
    ("03_edge_scanned_no_po_cobalt.pdf", "REVIEW", "E-FIND"),
    ("04_edge_disguised_duplicate_apex.pdf", "REJECT", "F-INV"),
    ("05_edge_recurring_not_duplicate_summit.pdf", "APPROVE", None),
    ("06_edge_split_po_overbilling_northwind.pdf", "REVIEW", "E-PRICE"),
    ("07_edge_vendor_impersonation_bank_change.pdf", "REJECT", "D-FRAUD"),
    ("08_extra_bundled_no_invoice_number_brightpath.pdf", "REVIEW", "V-REQ"),
    ("09_extra_suspended_vendor_vertex.pdf", "REJECT", "D-STATUS"),
    ("10_extra_unknown_vendor_greenleaf.pdf", "REJECT", "D-FOUND"),
    ("11_extra_not_an_invoice_statement.pdf", "REJECT", "A-DOCTYPE"),
    ("12_extra_corrupted_file.pdf", "REJECT", "A-INTAKE"),
]


def wait(run_id, timeout=90):
    end = time.time() + timeout
    while time.time() < end:
        r = client.get(f"/api/runs/{run_id}").json()
        if r["status"] in ("completed", "error"):
            return r
        time.sleep(0.2)
    raise TimeoutError(run_id)


@pytest.fixture(scope="module", autouse=True)
def fresh():
    assert client.post("/api/reset").status_code == 200


@pytest.mark.parametrize("name,outcome,check_id", EXPECTED)
def test_scenario(name, outcome, check_id):
    rid = client.post(f"/api/samples/{name}/run").json()["run_id"]
    r = wait(rid)
    assert r["status"] == "completed", r.get("headline")
    assert r["decision"] == outcome, r["headline"]
    if check_id:
        failed = {c["id"] for c in r["result"]["checks"] if c["status"] == "fail"}
        assert check_id in failed, failed


def test_recurring_invoice_not_flagged_duplicate():
    runs = client.get("/api/runs").json()
    summit = next(r for r in runs if r["filename"].startswith("05_"))
    detail = client.get(f"/api/runs/{summit['id']}").json()
    fuzzy = next(c for c in detail["result"]["checks"] if c["id"] == "F-FUZZY")
    assert fuzzy["status"] == "pass" and "recurring" in fuzzy["message"]


def test_resubmitting_same_file_is_rejected():
    rid = client.post("/api/samples/01_happy_apex_office_supplies.pdf/run").json()["run_id"]
    r = wait(rid)
    assert r["decision"] == "REJECT"
    assert any(c["id"] == "F-FILE" and c["status"] == "fail" for c in r["result"]["checks"])


def test_review_requires_note_and_is_single_use():
    runs = client.get("/api/runs").json()
    cobalt = next(r for r in runs if r["filename"].startswith("03_"))
    assert client.post(f"/api/runs/{cobalt['id']}/review", json={"action": "approve", "note": ""}).status_code == 422
    ok = client.post(f"/api/runs/{cobalt['id']}/review", json={"action": "approve", "note": "Buyer confirmed PO", "reviewer": "Test"})
    assert ok.status_code == 200 and ok.json()["final_status"] == "approved_manual"
    again = client.post(f"/api/runs/{cobalt['id']}/review", json={"action": "approve", "note": "again"})
    assert again.status_code == 409


def test_upload_validation_and_headers():
    assert client.post("/api/runs", files={"file": ("empty.pdf", b"", "application/pdf")}).status_code == 400
    r = client.get("/")
    assert "Content-Security-Policy" in r.headers and r.headers["X-Content-Type-Options"] == "nosniff"
    assert client.get("/api/runs/not-a-run").status_code == 404
    # Encoded traversal must not escape the samples directory.
    assert client.get("/api/samples/..%2F..%2Fapp%2Fconfig.py/file").status_code == 404
    assert client.get("/api/does-not-exist").status_code == 404
