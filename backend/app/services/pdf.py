import io

from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    HRFlowable,
    PageTemplate,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.models.outlet import PaperSize
from app.models.purchase import PurchaseOrder
from app.models.sale import Sale
from app.models.settings import AppSettings
from app.models.transfer import StockTransfer

THERMAL_WIDTHS_MM = {PaperSize.THERMAL_58: 58, PaperSize.THERMAL_80: 80}

# Brand palette - matches the app's UI primary color for a cohesive, branded feel.
BRAND = colors.HexColor("#9d174d")
INK = colors.HexColor("#1f2937")
MUTED = colors.HexColor("#6b7280")
FAINT = colors.HexColor("#9ca3af")
LINE = colors.HexColor("#e5e7eb")
ROW_TINT = colors.HexColor("#fdf2f7")

CONTENT_WIDTH = 170 * mm  # A4 minus 20mm margins each side

biz_name_style = ParagraphStyle("biz_name", fontName="Helvetica-Bold", fontSize=18, textColor=INK, leading=22)
biz_detail_style = ParagraphStyle("biz_detail", fontName="Helvetica", fontSize=9, textColor=MUTED, leading=13)
doc_title_style = ParagraphStyle(
    "doc_title", fontName="Helvetica-Bold", fontSize=14, textColor=BRAND, leading=17, alignment=TA_RIGHT
)
doc_number_style = ParagraphStyle(
    "doc_number", fontName="Helvetica-Bold", fontSize=11, textColor=INK, leading=14, alignment=TA_RIGHT
)
doc_meta_style = ParagraphStyle(
    "doc_meta", fontName="Helvetica", fontSize=9, textColor=MUTED, leading=13, alignment=TA_RIGHT
)
meta_cell_style = ParagraphStyle("meta_cell", fontName="Helvetica", fontSize=9.5, textColor=INK, leading=14)
notes_style = ParagraphStyle("notes", fontName="Helvetica", fontSize=9, textColor=MUTED, leading=13)
footer_style = ParagraphStyle(
    "footer", fontName="Helvetica-Oblique", fontSize=9, textColor=MUTED, leading=13, alignment=1
)
fineprint_style = ParagraphStyle("fineprint", fontName="Helvetica", fontSize=6.5, textColor=FAINT, alignment=1)


def _tracked(text: str) -> str:
    """Poor-man's letter-spacing for small caps-style section labels."""
    return " ".join(text.upper())


def _document_header(business: AppSettings, doc_title: str, doc_number: str, meta_lines: list[str]) -> list:
    """Two-column masthead: business identity on the left, document type/number/
    meta on the right - the layout convention of a real letterhead invoice."""
    left = [Paragraph(business.business_name, biz_name_style)] if business.business_name else [Spacer(1, 1)]
    if business.business_address:
        left.append(Paragraph(business.business_address, biz_detail_style))
    contact_bits = []
    if business.business_gstin:
        contact_bits.append(f"GSTIN {business.business_gstin}")
    if business.business_phone:
        contact_bits.append(business.business_phone)
    if business.business_email:
        contact_bits.append(business.business_email)
    if contact_bits:
        left.append(Paragraph("  ·  ".join(contact_bits), biz_detail_style))

    right = [Paragraph(_tracked(doc_title), doc_title_style), Paragraph(doc_number, doc_number_style)]
    for line in meta_lines:
        right.append(Paragraph(line, doc_meta_style))

    header_table = Table([[left, right]], colWidths=[CONTENT_WIDTH * 0.6, CONTENT_WIDTH * 0.4])
    header_table.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    return [
        header_table,
        Spacer(1, 4 * mm),
        HRFlowable(width="100%", thickness=1.4, color=BRAND, spaceAfter=6 * mm),
    ]


def _meta_grid(pairs: list[tuple[str, str]], cols: int = 2) -> list:
    """Borderless label/value grid (e.g. Vendor / Deliver To / Date / Status)."""
    col_width = CONTENT_WIDTH / cols
    rows = []
    for i in range(0, len(pairs), cols):
        chunk = pairs[i : i + cols]
        row = []
        for label, value in chunk:
            row.append(Paragraph(f'<font size="7.5" color="#6b7280">{_tracked(label)}</font><br/>{value}', meta_cell_style))
        while len(row) < cols:
            row.append("")
        rows.append(row)
    table = Table(rows, colWidths=[col_width] * cols)
    table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("LEFTPADDING", (0, 0), (0, -1), 0),
            ]
        )
    )
    return [table, HRFlowable(width="100%", thickness=0.6, color=LINE, spaceBefore=2, spaceAfter=6 * mm)]


