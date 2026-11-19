"""Parser regressions on layouts the sample set does not cover."""
import pytest

from app.pipeline import extract_rules
from app.utils import parse_date


@pytest.mark.parametrize("raw,iso,ambiguous", [
    ("12.11.2026", "2026-11-12", False),   # dotted = day-first (DE/EU)
    ("5.3.2026", "2026-03-05", False),
    ("16/11/2026", "2026-11-16", False),   # unambiguous slash date
    ("11/12/2026", "2026-11-12", True),    # ambiguous slash date -> US default, flagged
    ("2026-11-10", "2026-11-10", False),
    ("Nov 14, 2026", "2026-11-14", False),
    ("3rd November 2026", "2026-11-03", False),
])
def test_dates(raw, iso, ambiguous):
    got, note = parse_date(raw)
    assert got == iso
    assert bool(note) == ambiguous


def test_total_label_is_not_a_line_item_without_table_header():
    text = "\n".join([
        "Northwind Logistics LLC", "INVOICE", "Invoice # NWL-INV-7820", "Date: Nov 17, 2026", "Ref: PO-2026-0398",
        "Freight lane fee November top-up    $1,200.00", "Amount Due $1,200.00",
    ])
    x = extract_rules.extract(text)
    assert [i["amount"] for i in x["line_items"]] == [1200.0]
    assert x["fields"]["total"]["value"] == 1200.0


def test_vat_inclusive_eur_invoice():
    text = "\n".join([
        "Lumen Druck GmbH", "RECHNUNG / INVOICE", "Invoice number: LD-2026-117", "Invoice date: 12.11.2026",
        "Description Qty Unit price Amount", "Brochure printing A5 2000 0.45 900.00", "Prices include VAT (19%)", "Total EUR 900.00",
    ])
    f = {k: v["value"] for k, v in extract_rules.extract(text)["fields"].items()}
    assert f["invoice_date"] == "2026-11-12"
    assert f["currency"] == "EUR" and f["total"] == 900.0 and f["tax_inclusive"] is True
