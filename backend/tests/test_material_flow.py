"""Phase 3D - reservation, issue, consumption and return.

The tests that matter most here are the concurrency ones. They use real threads
on real connections, because the guarantees being tested are database row locks -
a mocked lock would prove nothing.
"""

import threading
from decimal import Decimal

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import sessionmaker

from app.core.tenant_context import tenant_scope
from app.models.inventory import MovementType, StockLevel
from app.models.material_flow import (
    ProductionMaterialConsumption,
    ProductionMaterialIssue,
    ProductionMaterialReturn,
    ReservationStatus,
    StockReservation,
)
from app.models.outlet import Outlet
from app.models.product import Item, ItemType
from app.models.production import ProductionOrder, ProductionStatus
from app.models.tenant import Tenant
from app.models.uom import UnitOfMeasure, UomCategory
from app.services import material_flow as mf
from app.services.inventory import apply_stock_delta
from tests.conftest import stock_of
from tests.test_ledger_integrity import assert_ledger_reconciles
from tests.test_production_orders import make_bom, make_item, make_order, uom


@pytest.fixture()
def lace(db, tenant):
    return make_item(db, "LAC-3D", "Gold Lace", stock_uom="M", cost="120")


@pytest.fixture()
def order_with_stock(db, tenant, warehouse, lace):
    """An order for 20 m of lace, with 100 m physically in stock."""
    apply_stock_delta(db, variant_id=lace.id, outlet_id=warehouse.id,
                      quantity_delta=Decimal("100"), movement_type=MovementType.OPENING_STOCK)
    db.flush()
    garment = make_item(db, "GAR-3D", "Lehenga", stock_uom="PC",
                        item_type=ItemType.FINISHED_PRODUCT)
    v = make_bom(db, garment, [(lace, "20", "M", 0)])
    # Built as a draft so the snapshot can be derived, then released - the
    # service correctly refuses to rebuild requirements for a released order.
    order = make_order(db, garment, v, 1, warehouse)
    order.status = ProductionStatus.RELEASED
    db.flush()
    return order


def only_material(order):
    return next(m for m in order.materials if not m.is_subassembly)


# --------------------------------------------------------------- reservation


def test_reservation_does_not_move_physical_stock(db, order_with_stock, lace, warehouse):
    """The defining property: a promise, not a movement."""
    before_qty = stock_of(db, lace.id, warehouse.id)
    before_moves = db.execute(sa.text("SELECT count(*) FROM stock_movements")).scalar_one()

    mf.reserve(db, order_with_stock, only_material(order_with_stock).id, Decimal("20"))
    db.flush()

    assert stock_of(db, lace.id, warehouse.id) == before_qty
    assert db.execute(sa.text("SELECT count(*) FROM stock_movements")).scalar_one() == before_moves
    assert_ledger_reconciles(db)


def test_reservation_reduces_available_not_on_hand(db, order_with_stock, lace, warehouse):
    m = only_material(order_with_stock)
    assert mf.available_at_location(db, lace.id, warehouse.id) == Decimal("100")
    mf.reserve(db, order_with_stock, m.id, Decimal("20"))
    db.flush()
    assert stock_of(db, lace.id, warehouse.id) == Decimal("100.0000")
    assert mf.available_at_location(db, lace.id, warehouse.id) == Decimal("80")
    assert m.reserved_quantity == Decimal("20.0000")


def test_cannot_reserve_more_than_available(db, order_with_stock, lace, warehouse):
    m = only_material(order_with_stock)
    apply_stock_delta(db, variant_id=lace.id, outlet_id=warehouse.id,
                      quantity_delta=Decimal("-95"), movement_type=MovementType.ADJUSTMENT)
    db.flush()
    with pytest.raises(mf.InsufficientStock, match="only 5"):
        mf.reserve(db, order_with_stock, m.id, Decimal("20"))


def test_cannot_reserve_beyond_the_planned_requirement(db, order_with_stock):
    m = only_material(order_with_stock)
    with pytest.raises(mf.MaterialFlowError, match="needs 20"):
        mf.reserve(db, order_with_stock, m.id, Decimal("25"))