def _items_table(headers: list[str], rows: list[list[str]], col_widths: list[float]) -> Table:
    """Ruled-only (no vertical grid) zebra-striped item table - the modern,
    less spreadsheet-y look used on premium invoices."""
    table = Table([headers] + rows, colWidths=col_widths, repeatRows=1)
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), BRAND),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 8.5),
        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 1), (-1, -1), 9),
        ("ALIGN", (2, 0), (-1, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LINEBELOW", (0, 0), (-1, 0), 1, BRAND),
        ("LINEBELOW", (0, 1), (-1, -1), 0.5, LINE),
    ]
    for i in range(1, len(rows) + 1):
        if i % 2 == 0:
            style.append(("BACKGROUND", (0, i), (-1, i), ROW_TINT))
    table.setStyle(TableStyle(style))
    return table


def _totals_box(rows: list[tuple[str, str]], total_label: str = "Total") -> Table:
    """Right-aligned summary box with the grand total emphasised - separate
    from the line-item table, the way a real invoice foots its numbers."""
    label_style = ParagraphStyle("totals_label", fontName="Helvetica", fontSize=9.5, textColor=MUTED, alignment=TA_RIGHT)
    value_style = ParagraphStyle("totals_value", fontName="Helvetica", fontSize=9.5, textColor=INK, alignment=TA_RIGHT)
    total_label_style = ParagraphStyle(
        "grand_total_label", fontName="Helvetica-Bold", fontSize=12, textColor=BRAND, alignment=TA_RIGHT
    )
    total_value_style = ParagraphStyle(
        "grand_total_value", fontName="Helvetica-Bold", fontSize=12, textColor=BRAND, alignment=TA_RIGHT
    )

    data = []
    for label, value in rows:
        if label == total_label:
            data.append([Paragraph(label, total_label_style), Paragraph(value, total_value_style)])
        else:
            data.append([Paragraph(label, label_style), Paragraph(value, value_style)])

    table = Table(data, colWidths=[35 * mm, 30 * mm])
    style = [
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LINEABOVE", (0, -1), (-1, -1), 1.2, BRAND),
        ("TOPPADDING", (0, -1), (-1, -1), 6),
    ]
    table.setStyle(TableStyle(style))
    table.hAlign = "RIGHT"
    return table


def _footer(business: AppSettings, computer_generated_note: str) -> list:
    elements = [Spacer(1, 10 * mm), HRFlowable(width="100%", thickness=0.6, color=LINE, spaceAfter=4 * mm)]
    text = business.invoice_footer_text or "Thank you for shopping with us!"
    elements.append(Paragraph(text, footer_style))
    elements.append(Spacer(1, 2 * mm))
    elements.append(Paragraph(computer_generated_note, fineprint_style))
    return elements


def render_purchase_order_pdf(po: PurchaseOrder, business: AppSettings) -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=18 * mm, bottomMargin=18 * mm, leftMargin=20 * mm, rightMargin=20 * mm)
    meta_lines = [
        f"Order date: {po.order_date.strftime('%d %b %Y')}",
        f"Status: {po.status.value.replace('_', ' ').title()}",
    ]
    elements = _document_header(business, "Purchase Order", po.po_number, meta_lines)
    elements += _meta_grid(
        [
            ("Vendor", f"<b>{po.vendor.name}</b>"),
            ("Deliver to", f"<b>{po.outlet.name}</b>"),
            ("Expected date", po.expected_date.strftime("%d %b %Y") if po.expected_date else "-"),
        ],
        cols=3,
    )

    show_hsn = business.show_hsn_on_documents
    headers = ["SKU"] + (["HSN"] if show_hsn else []) + ["Item", "Qty", "Unit Cost", "Tax %", "Amount"]
    rows = []
    for item in po.items:
        row = [item.variant.sku]
        if show_hsn:
            row.append(item.variant.product.hsn_code or "-")
        row += [
            item.variant.display_name,
            str(item.quantity_ordered),
            f"{float(item.unit_cost):,.2f}",
            f"{float(item.tax_rate):.1f}",
            f"{item.amount:,.2f}",
        ]
        rows.append(row)
    col_widths = [25 * mm] + ([16 * mm] if show_hsn else []) + [
        44 * mm if show_hsn else 60 * mm,
        14 * mm,
        27 * mm,
        14 * mm,
        26 * mm,
    ]
    elements.append(_items_table(headers, rows, col_widths))
    elements.append(Spacer(1, 6 * mm))
    elements.append(_totals_box([("Total", f"Rs. {po.total_amount:,.2f}")]))

    if po.notes:
        elements.append(Spacer(1, 8 * mm))
        elements.append(Paragraph(f"<b>Notes:</b> {po.notes}", notes_style))
    elements += _footer(business, "This purchase order was generated electronically.")

    doc.build(elements)
    return buffer.getvalue()


def render_sale_receipt_pdf(sale: Sale, paper_size: PaperSize, business: AppSettings) -> bytes:
    if paper_size in THERMAL_WIDTHS_MM:
        return _render_thermal_receipt(sale, THERMAL_WIDTHS_MM[paper_size], business)
    return _render_a4_receipt(sale, business)


