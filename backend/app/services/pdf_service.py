"""Professional PDF invoice generation using ReportLab."""

import io
from datetime import date

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    HRFlowable,
    Image,
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.models.business import Business
from app.models.customer import Customer
from app.models.invoice import Invoice
from app.services.upi_service import generate_qr_png, invoice_upi_uri

NAVY = colors.HexColor("#0f172a")
SLATE = colors.HexColor("#475569")
LIGHT = colors.HexColor("#f1f5f9")
BORDER = colors.HexColor("#e2e8f0")
ACCENT = colors.HexColor("#2563eb")


def _styles():
    ss = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "t", parent=ss["Title"], fontName="Helvetica-Bold", fontSize=22,
            textColor=NAVY, spaceAfter=2, alignment=0,
        ),
        "sub": ParagraphStyle(
            "s", parent=ss["Normal"], fontName="Helvetica", fontSize=9,
            textColor=SLATE, spaceAfter=2,
        ),
        "h": ParagraphStyle(
            "h", parent=ss["Normal"], fontName="Helvetica-Bold", fontSize=9,
            textColor=NAVY, spaceAfter=3,
        ),
        "body": ParagraphStyle(
            "b", parent=ss["Normal"], fontName="Helvetica", fontSize=9,
            textColor=SLATE, leading=13,
        ),
        "small": ParagraphStyle(
            "sm", parent=ss["Normal"], fontName="Helvetica", fontSize=8,
            textColor=SLATE, leading=11,
        ),
        "right": ParagraphStyle(
            "r", parent=ss["Normal"], fontName="Helvetica", fontSize=9,
            textColor=NAVY, alignment=TA_RIGHT, leading=13,
        ),
        "total_label": ParagraphStyle(
            "tl", parent=ss["Normal"], fontName="Helvetica", fontSize=9,
            textColor=SLATE, alignment=TA_RIGHT,
        ),
        "total_value": ParagraphStyle(
            "tv", parent=ss["Normal"], fontName="Helvetica-Bold", fontSize=9,
            textColor=NAVY, alignment=TA_RIGHT,
        ),
        "grand": ParagraphStyle(
            "g", parent=ss["Normal"], fontName="Helvetica-Bold", fontSize=12,
            textColor=colors.white, alignment=TA_RIGHT,
        ),
        "center": ParagraphStyle(
            "c", parent=ss["Normal"], fontName="Helvetica", fontSize=8,
            textColor=SLATE, alignment=TA_CENTER, leading=11,
        ),
    }