def test_partial_reservation_is_explicit(db, order_with_stock, lace, warehouse):
    """Reserve 12 of 20; the remaining 8 stays visible as outstanding."""
    m = only_material(order_with_stock)
    mf.reserve(db, order_with_stock, m.id, Decimal("12"))
    db.flush()
    assert m.reserved_quantity == Decimal("12.0000")
    assert m.remaining_to_reserve == Decimal("8.0000")


def test_releasing_a_reservation_frees_availability(db, order_with_stock, lace, warehouse):
    m = only_material(order_with_stock)
    r = mf.reserve(db, order_with_stock, m.id, Decimal("20"))
    db.flush()
    assert mf.available_at_location(db, lace.id, warehouse.id) == Decimal("80")

    freed = mf.release_reservation(db, r, reason="order cancelled")
    db.flush()
    assert freed == Decimal("20.0000")
    assert r.status == ReservationStatus.RELEASED
    assert mf.available_at_location(db, lace.id, warehouse.id) == Decimal("100")
    assert m.reserved_quantity == Decimal("0.0000")


def test_release_never_gives_back_already_issued_material(db, order_with_stock, lace, warehouse):
    """Reserved 20, issued 12 - releasing frees only the unissued 8."""
    m = only_material(order_with_stock)
    r = mf.reserve(db, order_with_stock, m.id, Decimal("20"))
    db.flush()
    mf.issue(db, order_with_stock, m.id, Decimal("12"))
    db.flush()

    freed = mf.release_reservation(db, r, reason="rest not needed")
    db.flush()
    assert freed == Decimal("8.0000")
    assert stock_of(db, lace.id, warehouse.id) == Decimal("88.0000")  # 12 physically gone
    assert m.issued_quantity == Decimal("12.0000")
    assert_ledger_reconciles(db)


# --------------------------------------------------------------------- issue


def test_issue_moves_stock_and_writes_one_ledger_row(db, order_with_stock, lace, warehouse):
    m = only_material(order_with_stock)
    mf.reserve(db, order_with_stock, m.id, Decimal("20"))
    db.flush()
    before = db.execute(sa.text("SELECT count(*) FROM stock_movements")).scalar_one()

    rec = mf.issue(db, order_with_stock, m.id, Decimal("20"))
    db.flush()

    after = db.execute(sa.text("SELECT count(*) FROM stock_movements")).scalar_one()
    assert after == before + 1
    assert stock_of(db, lace.id, warehouse.id) == Decimal("80.0000")
    assert rec.stock_movement_id is not None
    kind = db.execute(sa.text("SELECT movement_type FROM stock_movements WHERE id = :i"),
                      {"i": rec.stock_movement_id}).scalar_one()
    assert kind == "PRODUCTION_ISSUE"
    assert_ledger_reconciles(db)


def test_issue_without_reservation_is_refused(db, order_with_stock):
    m = only_material(order_with_stock)
    with pytest.raises(mf.MaterialFlowError, match="only 0 is reserved"):
        mf.issue(db, order_with_stock, m.id, Decimal("5"))


def test_unreserved_issue_needs_permission_and_a_reason(db, order_with_stock, lace, warehouse):
    m = only_material(order_with_stock)
    with pytest.raises(mf.MaterialFlowError, match="requires a reason"):
        mf.issue(db, order_with_stock, m.id, Decimal("5"), allow_unreserved=True)

    rec = mf.issue(db, order_with_stock, m.id, Decimal("5"),
                   allow_unreserved=True, unreserved_reason="urgent sample run")
    db.flush()
    assert rec.unreserved_reason == "urgent sample run"
    assert stock_of(db, lace.id, warehouse.id) == Decimal("95.0000")


