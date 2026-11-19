"""Generate the demo invoice set.

Each vendor gets a deliberately different layout and vocabulary (label names, date
formats, PO reference styles, tax presentation) so the extraction layer is exercised
on genuinely different documents rather than one template.

Run:  .venv/bin/python scripts/generate_samples.py
"""
from __future__ import annotations

import io
import random
from pathlib import Path

import pymupdf
from PIL import Image, ImageFilter
from reportlab.lib import colors
from reportlab.lib.pagesizes import LETTER
from reportlab.pdfgen import canvas

OUT = Path(__file__).resolve().parent.parent / "samples"
OUT.mkdir(exist_ok=True)
W, H = LETTER


def money(v: float, sym: str = "$") -> str:
    return f"{sym}{v:,.2f}"


def table(c, x, y, cols, rows, widths, header_fill=colors.HexColor("#1f2937"), header_text=colors.white,
          zebra=None, font="Helvetica", size=9, row_h=18, grid=True, align=None):
    align = align or ["l"] + ["r"] * (len(cols) - 1)
    total_w = sum(widths)
    c.setFillColor(header_fill)
    c.rect(x, y - row_h, total_w, row_h, stroke=0, fill=1)
    c.setFillColor(header_text)
    c.setFont(font + "-Bold", size)
    cx = x
    for col, w, a in zip(cols, widths, align):
        if a == "r":
            c.drawRightString(cx + w - 6, y - row_h + 5, col)
        else:
            c.drawString(cx + 6, y - row_h + 5, col)
        cx += w
    y -= row_h
    c.setFont("Times-Roman" if font == "Times" else font, size)
    for i, r in enumerate(rows):
        if zebra and i % 2 == 0:
            c.setFillColor(zebra)
            c.rect(x, y - row_h, total_w, row_h, stroke=0, fill=1)
        c.setFillColor(colors.black)
        cx = x
        for val, w, a in zip(r, widths, align):
            if a == "r":
                c.drawRightString(cx + w - 6, y - row_h + 5, str(val))
            else:
                c.drawString(cx + 6, y - row_h + 5, str(val))
            cx += w
        if grid:
            c.setStrokeColor(colors.HexColor("#d1d5db"))
            c.line(x, y - row_h, x + total_w, y - row_h)
        y -= row_h
    return y


def totals_block(c, x_label, x_val, y, items, size=10, bold_last=True):
    for i, (label, val) in enumerate(items):
        last = i == len(items) - 1
        c.setFont("Helvetica-Bold" if (last and bold_last) else "Helvetica", size)
        c.drawRightString(x_label, y, label)
        c.drawRightString(x_val, y, val)
        y -= 16
    return y


# --------------------------------------------------------------------------- layouts

