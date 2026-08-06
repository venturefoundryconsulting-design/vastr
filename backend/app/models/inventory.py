import enum

from sqlalchemy import Enum, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.mixins import TenantMixin, TimestampMixin


class StockLevel(Base, TimestampMixin, TenantMixin):
    """Current on-hand quantity of a variant at an outlet/warehouse."""

    __tablename__ = "stock_levels"
    __table_args__ = (
        UniqueConstraint("tenant_id", "variant_id", "outlet_id", name="uq_stock_variant_outlet"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    variant_id: Mapped[int] = mapped_column(ForeignKey("product_variants.id"))
    outlet_id: Mapped[int] = mapped_column(ForeignKey("outlets.id"))
    quantity: Mapped[int] = mapped_column(Integer, default=0)

    variant: Mapped["ProductVariant"] = relationship(back_populates="stock_levels")  # noqa: F821
    outlet: Mapped["Outlet"] = relationship(back_populates="stock_levels")  # noqa: F821


class MovementType(str, enum.Enum):
    PURCHASE_RECEIPT = "purchase_receipt"
    SALE = "sale"
    TRANSFER_OUT = "transfer_out"
    TRANSFER_IN = "transfer_in"
    ADJUSTMENT = "adjustment"
    RETURN = "return"


class StockMovement(Base, TimestampMixin, TenantMixin):
    """Immutable audit trail of every stock quantity change."""

    __tablename__ = "stock_movements"

    id: Mapped[int] = mapped_column(primary_key=True)
    variant_id: Mapped[int] = mapped_column(ForeignKey("product_variants.id"))
    outlet_id: Mapped[int] = mapped_column(ForeignKey("outlets.id"))
    movement_type: Mapped[MovementType] = mapped_column(Enum(MovementType))
    quantity_delta: Mapped[int] = mapped_column(Integer)  # positive = stock in, negative = stock out
    reference_type: Mapped[str | None] = mapped_column(String(40), default=None)
    reference_id: Mapped[int | None] = mapped_column(Integer, default=None)
    note: Mapped[str | None] = mapped_column(String(255), default=None)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), default=None)

    variant: Mapped["ProductVariant"] = relationship()  # noqa: F821
    outlet: Mapped["Outlet"] = relationship()  # noqa: F821
