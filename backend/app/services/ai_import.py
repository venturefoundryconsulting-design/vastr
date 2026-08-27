"""Phase 9 - AI-assisted invoice import.

Three concerns kept deliberately separate, in three groups of functions below:

1. **Extraction** (`call_extraction`) - the only function in this module that
   talks to the network. Everything downstream of it works off a plain dict,
   so it is the one thing that needs mocking in tests and the one thing that
   can fail for reasons unrelated to this app's own logic (a bad API key, a
   timeout, a model that didn't return valid JSON).
2. **Matching** (`match_item`, `guess_uom`) - best-effort, always overridable,
   never authoritative. A human reviews every match before approval; nothing
   here writes anything.
3. **Staging and approval** (`create_batch`, `update_row`, `approve_batch`,
   `reject_batch`) - the only functions that touch the database. Approval is
   the one moment this module writes outside its own two tables, and even
   then it only ever creates a DRAFT GoodsReceipt - never posts one. Posting,
   and therefore ever touching stock, stays exactly where Phase 5 put it:
   an explicit action in Goods Receipts, made by a person looking at the
   physical delivery, not by this module.
"""

import json
from decimal import Decimal, InvalidOperation

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.money import money, quantity as q, to_decimal
from app.models.ai_import import AiImportBatch, AiImportRow, AiImportStatus
from app.models.goods_receipt import GoodsReceipt, GoodsReceiptItem, ReceiptStatus
from app.models.product import Item, ItemType
from app.models.uom import UnitOfMeasure

EXTRACTION_MODEL_DEFAULT = "gpt-4o-mini"

EXTRACTION_PROMPT = """You are reading a vendor invoice or delivery note for a \
boutique garment manufacturer. Extract every line item you can find.

Return ONLY valid JSON, no markdown fences, in exactly this shape:
{
  "vendor_name": "string or null",
  "invoice_ref": "string or null",
  "lines": [
    {
      "description": "string, as printed on the invoice",
      "quantity": "number as a string, e.g. \\"12.5\\"",
      "unit": "short unit code if shown, e.g. M, PC, KG, ROLL, or null",
      "unit_cost": "number as a string, e.g. \\"450.00\\"",
      "description_confidence": 0.0-1.0,
      "quantity_confidence": 0.0-1.0,
      "cost_confidence": 0.0-1.0
    }
  ]
}

Confidence reflects how legible/unambiguous that specific field was on the
page - a smudged handwritten quantity should score low even if you produced a
best guess. If you cannot read a line item at all, omit it rather than
guessing at everything.
"""


class AiImportError(ValueError):
    pass


# ---------------------------------------------------------------- extraction


def call_extraction(*, api_key: str, model: str, image_bytes: bytes, mime_type: str) -> dict:
    """Send one invoice image to the vision model and return its parsed JSON.

    The only network call in this module - kept to one small function so
    tests can monkeypatch this single name rather than mock an HTTP client.
    """
    import base64

    from openai import OpenAI

    client = OpenAI(api_key=api_key)
    b64 = base64.b64encode(image_bytes).decode("ascii")
    response = client.chat.completions.create(
        model=model or EXTRACTION_MODEL_DEFAULT,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": EXTRACTION_PROMPT},
                    {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{b64}"}},
                ],
            }
        ],
        response_format={"type": "json_object"},
        max_tokens=4000,
    )
    raw = response.choices[0].message.content
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError) as e:
        raise AiImportError(f"The model did not return valid JSON: {e}") from e


# ------------------------------------------------------------------ matching


def match_item(db: Session, description: str) -> tuple[Item | None, Decimal]:
    """Best-effort match against the existing item master.

    Deliberately simple - a case-insensitive substring match on name or SKU,
    not a trigram/embedding search. Every match is a proposal a human can
    reject or change before approval, so a simple heuristic that is easy to
    reason about beats a clever one that is easy to get confidently wrong.
    """
    desc = (description or "").strip()
    if not desc:
        return None, Decimal("0")

    like = f"%{desc}%"
    exact = db.query(Item).filter(func.lower(Item.name) == desc.lower()).first()
    if exact:
        return exact, Decimal("0.95")

    partial = (
        db.query(Item)
        .filter(Item.name.ilike(like) | Item.sku.ilike(like))
        .first()
    )
    if partial:
        return partial, Decimal("0.6")

    # Try the other direction - the invoice description is often longer than
    # the item name ("Gold Zari Lace 2 inch" vs "Zari Lace").
    words = [w for w in desc.split() if len(w) > 3]
    for word in words:
        hit = db.query(Item).filter(Item.name.ilike(f"%{word}%")).first()
        if hit:
            return hit, Decimal("0.4")

    return None, Decimal("0")


def guess_uom(db: Session, unit_text: str | None) -> UnitOfMeasure | None:
    if not unit_text:
        return None
    code = unit_text.strip().upper()
    return (
        db.query(UnitOfMeasure)
        .filter((func.upper(UnitOfMeasure.code) == code) | (func.upper(UnitOfMeasure.symbol) == code))
        .first()
    )


# ------------------------------------------------------------- staging & CRUD


def _safe_decimal(value, default="0") -> Decimal:
    try:
        return to_decimal(value if value not in (None, "") else default)
    except (InvalidOperation, TypeError):
        return to_decimal(default)


def _safe_confidence(value) -> Decimal | None:
    if value is None:
        return None
    try:
        d = to_decimal(value)
    except (InvalidOperation, TypeError):
        return None
    return max(Decimal("0"), min(Decimal("1"), d))


