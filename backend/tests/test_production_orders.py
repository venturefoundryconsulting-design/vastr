"""Phase 3C - production order planning.

The single most important test in this file is
``test_inventory_is_never_touched``: Phase 3C is planning only, and the whole
phase boundary rests on nothing here moving stock.
"""

from datetime import date
from decimal import Decimal

import pytest
import sqlalchemy as sa

from app.models.bom import Bom, BomComponent, BomStatus, BomVersion
from app.models.inventory import MovementType, StockLevel, StockMovement
from app.models.product import Item, ItemType
from app.models.production import (
    MaterialAvailability,
    OrderAvailability,
    ProductionOrder,
    ProductionStatus,
)
from app.models.uom import UnitOfMeasure
from app.services import production as prod
from app.services.inventory import apply_stock_delta
from tests.test_ledger_integrity import assert_ledger_reconciles


def uom(db, code: str) -> UnitOfMeasure:
    return db.query(UnitOfMeasure).filter(UnitOfMeasure.code == code).one()


def make_item(db, sku, name, *, stock_uom="M", cost="0", item_type=ItemType.RAW_MATERIAL) -> Item:
    it = Item(sku=sku, name=name, item_type=item_type,
              stock_uom_id=uom(db, stock_uom).id, cost_price=Decimal(cost), is_sellable=False)
    db.add(it)
    db.flush()
    return it


def make_bom(db, item, components, *, output_qty="1", activate=True, version_no=1) -> BomVersion:
    """components: [(item, qty, uom_code, scrap_pct)]"""
    bom = db.query(Bom).filter(Bom.item_id == item.id).first()
    if not bom:
        bom = Bom(item_id=item.id, name=f"{item.name} BOM")
        db.add(bom)
        db.flush()
    v = BomVersion(bom_id=bom.id, version_no=version_no, status=BomStatus.DRAFT,
                   output_quantity=Decimal(output_qty), output_uom_id=uom(db, "PC").id)
    db.add(v)
    db.flush()
    for i, (comp, qty, code, scrap) in enumerate(components):
        db.add(BomComponent(
            bom_version_id=v.id, item_id=comp.id, quantity=Decimal(str(qty)),
            uom_id=uom(db, code).id, scrap_pct=Decimal(str(scrap)), sequence=i,
        ))
    db.flush()
    if activate:
        from app.services.bom import activate as do_activate
        do_activate(db, v)
    return v


def make_order(db, item, version, qty, outlet, status=ProductionStatus.DRAFT) -> ProductionOrder:
    order = ProductionOrder(
        po_number=f"PRD-TEST-{item.id}-{qty}", item_id=item.id,
        bom_id=version.bom_id, bom_version_id=version.id,
        planned_quantity=Decimal(str(qty)), location_id=outlet.id,
        uom_id=item.stock_uom_id, status=status,
    )
    db.add(order)
    db.flush()
    prod.rebuild_materials(db, order)
    db.refresh(order)
    return order


@pytest.fixture()
def lehenga(db, tenant):
    return make_item(db, "GAR-LHNG-3C", "Designer Lehenga", stock_uom="PC",
                     item_type=ItemType.FINISHED_PRODUCT)


@pytest.fixture()
def silk(db, tenant):
    return make_item(db, "FAB-SLK-3C", "Silk Fabric", stock_uom="M", cost="800")


@pytest.fixture()
def lace(db, tenant):
    return make_item(db, "LAC-GOLD-3C", "Gold Lace", stock_uom="M", cost="120")


@pytest.fixture()
def stones(db, tenant):
    return make_item(db, "STM-SWR-3C", "Swarovski Stones", stock_uom="PC", cost="4")


# --------------------------------------------------- INVENTORY SAFETY (key)


