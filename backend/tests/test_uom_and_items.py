"""Phase 2 - UoM foundation and unified Item Master.

Covers unit creation, the compatible/incompatible conversion rule, item-specific
packaging conversions, the item master itself (all five types), uniqueness
constraints, vendor-item relationships, and - most importantly - that the
pre-Phase-2 product/POS world still works after product_variants was renamed.
"""

from decimal import Decimal

import pytest
import sqlalchemy as sa

from app.models.inventory import MovementType
from app.models.product import Item, ItemType, Product, ProductVariant
from app.models.uom import ItemUomConversion, UnitOfMeasure, UomCategory
from app.models.vendor import Vendor, VendorItem, VendorProduct
from app.services.inventory import apply_stock_delta
from app.services.uom import (
    UomConversionError,
    convert,
    to_stock_uom,
    validate_conversion_pair,
)
from tests.conftest import stock_of


def uom(db, code: str) -> UnitOfMeasure:
    return db.query(UnitOfMeasure).filter(UnitOfMeasure.code == code).one()


# ---------------------------------------------------------------- UoM basics


def test_migration_seeds_the_required_units(db, tenant):
    """All 13 units from the brief exist out of the box."""
    codes = {u.code for u in db.query(UnitOfMeasure).all()}
    assert {"PC", "M", "CM", "MM", "KG", "G", "L", "ML",
            "ROLL", "BOX", "PKT", "DOZ", "SET"} <= codes


def test_each_category_has_exactly_one_base_unit(db, tenant):
    for cat in db.query(UomCategory).all():
        bases = [u for u in cat.units if u.is_base]
        assert len(bases) == 1, f"{cat.code} has {len(bases)} base units"


def test_uom_can_be_added_without_a_code_change(db, tenant):
    """The admin UI must be able to add a unit; nothing here is an enum."""
    length = db.query(UomCategory).filter(UomCategory.code == "LENGTH").one()
    yard = UnitOfMeasure(
        code="YD", name="Yard", symbol="yd", category_id=length.id,
        factor_to_base=Decimal("0.9144"), decimal_precision=2,
    )
    db.add(yard)
    db.flush()
    assert convert(db, Decimal("2"), yard, uom(db, "M")) == Decimal("1.8288")


def test_uom_code_is_unique_per_tenant(db, tenant):
    length = db.query(UomCategory).filter(UomCategory.code == "LENGTH").one()
    db.add(UnitOfMeasure(code="M", name="Duplicate Meter", category_id=length.id))
    with pytest.raises(sa.exc.IntegrityError):
        db.flush()


# ------------------------------------------------------- standard conversions


@pytest.mark.parametrize(
    "qty,frm,to,expected",
    [
        ("1", "M", "CM", "100"),
        ("2.5", "M", "CM", "250"),
        ("1", "M", "MM", "1000"),
        ("150", "CM", "M", "1.5"),
        ("1", "KG", "G", "1000"),
        ("250", "G", "KG", "0.25"),
        ("1", "L", "ML", "1000"),
        ("1", "DOZ", "PC", "12"),
    ],
)
def test_compatible_conversions(db, tenant, qty, frm, to, expected):
    got = convert(db, Decimal(qty), uom(db, frm), uom(db, to))
    assert got == Decimal(expected), f"{qty}{frm} -> {to} gave {got}"


@pytest.mark.parametrize("frm,to", [("PC", "M"), ("KG", "M"), ("L", "G"), ("M", "KG")])
def test_incompatible_conversions_are_refused(db, tenant, frm, to):
    """piece -> metre is not a fact about the world; refusing beats guessing."""
    with pytest.raises(UomConversionError) as exc:
        convert(db, Decimal("1"), uom(db, frm), uom(db, to))
    assert "different things" in str(exc.value)


def test_conversion_error_suggests_the_item_level_fix(db, tenant):
    with pytest.raises(UomConversionError) as exc:
        convert(db, Decimal("1"), uom(db, "ROLL"), uom(db, "M"))
    assert "item" in str(exc.value).lower()


def test_validate_conversion_pair_guards_the_admin_ui(db, tenant):
    validate_conversion_pair(uom(db, "M"), uom(db, "CM"))  # fine
    with pytest.raises(UomConversionError):
        validate_conversion_pair(uom(db, "PC"), uom(db, "M"))


def test_decimal_conversion_is_exact(db, tenant):
    """0.125 kg is 125 g exactly - no float drift."""
    assert convert(db, Decimal("0.125"), uom(db, "KG"), uom(db, "G")) == Decimal("125")
    assert convert(db, Decimal("4.5"), uom(db, "M"), uom(db, "CM")) == Decimal("450")


