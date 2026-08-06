import io
from dataclasses import dataclass

from reportlab.graphics.barcode import createBarcodeDrawing
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    PageBreak,
    PageTemplate,
    Paragraph,
    SimpleDocTemplate,
    Table,
    TableStyle,
)

from app.services.pdf import INK, LINE, MUTED

label_name_style = ParagraphStyle(
    "label_name", fontName="Helvetica-Bold", fontSize=7.5, textColor=INK, alignment=1, leading=9
)
label_meta_style = ParagraphStyle(
    "label_meta", fontName="Helvetica", fontSize=7, textColor=MUTED, alignment=1, leading=8.5
)
label_price_style = ParagraphStyle(
    "label_price", fontName="Helvetica-Bold", fontSize=8, textColor=INK, alignment=1, leading=10
)


@dataclass
class LabelItem:
    sku: str
    barcode: str | None
    product_name: str
    size: str | None
    color: str | None
    mrp: float
    quantity: int


def _label_flowables(item: LabelItem, width: float) -> list:
    code_value = item.barcode or item.sku
    barcode = createBarcodeDrawing(
        "Code128",
        value=code_value,
        barHeight=9 * mm,
        width=width * 0.94,
        humanReadable=True,
        fontSize=6,
        fontName="Helvetica",
    )
    barcode.hAlign = "CENTER"

    name = item.product_name
    if len(name) > 28:
        name = name[:26] + "…"

    elements = [barcode, Paragraph(name, label_name_style)]
    meta_bits = [b for b in [item.color, item.size] if b]
    if meta_bits:
        elements.append(Paragraph(" / ".join(meta_bits), label_meta_style))
    elements.append(Paragraph(f"MRP ₹{item.mrp:,.2f}", label_price_style))
    return elements


def render_labels_pdf(items: list[LabelItem], layout: str) -> bytes:
    if layout == "a4_sheet":
        return _render_a4_label_sheet(items)
    return _render_thermal_labels(items)


def _render_thermal_labels(items: list[LabelItem], width_mm: float = 50, height_mm: float = 25) -> bytes:
    buffer = io.BytesIO()
    page_width = width_mm * mm
    page_height = height_mm * mm
    margin = 2 * mm
    content_width = page_width - 2 * margin

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
        leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0, id="label",
    )
    doc.addPageTemplates([PageTemplate(id="label", frames=[frame])])

    elements: list = []
    for item in items:
        for _ in range(item.quantity):
            elements += _label_flowables(item, content_width)
            elements.append(PageBreak())
    if elements and isinstance(elements[-1], PageBreak):
        elements.pop()

    doc.build(elements)
    return buffer.getvalue()


def _render_a4_label_sheet(items: list[LabelItem], cols: int = 3) -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4, topMargin=10 * mm, bottomMargin=10 * mm, leftMargin=8 * mm, rightMargin=8 * mm
    )
    content_width = A4[0] - 16 * mm
    cell_width = content_width / cols
    cell_height = 28 * mm

    cells: list = []
    for item in items:
        for _ in range(item.quantity):
            cells.append(_label_flowables(item, cell_width - 4 * mm))
    while len(cells) % cols != 0:
        cells.append("")
    rows = [cells[i : i + cols] for i in range(0, len(cells), cols)]

    table = Table(rows, colWidths=[cell_width] * cols, rowHeights=[cell_height] * len(rows))
    table.setStyle(
        TableStyle(
            [
                ("BOX", (0, 0), (-1, -1), 0.5, LINE),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, LINE),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    doc.build([table])
    return buffer.getvalue()