def _render_a4_receipt(sale: Sale, business: AppSettings) -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=18 * mm, bottomMargin=18 * mm, leftMargin=20 * mm, rightMargin=20 * mm)
    doc_title = "Tax Invoice" if business.business_gstin else "Receipt"
    meta_lines = [
        sale.created_at.strftime("%d %b %Y, %H:%M"),
        f"Payment: {sale.payment_mode.value.upper()}",
    ]
    elements = _document_header(business, doc_title, sale.invoice_number, meta_lines)
    elements += _meta_grid(
        [
            ("Outlet", f"<b>{sale.outlet.name}</b>"),
            ("Customer", f"<b>{sale.customer_name}</b>" if sale.customer_name else "Walk-in customer"),
        ],
        cols=2,
    )

    show_hsn = business.show_hsn_on_documents
    headers = ["SKU"] + (["HSN"] if show_hsn else []) + ["Item", "Qty", "Unit Price", "Tax %", "Amount"]
    rows = []
    for item in sale.items:
        amount = float(item.unit_price) * item.quantity * (1 + float(item.tax_rate) / 100)
        row = [item.variant.sku]
        if show_hsn:
            row.append(item.variant.product.hsn_code or "-")
        row += [
            item.variant.display_name,
            str(item.quantity),
            f"{float(item.unit_price):,.2f}",
            f"{float(item.tax_rate):.1f}",
            f"{amount:,.2f}",
        ]
        rows.append(row)
    col_widths = [25 * mm] + ([16 * mm] if show_hsn else []) + [
        36 * mm if show_hsn else 52 * mm,
        14 * mm,
        27 * mm,
        18 * mm,
        26 * mm,
    ]
    elements.append(_items_table(headers, rows, col_widths))
    elements.append(Spacer(1, 6 * mm))

    totals_rows = [("Subtotal", f"Rs. {sale.subtotal:,.2f}"), ("Tax", f"Rs. {sale.tax_amount:,.2f}")]
    if float(sale.discount_amount):
        totals_rows.append(("Discount", f"-Rs. {float(sale.discount_amount):,.2f}"))
    totals_rows.append(("Total", f"Rs. {sale.total:,.2f}"))
    elements.append(_totals_box(totals_rows))
    elements += _footer(business, "This is a computer-generated invoice.")

    doc.build(elements)
    return buffer.getvalue()