def test_multiple_partial_issues_accumulate(db, order_with_stock, lace, warehouse):
    """20 required, issued as 12 + 5 + 3."""
    m = only_material(order_with_stock)
    mf.reserve(db, order_with_stock, m.id, Decimal("20"))
    db.flush()
    for part in ("12", "5", "3"):
        mf.issue(db, order_with_stock, m.id, Decimal(part))
        db.flush()
    assert m.issued_quantity == Decimal("20.0000")
    assert m.remaining_to_issue == Decimal("0.0000")
    assert stock_of(db, lace.id, warehouse.id) == Decimal("80.0000")
    assert_ledger_reconciles(db)


def test_over_issue_beyond_plan_is_refused(db, order_with_stock):
    m = only_material(order_with_stock)
    mf.reserve(db, order_with_stock, m.id, Decimal("20"))
    db.flush()
    mf.issue(db, order_with_stock, m.id, Decimal("20"))
    db.flush()
    with pytest.raises(mf.MaterialFlowError, match="plans 20"):
        mf.issue(db, order_with_stock, m.id, Decimal("1"),
                 allow_unreserved=True, unreserved_reason="x")


def test_issue_refused_when_physical_stock_is_absent(db, order_with_stock, lace, warehouse):
    """Reserved, but someone adjusted the stock away underneath."""
    m = only_material(order_with_stock)
    mf.reserve(db, order_with_stock, m.id, Decimal("20"))
    db.flush()
    apply_stock_delta(db, variant_id=lace.id, outlet_id=warehouse.id,
                      quantity_delta=Decimal("-95"), movement_type=MovementType.ADJUSTMENT)
    db.flush()
    with pytest.raises(mf.InsufficientStock, match="physically in stock"):
        mf.issue(db, order_with_stock, m.id, Decimal("20"))


# --------------------------------------------------------------- consumption


def test_consumption_does_not_deduct_stock_again(db, order_with_stock, lace, warehouse):
    """The material left at issue. Consuming must not double-count."""
    m = only_material(order_with_stock)
    mf.reserve(db, order_with_stock, m.id, Decimal("20"))
    db.flush()
    mf.issue(db, order_with_stock, m.id, Decimal("20"))
    db.flush()

    after_issue = stock_of(db, lace.id, warehouse.id)
    moves_after_issue = db.execute(sa.text("SELECT count(*) FROM stock_movements")).scalar_one()

    mf.consume(db, order_with_stock, m.id, Decimal("17.5"))
    db.flush()

    assert stock_of(db, lace.id, warehouse.id) == after_issue
    assert db.execute(sa.text("SELECT count(*) FROM stock_movements")).scalar_one() == moves_after_issue
    assert m.consumed_quantity == Decimal("17.5000")
    assert_ledger_reconciles(db)


def test_consumption_cannot_exceed_issued(db, order_with_stock):
    m = only_material(order_with_stock)
    mf.reserve(db, order_with_stock, m.id, Decimal("20"))
    db.flush()
    mf.issue(db, order_with_stock, m.id, Decimal("10"))
    db.flush()
    with pytest.raises(mf.MaterialFlowError, match="was issued"):
        mf.consume(db, order_with_stock, m.id, Decimal("12"))


def test_consumed_plus_returned_cannot_exceed_issued(db, order_with_stock):
    """The brief's invalid case: issued 20, consumed 16, return 5 -> 21 > 20."""
    m = only_material(order_with_stock)
    mf.reserve(db, order_with_stock, m.id, Decimal("20"))
    db.flush()
    mf.issue(db, order_with_stock, m.id, Decimal("20"))
    db.flush()
    mf.consume(db, order_with_stock, m.id, Decimal("16"))
    db.flush()
    with pytest.raises(mf.MaterialFlowError, match="at most 4"):
        mf.return_material(db, order_with_stock, m.id, Decimal("5"))


def test_over_consumption_needs_an_explicit_reason(db, order_with_stock):
    m = only_material(order_with_stock)
    mf.reserve(db, order_with_stock, m.id, Decimal("20"))
    db.flush()
    mf.issue(db, order_with_stock, m.id, Decimal("20"))
    db.flush()
    mf.consume(db, order_with_stock, m.id, Decimal("20"))
    db.flush()
    # Planned is 20; consuming more needs the flag AND a reason.
    with pytest.raises(mf.MaterialFlowError):
        mf.consume(db, order_with_stock, m.id, Decimal("1"))