def test_same_unit_conversion_is_identity(db, tenant):
    assert convert(db, Decimal("7.25"), uom(db, "M"), uom(db, "M")) == Decimal("7.25")


# --------------------------------------------------- item-specific conversions


@pytest.fixture()
def lace(db, tenant):
    """Gold lace: bought in rolls, stocked and consumed in metres."""
    item = Item(
        sku="LAC-GOLD-002", name="Gold Lace 2 inch", item_type=ItemType.RAW_MATERIAL,
        stock_uom_id=uom(db, "M").id, purchase_uom_id=uom(db, "ROLL").id,
        is_sellable=False, cost_price=Decimal("120.00"),
    )
    db.add(item)
    db.flush()
    db.add(ItemUomConversion(
        item_id=item.id, from_uom_id=uom(db, "ROLL").id,
        to_uom_id=uom(db, "M").id, factor=Decimal("25"),
    ))
    db.flush()
    return item


def test_one_roll_is_twenty_five_metres(db, tenant, lace):
    assert convert(db, Decimal("1"), uom(db, "ROLL"), uom(db, "M"), item_id=lace.id) == Decimal("25")


def test_two_rolls_are_fifty_metres(db, tenant, lace):
    assert convert(db, Decimal("2"), uom(db, "ROLL"), uom(db, "M"), item_id=lace.id) == Decimal("50")


def test_reverse_direction_is_derived_not_duplicated(db, tenant, lace):
    """Defining 1 roll = 25 m implies 1 m = 0.04 roll; requiring both invites
    contradictory data."""
    assert convert(db, Decimal("50"), uom(db, "M"), uom(db, "ROLL"), item_id=lace.id) == Decimal("2")


def test_vendor_specific_conversion_beats_the_generic_one(db, tenant, lace):
    """Vendor A's roll is 25 m; vendor B ships 50 m rolls of the same lace."""
    v = Vendor(name="Vendor B")
    db.add(v)
    db.flush()
    db.add(ItemUomConversion(
        item_id=lace.id, from_uom_id=uom(db, "ROLL").id, to_uom_id=uom(db, "M").id,
        factor=Decimal("50"), vendor_id=v.id,
    ))
    db.flush()

    assert convert(db, Decimal("1"), uom(db, "ROLL"), uom(db, "M"), item_id=lace.id) == Decimal("25")
    assert convert(db, Decimal("1"), uom(db, "ROLL"), uom(db, "M"),
                   item_id=lace.id, vendor_id=v.id) == Decimal("50")


def test_purchase_uom_converts_into_stock_uom(db, tenant, lace):
    """The brief's worked example: buy 2 rolls, hold 50 m."""
    assert to_stock_uom(db, lace, Decimal("2"), uom(db, "ROLL")) == Decimal("50")


def test_full_roll_to_consumption_workflow(db, tenant, lace, warehouse):
    """2 rolls in -> 50 m; consume 4.5 m -> 45.5 m left."""
    received = to_stock_uom(db, lace, Decimal("2"), uom(db, "ROLL"))
    apply_stock_delta(db, variant_id=lace.id, outlet_id=warehouse.id,
                      quantity_delta=received, movement_type=MovementType.PURCHASE_RECEIPT)
    assert stock_of(db, lace.id, warehouse.id) == Decimal("50.0000")

    apply_stock_delta(db, variant_id=lace.id, outlet_id=warehouse.id,
                      quantity_delta=Decimal("-4.5"), movement_type=MovementType.ADJUSTMENT)
    assert stock_of(db, lace.id, warehouse.id) == Decimal("45.5000")


def test_box_of_stones_workflow(db, tenant, warehouse):
    """1 box = 500 pieces; 3 boxes minus 125 pieces = 1375."""
    stones = Item(
        sku="STM-SWR-005", name="Swarovski Stone 5mm", item_type=ItemType.RAW_MATERIAL,
        stock_uom_id=uom(db, "PC").id, purchase_uom_id=uom(db, "BOX").id, is_sellable=False,
    )
    db.add(stones)
    db.flush()
    db.add(ItemUomConversion(
        item_id=stones.id, from_uom_id=uom(db, "BOX").id,
        to_uom_id=uom(db, "PC").id, factor=Decimal("500"),
    ))
    db.flush()

    received = to_stock_uom(db, stones, Decimal("3"), uom(db, "BOX"))
    assert received == Decimal("1500")
    apply_stock_delta(db, variant_id=stones.id, outlet_id=warehouse.id,
                      quantity_delta=received, movement_type=MovementType.PURCHASE_RECEIPT)
    apply_stock_delta(db, variant_id=stones.id, outlet_id=warehouse.id,
                      quantity_delta=Decimal("-125"), movement_type=MovementType.ADJUSTMENT)
    assert stock_of(db, stones.id, warehouse.id) == Decimal("1375.0000")


