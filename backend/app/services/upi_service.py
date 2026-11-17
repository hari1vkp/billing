"""Dynamic UPI QR code generation (NPCI UPI deep-link format)."""

import io
from urllib.parse import urlencode

import qrcode
from qrcode.constants import ERROR_CORRECT_M

from app.models.business import Business
from app.models.invoice import Invoice


def build_upi_uri(
    vpa: str,
    payee_name: str,
    amount: float,
    note: str = "",
    transaction_ref: str = "",
    currency: str = "INR",
) -> str:
    """Build a UPI payment URI compatible with all major Indian UPI apps."""
    params = {
        "pa": vpa.strip(),
        "pn": payee_name.strip(),
        "am": f"{float(amount):.2f}",
        "cu": currency or "INR",
    }
    if note:
        params["tn"] = note[:80]
    if transaction_ref:
        params["tr"] = transaction_ref
    return "upi://pay?" + urlencode(params)


def invoice_upi_uri(business: Business, invoice: Invoice) -> str:
    return build_upi_uri(
        vpa=business.upi_id or "",
        payee_name=business.upi_name or business.name,
        amount=float(invoice.balance_amount or invoice.total_amount),
        note=f"Invoice {invoice.invoice_number}",
        transaction_ref=invoice.transaction_ref or invoice.invoice_number,
        currency=business.currency,
    )


def generate_qr_png(uri: str, box_size: int = 9, border: int = 2) -> bytes:
    qr = qrcode.QRCode(
        version=None,
        error_correction=ERROR_CORRECT_M,
        box_size=box_size,
        border=border,
    )
    qr.add_data(uri)
    qr.make(fit=True)
    img = qr.make_image(fill_color="#252421", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