def test_inventory_is_never_touched(db, lehenga, silk, lace, warehouse, user):
    """MANDATORY: the entire 3C lifecycle must leave inventory byte-identical.

    Runs create -> plan -> release -> start -> close short, plus availability
    calls throughout, and asserts stock_levels and stock_movements are unchanged
    row-for-row and value-for-value.
    """
    apply_stock_delta(db, variant_id=silk.id, outlet_id=warehouse.id,
                      quantity_delta=Decimal("100"), movement_type=MovementType.OPENING_STOCK)
    apply_stock_delta(db, variant_id=lace.id, outlet_id=warehouse.id,
                      quantity_delta=Decimal("20"), movement_type=MovementType.OPENING_STOCK)
    db.flush()

    def snapshot():
        levels = db.execute(sa.text(
            "SELECT variant_id, outlet_id, quantity FROM stock_levels ORDER BY variant_id, outlet_id"
        )).fetchall()
        moves = db.execute(sa.text(
            "SELECT id, variant_id, outlet_id, movement_type, quantity_delta "
            "FROM stock_movements ORDER BY id"
        )).fetchall()
        return [tuple(r) for r in levels], [tuple(r) for r in moves]

    before_levels, before_moves = snapshot()

    v = make_bom(db, lehenga, [(silk, "4.5", "M", 0), (lace, "8", "M", 5)])
    order = make_order(db, lehenga, v, 10, warehouse)

    prod.availability(db, order)
    order.status = ProductionStatus.PLANNED
    db.flush()
    prod.availability(db, order)
    order.status = ProductionStatus.RELEASED
    db.flush()
    prod.availability(db, order)
    order.status = ProductionStatus.IN_PROGRESS
    db.flush()
    order.status = ProductionStatus.CLOSED_SHORT
    order.produced_quantity = Decimal("6")
    order.cancelled_quantity = Decimal("4")
    db.flush()
    prod.availability(db, order)

    after_levels, after_moves = snapshot()
    assert after_levels == before_levels, "stock_levels changed during Phase 3C planning"
    assert after_moves == before_moves, "stock_movements changed during Phase 3C planning"
    assert_ledger_reconciles(db)


def test_availability_is_pure(db, lehenga, silk, warehouse):
    """Calling availability repeatedly must not accumulate anything."""
    apply_stock_delta(db, variant_id=silk.id, outlet_id=warehouse.id,
                      quantity_delta=Decimal("50"), movement_type=MovementType.OPENING_STOCK)
    db.flush()
    v = make_bom(db, lehenga, [(silk, "4.5", "M", 0)])
    order = make_order(db, lehenga, v, 1, warehouse)

    count_before = db.execute(sa.text("SELECT count(*) FROM stock_movements")).scalar_one()
    results = [prod.availability(db, order) for _ in range(5)]
    count_after = db.execute(sa.text("SELECT count(*) FROM stock_movements")).scalar_one()

    assert count_before == count_after
    assert all(r["lines"][0]["available"] == results[0]["lines"][0]["available"] for r in results)


# ------------------------------------------------- requirement calculation


def test_requirements_scale_to_order_quantity(db, lehenga, silk, lace, stones, warehouse):
    """The brief's example: 1 garment -> 10 garments."""
    v = make_bom(db, lehenga, [(silk, "4.5", "M", 0), (lace, "8", "M", 0), (stones, "250", "PC", 0)])
    order = make_order(db, lehenga, v, 10, warehouse)
    by_sku = {m.item.sku: m for m in order.materials}
    assert by_sku["FAB-SLK-3C"].planned_quantity == Decimal("45")
    assert by_sku["LAC-GOLD-3C"].planned_quantity == Decimal("80")
    assert by_sku["STM-SWR-3C"].planned_quantity == Decimal("2500")


def test_wastage_is_separate_from_base_requirement(db, lehenga, lace, warehouse):
    """8 m at 5%, x10 -> base 80, wastage 4, planned issue 84."""
    v = make_bom(db, lehenga, [(lace, "8", "M", 5)])
    order = make_order(db, lehenga, v, 10, warehouse)
    m = order.materials[0]
    assert m.base_quantity == Decimal("80")
    assert m.planned_quantity == Decimal("84")
    assert m.expected_wastage == Decimal("4")
    assert m.scrap_pct == Decimal("5.000")


def test_decimal_production_quantity(db, warehouse, tenant, silk):
    """A semi-finished run can be 12.5 metres, not just whole units."""
    piping = make_item(db, "SEMI-PIPE-3C", "Piping", stock_uom="M",
                       item_type=ItemType.SEMI_FINISHED)
    v = make_bom(db, piping, [(silk, "0.2", "M", 0)])
    order = make_order(db, piping, v, "12.5", warehouse)
    assert order.planned_quantity == Decimal("12.5000")
    assert order.materials[0].planned_quantity == Decimal("2.5")


def test_batch_output_greater_than_one(db, warehouse, tenant, stones):
    panel = make_item(db, "SEMI-PANEL-3C", "Panel", stock_uom="PC",
                      item_type=ItemType.SEMI_FINISHED)
    v = make_bom(db, panel, [(stones, "500", "PC", 0)], output_qty="2")
    order = make_order(db, panel, v, 10, warehouse)
    assert order.materials[0].planned_quantity == Decimal("2500")


