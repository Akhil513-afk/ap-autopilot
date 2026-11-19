from __future__ import annotations


def check(cid: str, stage: str, name: str, status: str, message: str, severity: str | None = None, **evidence) -> dict:
    """status: pass | warn | fail | info | skip.  severity (fails only): review | reject."""
    if status == "fail" and severity is None:
        severity = "review"
    return {"id": cid, "stage": stage, "name": name, "status": status, "severity": severity if status == "fail" else None,
            "message": message, "evidence": evidence or None}