# -------------------------------------------------------------------- return


def test_return_creates_a_compensating_movement(db, order_with_stock, lace, warehouse):
    m = only_material(order_with_stock)
    mf.reserve(db, order_with_stock, m.id, Decimal("20"))
    db.flush()
    issue_rec = mf.issue(db, order_with_stock, m.id, Decimal("20"))
    db.flush()
    mf.consume(db, order_with_stock, m.id, Decimal("17.5"))
    db.flush()

    ret = mf.return_material(db, order_with_stock, m.id, Decimal("2.5"))
    db.flush()

    assert stock_of(db, lace.id, warehouse.id) == Decimal("82.5000")
    kind = db.execute(sa.text("SELECT movement_type FROM stock_movements WHERE id = :i"),
                      {"i": ret.stock_movement_id}).scalar_one()
    assert kind == "PRODUCTION_RETURN"
    # The original issue is untouched - corrections are new rows, never edits.
    assert db.get(ProductionMaterialIssue, issue_rec.id).quantity == Decimal("20.0000")
    assert_ledger_reconciles(db)


def test_return_cannot_exceed_returnable(db, order_with_stock):
    m = only_material(order_with_stock)
    mf.reserve(db, order_with_stock, m.id, Decimal("20"))
    db.flush()
    mf.issue(db, order_with_stock, m.id, Decimal("10"))
    db.flush()
    mf.return_material(db, order_with_stock, m.id, Decimal("5"))
    db.flush()
    with pytest.raises(mf.MaterialFlowError, match="at most 5"):
        mf.return_material(db, order_with_stock, m.id, Decimal("6"))


def test_damaged_return_does_not_restock(db, order_with_stock, lace, warehouse):
    m = only_material(order_with_stock)
    mf.reserve(db, order_with_stock, m.id, Decimal("20"))
    db.flush()
    mf.issue(db, order_with_stock, m.id, Decimal("20"))
    db.flush()
    after_issue = stock_of(db, lace.id, warehouse.id)

    ret = mf.return_material(db, order_with_stock, m.id, Decimal("2"),
                             restock=False, reason="water damaged")
    db.flush()
    assert ret.stock_movement_id is None
    assert stock_of(db, lace.id, warehouse.id) == after_issue
    assert_ledger_reconciles(db)


# ------------------------------------------------------------ reconciliation


def test_full_workflow_reconciles(db, order_with_stock, lace, warehouse):
    """The brief's end-to-end example.

    Required 20, reserved 20, issued 20, consumed 17.5, returned 2.5,
    still with production 0. Stock: 100 - 20 + 2.5 = 82.5.
    """
    m = only_material(order_with_stock)
    mf.reserve(db, order_with_stock, m.id, Decimal("20"))
    db.flush()
    mf.issue(db, order_with_stock, m.id, Decimal("20"))
    db.flush()
    mf.consume(db, order_with_stock, m.id, Decimal("17.5"))
    db.flush()
    mf.return_material(db, order_with_stock, m.id, Decimal("2.5"))
    db.flush()

    assert m.planned_quantity == Decimal("20.0000")
    assert m.reserved_quantity == Decimal("20.0000")
    assert m.issued_quantity == Decimal("20.0000")
    assert m.consumed_quantity == Decimal("17.5000")
    assert m.returned_quantity == Decimal("2.5000")
    assert m.still_with_production == Decimal("0.0000")
    assert stock_of(db, lace.id, warehouse.id) == Decimal("82.5000")
    assert_ledger_reconciles(db)


def test_still_with_production_is_explicit(db, order_with_stock):
    """Issued 20, consumed 15, returned 3 -> 2 still on the floor."""
    m = only_material(order_with_stock)
    mf.reserve(db, order_with_stock, m.id, Decimal("20"))
    db.flush()
    mf.issue(db, order_with_stock, m.id, Decimal("20"))
    db.flush()
    mf.consume(db, order_with_stock, m.id, Decimal("15"))
    db.flush()
    mf.return_material(db, order_with_stock, m.id, Decimal("3"))
    db.flush()
    assert m.still_with_production == Decimal("2.0000")


