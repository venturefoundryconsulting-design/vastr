"""Phase 9 - AI-assisted invoice import.

`call_extraction` is the one function that talks to a network API; every test
here works off a plain dict standing in for its return value, exactly as the
docstring in app.services.ai_import intends. Nothing in this file makes a
real API call.
"""

from decimal import Decimal

import pytest

from app.models.ai_import import AiImportBatch, AiImportStatus
from app.models.goods_receipt import GoodsReceipt, ReceiptStatus
from app.models.product import Item, ItemType
from app.services import ai_import as ai
from tests.conftest import stock_of
from tests.test_production_orders import make_item, uom


@pytest.fixture()
def extraction() -> dict:
    return {
        "vendor_name": "Deepa Textiles",
        "invoice_ref": "DT-INV-2208",
        "lines": [
            {
                "description": "Silk Fabric Red",
                "quantity": "10.5", "unit": "M", "unit_cost": "450.00",
                "description_confidence": 0.9, "quantity_confidence": 0.85, "cost_confidence": 0.95,
            },
            {
                "description": "Brand New Sequin Trim",
                "quantity": "20", "unit": "M", "unit_cost": "60.00",
                "description_confidence": 0.7, "quantity_confidence": 0.6, "cost_confidence": 0.8,
            },
        ],
    }


# ------------------------------------------------------------------ matching


def test_matches_an_existing_item_by_exact_name(db, tenant):
    make_item(db, "FAB-AI1", "Silk Fabric Red", stock_uom="M")
    item, confidence = ai.match_item(db, "Silk Fabric Red")
    assert item is not None
    assert item.sku == "FAB-AI1"
    assert confidence == Decimal("0.95")


def test_no_match_for_a_genuinely_new_material(db, tenant):
    make_item(db, "FAB-AI2", "Cotton Voile", stock_uom="M")
    item, confidence = ai.match_item(db, "Completely Unrelated Trim")
    assert item is None
    assert confidence == Decimal("0")


def test_guesses_uom_from_unit_code(db, tenant):
    m = ai.guess_uom(db, "M")
    assert m is not None
    assert m.code == "M"
    assert ai.guess_uom(db, "not-a-real-unit") is None
    assert ai.guess_uom(db, None) is None


# -------------------------------------------------------------- staging build


def test_create_batch_stages_rows_without_touching_master_data(db, tenant, warehouse, extraction):
    make_item(db, "FAB-AI3", "Silk Fabric Red", stock_uom="M", cost="400")
    items_before = db.query(Item).count()

    batch = ai.create_batch(
        db, outlet_id=warehouse.id, vendor_id=None,
        source_filename="invoice.jpg", source_path="tenant-1/ai-import/invoice.jpg",
        extraction=extraction,
    )

    assert batch.status == AiImportStatus.PENDING
    assert batch.vendor_name_guess == "Deepa Textiles"
    assert batch.invoice_ref_guess == "DT-INV-2208"
    assert len(batch.rows) == 2
    assert db.query(Item).count() == items_before, "staging must not create items"

    matched, new = batch.rows
    assert matched.matched_item_id is not None
    assert matched.is_new_item is False
    assert matched.quantity == Decimal("10.5000")
    assert matched.unit_cost == Decimal("450.00")

    assert new.matched_item_id is None
    assert new.is_new_item is True


def test_low_confidence_words_still_get_no_match_if_too_short(db, tenant, warehouse):
    """The word-fallback only tries words longer than 3 characters, so short
    filler words in a description don't cause bogus matches."""
    make_item(db, "FAB-AI4", "The Big One", stock_uom="M")
    item, confidence = ai.match_item(db, "the big red one")
    # "big" (3 chars) is excluded by len>3; "red" too. Nothing should hit
    # unless a genuinely descriptive word matches.
    assert confidence <= Decimal("0.4")


# ----------------------------------------------------------------- row edits


def test_human_can_correct_a_staged_row(db, tenant, warehouse, extraction):
    batch = ai.create_batch(
        db, outlet_id=warehouse.id, vendor_id=None,
        source_filename="invoice.jpg", source_path="x", extraction=extraction,
    )
    row = batch.rows[1]
    ai.update_row(db, row, quantity="25", unit_cost="55.50", proposed_sku="TRIM-SEQ-01")
    assert row.quantity == Decimal("25.0000")
    assert row.unit_cost == Decimal("55.5000")
    assert row.proposed_sku == "TRIM-SEQ-01"


def test_setting_matched_item_id_clears_is_new_item(db, tenant, warehouse, extraction):
    existing = make_item(db, "FAB-AI5", "Unrelated Material XYZ", stock_uom="M")
    batch = ai.create_batch(
        db, outlet_id=warehouse.id, vendor_id=None,
        source_filename="invoice.jpg", source_path="x", extraction=extraction,
    )
    row = batch.rows[1]
    assert row.is_new_item is True
    ai.update_row(db, row, matched_item_id=existing.id)
    assert row.is_new_item is False
    assert row.matched_item_id == existing.id


