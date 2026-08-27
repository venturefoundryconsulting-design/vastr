"""Phase 3B - Bill of Materials.

Covers the recipe itself (components, scaling, wastage, UoM), the versioning
guarantees that make historical production reproducible, multi-level explosion
with cycle rejection, substitutes, and Decimal-exact costing.
"""

from decimal import Decimal

import pytest
import sqlalchemy as sa

from app.models.bom import Bom, BomComponent, BomComponentSubstitute, BomStatus, BomVersion
from app.models.product import Item, ItemType
from app.models.uom import ItemUomConversion, UnitOfMeasure
from app.services.bom import (
    BomError,
    CircularBomError,
    activate,
    assert_editable,
    assert_no_cycle,
    availability,
    copy_components,
    cost_version,
    explode,
    find_duplicate_components,
    next_version_no,
    validate_component_uom,
)
from app.services.inventory import apply_stock_delta
from app.models.inventory import MovementType


def uom(db, code: str) -> UnitOfMeasure:
    return db.query(UnitOfMeasure).filter(UnitOfMeasure.code == code).one()


def make_item(db, sku, name, *, stock_uom="M", cost="0", item_type=ItemType.RAW_MATERIAL) -> Item:
    it = Item(
        sku=sku, name=name, item_type=item_type,
        stock_uom_id=uom(db, stock_uom).id, cost_price=Decimal(cost), is_sellable=False,
    )
    db.add(it)
    db.flush()
    return it


def make_bom(db, item, *, output_qty="1", status=BomStatus.DRAFT, version_no=1) -> BomVersion:
    bom = db.query(Bom).filter(Bom.item_id == item.id).first()
    if not bom:
        bom = Bom(item_id=item.id, name=f"{item.name} BOM")
        db.add(bom)
        db.flush()
    v = BomVersion(
        bom_id=bom.id, version_no=version_no, status=status,
        output_quantity=Decimal(output_qty), output_uom_id=uom(db, "PC").id,
    )
    db.add(v)
    db.flush()
    return v


def add_component(db, version, item, qty, uom_code="M", scrap="0", optional=False, seq=0):
    c = BomComponent(
        bom_version_id=version.id, item_id=item.id, quantity=Decimal(str(qty)),
        uom_id=uom(db, uom_code).id, scrap_pct=Decimal(str(scrap)),
        is_optional=optional, sequence=seq,
    )
    db.add(c)
    db.flush()
    return c


@pytest.fixture()
def lehenga(db, tenant):
    return make_item(db, "GAR-LHNG-RED", "Designer Lehenga - Red",
                     stock_uom="PC", cost="0", item_type=ItemType.FINISHED_PRODUCT)


@pytest.fixture()
def materials(db, tenant):
    """The eight materials from the brief, with the units they are stocked in."""
    return {
        "fabric": make_item(db, "FAB-SLK-RED", "Silk Fabric", stock_uom="M", cost="800"),
        "lining": make_item(db, "FAB-LIN-001", "Lining", stock_uom="M", cost="150"),
        "lace": make_item(db, "LAC-GOLD-002", "Gold Lace", stock_uom="M", cost="120"),
        "buttons": make_item(db, "BTN-PRL-012", "Pearl Buttons", stock_uom="PC", cost="8"),
        "stones": make_item(db, "STM-SWR-005", "Swarovski Stones", stock_uom="PC", cost="4"),
        "thread": make_item(db, "THR-SLK-RED", "Silk Thread", stock_uom="G", cost="0.5"),
        "zipper": make_item(db, "ZIP-001", "Zipper", stock_uom="PC", cost="25"),
        "hooks": make_item(db, "HOK-001", "Hooks", stock_uom="PC", cost="2"),
    }


# ------------------------------------------------------------------ basic BOM


def test_create_bom_with_eight_components(db, lehenga, materials):
    """The worked example from the brief."""
    v = make_bom(db, lehenga)
    spec = [
        (materials["fabric"], "4.5", "M"), (materials["lining"], "3", "M"),
        (materials["lace"], "8", "M"), (materials["buttons"], "18", "PC"),
        (materials["stones"], "250", "PC"), (materials["thread"], "200", "G"),
        (materials["zipper"], "1", "PC"), (materials["hooks"], "12", "PC"),
    ]
    for i, (item, qty, u) in enumerate(spec):
        add_component(db, v, item, qty, u, seq=i)
    db.flush()

    assert len(v.components) == 8
    rows = {r["item"].sku: r["quantity"] for r in explode(db, v, Decimal("1"))}
    assert rows["FAB-SLK-RED"] == Decimal("4.5")
    assert rows["STM-SWR-005"] == Decimal("250")