def layout_apex(path, *, vendor_name, address, email, tax_id, inv_no, date, po, lines, tax_rate,
                bank_name, bank_acct, banner=None, note=None):
    c = canvas.Canvas(str(path), pagesize=LETTER)
    c.setFillColor(colors.HexColor("#0f4c81"))
    c.rect(0, H - 90, W, 90, stroke=0, fill=1)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 20)
    c.drawString(40, H - 45, vendor_name)
    c.setFont("Helvetica", 9)
    c.drawString(40, H - 62, address)
    c.drawString(40, H - 75, f"{email}   |   Tax ID: {tax_id}")
    c.setFont("Helvetica-Bold", 26)
    c.drawRightString(W - 40, H - 55, "INVOICE")
    if banner:
        c.setFillColor(colors.HexColor("#b91c1c"))
        c.setFont("Helvetica-Bold", 12)
        c.drawString(40, H - 115, banner)
    c.setFillColor(colors.black)
    y = H - 145
    c.setFont("Helvetica-Bold", 10)
    c.drawString(40, y, "Bill To")
    c.setFont("Helvetica", 10)
    for i, ln in enumerate(["Meridian Home Goods Inc.", "Accounts Payable", "500 Market Street", "Columbus, OH 43215"]):
        c.drawString(40, y - 14 * (i + 1), ln)
    meta = [("Invoice No:", inv_no), ("Invoice Date:", date), ("PO Number:", po), ("Terms:", "Net 30")]
    for i, (k, v) in enumerate(meta):
        c.setFont("Helvetica-Bold", 10)
        c.drawString(360, y - 14 * i, k)
        c.setFont("Helvetica", 10)
        c.drawString(450, y - 14 * i, v)
    y -= 90
    rows = [(d, q, money(p), money(q * p)) for d, q, p in lines]
    y = table(c, 40, y, ["Description", "Qty", "Unit Price", "Amount"], rows, [290, 50, 90, 102])
    sub = round(sum(q * p for _, q, p in lines), 2)
    tax = round(sub * tax_rate, 2)
    y -= 20
    y = totals_block(c, 470, W - 46, y, [("Subtotal", money(sub)), (f"Sales Tax ({tax_rate*100:.2f}%)", money(tax)),
                                         ("Total Due (USD)", money(sub + tax))])
    y -= 30
    c.setFont("Helvetica-Bold", 9)
    c.drawString(40, y, "Remit to")
    c.setFont("Helvetica", 9)
    c.drawString(40, y - 13, f"{bank_name}  -  Account No: {bank_acct}")
    if note:
        c.setFont("Helvetica-Oblique", 9)
        c.setFillColor(colors.HexColor("#b91c1c"))
        c.drawString(40, y - 30, note)
        c.setFillColor(colors.black)
    c.setFont("Helvetica", 8)
    c.drawString(40, 40, "Thank you for your business. Late payments subject to 1.5% monthly finance charge.")
    c.save()


def layout_northwind(path, *, inv_no, date, po_ref, lines, period):
    c = canvas.Canvas(str(path), pagesize=LETTER)
    c.setFont("Helvetica-Bold", 18)
    c.drawRightString(W - 40, H - 50, "NORTHWIND LOGISTICS LLC")
    c.setFont("Helvetica", 9)
    c.drawRightString(W - 40, H - 64, "77 Harbor Freight Rd, Newark, NJ 07114")
    c.drawRightString(W - 40, H - 76, "accounts@northwindlogistics.com  -  EIN 83-2291047")
    c.setStrokeColor(colors.HexColor("#f59e0b"))
    c.setLineWidth(3)
    c.line(40, H - 90, W - 40, H - 90)
    c.setFont("Helvetica-Bold", 14)
    c.drawString(40, H - 120, "Tax Invoice")
    c.setFont("Helvetica", 10)
    y = H - 145
    for k, v in [("Invoice #", inv_no), ("Date of Issue", date), ("Your Order Ref", po_ref), ("Service Period", period)]:
        c.drawString(40, y, f"{k}: {v}")
        y -= 15
    c.drawString(330, H - 145, "Customer: Meridian Home Goods Inc.")
    c.drawString(330, H - 160, "Account: MHG-0042")
    y -= 15
    rows = [(d, money(p), q, money(q * p)) for d, q, p in lines]
    y = table(c, 40, y, ["Service Description", "Rate", "Units", "Line Total"], rows, [300, 90, 50, 92],
              header_fill=colors.HexColor("#f59e0b"), header_text=colors.black, zebra=colors.HexColor("#fff7e6"))
    sub = round(sum(q * p for _, q, p in lines), 2)
    y -= 20
    y = totals_block(c, 470, W - 46, y, [("Net Amount", money(sub)), ("Tax", "Exempt"), ("Amount Due", money(sub))])
    c.setFont("Helvetica", 8)
    c.drawString(40, 70, "Payment by ACH to Lakeshore Trust Bank, Account Number 778812349032. Terms: Net 45.")
    c.drawString(40, 58, "Lane fees are billed monthly in advance per the Q4 dedicated capacity agreement.")
    c.save()


