"""Small, dependency-free helpers shared by the pipeline stages."""
from __future__ import annotations

import re
from datetime import date, datetime
from typing import Optional

from rapidfuzz import fuzz

MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}

LEGAL_SUFFIXES = r"\b(inc|incorporated|llc|ltd|limited|co|company|corp|corporation|plc|gmbh|pvt|llp)\b\.?"


def parse_money(s: Optional[str]) -> Optional[float]:
    if s is None:
        return None
    if isinstance(s, (int, float)):
        return float(s)
    t = str(s).strip()
    neg = t.startswith("(") and t.endswith(")") or t.startswith("-")
    t = re.sub(r"[^\d.,]", "", t)
    if not t:
        return None
    # European style 1.234,56
    if re.fullmatch(r"\d{1,3}(\.\d{3})+,\d{2}", t):
        t = t.replace(".", "").replace(",", ".")
    else:
        t = t.replace(",", "")
    try:
        v = float(t)
    except ValueError:
        return None
    return -v if neg else v


def parse_date(raw: Optional[str], prefer_dmy: bool = False) -> tuple[Optional[str], Optional[str]]:
    """Parse many human date formats. Returns (iso_date, ambiguity_note)."""
    if not raw:
        return None, None
    s = raw.strip().rstrip(".,;")
    # ISO
    m = re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})", s)
    if m:
        return _iso(int(m.group(1)), int(m.group(2)), int(m.group(3))), None
    # Month name forms: "Nov 14, 2026", "November 15, 2026", "14 Nov 2026"
    m = re.search(r"([A-Za-z]{3,9})\.?\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})", s)
    if m and m.group(1)[:3].lower() in MONTHS:
        return _iso(int(m.group(3)), MONTHS[m.group(1)[:3].lower()], int(m.group(2))), None
    m = re.search(r"(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]{3,9})\.?,?\s+(\d{4})", s)
    if m and m.group(2)[:3].lower() in MONTHS:
        return _iso(int(m.group(3)), MONTHS[m.group(2)[:3].lower()], int(m.group(1))), None
    # Numeric a/b/yyyy
    # Dot-separated dates (12.11.2026) are a day-first convention (DE, CH, AT, NL, Nordics, ...);
    # month-first never uses dots, so this is not treated as ambiguous.
    m = re.search(r"(\d{1,2})\.(\d{1,2})\.(\d{4})", s)
    if m:
        d_, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if mo > 12 and d_ <= 12:  # malformed month-first with dots: still recoverable
            d_, mo = mo, d_
        return _iso(y, mo, d_), None
    m = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", s)
    if m:
        a, b, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if a > 12 and b <= 12:
            return _iso(y, b, a), None
        if b > 12 and a <= 12:
            return _iso(y, a, b), None
        if a == b:
            return _iso(y, a, b), None
        raw = m.group(0)
        if prefer_dmy:
            return _iso(y, b, a), f"'{raw}' is ambiguous (DD/MM vs MM/DD); interpreted as DD/MM"
        return _iso(y, a, b), f"'{raw}' is ambiguous (MM/DD vs DD/MM); interpreted as MM/DD (US vendor convention)"
    return None, None


def _iso(y: int, mth: int, d: int) -> Optional[str]:
    try:
        return date(y, mth, d).isoformat()
    except ValueError:
        return None


def to_date(iso: Optional[str]) -> Optional[date]:
    if not iso:
        return None
    try:
        return datetime.fromisoformat(iso).date()
    except ValueError:
        return None


def norm_company(name: Optional[str]) -> str:
    if not name:
        return ""
    s = name.lower().replace("&", " and ")
    s = re.sub(LEGAL_SUFFIXES, " ", s)
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def norm_invoice_number(num: Optional[str]) -> str:
    """Canonical form used for duplicate detection: case, separators, leading zeros and
    common re-send suffixes are removed so 'AOS-047950', 'aos 47950' and 'AOS47950-R' collide."""
    if not num:
        return ""
    s = num.upper()
    s = re.sub(r"[-_/ ]?(COPY|DUP|DUPLICATE|REV\d*|R\d?)$", "", s)
    s = re.sub(r"[^A-Z0-9]", "", s)
    s = re.sub(r"(?<![0-9])0+(?=\d)", "", s)  # drop leading zeros of every digit group
    return s


def norm_po(ref: Optional[str]) -> str:
    if not ref:
        return ""
    return re.sub(r"[^A-Z0-9]", "", ref.upper()).replace("PO", "", 1) if ref else ""


def similarity(a: Optional[str], b: Optional[str]) -> float:
    if not a or not b:
        return 0.0
    return fuzz.token_set_ratio(a.lower(), b.lower()) / 100.0


def close(a: Optional[float], b: Optional[float], tol: float = 0.05) -> bool:
    if a is None or b is None:
        return False
    return abs(a - b) <= tol


def fmt_money(v: Optional[float], cur: str = "USD") -> str:
    if v is None:
        return "—"
    sym = {"USD": "$", "EUR": "€", "GBP": "£", "INR": "₹"}.get(cur or "USD", "")
    return f"{sym}{v:,.2f}" if sym else f"{v:,.2f} {cur}"