# ----------------------------------------------------------- availability


def test_available_when_stock_exceeds_requirement(db, lehenga, silk, warehouse):
    apply_stock_delta(db, variant_id=silk.id, outlet_id=warehouse.id,
                      quantity_delta=Decimal("15"), movement_type=MovementType.OPENING_STOCK)
    db.flush()
    v = make_bom(db, lehenga, [(silk, "10", "M", 0)])
    order = make_order(db, lehenga, v, 1, warehouse)
    result = prod.availability(db, order)
    assert result["lines"][0]["status"] == MaterialAvailability.AVAILABLE
    assert result["overall"] == OrderAvailability.READY


def test_partial_when_some_stock_exists(db, lehenga, silk, warehouse):
    apply_stock_delta(db, variant_id=silk.id, outlet_id=warehouse.id,
                      quantity_delta=Decimal("6"), movement_type=MovementType.OPENING_STOCK)
    db.flush()
    v = make_bom(db, lehenga, [(silk, "10", "M", 0)])
    order = make_order(db, lehenga, v, 1, warehouse)
    result = prod.availability(db, order)
    line = result["lines"][0]
    assert line["status"] == MaterialAvailability.PARTIAL
    assert line["shortage"] == Decimal("4")
    assert result["overall"] == OrderAvailability.PARTIAL_MATERIAL


def test_short_when_no_stock(db, lehenga, silk, warehouse):
    v = make_bom(db, lehenga, [(silk, "10", "M", 0)])
    order = make_order(db, lehenga, v, 1, warehouse)
    result = prod.availability(db, order)
    line = result["lines"][0]
    assert line["status"] == MaterialAvailability.SHORT
    assert line["shortage"] == Decimal("10")
    assert line["suggested_purchase_qty"] == Decimal("10")
    assert result["overall"] == OrderAvailability.MATERIAL_SHORTAGE


def test_not_stocked_material_is_flagged(db, lehenga, warehouse, tenant):
    service = Item(sku="SRV-EMB-3C", name="Embroidery Service", item_type=ItemType.SERVICE,
                   stock_uom_id=uom(db, "PC").id, is_stocked=False, is_sellable=False)
    db.add(service)
    db.flush()
    v = make_bom(db, lehenga, [(service, "1", "PC", 0)])
    order = make_order(db, lehenga, v, 1, warehouse)
    assert prod.availability(db, order)["lines"][0]["status"] == MaterialAvailability.NOT_STOCKED


def test_available_subtracts_reserved_not_just_on_hand(db, lehenga, silk, warehouse, monkeypatch):
    """On hand 20, reserved 15, required 10 -> available 5, shortage 5.

    Reservations arrive in Phase 3D; this pins the arithmetic now by stubbing the
    seam, so 3D only has to fill in the query rather than re-deriving the rule.
    """
    apply_stock_delta(db, variant_id=silk.id, outlet_id=warehouse.id,
                      quantity_delta=Decimal("20"), movement_type=MovementType.OPENING_STOCK)
    db.flush()
    v = make_bom(db, lehenga, [(silk, "10", "M", 0)])
    order = make_order(db, lehenga, v, 1, warehouse)

    monkeypatch.setattr(prod, "_reserved_by_item", lambda db, loc: {silk.id: Decimal("15")})
    line = prod.availability(db, order)["lines"][0]
    assert line["on_hand"] == Decimal("20")
    assert line["reserved"] == Decimal("15")
    assert line["available"] == Decimal("5")
    assert line["shortage"] == Decimal("5")
    assert line["status"] == MaterialAvailability.PARTIAL


def test_repeated_material_is_aggregated_before_comparing(db, lehenga, lace, warehouse):
    apply_stock_delta(db, variant_id=lace.id, outlet_id=warehouse.id,
                      quantity_delta=Decimal("6"), movement_type=MovementType.OPENING_STOCK)
    db.flush()
    v = make_bom(db, lehenga, [(lace, "4", "M", 0), (lace, "4", "M", 0)])
    order = make_order(db, lehenga, v, 1, warehouse)
    line = prod.availability(db, order)["lines"][0]
    assert line["planned_quantity"] == Decimal("8")
    assert line["shortage"] == Decimal("2")