def generate_invoice_pdf(
    invoice: Invoice,
    business: Business,
    customer: Customer,
    payments: list | None = None,
) -> bytes:
    st = _styles()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
        title=f"Invoice {invoice.invoice_number}",
        author=business.name,
    )
    width = doc.width
    story = []

    # ---- Header -----------------------------------------------------------
    header = Table(
        [
            [
                Paragraph(business.name, st["title"]),
                Paragraph(
                    f"<b>INVOICE</b><br/>{invoice.invoice_number}",
                    ParagraphStyle("inv", parent=st["right"], fontSize=13,
                                   fontName="Helvetica-Bold", textColor=NAVY),
                ),
            ],
            [
                Paragraph(
                    "<br/>".join(
                        p for p in [
                            business.address,
                            " ".join(filter(None, [business.city, business.state, business.pincode])),
                            f"Phone: {business.phone}" if business.phone else "",
                            f"Email: {business.email}" if business.email else "",
                            f"GSTIN: {business.gstin}" if business.gstin else "",
                            f"UPI: {business.upi_id}" if business.upi_id else "",
                        ] if p
                    ),
                    st["sub"],
                ),
                Paragraph(
                    f"Issue date: {invoice.issue_date}<br/>"
                    + (f"Due date: {invoice.due_date}<br/>" if invoice.due_date else "")
                    + f"Status: {invoice.status.replace('_', ' ').title()}",
                    st["right"],
                ),
            ],
        ],
        colWidths=[width * 0.62, width * 0.38],
    )
    header.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"),
                                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                                ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
    story += [header, Spacer(1, 6), HRFlowable(width="100%", thickness=1.2,
                                                color=ACCENT), Spacer(1, 8)]

    # ---- Bill to ----------------------------------------------------------
    bill_to = Table(
        [[
            Paragraph("<b>BILL TO</b>", st["h"]),
            Paragraph("<b>PAYMENT SUMMARY</b>", st["h"]),
        ], [
            Paragraph(
                f"<b>{customer.name}</b><br/>"
                + "<br/>".join(
                    p for p in [
                        customer.address,
                        " ".join(filter(None, [customer.city, customer.state, customer.pincode])),
                        f"Phone: {customer.phone}" if customer.phone else "",
                        f"Email: {customer.email}" if customer.email else "",
                        f"GSTIN: {customer.gstin}" if customer.gstin else "",
                    ] if p
                ),
                st["body"],
            ),
            Paragraph(
                f"Total: <b>{business.currency} {float(invoice.total_amount):,.2f}</b><br/>"
                f"Paid: {business.currency} {float(invoice.paid_amount):,.2f}<br/>"
                f"Balance: <b>{business.currency} {float(invoice.balance_amount):,.2f}</b>",
                st["body"],
            ),
        ]],
        colWidths=[width * 0.5, width * 0.5],
    )
    bill_to.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BACKGROUND", (0, 0), (-1, 0), LIGHT),
        ("BOX", (0, 0), (-1, -1), 0.5, BORDER),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, BORDER),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story += [bill_to, Spacer(1, 10)]

    # ---- Line items -------------------------------------------------------
    data = [[
        Paragraph("<b>#</b>", st["small"]),
        Paragraph("<b>Description</b>", st["small"]),
        Paragraph("<b>Qty</b>", st["small"]),
        Paragraph("<b>Rate</b>", st["small"]),
        Paragraph("<b>Disc.</b>", st["small"]),
        Paragraph("<b>GST</b>", st["small"]),
        Paragraph("<b>Amount</b>", st["small"]),
    ]]
    for idx, item in enumerate(invoice.items, 1):
        data.append([
            str(idx),
            Paragraph(
                f"{item.description}"
                + (f"<br/><font size=7 color='#94a3b8'>HSN: {item.product.hsn_code}</font>"
                   if getattr(item, "product", None) and getattr(item.product, "hsn_code", None)
                   else ""),
                st["small"],
            ),
            f"{float(item.quantity):g}",
            f"{float(item.unit_price):,.2f}",
            f"{float(item.discount_amount):,.2f}",
            f"{float(item.gst_rate):g}%",
            f"{float(item.line_total):,.2f}",
        ])
    col_widths = [width * x for x in (0.05, 0.34, 0.08, 0.13, 0.12, 0.09, 0.19)]
    table = Table(data, colWidths=col_widths, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 1), (-1, -1), 8),
        ("ALIGN", (2, 0), (-1, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT]),
        ("GRID", (0, 0), (-1, -1), 0.4, BORDER),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story += [table, Spacer(1, 8)]

    # ---- Totals -----------------------------------------------------------
    tot = [
        [Paragraph("Subtotal", st["total_label"]),
         Paragraph(f"{business.currency} {float(invoice.subtotal):,.2f}", st["total_value"])],
        [Paragraph("Item discounts", st["total_label"]),
         Paragraph(f"- {business.currency} {float(invoice.discount_amount):,.2f}", st["total_value"])],
        [Paragraph("Taxable amount", st["total_label"]),
         Paragraph(f"{business.currency} {float(invoice.taxable_amount):,.2f}", st["total_value"])],
        [Paragraph("GST (total)", st["total_label"]),
         Paragraph(f"{business.currency} {float(invoice.tax_amount):,.2f}", st["total_value"])],
    ]
    totals_table = Table(tot, colWidths=[width * 0.55, width * 0.45])
    totals_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))
    grand = Table(
        [[
            Paragraph("TOTAL PAYABLE", st["grand"]),
            Paragraph(f"{business.currency} {float(invoice.total_amount):,.2f}", st["grand"]),
        ]],
        colWidths=[width * 0.55, width * 0.45],
    )
    grand.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), NAVY),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
    ]))
    totals_block = Table([[totals_table], [grand]], colWidths=[width])
    totals_block.setStyle(TableStyle([
        ("ALIGN", (0, 0), (-1, -1), "RIGHT"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))
    story += [totals_block, Spacer(1, 10)]

    if invoice.notes:
        story += [Paragraph(f"<b>Notes:</b> {invoice.notes}", st["small"]), Spacer(1, 6)]

    # ---- UPI payment block ------------------------------------------------
    if business.upi_id and invoice.balance_amount > 0:
        uri = invoice_upi_uri(business, invoice)
        qr_png = generate_qr_png(uri)
        qr_img = Image(io.BytesIO(qr_png), width=34 * mm, height=34 * mm)
        pay_table = Table(
            [[
                qr_img,
                Paragraph(
                    f"<b>Scan &amp; pay {business.currency} {float(invoice.balance_amount):,.2f}</b><br/>"
                    f"UPI ID: <b>{business.upi_id}</b><br/>"
                    f"Name: {business.upi_name or business.name}<br/>"
                    f"Ref: {invoice.invoice_number}<br/><br/>"
                    f"<font size=7>Scan with any UPI app (GPay, PhonePe, Paytm, BHIM...). "
                    f"Share the UTR reference with us to confirm.</font>",
                    st["body"],
                ),
            ]],
            colWidths=[40 * mm, width - 40 * mm],
        )
        pay_table.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("BACKGROUND", (0, 0), (-1, -1), LIGHT),
            ("BOX", (0, 0), (-1, -1), 0.5, BORDER),
            ("LEFTPADDING", (0, 0), (-1, -1), 10),
            ("RIGHTPADDING", (0, 0), (-1, -1), 10),
            ("TOPPADDING", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ]))
        story += [KeepTogether(pay_table), Spacer(1, 8)]

    # ---- Payment history --------------------------------------------------
    confirmed_payments = [p for p in (payments or []) if p.status == "confirmed"]
    if confirmed_payments:
        prows = [[Paragraph("<b>Date</b>", st["small"]),
                  Paragraph("<b>Method</b>", st["small"]),
                  Paragraph("<b>Reference</b>", st["small"]),
                  Paragraph("<b>Amount</b>", st["small"])]]
        for p in confirmed_payments:
            prows.append([
                str(p.payment_date or p.created_at.date()),
                p.method.upper(),
                p.reference or "-",
                f"{business.currency} {float(p.amount):,.2f}",
            ])
        pt = Table(prows, colWidths=[width * x for x in (0.2, 0.2, 0.35, 0.25)])
        pt.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), SLATE),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("GRID", (0, 0), (-1, -1), 0.4, BORDER),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("ALIGN", (3, 0), (3, -1), "RIGHT"),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        story += [Paragraph("<b>Payment history</b>", st["h"]), pt, Spacer(1, 8)]

    story += [
        HRFlowable(width="100%", thickness=0.6, color=BORDER),
        Spacer(1, 4),
        Paragraph(
            business.invoice_footer
            or "Thank you for your business! Payment due within the agreed terms.",
            st["center"],
        ),
        Paragraph(f"Generated by {business.name} · {date.today()}", st["center"]),
    ]

    doc.build(story)
    return buf.getvalue()