def test_aggregate_cache_equals_sum_of_transactions(db, order_with_stock):
    """The cached columns are a cache. Prove they match their transactions."""
    m = only_material(order_with_stock)
    mf.reserve(db, order_with_stock, m.id, Decimal("20"))
    db.flush()
    for part in ("8", "7", "5"):
        mf.issue(db, order_with_stock, m.id, Decimal(part))
        db.flush()
    for part in ("6", "4"):
        mf.consume(db, order_with_stock, m.id, Decimal(part))
        db.flush()
    mf.return_material(db, order_with_stock, m.id, Decimal("3"))
    db.flush()

    def total(model):
        return db.query(sa.func.coalesce(sa.func.sum(model.quantity), 0)).filter(
            model.production_order_material_id == m.id
        ).scalar()

    assert m.issued_quantity == total(ProductionMaterialIssue)
    assert m.consumed_quantity == total(ProductionMaterialConsumption)
    assert m.returned_quantity == total(ProductionMaterialReturn)


@pytest.mark.parametrize("qty", ["4.5", "0.125", "0.3333", "12.75"])
def test_decimal_quantities_are_exact(db, order_with_stock, lace, warehouse, qty):
    m = only_material(order_with_stock)
    amount = Decimal(qty)
    mf.reserve(db, order_with_stock, m.id, amount)
    db.flush()
    mf.issue(db, order_with_stock, m.id, amount)
    db.flush()
    assert m.issued_quantity == amount
    assert stock_of(db, lace.id, warehouse.id) == Decimal("100") - amount
    assert_ledger_reconciles(db)


def test_cancel_releases_all_outstanding_reservations(db, order_with_stock, lace, warehouse):
    """Rule 8: cancelling frees the promise but not the issued material."""
    m = only_material(order_with_stock)
    mf.reserve(db, order_with_stock, m.id, Decimal("20"))
    db.flush()
    mf.issue(db, order_with_stock, m.id, Decimal("5"))
    db.flush()

    freed = mf.release_all_for_order(db, order_with_stock, reason="cancelled")
    db.flush()
    assert freed == Decimal("15.0000")
    assert mf.available_at_location(db, lace.id, warehouse.id) == Decimal("95")
    assert stock_of(db, lace.id, warehouse.id) == Decimal("95.0000")


# ------------------------------------------------------- ATOMICITY (mandatory)


def test_failed_issue_rolls_back_the_stock_movement(db, order_with_stock, lace, warehouse):
    """A stock movement must never survive a failed production record.

    Forces the production-record insert to fail after the ledger row is written,
    and asserts the whole savepoint unwinds - no orphan movement, no phantom
    deduction.
    """
    m = only_material(order_with_stock)
    mf.reserve(db, order_with_stock, m.id, Decimal("20"))
    db.flush()

    before_qty = stock_of(db, lace.id, warehouse.id)
    before_moves = db.execute(sa.text("SELECT count(*) FROM stock_movements")).scalar_one()

    sp = db.begin_nested()
    try:
        mf.issue(db, order_with_stock, m.id, Decimal("10"))
        raise RuntimeError("simulated failure after the ledger row was written")
    except RuntimeError:
        sp.rollback()

    assert stock_of(db, lace.id, warehouse.id) == before_qty
    assert db.execute(sa.text("SELECT count(*) FROM stock_movements")).scalar_one() == before_moves
    assert db.query(ProductionMaterialIssue).filter(
        ProductionMaterialIssue.production_order_material_id == m.id
    ).count() == 0
    assert_ledger_reconciles(db)