def test_uom_conversion_is_applied_to_requirements(db, lehenga, silk, warehouse):
    """A BOM line in centimetres against stock held in metres."""
    apply_stock_delta(db, variant_id=silk.id, outlet_id=warehouse.id,
                      quantity_delta=Decimal("10"), movement_type=MovementType.OPENING_STOCK)
    db.flush()
    v = make_bom(db, lehenga, [(silk, "450", "CM", 0)])
    order = make_order(db, lehenga, v, 1, warehouse)
    line = prod.availability(db, order)["lines"][0]
    assert line["required"] == Decimal("4.5")
    assert line["status"] == MaterialAvailability.AVAILABLE


# ---------------------------------------------------------- multi-level BOM


def test_multi_level_explosion_does_not_double_count(db, warehouse, tenant, silk):
    """10 lehengas -> 10 blouses -> 20 m fabric. Not 30, not 200."""
    blouse = make_item(db, "SEMI-BLOUSE-3C", "Blouse", stock_uom="PC",
                       item_type=ItemType.SEMI_FINISHED)
    make_bom(db, blouse, [(silk, "2", "M", 0)])

    lehenga = make_item(db, "GAR-ML-3C", "Lehenga ML", stock_uom="PC",
                        item_type=ItemType.FINISHED_PRODUCT)
    v = make_bom(db, lehenga, [(blouse, "1", "PC", 0)])
    order = make_order(db, lehenga, v, 10, warehouse)

    by_sku = {m.item.sku: m for m in order.materials}
    assert by_sku["SEMI-BLOUSE-3C"].planned_quantity == Decimal("10")
    assert by_sku["SEMI-BLOUSE-3C"].is_subassembly is True
    assert by_sku["FAB-SLK-3C"].planned_quantity == Decimal("20")

    # The sub-assembly is excluded from material totals, so fabric appears once.
    lines = prod.availability(db, order)["lines"]
    fabric = [line for line in lines if line["sku"] == "FAB-SLK-3C"]
    assert len(fabric) == 1
    assert fabric[0]["planned_quantity"] == Decimal("20")


def test_three_level_explosion(db, warehouse, tenant, stones):
    panel = make_item(db, "SEMI-PANEL-ML", "Panel", stock_uom="PC", item_type=ItemType.SEMI_FINISHED)
    make_bom(db, panel, [(stones, "100", "PC", 0)])
    blouse = make_item(db, "SEMI-BLOUSE-ML", "Blouse", stock_uom="PC", item_type=ItemType.SEMI_FINISHED)
    make_bom(db, blouse, [(panel, "2", "PC", 0)])
    lehenga = make_item(db, "GAR-3LVL", "Lehenga 3L", stock_uom="PC", item_type=ItemType.FINISHED_PRODUCT)
    v = make_bom(db, lehenga, [(blouse, "1", "PC", 0)])

    order = make_order(db, lehenga, v, 5, warehouse)
    by_sku = {m.item.sku: m for m in order.materials}
    assert by_sku["SEMI-BLOUSE-ML"].planned_quantity == Decimal("5")
    assert by_sku["SEMI-PANEL-ML"].planned_quantity == Decimal("10")
    assert by_sku["STM-SWR-3C"].planned_quantity == Decimal("1000")
    assert by_sku["STM-SWR-3C"].level == 2


def test_requirement_trace_explains_the_number(db, lehenga, silk, warehouse):
    v = make_bom(db, lehenga, [(silk, "4.5", "M", 0)])
    order = make_order(db, lehenga, v, 10, warehouse)
    chains = prod.trace(db, order, silk.id)
    assert len(chains) == 1
    step = chains[0][-1]
    assert step["quantity_per_unit"] == Decimal("4.5000")
    assert step["planned_quantity"] == Decimal("45")


# --------------------------------------------------------- BOM immutability


def test_order_stays_on_its_bom_version_after_a_newer_one_activates(
    db, lehenga, silk, lace, warehouse
):
    """A PO created on V1 must still explode V1 after V2 goes active."""
    v1 = make_bom(db, lehenga, [(lace, "8", "M", 0)], version_no=1)
    order = make_order(db, lehenga, v1, 1, warehouse)
    assert order.materials[0].planned_quantity == Decimal("8")

    from app.services.bom import activate as do_activate
    v2 = BomVersion(bom_id=v1.bom_id, version_no=2, status=BomStatus.DRAFT,
                    output_quantity=Decimal("1"), output_uom_id=uom(db, "PC").id)
    db.add(v2)
    db.flush()
    db.add(BomComponent(bom_version_id=v2.id, item_id=lace.id, quantity=Decimal("10"),
                        uom_id=uom(db, "M").id, sequence=0))
    db.flush()
    do_activate(db, v2)

    db.refresh(order)
    assert order.bom_version_id == v1.id
    assert order.materials[0].planned_quantity == Decimal("8")