def layout_brightpath(path, *, date, po_ref, lines, tax_label, tax_amount):
    c = canvas.Canvas(str(path), pagesize=LETTER)
    c.setFillColor(colors.HexColor("#6d28d9"))
    c.circle(55, H - 55, 16, stroke=0, fill=1)
    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 16)
    c.drawString(80, H - 50, "BrightPath IT Services")
    c.setFont("Helvetica", 9)
    c.drawString(80, H - 63, "300 Innovation Dr, Austin, TX 78701  -  billing@brightpath-it.com  -  TIN 26-5501873")
    c.setFont("Helvetica-Bold", 22)
    c.drawString(40, H - 120, "Invoice")
    c.setFont("Helvetica", 10)
    c.drawString(40, H - 140, f"Issued: {date}")
    c.drawString(40, H - 155, f"Ref: {po_ref}")
    c.drawString(330, H - 140, "Billed to: Meridian Home Goods Inc. - IT Department")
    y = H - 190
    rows = [(d, q, money(p), money(q * p)) for d, q, p in lines]
    y = table(c, 40, y, ["Deliverable", "Qty", "Price", "Total"], rows, [310, 40, 90, 92],
              header_fill=colors.HexColor("#ede9fe"), header_text=colors.HexColor("#4c1d95"), grid=False)
    sub = round(sum(q * p for _, q, p in lines), 2)
    y -= 20
    y = totals_block(c, 470, W - 46, y, [("Sub-total", money(sub)), (tax_label, money(tax_amount)),
                                         ("Grand Total", money(sub + tax_amount))])
    c.setFont("Helvetica", 8)
    c.drawString(40, 60, "Wire to Pioneer Commercial Bank, A/C 450019873310. Questions: billing@brightpath-it.com")
    c.save()


def layout_cobalt(path, *, inv_no, date, lines, tax_rate):
    c = canvas.Canvas(str(path), pagesize=LETTER)
    c.setFont("Times-Bold", 20)
    c.drawCentredString(W / 2, H - 50, "COBALT INDUSTRIAL PARTS CO.")
    c.setFont("Times-Roman", 10)
    c.drawCentredString(W / 2, H - 65, "4410 Foundry Ave, Gary, IN 46402  |  Fed Tax ID 91-3348210  |  orders@cobaltparts.com")
    c.setFont("Times-Bold", 14)
    c.drawCentredString(W / 2, H - 95, "INVOICE")
    c.setFont("Times-Roman", 11)
    c.drawString(50, H - 125, f"Invoice Number: {inv_no}")
    c.drawString(50, H - 141, f"Invoice Date: {date}")
    c.drawString(330, H - 125, "Sold To: Meridian Home Goods Inc.")
    c.drawString(330, H - 141, "Plant Maintenance Dept.")
    c.drawString(50, H - 160, "Ship Via: Ground   Packing Slip: PS-88412")
    y = H - 185
    rows = [(d, q, f"{p:,.2f}", f"{q*p:,.2f}") for d, q, p in lines]
    y = table(c, 50, y, ["Item / Description", "Qty", "Unit Price", "Ext. Price"], rows, [280, 50, 90, 92],
              header_fill=colors.white, header_text=colors.black, font="Times", size=11, row_h=20)
    sub = round(sum(q * p for _, q, p in lines), 2)
    tax = round(sub * tax_rate, 2)
    y -= 22
    c.setFont("Times-Roman", 11)
    for label, val in [("Subtotal", f"{sub:,.2f}"), (f"Tax {tax_rate*100:.2f}%", f"{tax:,.2f}"), ("TOTAL USD", f"{sub+tax:,.2f}")]:
        c.drawRightString(440, y, label)
        c.drawRightString(W - 68, y, val)
        y -= 17
    c.setFont("Times-Roman", 9)
    c.drawString(50, 60, "Remit: Great Plains Savings Bank, Account 302288150077. Terms Net 30.")
    c.save()