def test_failed_return_rolls_back_completely(db, order_with_stock, lace, warehouse):
    m = only_material(order_with_stock)
    mf.reserve(db, order_with_stock, m.id, Decimal("20"))
    db.flush()
    mf.issue(db, order_with_stock, m.id, Decimal("20"))
    db.flush()

    before_qty = stock_of(db, lace.id, warehouse.id)
    before_moves = db.execute(sa.text("SELECT count(*) FROM stock_movements")).scalar_one()

    sp = db.begin_nested()
    try:
        mf.return_material(db, order_with_stock, m.id, Decimal("5"))
        raise RuntimeError("simulated failure")
    except RuntimeError:
        sp.rollback()

    assert stock_of(db, lace.id, warehouse.id) == before_qty
    assert db.execute(sa.text("SELECT count(*) FROM stock_movements")).scalar_one() == before_moves
    assert_ledger_reconciles(db)


# ----------------------------------------------------- CONCURRENCY (mandatory)


_TENANT_SEQ = iter(range(9500, 9600))


class _Fixture:
    """Committed data on real connections, for the threaded tests.

    The rollback-per-test session cannot be shared across threads, so these build
    their own committed rows and clean up afterwards.

    Each instance gets its own tenant id. A shared one deadlocks: these tests
    commit on separate connections, so a second fixture inserting the same
    primary key waits on the first transaction rather than failing fast.
    """

    def __init__(self, engine, on_hand: str, planned: str):
        self.TENANT = next(_TENANT_SEQ)
        self.engine = engine
        self.Session = sessionmaker(bind=engine)
        s = self.Session()
        s.execute(sa.text("SET LOCAL lock_timeout = '10s'"))
        with tenant_scope(self.TENANT):
            s.add(Tenant(id=self.TENANT, company_name="MF Co", slug=f"mf-co-{self.TENANT}"))
            s.flush()
            outlet = Outlet(name="MF Store", code="MFS")
            s.add(outlet)
            # This tenant needs its own unit: the tenant filter is active inside
            # this scope, so tenant 1's seeded metres are invisible here.
            category = UomCategory(code="LENGTH", name="Length")
            s.add(category)
            s.flush()
            metre = UnitOfMeasure(code="M", name="Meter", category_id=category.id,
                                  factor_to_base=Decimal("1"), is_base=True)
            s.add(metre)
            s.flush()
            item = Item(sku=f"MF-LACE-{self.TENANT}", name="MF Lace",
                        item_type=ItemType.RAW_MATERIAL, stock_uom_id=metre.id)
            garment = Item(sku=f"MF-GAR-{self.TENANT}", name="MF Garment",
                           item_type=ItemType.FINISHED_PRODUCT)
            s.add_all([item, garment])
            s.flush()
            s.add(StockLevel(variant_id=item.id, outlet_id=outlet.id, quantity=Decimal(on_hand)))
            s.flush()
            # Ledger row so the invariant holds for this fixture too.
            from app.models.inventory import StockMovement
            s.add(StockMovement(variant_id=item.id, outlet_id=outlet.id,
                                movement_type=MovementType.OPENING_STOCK,
                                quantity_delta=Decimal(on_hand)))
            order = ProductionOrder(
                po_number=f"MF-{self.TENANT}", item_id=garment.id,
                planned_quantity=Decimal("1"), location_id=outlet.id,
                status=ProductionStatus.RELEASED,
            )
            s.add(order)
            s.flush()
            from app.models.production import ProductionOrderMaterial
            mat = ProductionOrderMaterial(
                production_order_id=order.id, item_id=item.id,
                base_quantity=Decimal(planned), planned_quantity=Decimal(planned),
                uom_id=item.stock_uom_id, sequence=0,
            )
            s.add(mat)
            s.commit()
            self.order_id, self.material_id = order.id, mat.id
            self.item_id, self.outlet_id = item.id, outlet.id
        s.close()

    def run(self, fn, requests):
        errors, ok = [], []

        def worker(amount):
            s = self.Session()
            try:
                s.execute(sa.text("SET LOCAL lock_timeout = '15s'"))
                with tenant_scope(self.TENANT):
                    order = s.get(ProductionOrder, self.order_id)
                    fn(s, order, self.material_id, amount)
                    s.commit()
                    ok.append(amount)
            except Exception as e:  # noqa: BLE001 - collected and asserted on
                s.rollback()
                errors.append(e)
            finally:
                s.close()

        threads = [threading.Thread(target=worker, args=(a,)) for a in requests]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        return ok, errors

    def cleanup(self):
        """Best-effort teardown, in foreign-key order.

        Deliberately swallows its own errors: this runs in a `finally`, and an
        exception here would replace the assertion failure that actually matters
        with a confusing teardown traceback.
        """
        s = self.Session()
        try:
            with tenant_scope(None):
                for stmt, params in (
                    ("DELETE FROM production_material_returns WHERE production_order_id = :o", {"o": self.order_id}),
                    ("DELETE FROM production_material_consumptions WHERE production_order_id = :o", {"o": self.order_id}),
                    ("DELETE FROM production_material_issues WHERE production_order_id = :o", {"o": self.order_id}),
                    ("DELETE FROM stock_reservations WHERE production_order_id = :o", {"o": self.order_id}),
                    ("DELETE FROM production_order_materials WHERE production_order_id = :o", {"o": self.order_id}),
                    ("DELETE FROM production_orders WHERE id = :o", {"o": self.order_id}),
                    ("DELETE FROM stock_movements WHERE variant_id = :i", {"i": self.item_id}),
                    ("DELETE FROM stock_levels WHERE variant_id = :i", {"i": self.item_id}),
                    # items reference units_of_measure, which reference
                    # uom_categories, which reference tenants - unwind in that order.
                    ("DELETE FROM items WHERE tenant_id = :t", {"t": self.TENANT}),
                    ("DELETE FROM units_of_measure WHERE tenant_id = :t", {"t": self.TENANT}),
                    ("DELETE FROM uom_categories WHERE tenant_id = :t", {"t": self.TENANT}),
                    ("DELETE FROM outlets WHERE tenant_id = :t", {"t": self.TENANT}),
                    ("DELETE FROM tenants WHERE id = :t", {"t": self.TENANT}),
                ):
                    s.execute(sa.text(stmt), params)
                s.commit()
        except Exception as e:  # noqa: BLE001 - teardown must not mask the test result
            s.rollback()
            print(f"[cleanup] tenant {self.TENANT} left behind: {e}")
        finally:
            s.close()


