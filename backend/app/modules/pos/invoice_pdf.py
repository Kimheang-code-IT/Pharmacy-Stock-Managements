"""Invoice PDF generation and storage (spec: PDF invoices, object keys in PG).

A dependency-free PDF writer renders the print payload from
`POSService.build_receipt` into a single-file PDF. Generated files are stored
on the invoice storage volume (never in PostgreSQL, which keeps only the
object key on `sales.invoice_pdf_object_key`). The browser-printable HTML
invoice remains the primary print path — this PDF is the archived document
served by `GET /pos/sales/{id}/invoice.pdf`.

Text uses the Helvetica base-14 fonts; characters outside Latin-1 (e.g.
Khmer) are dropped in the archived PDF while the HTML invoice keeps them.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from app.core.config import settings

PAGE_WIDTH = 595  # A4 at 72 dpi
PAGE_HEIGHT = 842
MARGIN = 48
LINE_HEIGHT = 16
MAX_CONTENT_CHARS = 180


def _escape(text: str) -> str:
    escaped = text.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")
    return escaped.encode("latin-1", "ignore").decode("latin-1")


def _pdf_escape_summary(text: str) -> str:
    trimmed = text if len(text) <= MAX_CONTENT_CHARS else text[:MAX_CONTENT_CHARS] + "…"
    return _escape(trimmed)


def _line(op: str, x: float, y: float, text: str, size: float = 10, font: str = "F1") -> str:
    return f"BT /{font} {size} Tf {x} {y:.1f} Td ({_pdf_escape_summary(text)}) Tj ET"


def build_invoice_pdf(receipt: dict) -> bytes:
    """Render the receipt payload as a minimal, valid single-page PDF."""
    shop = receipt.get("shop") or {}
    lines: list[tuple[str, float, str]] = []  # (text, size, font)

    def add(text: str, *, size: float = 10, font: str = "F1") -> None:
        lines.append((str(text if text is not None else ""), size, font))

    add(str(shop.get("name") or ""), size=16, font="F2")
    if shop.get("address"):
        add(str(shop["address"]))
    if shop.get("phone"):
        add(str(shop["phone"]))
    add("")
    add(f"Invoice No: {receipt.get('invoice_no', '')}")
    add(f"Date: {receipt.get('sale_date', '')}")
    if receipt.get("cashier"):
        add(f"Cashier: {receipt['cashier']}")
    if receipt.get("customer"):
        add(f"Customer: {receipt['customer']}")
    add("")
    add("Item                        Qty      Price    Discount    Total", font="F2")
    for item in receipt.get("items") or []:
        name = str(item.get("name") or "")
        qty = str(item.get("qty") or "")
        price = str(item.get("unit_price") or "")
        discount = str(item.get("discount") or "")
        total = str(item.get("line_total") or "")
        add(f"{name[:24]:<24} {qty:>6} {price:>10} {discount:>10} {total:>10}")
    add("")
    add(f"Subtotal: {receipt.get('subtotal', '')}")
    add(f"Discount: {receipt.get('discount', '')}")
    add(f"Delivery: {receipt.get('delivery_price', '')}")
    add(f"Grand Total: {receipt.get('grand_total', '')}", font="F2")
    add(f"Paid: {receipt.get('paid', '')}")
    if receipt.get("change") is not None:
        add(f"Change: {receipt.get('change', '')}")
    if receipt.get("debt_remaining") is not None:
        add(f"Debt Remaining: {receipt.get('debt_remaining', '')}")
    if receipt.get("payment_method"):
        add(f"Payment Method: {receipt.get('payment_method', '')}")
    if receipt.get("note"):
        add(f"Note: {receipt.get('note', '')}")
    footer = receipt.get("footer") or "Thank you for your purchase!"
    if footer:
        add("")
        add(str(footer))

    y = PAGE_HEIGHT - MARGIN
    parts: list[str] = []
    for text, size, font in lines:
        if y < MARGIN:
            break
        parts.append(_line("Tj", MARGIN, y, text, size=size, font=font))
        y -= LINE_HEIGHT if size <= 12 else LINE_HEIGHT + 6

    content = "\n".join(parts).encode("latin-1", "ignore")
    stream_len = len(content)
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 "
            + str(PAGE_WIDTH).encode()
            + b" "
            + str(PAGE_HEIGHT).encode()
            + b"] /Resources << /Font << /F1 5 0 R /F2 6 0 R >> >> /Contents 4 0 R >>"
        ),
        b"<< /Length " + str(stream_len).encode() + b" >>\nstream\n" + content + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>",
    ]

    out = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for index, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{index} 0 obj\n".encode() + body + b"\nendobj\n"
    xref_at = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode()
    out += b"0000000000 65535 f \n"
    for offset in offsets[1:]:
        out += f"{offset:010d} 00000 n \n".encode()
    out += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_at}\n%%EOF".encode()
    )
    return bytes(out)


# --------------------------------------------------------------------- storage


def _invoice_root() -> Path:
    root = Path(settings.invoice_storage_dir).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def _resolve_object_path(object_key: str) -> Path | None:
    key = (object_key or "").replace("\\", "/").strip("/")
    if not key or ".." in key.split("/"):
        return None
    return _invoice_root() / key


def save_invoice_pdf(object_key: str, content: bytes) -> str:
    path = _resolve_object_path(object_key)
    if path is None:
        raise ValueError("Invalid invoice object key")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return hashlib.sha256(content).hexdigest()[:16]


def load_invoice_pdf(object_key: str) -> bytes | None:
    path = _resolve_object_path(object_key)
    if path is None or not path.is_file():
        return None
    return path.read_bytes()