def test_large_bom_of_120_components(db, lehenga, tenant):
    """Hundreds of small trims is the realistic case for a boutique garment."""
    v = make_bom(db, lehenga)
    for i in range(120):
        item = make_item(db, f"TRIM-{i:04d}", f"Trim {i}", stock_uom="PC", cost="1")
        add_component(db, v, item, "2", "PC", seq=i)
    db.flush()
    assert len(v.components) == 120
    assert len(explode(db, v, Decimal("1"))) == 120


# ------------------------------------------------------------------ scaling


def test_requirements_scale_with_output_quantity(db, lehenga, materials):
    v = make_bom(db, lehenga)
    add_component(db, v, materials["fabric"], "4.5", "M")
    db.flush()

    one = {r["item"].sku: r["quantity"] for r in explode(db, v, Decimal("1"))}
    ten = {r["item"].sku: r["quantity"] for r in explode(db, v, Decimal("10"))}
    assert one["FAB-SLK-RED"] == Decimal("4.5")
    assert ten["FAB-SLK-RED"] == Decimal("45.0")


def test_batch_output_greater_than_one_divides_correctly(db, tenant, materials):
    """A BOM whose batch yields 2 panels needs half the material per panel."""
    panel = make_item(db, "SEMI-PANEL", "Embroidered Panel", stock_uom="PC",
                      item_type=ItemType.SEMI_FINISHED)
    v = make_bom(db, panel, output_qty="2")
    add_component(db, v, materials["stones"], "500", "PC")
    db.flush()
    rows = {r["item"].sku: r["quantity"] for r in explode(db, v, Decimal("1"))}
    assert rows["STM-SWR-005"] == Decimal("250")


# ------------------------------------------------------------------ wastage


def test_scrap_adds_to_requirement_without_changing_the_recipe(db, lehenga, materials):
    """8 m at 5% scrap requires 8.4 m issued - but the BOM still reads 8 m."""
    v = make_bom(db, lehenga)
    c = add_component(db, v, materials["lace"], "8", "M", scrap="5")
    db.flush()

    assert c.quantity == Decimal("8.0000")           # recipe unchanged
    assert c.gross_quantity == Decimal("8.400000")   # derived
    rows = {r["item"].sku: r for r in explode(db, v, Decimal("1"))}
    assert rows["LAC-GOLD-002"]["quantity"] == Decimal("8.400000")
    assert rows["LAC-GOLD-002"]["net_quantity"] == Decimal("8.0000")


def test_scrap_scales_with_batch_size(db, lehenga, materials):
    v = make_bom(db, lehenga)
    add_component(db, v, materials["lace"], "8", "M", scrap="5")
    db.flush()
    rows = {r["item"].sku: r["quantity"] for r in explode(db, v, Decimal("10"))}
    assert rows["LAC-GOLD-002"] == Decimal("84.000000")


# ---------------------------------------------------------------------- UoM


def test_component_may_use_a_different_but_convertible_uom(db, lehenga, materials, warehouse):
    """450 cm of a fabric stocked in metres is 4.5 m of stock."""
    v = make_bom(db, lehenga)
    add_component(db, v, materials["fabric"], "450", "CM")
    db.flush()
    apply_stock_delta(db, variant_id=materials["fabric"].id, outlet_id=warehouse.id,
                      quantity_delta=Decimal("10"), movement_type=MovementType.OPENING_STOCK)
    db.flush()

    rows = {r["sku"]: r for r in availability(db, v, Decimal("1"), outlet_id=warehouse.id)}
    assert rows["FAB-SLK-RED"]["required"] == Decimal("4.5")


def test_incompatible_component_uom_is_rejected(db, materials):
    """Pieces cannot be a unit for a fabric stocked in metres."""
    with pytest.raises(BomError, match="different things"):
        validate_component_uom(db, materials["fabric"], uom(db, "PC").id)


def test_item_specific_conversion_makes_a_cross_dimension_uom_valid(db, tenant, materials):
    """A roll is a count and a metre is a length - but 1 roll = 25 m of THIS lace."""
    lace = materials["lace"]
    db.add(ItemUomConversion(
        item_id=lace.id, from_uom_id=uom(db, "ROLL").id,
        to_uom_id=uom(db, "M").id, factor=Decimal("25"),
    ))
    db.flush()
    validate_component_uom(db, lace, uom(db, "ROLL").id)  # must not raise


# ---------------------------------------------------------------- versioning


