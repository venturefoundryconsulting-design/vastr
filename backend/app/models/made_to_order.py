"""Customer measurements and made-to-order customer orders.

MEASUREMENTS ARE FIELDS, NOT COLUMNS. Bust, waist, sleeve and the rest live in
``measurement_fields`` as configurable rows, because every boutique measures
slightly differently and a schema change per garment style is not a workable
answer. A customer can hold several named profiles ("Riya - blouse", "Riya -
lehenga"), since one person is not one set of numbers.

READY STOCK vs MADE TO ORDER

Both live on the same customer order. A ready-stock line sells something that
already exists; a made-to-order line spawns a production order and waits for it.
Keeping them on one order is deliberate - a customer buying a dupatta off the
rack and commissioning a lehenga in the same visit is one transaction to them,
and splitting it would make the boutique reconcile two documents by hand.

DELIVERY GOES THROUGH THE EXISTING POS

Handing the garment over creates an ordinary Sale via the normal checkout path,
which is what deducts stock, applies loyalty and prints the receipt. There is no
parallel sales ledger: a made-to-order garment leaves inventory exactly the way
an off-the-rack one does.
"""

import enum
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.inventory import QuantityType
from app.models.mixins import TenantMixin, TimestampMixin


class MeasurementUnit(str, enum.Enum):
    INCH = "inch"
    CM = "cm"


class Fulfilment(str, enum.Enum):
    READY_STOCK = "ready_stock"
    MADE_TO_ORDER = "made_to_order"


class CustomerOrderStatus(str, enum.Enum):
    DRAFT = "draft"
    CONFIRMED = "confirmed"
    IN_PRODUCTION = "in_production"
    READY = "ready"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"


CO_TERMINAL = {CustomerOrderStatus.DELIVERED, CustomerOrderStatus.CANCELLED}

# Server-enforced, like every other lifecycle in this codebase.
CO_TRANSITIONS: dict[CustomerOrderStatus, set[CustomerOrderStatus]] = {
    CustomerOrderStatus.DRAFT: {CustomerOrderStatus.CONFIRMED, CustomerOrderStatus.CANCELLED},
    # Confirmed goes straight to READY when everything is off the rack; it goes
    # via IN_PRODUCTION only when a made-to-order line spawned production.
    CustomerOrderStatus.CONFIRMED: {
        CustomerOrderStatus.IN_PRODUCTION,
        CustomerOrderStatus.READY,
        CustomerOrderStatus.CANCELLED,
    },
    CustomerOrderStatus.IN_PRODUCTION: {
        CustomerOrderStatus.READY,
        CustomerOrderStatus.CANCELLED,
    },
    CustomerOrderStatus.READY: {CustomerOrderStatus.DELIVERED, CustomerOrderStatus.CANCELLED},
    CustomerOrderStatus.DELIVERED: set(),
    CustomerOrderStatus.CANCELLED: set(),
}