# ------------------------------------------------------------- item master


def test_create_raw_material(db, tenant):
    item = Item(
        sku="FAB-SLK-RED", name="Silk Fabric Red", item_type=ItemType.RAW_MATERIAL,
        stock_uom_id=uom(db, "M").id, is_sellable=False, reorder_level=Decimal("10.5"),
    )
    db.add(item)
    db.flush()
    assert item.id and item.product_id is None
    assert item.item_type == ItemType.RAW_MATERIAL
    assert item.reorder_level == Decimal("10.5")


def test_raw_material_needs_no_parent_product(db, tenant):
    """product_id is nullable now - a bolt of silk is not a variant of anything."""
    db.add(Item(sku="THR-SLK-RED", name="Silk Thread", item_type=ItemType.RAW_MATERIAL))
    db.flush()  # would raise NotNullViolation before Phase 2


@pytest.mark.parametrize(
    "item_type", [ItemType.RAW_MATERIAL, ItemType.SEMI_FINISHED,
                  ItemType.FINISHED_PRODUCT, ItemType.PACKAGING, ItemType.SERVICE]
)
def test_all_five_item_types_are_storable(db, tenant, item_type):
    db.add(Item(sku=f"SKU-{item_type.value}", name=item_type.value, item_type=item_type))
    db.flush()


def test_service_item_is_not_stocked(db, tenant):
    svc = Item(sku="SRV-STITCH", name="Stitching Charge", item_type=ItemType.SERVICE,
               is_stocked=False, is_purchasable=False)
    db.add(svc)
    db.flush()
    assert not svc.is_stocked


def test_sku_is_unique_per_tenant(db, tenant, fabric):
    db.add(Item(sku=fabric.sku, name="Clashing SKU"))
    with pytest.raises(sa.exc.IntegrityError):
        db.flush()


def test_barcode_is_unique_per_tenant(db, tenant):
    db.add(Item(sku="A-1", name="A", barcode="8901234567890"))
    db.flush()
    db.add(Item(sku="A-2", name="B", barcode="8901234567890"))
    with pytest.raises(sa.exc.IntegrityError):
        db.flush()


def test_resolved_name_prefers_own_name_then_product(db, tenant):
    p = Product(name="Designer Lehenga")
    db.add(p)
    db.flush()
    variant = Item(sku="V-1", product_id=p.id)          # legacy shape, no own name
    standalone = Item(sku="V-2", name="Gold Lace")      # new shape
    db.add_all([variant, standalone])
    db.flush()
    assert variant.resolved_name == "Designer Lehenga"
    assert standalone.resolved_name == "Gold Lace"


# --------------------------------------------------------- vendor relationships


def test_an_item_may_have_several_vendors_at_different_prices(db, tenant, lace):
    vendors = []
    for name, price in [("Vendor A", "120"), ("Vendor B", "135"), ("Vendor C", "110")]:
        v = Vendor(name=name)
        db.add(v)
        db.flush()
        vendors.append(v)
        db.add(VendorItem(
            vendor_id=v.id, variant_id=lace.id, cost_price=Decimal(price),
            purchase_uom_id=uom(db, "ROLL").id, min_order_qty=Decimal("2"),
            lead_time_days=7, is_preferred=(name == "Vendor C"),
        ))
    db.flush()

    links = db.query(VendorItem).filter(VendorItem.variant_id == lace.id).all()
    assert len(links) == 3
    cheapest = min(links, key=lambda r: r.cost_price)
    assert cheapest.cost_price == Decimal("110.0000")
    assert cheapest.is_preferred


def test_vendor_item_carries_purchasing_terms(db, tenant, lace):
    v = Vendor(name="Lace Supplier")
    db.add(v)
    db.flush()
    link = VendorItem(
        vendor_id=v.id, variant_id=lace.id, vendor_sku="GL-2IN",
        cost_price=Decimal("118.5000"), purchase_uom_id=uom(db, "ROLL").id,
        min_order_qty=Decimal("2"), lead_time_days=10,
    )
    db.add(link)
    db.flush()
    assert link.item_id == lace.id           # new-world alias
    assert link.min_order_qty == Decimal("2")
    assert link.lead_time_days == 10


def test_vendorproduct_alias_still_resolves(db):
    assert VendorProduct is VendorItem


# ------------------------------------------- backward compatibility (critical)


def test_productvariant_alias_is_the_item_class(db):
    assert ProductVariant is Item
    assert Item.__tablename__ == "items"