def test_new_version_does_not_disturb_the_old_one(db, lehenga, materials):
    """V1 says 8 m of lace; V2 says 10 m; V1 must still say 8 m."""
    v1 = make_bom(db, lehenga, version_no=1)
    add_component(db, v1, materials["lace"], "8", "M")
    db.flush()
    activate(db, v1)

    v2 = make_bom(db, lehenga, version_no=next_version_no(db, v1.bom_id))
    copy_components(db, v1, v2)
    db.flush()
    v2.components[0].quantity = Decimal("10")
    db.flush()

    db.refresh(v1)
    assert v1.components[0].quantity == Decimal("8.0000")
    assert v2.components[0].quantity == Decimal("10.0000")
    assert v1.status == BomStatus.ACTIVE and v2.status == BomStatus.DRAFT


def test_activating_v2_archives_v1(db, lehenga, materials):
    v1 = make_bom(db, lehenga, version_no=1)
    add_component(db, v1, materials["lace"], "8", "M")
    db.flush()
    activate(db, v1)

    v2 = make_bom(db, lehenga, version_no=2)
    add_component(db, v2, materials["lace"], "10", "M")
    db.flush()
    activate(db, v2)

    db.refresh(v1)
    assert v1.status == BomStatus.ARCHIVED
    assert v2.status == BomStatus.ACTIVE


def test_only_one_active_version_per_bom_enforced_by_the_database(db, lehenga, materials):
    """Not just service discipline - the partial unique index must refuse it."""
    v1 = make_bom(db, lehenga, version_no=1, status=BomStatus.ACTIVE)
    db.flush()
    db.add(BomVersion(bom_id=v1.bom_id, version_no=2, status=BomStatus.ACTIVE,
                      output_quantity=Decimal("1")))
    with pytest.raises(sa.exc.IntegrityError):
        db.flush()


def test_active_version_cannot_be_edited(db, lehenga, materials):
    v = make_bom(db, lehenga)
    add_component(db, v, materials["lace"], "8", "M")
    db.flush()
    activate(db, v)
    with pytest.raises(BomError, match="cannot be edited"):
        assert_editable(v)


def test_locked_version_can_never_be_edited(db, lehenga, materials):
    """is_locked is the harder stop: it survives even in DRAFT."""
    v = make_bom(db, lehenga)
    add_component(db, v, materials["lace"], "8", "M")
    v.is_locked = True
    db.flush()
    with pytest.raises(BomError, match="used by production"):
        assert_editable(v)


def test_archived_version_cannot_be_reactivated(db, lehenga, materials):
    v = make_bom(db, lehenga, status=BomStatus.ARCHIVED)
    add_component(db, v, materials["lace"], "8", "M")
    db.flush()
    with pytest.raises(BomError, match="archived"):
        activate(db, v)


def test_empty_version_cannot_be_activated(db, lehenga):
    v = make_bom(db, lehenga)
    db.flush()
    with pytest.raises(BomError, match="at least one component"):
        activate(db, v)


def test_version_numbers_increment(db, lehenga, materials):
    v1 = make_bom(db, lehenga, version_no=1)
    db.flush()
    assert next_version_no(db, v1.bom_id) == 2
    make_bom(db, lehenga, version_no=2)
    db.flush()
    assert next_version_no(db, v1.bom_id) == 3


def test_copy_carries_substitutes_forward(db, lehenga, materials):
    v1 = make_bom(db, lehenga, version_no=1)
    c = add_component(db, v1, materials["stones"], "250", "PC")
    crystal = make_item(db, "STM-CRY-005", "Crystal Stone 5mm", stock_uom="PC", cost="2")
    db.add(BomComponentSubstitute(bom_component_id=c.id, item_id=crystal.id, priority=1))
    db.flush()

    v2 = make_bom(db, lehenga, version_no=2)
    copy_components(db, v1, v2)
    db.flush()
    assert len(v2.components[0].substitutes) == 1
    assert v2.components[0].substitutes[0].item_id == crystal.id


# ------------------------------------------------------------- multi-level