# ------------------------------------------------------------------- approval


def test_approve_creates_a_draft_receipt_and_new_items(db, tenant, warehouse, extraction):
    existing = make_item(db, "FAB-AI6", "Silk Fabric Red", stock_uom="M", cost="400")
    batch = ai.create_batch(
        db, outlet_id=warehouse.id, vendor_id=None,
        source_filename="invoice.jpg", source_path="x", extraction=extraction,
    )
    batch.rows[1].proposed_sku = "TRIM-SEQ-02"  # required for a new-item row
    db.flush()

    items_before = db.query(Item).count()
    receipt = ai.approve_batch(db, batch, receipt_number="GRN-AI-TEST-0001")

    assert receipt.status == ReceiptStatus.DRAFT, "approval must never post - stock has not moved yet"
    assert stock_of(db, existing.id, warehouse.id) == Decimal("0"), "draft receipt does not touch stock"
    assert db.query(Item).count() == items_before + 1, "exactly one new item created for the unmatched row"
    assert batch.status == AiImportStatus.APPROVED
    assert batch.goods_receipt_id == receipt.id
    assert len(receipt.items) == 2


def test_approve_refuses_a_new_item_row_with_no_sku(db, tenant, warehouse, extraction):
    batch = ai.create_batch(
        db, outlet_id=warehouse.id, vendor_id=None,
        source_filename="invoice.jpg", source_path="x", extraction=extraction,
    )
    # batch.rows[1] is a new-item row with no proposed_sku set.
    with pytest.raises(ai.AiImportError, match="mark it as new and give it a SKU"):
        ai.approve_batch(db, batch, receipt_number="GRN-AI-TEST-0002")


def test_approve_refuses_a_zero_quantity_row(db, tenant, warehouse, extraction):
    existing = make_item(db, "FAB-AI7", "Silk Fabric Red", stock_uom="M")
    batch = ai.create_batch(
        db, outlet_id=warehouse.id, vendor_id=None,
        source_filename="invoice.jpg", source_path="x", extraction=extraction,
    )
    batch.rows[0].quantity = Decimal("0")
    batch.rows[1].excluded = True  # exclude the unresolved new-item row
    db.flush()
    with pytest.raises(ai.AiImportError, match="quantity must be greater than zero"):
        ai.approve_batch(db, batch, receipt_number="GRN-AI-TEST-0003")


def test_excluded_rows_are_skipped_at_approval(db, tenant, warehouse, extraction):
    make_item(db, "FAB-AI8", "Silk Fabric Red", stock_uom="M")
    batch = ai.create_batch(
        db, outlet_id=warehouse.id, vendor_id=None,
        source_filename="invoice.jpg", source_path="x", extraction=extraction,
    )
    batch.rows[1].excluded = True  # the unresolved new-item row
    db.flush()
    receipt = ai.approve_batch(db, batch, receipt_number="GRN-AI-TEST-0004")
    assert len(receipt.items) == 1


def test_approving_twice_is_refused(db, tenant, warehouse, extraction):
    make_item(db, "FAB-AI9", "Silk Fabric Red", stock_uom="M")
    batch = ai.create_batch(
        db, outlet_id=warehouse.id, vendor_id=None,
        source_filename="invoice.jpg", source_path="x", extraction=extraction,
    )
    batch.rows[1].excluded = True
    db.flush()
    ai.approve_batch(db, batch, receipt_number="GRN-AI-TEST-0005")
    with pytest.raises(ai.AiImportError, match="already approved"):
        ai.approve_batch(db, batch, receipt_number="GRN-AI-TEST-0006")


def test_reject_marks_the_batch_and_blocks_further_action(db, tenant, warehouse, extraction):
    batch = ai.create_batch(
        db, outlet_id=warehouse.id, vendor_id=None,
        source_filename="invoice.jpg", source_path="x", extraction=extraction,
    )
    ai.reject_batch(db, batch)
    assert batch.status == AiImportStatus.REJECTED
    with pytest.raises(ai.AiImportError, match="already rejected"):
        ai.approve_batch(db, batch, receipt_number="GRN-AI-TEST-0007")


def test_a_batch_with_every_line_excluded_cannot_be_approved(db, tenant, warehouse, extraction):
    batch = ai.create_batch(
        db, outlet_id=warehouse.id, vendor_id=None,
        source_filename="invoice.jpg", source_path="x", extraction=extraction,
    )
    for row in batch.rows:
        row.excluded = True
    db.flush()
    with pytest.raises(ai.AiImportError, match="nothing to approve"):
        ai.approve_batch(db, batch, receipt_number="GRN-AI-TEST-0008")