class MeasurementField(Base, TimestampMixin, TenantMixin):
    """One thing a boutique measures. Configurable data, never a column."""

    __tablename__ = "measurement_fields"
    __table_args__ = (UniqueConstraint("tenant_id", "code", name="uq_measurement_field_code"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(40), index=True)
    name: Mapped[str] = mapped_column(String(80))
    unit: Mapped[MeasurementUnit] = mapped_column(
        Enum(MeasurementUnit), default=MeasurementUnit.INCH
    )
    sequence: Mapped[int] = mapped_column(Integer, default=0)
    # Free-text grouping ("Blouse", "Lehenga") so the form can be sectioned
    # without the application knowing what a blouse is.
    group_name: Mapped[str | None] = mapped_column(String(60), default=None)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class MeasurementProfile(Base, TimestampMixin, TenantMixin):
    """A named set of measurements for one customer.

    Several per customer on purpose: measurements taken for a blouse are not the
    ones taken for a lehenga, and a customer's numbers change over time. A
    production order references the profile it was cut from, so an old garment
    stays explainable after the customer is re-measured.
    """

    __tablename__ = "measurement_profiles"
    __table_args__ = (
        Index("ix_measurement_profile_customer", "customer_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    notes: Mapped[str | None] = mapped_column(String(1000), default=None)
    taken_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), default=None)
    taken_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    customer: Mapped["Customer"] = relationship()  # noqa: F821
    values: Mapped[list["MeasurementValue"]] = relationship(
        back_populates="profile", cascade="all, delete-orphan"
    )


class MeasurementValue(Base, TimestampMixin, TenantMixin):
    __tablename__ = "measurement_values"
    __table_args__ = (
        UniqueConstraint("tenant_id", "profile_id", "field_id", name="uq_measurement_value"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("measurement_profiles.id"), index=True)
    field_id: Mapped[int] = mapped_column(ForeignKey("measurement_fields.id"))
    # Numeric, not text: "34.5" must be comparable across profiles so a tailor
    # can see how a customer's measurements have moved.
    value: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    notes: Mapped[str | None] = mapped_column(String(255), default=None)

    profile: Mapped["MeasurementProfile"] = relationship(back_populates="values")
    field: Mapped["MeasurementField"] = relationship()


class CustomerOrder(Base, TimestampMixin, TenantMixin):
    """A commitment to a customer, ahead of delivery.

    Distinct from a Sale: a sale is money and stock changing hands now, an order
    is a promise. The sale is created *from* the order at delivery, and
    ``sale_id`` is the link between the two.
    """

    __tablename__ = "customer_orders"
    __table_args__ = (
        UniqueConstraint("tenant_id", "order_number", name="uq_customer_order_number"),
        Index("ix_customer_orders_tenant_status", "tenant_id", "status"),
        Index("ix_customer_orders_customer", "customer_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    order_number: Mapped[str] = mapped_column(String(30), index=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    outlet_id: Mapped[int] = mapped_column(ForeignKey("outlets.id"), index=True)

    status: Mapped[CustomerOrderStatus] = mapped_column(
        Enum(CustomerOrderStatus), default=CustomerOrderStatus.DRAFT, index=True
    )
    order_date: Mapped[date | None] = mapped_column(Date, default=None)
    promised_date: Mapped[date | None] = mapped_column(Date, default=None)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)

    # What the customer paid up front. Held here rather than as a Sale payment
    # because no sale exists yet - it is settled against the total at delivery.
    advance_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)

    # Set when the order is handed over. Its presence is what makes an order
    # delivered, and the audit link back to the money.
    sale_id: Mapped[int | None] = mapped_column(ForeignKey("sales.id"), default=None)

    notes: Mapped[str | None] = mapped_column(String(1000), default=None)
    cancel_reason: Mapped[str | None] = mapped_column(String(500), default=None)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), default=None)

    customer: Mapped["Customer"] = relationship()  # noqa: F821
    outlet: Mapped["Outlet"] = relationship()  # noqa: F821
    sale: Mapped["Sale | None"] = relationship()  # noqa: F821
    items: Mapped[list["CustomerOrderItem"]] = relationship(
        back_populates="order", cascade="all, delete-orphan", order_by="CustomerOrderItem.id"
    )

    @property
    def total_amount(self) -> Decimal:
        return sum((i.line_total for i in self.items), Decimal("0"))

    @property
    def balance_due(self) -> Decimal:
        return self.total_amount - Decimal(self.advance_amount or 0)

    @property
    def has_made_to_order(self) -> bool:
        return any(i.fulfilment == Fulfilment.MADE_TO_ORDER for i in self.items)


class CustomerOrderItem(Base, TimestampMixin, TenantMixin):
    __tablename__ = "customer_order_items"
    __table_args__ = (Index("ix_customer_order_items_order", "customer_order_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    customer_order_id: Mapped[int] = mapped_column(ForeignKey("customer_orders.id"), index=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id"), index=True)

    quantity: Mapped[Decimal] = mapped_column(QuantityType, default=Decimal("1"))
    unit_price: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0)
    tax_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=0)

    fulfilment: Mapped[Fulfilment] = mapped_column(
        Enum(Fulfilment), default=Fulfilment.READY_STOCK
    )
    # Which measurements this garment was cut to. Points at the profile, not a
    # copy of the numbers, and the profile is never edited destructively - a
    # re-measure creates a new one.
    measurement_profile_id: Mapped[int | None] = mapped_column(
        ForeignKey("measurement_profiles.id"), default=None
    )
    # Set when a made-to-order line spawns production. The link is what lets the
    # counter answer "where is my lehenga?" without anyone searching.
    production_order_id: Mapped[int | None] = mapped_column(
        ForeignKey("production_orders.id"), default=None, index=True
    )

    notes: Mapped[str | None] = mapped_column(String(500), default=None)

    order: Mapped["CustomerOrder"] = relationship(back_populates="items")
    item: Mapped["Item"] = relationship()  # noqa: F821
    measurement_profile: Mapped["MeasurementProfile | None"] = relationship()
    production_order: Mapped["ProductionOrder | None"] = relationship()  # noqa: F821

    @property
    def line_total(self) -> Decimal:
        base = Decimal(self.unit_price or 0) * Decimal(self.quantity or 0)
        return base * (Decimal("1") + Decimal(self.tax_rate or 0) / Decimal("100"))