def test_multi_level_bom_explodes_to_raw_materials(db, tenant, materials):
    """Lehenga -> Blouse -> Embroidered Panel -> stones + thread."""
    panel = make_item(db, "SEMI-PANEL", "Embroidered Panel", stock_uom="PC",
                      item_type=ItemType.SEMI_FINISHED)
    pv = make_bom(db, panel)
    add_component(db, pv, materials["stones"], "100", "PC")
    add_component(db, pv, materials["thread"], "50", "G")
    db.flush()
    activate(db, pv)

    blouse = make_item(db, "SEMI-BLOUSE", "Blouse", stock_uom="PC",
                       item_type=ItemType.SEMI_FINISHED)
    bv = make_bom(db, blouse)
    add_component(db, bv, panel, "2", "PC")
    add_component(db, bv, materials["fabric"], "1.5", "M")
    db.flush()
    activate(db, bv)

    lehenga = make_item(db, "GAR-LHNG-2", "Lehenga", stock_uom="PC",
                        item_type=ItemType.FINISHED_PRODUCT)
    lv = make_bom(db, lehenga)
    add_component(db, lv, blouse, "1", "PC")
    add_component(db, lv, materials["lace"], "8", "M")
    db.flush()

    rows = explode(db, lv, Decimal("1"))
    by_sku: dict[str, Decimal] = {}
    for r in rows:
        if not r["is_subassembly"]:
            by_sku[r["item"].sku] = by_sku.get(r["item"].sku, Decimal("0")) + r["quantity"]

    # 1 lehenga -> 1 blouse -> 2 panels -> 200 stones, 100 g thread
    assert by_sku["STM-SWR-005"] == Decimal("200")
    assert by_sku["THR-SLK-RED"] == Decimal("100")
    assert by_sku["FAB-SLK-RED"] == Decimal("1.5")
    assert by_sku["LAC-GOLD-002"] == Decimal("8")
    assert any(r["is_subassembly"] for r in rows)


def test_circular_bom_is_rejected(db, tenant, materials):
    """A -> B -> C -> A must fail."""
    a = make_item(db, "A-ITEM", "A", stock_uom="PC", item_type=ItemType.SEMI_FINISHED)
    b = make_item(db, "B-ITEM", "B", stock_uom="PC", item_type=ItemType.SEMI_FINISHED)
    c = make_item(db, "C-ITEM", "C", stock_uom="PC", item_type=ItemType.SEMI_FINISHED)

    av = make_bom(db, a)
    add_component(db, av, b, "1", "PC")
    db.flush()
    activate(db, av)

    bv = make_bom(db, b)
    add_component(db, bv, c, "1", "PC")
    db.flush()
    activate(db, bv)

    cv = make_bom(db, c)
    db.flush()
    with pytest.raises(CircularBomError):
        assert_no_cycle(db, parent_item_id=c.id, component_item_id=a.id)


def test_direct_self_reference_is_rejected(db, lehenga):
    with pytest.raises(CircularBomError, match="component of itself"):
        assert_no_cycle(db, parent_item_id=lehenga.id, component_item_id=lehenga.id)


def test_a_shared_subassembly_is_not_mistaken_for_a_cycle(db, tenant, materials):
    """Two parents using the same panel is a diamond, not a loop."""
    panel = make_item(db, "SEMI-SHARED", "Shared Panel", stock_uom="PC",
                      item_type=ItemType.SEMI_FINISHED)
    pv = make_bom(db, panel)
    add_component(db, pv, materials["stones"], "10", "PC")
    db.flush()
    activate(db, pv)

    top = make_item(db, "GAR-TOP", "Top", stock_uom="PC", item_type=ItemType.FINISHED_PRODUCT)
    assert_no_cycle(db, parent_item_id=top.id, component_item_id=panel.id)  # must not raise


# -------------------------------------------------------------- substitutes


def test_substitute_is_recorded_but_does_not_replace_the_primary(db, lehenga, materials):
    v = make_bom(db, lehenga)
    c = add_component(db, v, materials["stones"], "250", "PC")
    crystal = make_item(db, "STM-CRY-005", "Crystal Stone 5mm", stock_uom="PC", cost="2")
    db.add(BomComponentSubstitute(bom_component_id=c.id, item_id=crystal.id, priority=1))
    db.flush()

    rows = {r["item"].sku: r for r in explode(db, v, Decimal("1"))}
    assert "STM-SWR-005" in rows          # primary is what the BOM requires
    assert "STM-CRY-005" not in rows      # substitute is not silently swapped in
    assert len(c.substitutes) == 1


# --------------------------------------------------------------- duplicates


def test_duplicate_components_are_reported_not_merged(db, lehenga, materials):
    v = make_bom(db, lehenga)
    add_component(db, v, materials["lace"], "4", "M", seq=0)
    add_component(db, v, materials["lace"], "3", "M", seq=1)
    db.flush()

    dupes = find_duplicate_components(v.components)
    assert len(dupes) == 1
    assert dupes[0]["count"] == 2
    assert dupes[0]["total_quantity"] == Decimal("7.0000")
    assert len(v.components) == 2  # nothing was merged behind the user's back