def test_concurrent_reservation_cannot_oversubscribe(_database):
    """10 available; A wants 7 and B wants 6. Both must not succeed."""
    fx = _Fixture(_database, on_hand="10", planned="20")
    try:
        ok, errors = fx.run(
            lambda s, o, mid, amt: mf.reserve(s, o, mid, amt), [Decimal("7"), Decimal("6")]
        )
        assert len(ok) == 1, f"both reservations succeeded: {ok}"
        assert len(errors) == 1
        assert isinstance(errors[0], mf.MaterialFlowError)

        s = fx.Session()
        with tenant_scope(fx.TENANT):
            total = s.query(sa.func.coalesce(sa.func.sum(StockReservation.quantity), 0)).filter(
                StockReservation.item_id == fx.item_id
            ).scalar()
        s.close()
        assert Decimal(total) <= Decimal("10"), f"reserved {total} against 10 on hand"
    finally:
        fx.cleanup()


def test_concurrent_issue_cannot_exceed_reserved(_database):
    """10 reserved; two users try 7 and 6 at once."""
    fx = _Fixture(_database, on_hand="20", planned="20")
    try:
        s = fx.Session()
        with tenant_scope(fx.TENANT):
            order = s.get(ProductionOrder, fx.order_id)
            mf.reserve(s, order, fx.material_id, Decimal("10"))
            s.commit()
        s.close()

        ok, errors = fx.run(
            lambda s, o, mid, amt: mf.issue(s, o, mid, amt), [Decimal("7"), Decimal("6")]
        )
        assert len(ok) == 1, f"both issues succeeded: {ok}"

        s = fx.Session()
        with tenant_scope(fx.TENANT):
            issued = s.query(sa.func.coalesce(sa.func.sum(ProductionMaterialIssue.quantity), 0)).filter(
                ProductionMaterialIssue.production_order_material_id == fx.material_id
            ).scalar()
            level = s.query(StockLevel).filter(
                StockLevel.variant_id == fx.item_id, StockLevel.outlet_id == fx.outlet_id
            ).first()
            replay = s.execute(sa.text(
                "SELECT coalesce(sum(quantity_delta),0) FROM stock_movements WHERE variant_id = :i"
            ), {"i": fx.item_id}).scalar_one()
        s.close()
        assert Decimal(issued) <= Decimal("10")
        assert level.quantity == replay, "ledger and cached stock disagree after concurrent issue"
    finally:
        fx.cleanup()