def create_batch(
    db: Session,
    *,
    outlet_id: int,
    vendor_id: int | None,
    source_filename: str,
    source_path: str,
    extraction: dict,
    user_id: int | None = None,
) -> AiImportBatch:
    """Turn one extraction result into a reviewable batch. Writes only the
    two staging tables - no item, vendor or stock row is touched here."""
    batch = AiImportBatch(
        outlet_id=outlet_id, vendor_id=vendor_id,
        source_filename=source_filename, source_path=source_path,
        raw_extraction=json.dumps(extraction)[:20000],
        vendor_name_guess=(extraction.get("vendor_name") or None),
        invoice_ref_guess=(extraction.get("invoice_ref") or None),
        status=AiImportStatus.PENDING, uploaded_by_id=user_id,
    )
    db.add(batch)
    db.flush()

    for i, line in enumerate(extraction.get("lines") or []):
        description = str(line.get("description") or "").strip()
        if not description:
            continue
        matched_item, match_confidence = match_item(db, description)
        unit_text = line.get("unit")
        uom = guess_uom(db, unit_text) or (matched_item.stock_uom if matched_item else None)

        db.add(AiImportRow(
            batch_id=batch.id, line_no=i,
            raw_description=description[:300], raw_unit_text=(unit_text or None),
            matched_item_id=matched_item.id if matched_item else None,
            is_new_item=matched_item is None,
            proposed_sku=None,
            quantity=q(_safe_decimal(line.get("quantity"))),
            uom_id=uom.id if uom else None,
            unit_cost=money(_safe_decimal(line.get("unit_cost"))),
            description_confidence=_safe_confidence(line.get("description_confidence")),
            quantity_confidence=_safe_confidence(line.get("quantity_confidence")),
            cost_confidence=_safe_confidence(line.get("cost_confidence")),
            match_confidence=match_confidence if matched_item else None,
        ))
    db.flush()
    return batch


def update_row(db: Session, row: AiImportRow, **fields) -> AiImportRow:
    """A human correcting what the model read. Any field the review screen
    exposes may be overwritten; nothing here is validated against approval
    rules yet - that happens once, at approve_batch, so a row can sit in a
    half-corrected state while someone is still working on it."""
    allowed = {
        "raw_description", "quantity", "unit_cost", "uom_id",
        "matched_item_id", "is_new_item", "proposed_sku", "excluded",
    }
    for key, value in fields.items():
        if key not in allowed:
            continue
        if key == "quantity":
            value = q(_safe_decimal(value))
        elif key == "unit_cost":
            value = money(_safe_decimal(value))
        setattr(row, key, value)
    if fields.get("matched_item_id"):
        row.is_new_item = False
    db.flush()
    return row


def reject_batch(db: Session, batch: AiImportBatch, *, user_id: int | None = None) -> None:
    if batch.status != AiImportStatus.PENDING:
        raise AiImportError(f"This batch is already {batch.status.value}")
    batch.status = AiImportStatus.REJECTED
    batch.reviewed_by_id = user_id
    db.flush()


def approve_batch(
    db: Session, batch: AiImportBatch, *, user_id: int | None = None, receipt_number: str
) -> GoodsReceipt:
    """Approve every included row into one DRAFT goods receipt.

    New-item rows create the Item first (as a raw material, priced at the
    invoice cost) - always here, on explicit approval, never at extraction
    time. Nothing is posted: the resulting receipt still needs its own
    goods_receipts.post before any stock actually moves, exactly like a
    manually-entered receipt would.
    """
    if batch.status != AiImportStatus.PENDING:
        raise AiImportError(f"This batch is already {batch.status.value}")

    rows = [r for r in batch.rows if not r.excluded]
    if not rows:
        raise AiImportError("Every line is excluded - nothing to approve")

    for row in rows:
        if row.quantity <= 0:
            raise AiImportError(f"Line {row.line_no + 1} ({row.raw_description}): quantity must be greater than zero")
        if row.unit_cost < 0:
            raise AiImportError(f"Line {row.line_no + 1} ({row.raw_description}): unit cost cannot be negative")
        if not row.uom_id:
            raise AiImportError(
                f"Line {row.line_no + 1} ({row.raw_description}): set a unit of measure before approving"
            )
        if not row.matched_item_id and not (row.is_new_item and (row.proposed_sku or "").strip()):
            raise AiImportError(
                f"Line {row.line_no + 1} ({row.raw_description}): match it to an existing item, "
                "or mark it as new and give it a SKU"
            )

    receipt = GoodsReceipt(
        receipt_number=receipt_number, vendor_id=batch.vendor_id, outlet_id=batch.outlet_id,
        vendor_invoice_ref=batch.invoice_ref_guess, status=ReceiptStatus.DRAFT,
        received_by_id=user_id,
        notes=f"Created from AI import batch #{batch.id} ({batch.source_filename})",
    )
    db.add(receipt)
    db.flush()

    for row in rows:
        item_id = row.matched_item_id
        if not item_id:
            new_item = Item(
                item_type=ItemType.RAW_MATERIAL, sku=row.proposed_sku.strip(),
                name=row.raw_description[:200], stock_uom_id=row.uom_id,
                purchase_uom_id=row.uom_id, cost_price=row.unit_cost,
                is_sellable=False, is_purchasable=True, is_stocked=True,
            )
            db.add(new_item)
            db.flush()
            item_id = new_item.id
            row.matched_item_id = item_id

        db.add(GoodsReceiptItem(
            goods_receipt_id=receipt.id, item_id=item_id, quantity=row.quantity,
            uom_id=row.uom_id, quantity_in_stock_uom=row.quantity, unit_cost=row.unit_cost,
            note=f"AI-extracted: \"{row.raw_description}\"",
        ))

    batch.status = AiImportStatus.APPROVED
    batch.goods_receipt_id = receipt.id
    batch.reviewed_by_id = user_id
    db.flush()
    return receipt