def test_same_item_in_different_uom_is_not_a_duplicate(db, lehenga, materials):
    v = make_bom(db, lehenga)
    add_component(db, v, materials["fabric"], "4", "M", seq=0)
    add_component(db, v, materials["fabric"], "50", "CM", seq=1)
    db.flush()
    assert find_duplicate_components(v.components) == []


# ------------------------------------------------------------------ costing


def test_material_cost_is_decimal_exact(db, lehenga, materials):
    """The brief's worked example."""
    v = make_bom(db, lehenga)
    add_component(db, v, materials["fabric"], "4.5", "M")     # 4.5 x 800 = 3600
    add_component(db, v, materials["lace"], "8", "M")         # 8   x 120 = 960
    add_component(db, v, materials["stones"], "250", "PC")    # 250 x 4   = 1000
    add_component(db, v, materials["buttons"], "18", "PC")    # 18  x 8   = 144
    db.flush()

    result = cost_version(db, v, Decimal("1"))
    assert result["total_cost"] == Decimal("5704.00")
    assert all(isinstance(line["line_cost"], Decimal) for line in result["lines"])


def test_cost_scales_with_quantity(db, lehenga, materials):
    v = make_bom(db, lehenga)
    add_component(db, v, materials["lace"], "8", "M")
    db.flush()
    assert cost_version(db, v, Decimal("1"))["total_cost"] == Decimal("960.00")
    assert cost_version(db, v, Decimal("10"))["total_cost"] == Decimal("9600.00")


def test_cost_includes_scrap(db, lehenga, materials):
    v = make_bom(db, lehenga)
    add_component(db, v, materials["lace"], "8", "M", scrap="5")  # 8.4 x 120
    db.flush()
    assert cost_version(db, v, Decimal("1"))["total_cost"] == Decimal("1008.00")


@pytest.mark.parametrize("qty", ["4.5000", "0.1250", "0.3333"])
def test_decimal_quantities_survive_costing_without_float_error(db, lehenga, materials, qty):
    v = make_bom(db, lehenga)
    add_component(db, v, materials["fabric"], qty, "M")
    db.flush()
    expected = (Decimal(qty) * Decimal("800")).quantize(Decimal("0.01"))
    assert cost_version(db, v, Decimal("1"))["total_cost"] == expected


# ------------------------------------------------------------- availability


def test_availability_reports_shortage_without_touching_stock(db, lehenga, materials, warehouse):
    """The brief's example: fabric fine, lace short by 3, stones fine."""
    v = make_bom(db, lehenga)
    add_component(db, v, materials["fabric"], "4.5", "M")
    add_component(db, v, materials["lace"], "8", "M")
    add_component(db, v, materials["stones"], "250", "PC")
    db.flush()

    for item, qty in [(materials["fabric"], "20"), (materials["lace"], "5"),
                      (materials["stones"], "600")]:
        apply_stock_delta(db, variant_id=item.id, outlet_id=warehouse.id,
                          quantity_delta=Decimal(qty), movement_type=MovementType.OPENING_STOCK)
    db.flush()

    before = db.execute(sa.text("SELECT count(*) FROM stock_movements")).scalar_one()
    rows = {r["sku"]: r for r in availability(db, v, Decimal("1"), outlet_id=warehouse.id)}
    after = db.execute(sa.text("SELECT count(*) FROM stock_movements")).scalar_one()

    assert before == after, "availability must not write to the ledger"
    assert rows["FAB-SLK-RED"]["is_available"] is True
    assert rows["LAC-GOLD-002"]["is_available"] is False
    assert rows["LAC-GOLD-002"]["shortage"] == Decimal("3")
    assert rows["LAC-GOLD-002"]["suggested_purchase_qty"] == Decimal("3")
    assert rows["STM-SWR-005"]["is_available"] is True


def test_availability_aggregates_repeated_materials(db, lehenga, materials, warehouse):
    """Two lines of 4 m each against 6 m of stock is short, even though each
    line alone would look satisfiable."""
    v = make_bom(db, lehenga)
    add_component(db, v, materials["lace"], "4", "M", seq=0)
    add_component(db, v, materials["lace"], "4", "M", seq=1)
    db.flush()
    apply_stock_delta(db, variant_id=materials["lace"].id, outlet_id=warehouse.id,
                      quantity_delta=Decimal("6"), movement_type=MovementType.OPENING_STOCK)
    db.flush()

    rows = {r["sku"]: r for r in availability(db, v, Decimal("1"), outlet_id=warehouse.id)}
    assert rows["LAC-GOLD-002"]["required"] == Decimal("8")
    assert rows["LAC-GOLD-002"]["shortage"] == Decimal("2")
