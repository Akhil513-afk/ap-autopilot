"""Stage A - Intake and document reading.

Decides whether the file is a usable PDF, whether it has a machine-readable text layer
or is a scan that needs OCR, and produces the plain text used by the parser."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

import pdfplumber
import pymupdf
import pytesseract
from PIL import Image, ImageFilter, ImageOps

MAX_BYTES = 20 * 1024 * 1024
MAX_PAGES = 30
MIN_TEXT_CHARS_PER_PAGE = 40


class IntakeError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class DocumentRead:
    sha256: str
    size_bytes: int
    pages: int
    method: str                 # "text-layer" | "ocr" | "mixed"
    text: str
    ocr_confidence: float | None = None
    page_methods: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def intake(data: bytes, filename: str) -> dict:
    """Cheap structural checks before we spend any effort on the document."""
    if len(data) == 0:
        raise IntakeError("empty_file", "The uploaded file is empty (0 bytes).")
    if len(data) > MAX_BYTES:
        raise IntakeError("too_large", f"File is {len(data)/1e6:.1f} MB; limit is {MAX_BYTES/1e6:.0f} MB.")
    if not data[:1024].lstrip().startswith(b"%PDF"):
        raise IntakeError("not_pdf", "File is not a PDF (missing %PDF signature). Ask the vendor to resend as PDF.")
    try:
        doc = pymupdf.open(stream=data, filetype="pdf")
    except Exception as e:  # noqa: BLE001
        raise IntakeError("corrupt_pdf", f"PDF could not be opened - the file is corrupted or truncated ({e.__class__.__name__}).")
    if doc.needs_pass:
        raise IntakeError("encrypted", "PDF is password-protected; it cannot be read automatically.")
    if doc.page_count == 0:
        raise IntakeError("no_pages", "PDF contains no pages.")
    if doc.page_count > MAX_PAGES:
        raise IntakeError("too_many_pages", f"PDF has {doc.page_count} pages; this looks like a batch, not a single invoice.")
    # Pymupdf repairs some broken files silently - make sure page 1 actually renders.
    try:
        doc[0].get_pixmap(dpi=20)
    except Exception as e:  # noqa: BLE001
        raise IntakeError("corrupt_pdf", f"PDF structure is damaged; first page cannot be rendered ({e.__class__.__name__}).")
    xref_ok = not doc.is_repaired if hasattr(doc, "is_repaired") else True
    return {"pages": doc.page_count, "size_bytes": len(data), "sha256": sha256(data), "repaired": not xref_ok,
            "filename": filename}


def _ocr_page(page) -> tuple[str, float]:
    pix = page.get_pixmap(dpi=300, colorspace=pymupdf.csGRAY)
    img = Image.frombytes("L", (pix.width, pix.height), pix.samples)
    img = img.filter(ImageFilter.MedianFilter(3))       # remove scanner speckle
    img = ImageOps.autocontrast(img)
    img = img.point(lambda v: 255 if v > 170 else 0)    # binarise
    data = pytesseract.image_to_data(img, config="--psm 6", output_type=pytesseract.Output.DICT)
    confs = [float(c) for c, t in zip(data["conf"], data["text"]) if t.strip() and float(c) >= 0]
    text = pytesseract.image_to_string(img, config="--psm 6")
    return text, (sum(confs) / len(confs)) if confs else 0.0


def read(data: bytes) -> DocumentRead:
    doc = pymupdf.open(stream=data, filetype="pdf")
    texts, methods, confs, notes = [], [], [], []
    with pdfplumber.open(__import__("io").BytesIO(data)) as pdf:
        for i, page in enumerate(doc):
            layer = ""
            try:
                layer = pdf.pages[i].extract_text() or ""
            except Exception:  # noqa: BLE001
                layer = page.get_text() or ""
            if len(layer.strip()) >= MIN_TEXT_CHARS_PER_PAGE:
                texts.append(layer)
                methods.append("text-layer")
            else:
                t, conf = _ocr_page(page)
                texts.append(t)
                methods.append("ocr")
                confs.append(conf)
                notes.append(f"Page {i+1}: no usable text layer ({len(layer.strip())} chars) - OCR applied, mean word confidence {conf:.0f}%.")
    method = "ocr" if all(m == "ocr" for m in methods) else ("text-layer" if all(m == "text-layer" for m in methods) else "mixed")
    return DocumentRead(sha256=sha256(data), size_bytes=len(data), pages=len(methods), method=method,
                        text="\n".join(texts), ocr_confidence=(sum(confs) / len(confs)) if confs else None,
                        page_methods=methods, notes=notes)