def test_snapshot_is_frozen_once_released(db, lehenga, lace, warehouse):
    v = make_bom(db, lehenga, [(lace, "8", "M", 0)])
    order = make_order(db, lehenga, v, 1, warehouse)
    order.status = ProductionStatus.RELEASED
    db.flush()
    with pytest.raises(prod.ProductionError, match="fixed once"):
        prod.rebuild_materials(db, order)


def test_snapshot_rebuilds_while_still_draft(db, lehenga, lace, warehouse):
    v = make_bom(db, lehenga, [(lace, "8", "M", 0)])
    order = make_order(db, lehenga, v, 1, warehouse)
    assert order.materials[0].planned_quantity == Decimal("8")
    order.planned_quantity = Decimal("10")
    db.flush()
    prod.rebuild_materials(db, order)
    db.refresh(order)
    assert order.materials[0].planned_quantity == Decimal("80")


# ------------------------------------------------------------ state machine


@pytest.mark.parametrize("frm,to", [
    (ProductionStatus.DRAFT, ProductionStatus.PLANNED),
    (ProductionStatus.PLANNED, ProductionStatus.RELEASED),
    (ProductionStatus.RELEASED, ProductionStatus.IN_PROGRESS),
    (ProductionStatus.IN_PROGRESS, ProductionStatus.COMPLETED),
    (ProductionStatus.IN_PROGRESS, ProductionStatus.CLOSED_SHORT),
    (ProductionStatus.DRAFT, ProductionStatus.CANCELLED),
    (ProductionStatus.RELEASED, ProductionStatus.ON_HOLD),
])
def test_valid_transitions_are_allowed(frm, to):
    prod.assert_transition(frm, to)


@pytest.mark.parametrize("frm,to", [
    (ProductionStatus.DRAFT, ProductionStatus.RELEASED),      # must be planned first
    (ProductionStatus.DRAFT, ProductionStatus.COMPLETED),     # cannot skip the middle
    (ProductionStatus.PLANNED, ProductionStatus.IN_PROGRESS),  # must be released first
    (ProductionStatus.COMPLETED, ProductionStatus.DRAFT),     # terminal
    (ProductionStatus.CANCELLED, ProductionStatus.RELEASED),  # terminal
    (ProductionStatus.CLOSED_SHORT, ProductionStatus.IN_PROGRESS),  # terminal
])
def test_invalid_transitions_are_refused(frm, to):
    with pytest.raises(prod.InvalidTransition):
        prod.assert_transition(frm, to)


def test_terminal_states_say_so_clearly(db):
    with pytest.raises(prod.InvalidTransition, match="final"):
        prod.assert_transition(ProductionStatus.COMPLETED, ProductionStatus.IN_PROGRESS)


def test_transition_to_same_state_is_refused():
    with pytest.raises(prod.InvalidTransition, match="already"):
        prod.assert_transition(ProductionStatus.DRAFT, ProductionStatus.DRAFT)


# ------------------------------------------------------------- performance


def test_large_bom_requirement_calculation_is_batched(db, lehenga, warehouse, tenant):
    """A 200-component BOM must not issue a query per component.

    Counts real SQL statements around the calculation; the bound is generous but
    far below the ~600 a naive N+1 implementation would emit.
    """
    comps = []
    for i in range(200):
        it = make_item(db, f"PERF3C-{i:03d}", f"Trim {i}", stock_uom="PC", cost="2")
        comps.append((it, "2", "PC", 0))
    v = make_bom(db, lehenga, comps)
    order = make_order(db, lehenga, v, 10, warehouse)
    db.flush()

    statements: list[str] = []

    def record(conn, cursor, statement, params, context, executemany):
        statements.append(statement)

    sa.event.listen(db.get_bind(), "before_cursor_execute", record)
    try:
        result = prod.availability(db, order)
    finally:
        sa.event.remove(db.get_bind(), "before_cursor_execute", record)

    assert len(result["lines"]) == 200
    assert len(statements) < 20, (
        f"availability issued {len(statements)} queries for 200 components - "
        "this looks like an N+1"
    )
