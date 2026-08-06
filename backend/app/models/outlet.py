import enum

from sqlalchemy import Boolean, Enum, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.mixins import TenantMixin, TimestampMixin


class PaperSize(str, enum.Enum):
    A4 = "a4"
    THERMAL_58 = "thermal_58"
    THERMAL_80 = "thermal_80"


class Outlet(Base, TimestampMixin, TenantMixin):
    __tablename__ = "outlets"
    __table_args__ = (UniqueConstraint("tenant_id", "code", name="uq_outlet_tenant_code"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    code: Mapped[str] = mapped_column(String(20), index=True)
    address: Mapped[str | None] = mapped_column(String(255), default=None)
    phone: Mapped[str | None] = mapped_column(String(20), default=None)
    is_warehouse: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Printing preferences - which paper size the printer wired up at this outlet takes.
    # Actual printer selection happens in the browser's native print dialog (any OS-installed
    # printer, thermal or A4, can be chosen there); this just controls which layout is rendered.
    receipt_paper_size: Mapped[PaperSize] = mapped_column(Enum(PaperSize), default=PaperSize.A4)
    transfer_paper_size: Mapped[PaperSize] = mapped_column(Enum(PaperSize), default=PaperSize.A4)

    users: Mapped[list["User"]] = relationship(back_populates="outlet")  # noqa: F821
    stock_levels: Mapped[list["StockLevel"]] = relationship(back_populates="outlet")  # noqa: F821