def layout_summit(path, *, inv_no, date, po, period, lines):
    c = canvas.Canvas(str(path), pagesize=LETTER)
    c.setFillColor(colors.HexColor("#065f46"))
    c.setFont("Helvetica-Bold", 17)
    c.drawString(40, H - 50, "Summit Facilities Management")
    c.setFillColor(colors.black)
    c.setFont("Helvetica", 9)
    c.drawString(40, H - 64, "22 Ridgeview Plaza, Columbus, OH 43219  -  ar@summitfm.com  -  Tax ID 54-7719032")
    c.setFont("Helvetica-Bold", 12)
    c.drawString(40, H - 100, f"BILL NUMBER {inv_no}")
    c.setFont("Helvetica", 10)
    c.drawString(40, H - 116, f"Bill Date: {date}")
    c.drawString(40, H - 131, f"Purchase Order: {po}")
    c.drawString(40, H - 146, f"Service Period: {period}")
    c.drawString(330, H - 100, "Client: Meridian Home Goods Inc.")
    c.drawString(330, H - 115, "Site: HQ - 500 Market Street")
    y = H - 175
    rows = [(d, q, money(p), money(q * p)) for d, q, p in lines]
    y = table(c, 40, y, ["Description", "Qty", "Rate", "Amount"], rows, [300, 50, 90, 92],
              header_fill=colors.HexColor("#065f46"))
    sub = round(sum(q * p for _, q, p in lines), 2)
    y -= 20
    totals_block(c, 470, W - 46, y, [("Subtotal", money(sub)), ("Tax (services exempt)", money(0)), ("Total Payable", money(sub))])
    c.setFont("Helvetica", 8)
    c.drawString(40, 60, "ACH: Harbor National Bank, Acct 610077432219. Payment due within 15 days.")
    c.save()


def layout_generic(path, *, vendor, addr, inv_no, date, po, lines, tax_rate, footer):
    c = canvas.Canvas(str(path), pagesize=LETTER)
    c.setFont("Helvetica-Bold", 16)
    c.drawString(40, H - 50, vendor)
    c.setFont("Helvetica", 9)
    c.drawString(40, H - 64, addr)
    c.setFont("Helvetica-Bold", 20)
    c.drawRightString(W - 40, H - 50, "INVOICE")
    c.setFont("Helvetica", 10)
    y = H - 100
    meta = [("Invoice Number", inv_no), ("Date", date)]
    if po:
        meta.append(("PO Number", po))
    for k, v in meta:
        c.drawString(360, y, f"{k}: {v}")
        y -= 15
    c.drawString(40, H - 100, "Bill To: Meridian Home Goods Inc.")
    y = H - 160
    rows = [(d, q, money(p), money(q * p)) for d, q, p in lines]
    y = table(c, 40, y, ["Description", "Qty", "Unit Price", "Amount"], rows, [300, 50, 90, 92],
              header_fill=colors.HexColor("#374151"))
    sub = round(sum(q * p for _, q, p in lines), 2)
    tax = round(sub * tax_rate, 2)
    y -= 20
    totals_block(c, 470, W - 46, y, [("Subtotal", money(sub)), ("Tax", money(tax)), ("Total", money(sub + tax))])
    c.setFont("Helvetica", 8)
    c.drawString(40, 60, footer)
    c.save()