def _render_thermal_receipt(sale: Sale, width_mm: int, business: AppSettings) -> bytes:
    buffer = io.BytesIO()
    page_width = width_mm * mm
    margin = 3.5 * mm
    content_width = page_width - 2 * margin

    name_style = ParagraphStyle("t_name", fontName="Helvetica-Bold", fontSize=11, alignment=1, leading=14)
    small_center = ParagraphStyle("t_small_center", fontName="Helvetica", fontSize=7.5, alignment=1, leading=10, textColor=MUTED)
    label = ParagraphStyle("t_label", fontName="Helvetica-Bold", fontSize=7, alignment=1, textColor=MUTED, leading=10)
    item_name = ParagraphStyle("t_item", fontName="Helvetica-Bold", fontSize=8.5, leading=11)
    item_sub = ParagraphStyle("t_item_sub", fontName="Helvetica", fontSize=7.5, leading=10, textColor=MUTED)
    item_amount = ParagraphStyle("t_item_amount", fontName="Helvetica", fontSize=8.5, leading=11, alignment=TA_RIGHT)
    total_label = ParagraphStyle("t_total_label", fontName="Helvetica-Bold", fontSize=10, textColor=BRAND)
    total_value = ParagraphStyle("t_total_value", fontName="Helvetica-Bold", fontSize=10, textColor=BRAND, alignment=TA_RIGHT)
    sum_label = ParagraphStyle("t_sum_label", fontName="Helvetica", fontSize=8, textColor=MUTED)
    sum_value = ParagraphStyle("t_sum_value", fontName="Helvetica", fontSize=8, alignment=TA_RIGHT)
    footer_center = ParagraphStyle("t_footer", fontName="Helvetica-Oblique", fontSize=8, alignment=1, leading=11)

    elements = [Paragraph(business.business_name or sale.outlet.name, name_style)]
    if business.business_address:
        elements.append(Paragraph(business.business_address, small_center))
    if business.business_gstin:
        elements.append(Paragraph(f"GSTIN {business.business_gstin}", small_center))
    elements.append(Spacer(1, 2 * mm))
    elements.append(HRFlowable(width="100%", thickness=0.75, color=BRAND, spaceAfter=2 * mm))
    elements.append(Paragraph(sale.invoice_number, label))
    elements.append(Paragraph(sale.created_at.strftime("%d %b %Y, %H:%M"), small_center))
    elements.append(HRFlowable(width="100%", thickness=0.5, color=LINE, spaceBefore=2 * mm, spaceAfter=1 * mm))

    item_rows = []
    for item in sale.items:
        amount = float(item.unit_price) * item.quantity
        desc = Paragraph(
            f"{item.variant.display_name}<br/>"
            f'<font color="#6b7280">{item.quantity} × {float(item.unit_price):,.2f}</font>',
            item_name,
        )
        item_rows.append([desc, Paragraph(f"{amount:,.2f}", item_amount)])
    items_table = Table(item_rows, colWidths=[content_width * 0.68, content_width * 0.32])
    items_table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    elements.append(items_table)
    elements.append(HRFlowable(width="100%", thickness=0.5, color=LINE, spaceBefore=1 * mm, spaceAfter=2 * mm))

    summary_rows = [[Paragraph("Subtotal", sum_label), Paragraph(f"{sale.subtotal:,.2f}", sum_value)]]
    summary_rows.append([Paragraph("Tax", sum_label), Paragraph(f"{sale.tax_amount:,.2f}", sum_value)])
    if float(sale.discount_amount):
        summary_rows.append(
            [Paragraph("Discount", sum_label), Paragraph(f"-{float(sale.discount_amount):,.2f}", sum_value)]
        )
    summary_table = Table(summary_rows, colWidths=[content_width * 0.5, content_width * 0.5])
    summary_table.setStyle(
        TableStyle(
            [
                ("TOPPADDING", (0, 0), (-1, -1), 1.5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    elements.append(summary_table)
    elements.append(HRFlowable(width="100%", thickness=0.75, color=BRAND, spaceBefore=1 * mm, spaceAfter=1.5 * mm))
    total_table = Table(
        [[Paragraph("TOTAL", total_label), Paragraph(f"Rs. {sale.total:,.2f}", total_value)]],
        colWidths=[content_width * 0.5, content_width * 0.5],
    )
    total_table.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
    elements.append(total_table)
    elements.append(Paragraph(f"Paid via {sale.payment_mode.value.upper()}", small_center))
    elements.append(Spacer(1, 3 * mm))
    elements.append(HRFlowable(width="100%", thickness=0.5, color=LINE, spaceAfter=2 * mm))
    elements.append(Paragraph(business.invoice_footer_text or "Thank you for shopping with us!", footer_center))

    # Thermal rolls print continuously, so the page height must exactly fit the
    # content - guessing a fixed height overflows onto a wasted second page as
    # soon as any line wraps (longer address, narrower width, etc). Measure what
    # each flowable actually needs at this content width and size the page to
    # that. Must use a zero-padding Frame: SimpleDocTemplate's default Frame adds
    # its own 6pt padding on every side, which would silently narrow the usable
    # width below content_width and cause extra wrapping we didn't measure for.
    measured_height = sum(el.wrap(content_width, 5000 * mm)[1] for el in elements)
    page_height = 2 * margin + measured_height + 15 * mm
    doc = BaseDocTemplate(
        buffer,
        pagesize=(page_width, page_height),
        topMargin=margin,
        bottomMargin=margin,
        leftMargin=margin,
        rightMargin=margin,
    )
    frame = Frame(
        margin, margin, content_width, page_height - 2 * margin,
        leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0, id="thermal",
    )
    doc.addPageTemplates([PageTemplate(id="thermal", frames=[frame])])
    doc.build(elements)
    return buffer.getvalue()


def render_transfer_pdf(transfer: StockTransfer, business: AppSettings) -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=18 * mm, bottomMargin=18 * mm, leftMargin=20 * mm, rightMargin=20 * mm)
    meta_lines = [f"Status: {transfer.status.value.title()}"]
    elements = _document_header(business, "Stock Transfer", transfer.transfer_number, meta_lines)
    elements += _meta_grid(
        [
            ("From", f"<b>{transfer.source_outlet.name}</b>"),
            ("To", f"<b>{transfer.dest_outlet.name}</b>"),
        ],
        cols=2,
    )

    headers = ["SKU", "Item", "Requested", "Sent", "Received"]
    rows = [
        [
            item.variant.sku,
            item.variant.display_name,
            str(item.quantity_requested),
            str(item.quantity_sent),
            str(item.quantity_received),
        ]
        for item in transfer.items
    ]
    col_widths = [28 * mm, 67 * mm, 25 * mm, 25 * mm, 25 * mm]
    elements.append(_items_table(headers, rows, col_widths))

    if transfer.notes:
        elements.append(Spacer(1, 8 * mm))
        elements.append(Paragraph(f"<b>Notes:</b> {transfer.notes}", notes_style))
    elements += _footer(business, "This stock transfer document was generated electronically.")

    doc.build(elements)
    return buffer.getvalue()