def test_migration_preserved_ids_skus_and_prices(db, tenant):
    """The seeded pre-Phase-2 rows survived the rename intact."""
    row = db.execute(sa.text(
        "SELECT id, sku, cost_price, selling_price, product_id, item_type "
        "FROM items WHERE sku = 'BSS-RED-FS'"
    )).first()
    if row is None:
        pytest.skip("demo seed not present in this database")
    assert row.id == 1
    assert row.product_id is not None
    assert row.item_type == "FINISHED_PRODUCT"


def test_existing_rows_were_backfilled_as_finished_products(db, tenant):
    rows = db.execute(sa.text(
        "SELECT count(*) FROM items WHERE product_id IS NOT NULL AND item_type <> 'FINISHED_PRODUCT'"
    )).scalar_one()
    assert rows == 0, "a pre-existing variant was not classified as a finished product"


def test_compatibility_view_exposes_the_legacy_shape(db, tenant):
    """External SQL that hardcodes product_variants keeps working."""
    cols = {r[0] for r in db.execute(sa.text(
        "SELECT column_name FROM information_schema.columns WHERE table_name = 'product_variants'"
    )).fetchall()}
    assert {"id", "product_id", "sku", "barcode", "cost_price", "selling_price"} <= cols
    kind = db.execute(sa.text(
        "SELECT table_type FROM information_schema.tables WHERE table_name = 'product_variants'"
    )).scalar_one()
    assert kind == "VIEW"


def test_all_eight_foreign_keys_survived_the_rename(db, tenant):
    """The whole reason a rename was chosen over a new table + view."""
    referencing = {r[0] for r in db.execute(sa.text("""
        SELECT tc.table_name
        FROM information_schema.table_constraints tc
        JOIN information_schema.constraint_column_usage ccu
          ON tc.constraint_name = ccu.constraint_name
        WHERE tc.constraint_type = 'FOREIGN KEY' AND ccu.table_name = 'items'
    """)).fetchall()}
    assert {
        "stock_levels", "stock_movements", "sale_items", "return_items",
        "exchange_items", "stock_transfer_items", "purchase_order_items",
        "vendor_products",
    } <= referencing


def test_stock_still_moves_for_a_legacy_finished_product(db, garment, outlet):
    """Phase 1 behaviour is untouched by the Item Master."""
    apply_stock_delta(db, variant_id=garment.id, outlet_id=outlet.id,
                      quantity_delta=Decimal("5"), movement_type=MovementType.PURCHASE_RECEIPT)
    apply_stock_delta(db, variant_id=garment.id, outlet_id=outlet.id,
                      quantity_delta=Decimal("-2"), movement_type=MovementType.SALE)
    assert stock_of(db, garment.id, outlet.id) == Decimal("3")


def test_raw_materials_share_the_same_ledger_as_garments(db, tenant, lace, garment, warehouse):
    """One unified inventory ledger - not a parallel raw-material system."""
    apply_stock_delta(db, variant_id=lace.id, outlet_id=warehouse.id,
                      quantity_delta=Decimal("12.5"), movement_type=MovementType.PURCHASE_RECEIPT)
    apply_stock_delta(db, variant_id=garment.id, outlet_id=warehouse.id,
                      quantity_delta=Decimal("3"), movement_type=MovementType.PURCHASE_RECEIPT)
    rows = db.execute(sa.text(
        "SELECT count(DISTINCT variant_id) FROM stock_movements WHERE outlet_id = :o"
    ), {"o": warehouse.id}).scalar_one()
    assert rows == 2


# ------------------------------- regression: nullable product_id (found in 3B)


def test_listing_screens_survive_items_with_no_parent_product(db, tenant, warehouse):
    """Phase 2 made items.product_id nullable; several screens still did
    `variant.product.name` and raised AttributeError the moment a raw material
    appeared in them. Caught live on /api/dashboard/summary once raw materials
    existed and fell below reorder level.

    resolved_name is the guard: own name -> parent product name -> SKU.
    """
    orphan = Item(
        sku="RAW-NOPARENT", name="Gold Lace", item_type=ItemType.RAW_MATERIAL,
        stock_uom_id=uom(db, "M").id, reorder_level=Decimal("10"), is_sellable=False,
    )
    db.add(orphan)
    db.flush()
    apply_stock_delta(db, variant_id=orphan.id, outlet_id=warehouse.id,
                      quantity_delta=Decimal("1"), movement_type=MovementType.OPENING_STOCK)
    db.flush()

    assert orphan.product is None
    assert orphan.resolved_name == "Gold Lace"      # must not raise
    assert orphan.display_name.startswith("Gold Lace")

    nameless = Item(sku="RAW-NONAME", item_type=ItemType.RAW_MATERIAL)
    db.add(nameless)
    db.flush()
    assert nameless.resolved_name == "RAW-NONAME"   # falls back to SKU