def statement(path):
    c = canvas.Canvas(str(path), pagesize=LETTER)
    c.setFont("Helvetica-Bold", 18)
    c.drawString(40, H - 50, "NORTHWIND LOGISTICS LLC")
    c.setFont("Helvetica-Bold", 14)
    c.drawString(40, H - 85, "STATEMENT OF ACCOUNT")
    c.setFont("Helvetica", 10)
    c.drawString(40, H - 105, "Customer: Meridian Home Goods Inc.     Statement Date: 2026-11-15")
    c.drawString(40, H - 120, "This is a summary of your account. It is not a tax invoice.")
    rows = [("2026-10-31", "NWL-INV-7781", "Invoice", money(16000), money(0)), ("2026-11-10", "PMT-55120", "Payment received", money(0), money(16000))]
    y = table(c, 40, H - 150, ["Date", "Reference", "Type", "Debit", "Credit"], rows, [90, 110, 150, 90, 92],
              align=["l", "l", "l", "r", "r"])
    c.setFont("Helvetica-Bold", 11)
    c.drawRightString(W - 46, y - 25, "Balance Outstanding: $0.00")
    c.save()


# --------------------------------------------------------------------------- scanned conversion

def make_scanned(src: Path, dst: Path, rotate=0.7, seed=7):
    """Rasterise a PDF and save as an image-only PDF with skew, blur and speckle noise."""
    random.seed(seed)
    doc = pymupdf.open(src)
    imgs = []
    for page in doc:
        pix = page.get_pixmap(dpi=150, colorspace=pymupdf.csGRAY)
        img = Image.frombytes("L", (pix.width, pix.height), pix.samples)
        img = img.rotate(rotate, expand=False, fillcolor=255, resample=Image.BICUBIC)
        img = img.filter(ImageFilter.GaussianBlur(0.6))
        px = img.load()
        for _ in range(int(img.width * img.height * 0.0006)):
            x, y = random.randrange(img.width), random.randrange(img.height)
            px[x, y] = random.choice([0, 90, 160])
        # paper tone
        img = img.point(lambda v: min(255, int(v * 0.93 + 12)))
        imgs.append(img.convert("RGB"))
    buf = io.BytesIO()
    imgs[0].save(buf, format="PDF", save_all=True, append_images=imgs[1:], resolution=150)
    dst.write_bytes(buf.getvalue())
    src.unlink()


# --------------------------------------------------------------------------- the set

APEX_0412 = [("A4 copy paper, 80gsm (case of 5 reams)", 40, 42.50), ("Toner cartridge HP 58A black", 12, 89.00),
             ("Ergonomic office chair, mesh back", 6, 245.00), ("Whiteboard markers (pack of 12)", 25, 14.20)]
APEX_0366 = [("A4 copy paper, 80gsm (case of 5 reams)", 30, 42.50), ("Heavy duty stapler", 10, 34.90),
             ("Desk organiser, 5 compartment", 20, 28.75)]