def test_concurrent_returns_cannot_exceed_issued(_database):
    """10 issued; two returns of 6 and 5 race. At most 10 may come back."""
    fx = _Fixture(_database, on_hand="20", planned="20")
    try:
        s = fx.Session()
        with tenant_scope(fx.TENANT):
            order = s.get(ProductionOrder, fx.order_id)
            mf.reserve(s, order, fx.material_id, Decimal("10"))
            mf.issue(s, order, fx.material_id, Decimal("10"))
            s.commit()
        s.close()

        ok, errors = fx.run(
            lambda s, o, mid, amt: mf.return_material(s, o, mid, amt),
            [Decimal("6"), Decimal("5")],
        )
        assert len(ok) == 1, f"both returns succeeded: {ok}"

        s = fx.Session()
        with tenant_scope(fx.TENANT):
            returned = s.query(
                sa.func.coalesce(sa.func.sum(ProductionMaterialReturn.quantity), 0)
            ).filter(ProductionMaterialReturn.production_order_material_id == fx.material_id).scalar()
        s.close()
        assert Decimal(returned) <= Decimal("10")
    finally:
        fx.cleanup()


def test_concurrent_consumption_cannot_exceed_issued(_database):
    """10 issued; two users record 7 and 6. Total consumption must stay <= 10."""
    fx = _Fixture(_database, on_hand="20", planned="20")
    try:
        s = fx.Session()
        with tenant_scope(fx.TENANT):
            order = s.get(ProductionOrder, fx.order_id)
            mf.reserve(s, order, fx.material_id, Decimal("10"))
            mf.issue(s, order, fx.material_id, Decimal("10"))
            s.commit()
        s.close()

        ok, errors = fx.run(
            lambda s, o, mid, amt: mf.consume(s, o, mid, amt), [Decimal("7"), Decimal("6")]
        )
        assert len(ok) == 1, f"both consumptions succeeded: {ok}"

        s = fx.Session()
        with tenant_scope(fx.TENANT):
            consumed = s.query(
                sa.func.coalesce(sa.func.sum(ProductionMaterialConsumption.quantity), 0)
            ).filter(
                ProductionMaterialConsumption.production_order_material_id == fx.material_id
            ).scalar()
        s.close()
        assert Decimal(consumed) <= Decimal("10")
    finally:
        fx.cleanup()


def test_cancel_endpoint_frees_reservations_but_not_issued(db, order_with_stock, lace, warehouse, user):
    """Rule 8 through the router: cancelling releases the promise only."""
    from app.routers import production_orders as po_router
    from app.schemas.production import TransitionRequest

    m = only_material(order_with_stock)
    mf.reserve(db, order_with_stock, m.id, Decimal("20"))
    db.flush()
    mf.issue(db, order_with_stock, m.id, Decimal("5"))
    db.flush()

    po_router.cancel_order(order_with_stock.id, TransitionRequest(reason="customer withdrew"), db, user)

    db.refresh(m)
    assert mf.available_at_location(db, lace.id, warehouse.id) == Decimal("95")
    assert stock_of(db, lace.id, warehouse.id) == Decimal("95.0000")  # the 5 stays gone
    assert m.issued_quantity == Decimal("5.0000")
    assert_ledger_reconciles(db)