def main():
    common_apex = dict(vendor_name="Apex Office Supplies Inc.", address="1180 Commerce Pkwy, Columbus, OH 43215",
                       email="billing@apexofficesupplies.com", tax_id="47-1823956", tax_rate=0.0825,
                       bank_name="Harbor National Bank", bank_acct="000123454821")

    # Happy path 1 - clean, itemised, explicit PO, exact match
    layout_apex(OUT / "01_happy_apex_office_supplies.pdf", inv_no="AOS-48213", date="Nov 14, 2026",
                po="PO-2026-0412", lines=APEX_0412, **common_apex)

    # Happy path 2 - legitimate split invoice against a multi-month PO (2 of 3)
    layout_northwind(OUT / "02_happy_northwind_split_po_2of3.pdf", inv_no="NWL-INV-7809", date="16/11/2026",
                     po_ref="PO 2026/0398", period="01/11/2026 - 30/11/2026",
                     lines=[("Dedicated freight services - November 2026", 1, 16000.00)])

    # Edge 1 - scanned image, no PO reference, extra freight line
    tmp = OUT / "_cobalt_src.pdf"
    layout_cobalt(tmp, inv_no="CIP-20931", date="11/12/2026", tax_rate=0.0825,
                  lines=[("Hydraulic hose assembly 3/4 in", 20, 38.75), ("Bearing 6205-2RS sealed", 50, 6.40),
                         ("Pneumatic valve 5/2 way", 8, 112.00), ("Freight & handling", 1, 35.00)])
    make_scanned(tmp, OUT / "03_edge_scanned_no_po_cobalt.pdf")

    # Edge 2a - disguised duplicate of an already-paid invoice (re-numbered "reminder copy")
    layout_apex(OUT / "04_edge_disguised_duplicate_apex.pdf", inv_no="AOS-047950", date="Nov 12, 2026",
                po="PO-2026-0366", lines=APEX_0366, banner="COPY - PAYMENT REMINDER",
                **common_apex)

    # Edge 2b - recurring monthly invoice with identical amount: must NOT be flagged duplicate
    layout_summit(OUT / "05_edge_recurring_not_duplicate_summit.pdf", inv_no="SFM-2026-11", date="November 15, 2026",
                  po="PO-2026-0350", period="November 1, 2026 - November 30, 2026",
                  lines=[("Janitorial services - November 2026", 1, 4500.00)])

    # Edge 3 - split PO, final instalment over-bills the remaining PO balance / agreed rate
    layout_northwind(OUT / "06_edge_split_po_overbilling_northwind.pdf", inv_no="NWL-INV-7815", date="18/11/2026",
                     po_ref="PO-2026-0398", period="01/12/2026 - 31/12/2026",
                     lines=[("Dedicated freight services - December 2026 (incl. peak season surcharge)", 1, 19500.00)])

    # Edge 4 - vendor impersonation / bank-detail change (BEC fraud pattern)
    layout_apex(OUT / "07_edge_vendor_impersonation_bank_change.pdf", vendor_name="Apex Office Supplies Ltd.",
                address="1180 Commerce Pkwy, Columbus, OH 43215", email="billing@apex-officesupplies.co",
                tax_id="47-1823965", inv_no="AOS-48297", date="Nov 16, 2026", po="PO-2026-0412", lines=APEX_0412,
                tax_rate=0.0825, bank_name="Meridian Digital Bank", bank_acct="9921004417",
                note="IMPORTANT: Our banking details have changed. Please update your records and remit to the account above.")

    # Extra scenarios
    layout_brightpath(OUT / "08_extra_bundled_no_invoice_number_brightpath.pdf", date="2026-11-10",
                      po_ref="Purchase Order 0431",
                      lines=[("Milestone 2 deliverables - ERP integration services & middleware licence (bundled)", 1, 21700.00)],
                      tax_label="Sales Tax 9%", tax_amount=1953.00)
    layout_generic(OUT / "09_extra_suspended_vendor_vertex.pdf", vendor="Vertex Consulting Group",
                   addr="9 Exchange Pl, Chicago, IL 60603  -  ar@vertexcg.com  -  EIN 38-6620419",
                   inv_no="VCG-1107", date="2026-11-07", po="PO-2026-0405", tax_rate=0.0,
                   lines=[("Process advisory engagement - fixed fee", 1, 12000.00)],
                   footer="Remit to Continental Bank, Account 889120034456. Net 30.")
    layout_generic(OUT / "10_extra_unknown_vendor_greenleaf.pdf", vendor="Greenleaf Catering Co.",
                   addr="18 Orchard Ln, Columbus, OH 43206  -  hello@greenleafcatering.com",
                   inv_no="GLC-5521", date="2026-11-13", po=None, tax_rate=0.0575,
                   lines=[("Team offsite catering - lunch buffet (45 pax)", 45, 24.00), ("Coffee & refreshments service", 1, 160.00)],
                   footer="Please pay by card or bank transfer within 14 days.")
    statement(OUT / "11_extra_not_an_invoice_statement.pdf")

    good = (OUT / "01_happy_apex_office_supplies.pdf").read_bytes()
    (OUT / "12_extra_corrupted_file.pdf").write_bytes(good[: len(good) // 3])

    for p in sorted(OUT.glob("*.pdf")):
        print(p.name)


if __name__ == "__main__":
    main()
