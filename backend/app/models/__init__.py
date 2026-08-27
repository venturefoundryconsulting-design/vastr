from app.core.database import Base
from app.models.alteration import Alteration, AlterationStatus
from app.models.bom import Bom, BomComponent, BomComponentSubstitute, BomStatus, BomVersion
from app.models.campaign import (
    Campaign,
    CampaignMediaType,
    CampaignRecipient,
    CampaignStatus,
    MessageTemplate,
    SegmentType,
)
from app.models.customer import (
    BalanceType,
    Customer,
    CustomerAddress,
    CustomerBalanceAdjustment,
    CustomerLoyaltyAdjustment,
)
from app.models.discount import DiscountRule, DiscountScope, DiscountType
from app.models.goods_receipt import (
    GoodsReceipt,
    GoodsReceiptItem,
    PurchaseReturn,
    PurchaseReturnItem,
    ReceiptStatus,
)
from app.models.hardware import HardwareAiSettings
from app.models.hrm import Attendance, AttendanceStatus, LeaveRequest, LeaveStatus, LeaveType
from app.models.integrations import EmailProvider, EmailProviderType, SmsProviderConfig, SmsProviderType
from app.models.inventory import StockLevel, StockMovement
from app.models.made_to_order import (
    CustomerOrder,
    CustomerOrderItem,
    CustomerOrderStatus,
    Fulfilment,
    MeasurementField,
    MeasurementProfile,
    MeasurementUnit,
    MeasurementValue,
)
from app.models.material_flow import (
    ProductionMaterialConsumption,
    ProductionMaterialIssue,
    ProductionMaterialReturn,
    ReservationStatus,
    StockReservation,
)
from app.models.outlet import Outlet, PaperSize
from app.models.payroll import Payslip, PayslipStatus, StaffSalary
from app.models.platform_settings import (
    LandingContent,
    LegalPage,
    Payment,
    PlatformDomainConfig,
    PlatformEmailConfig,
    PlatformPaymentConfig,
    PlatformWebsiteConfig,
)
from app.models.product import (
    Category,
    ImageAngle,
    Item,
    ItemType,
    Product,
    ProductImage,
    ProductVariant,
)
from app.models.production import (
    MaterialAvailability,
    OrderAvailability,
    ProductionOrder,
    ProductionOrderMaterial,
    ProductionPriority,
    ProductionStatus,
)
from app.models.production_output import ProductionOutput
from app.models.quality import (
    DefectCategory,
    ProductionWastage,
    QcResult,
    QualityCheck,
    QualityDefect,
    ReworkOrder,
    ReworkStatus,
    WastageReason,
)
from app.models.purchase import PurchaseOrder, PurchaseOrderItem
from app.models.returns import ExchangeItem, RefundMode, Return, ReturnItem
from app.models.audit import AuditLog
from app.models.permission import Permission, RolePermission
from app.models.sale import Sale, SaleItem
from app.models.settings import AppSettings
from app.models.subscription_plan import SubscriptionPlan
from app.models.tenant import SubscriptionPlanName, SubscriptionStatus, Tenant
from app.models.transfer import StockTransfer, StockTransferItem
from app.models.user import User
from app.models.uom import ItemUomConversion, UnitOfMeasure, UomCategory
from app.models.workforce import (
    PayModel,
    ProductionStage,
    Tailor,
    TailorSkill,
    WorkOrder,
    WorkOrderStatus,
)
from app.models.vendor import Vendor, VendorItem, VendorProduct
from app.models.whatsapp import WhatsAppMessage

__all__ = [
    "ReceiptStatus",
    "PurchaseReturnItem",
    "PurchaseReturn",
    "GoodsReceiptItem",
    "GoodsReceipt",
    "MeasurementUnit",
    "MeasurementValue",
    "MeasurementProfile",
    "MeasurementField",
    "Fulfilment",
    "CustomerOrderStatus",
    "CustomerOrderItem",
    "CustomerOrder",
    "WastageReason",
    "ProductionWastage",
    "QcResult",
    "ReworkStatus",
    "ReworkOrder",
    "DefectCategory",
    "QualityDefect",
    "QualityCheck",
    "PayModel",
    "WorkOrderStatus",
    "WorkOrder",
    "ProductionStage",
    "TailorSkill",
    "Tailor",
    "ProductionOutput",
    "ProductionMaterialReturn",
    "ProductionMaterialConsumption",
    "ProductionMaterialIssue",
    "ReservationStatus",
    "StockReservation",
    "ProductionMaterialReturn",
    "ProductionMaterialConsumption",
    "ProductionMaterialIssue",
    "ReservationStatus",
    "StockReservation",
    "OrderAvailability",
    "MaterialAvailability",
    "ProductionPriority",
    "ProductionStatus",
    "ProductionOrderMaterial",
    "ProductionOrder",
    "BomStatus",
    "BomComponentSubstitute",
    "BomComponent",
    "BomVersion",
    "Bom",
    "VendorItem",
    "ItemUomConversion",
    "UomCategory",
    "UnitOfMeasure",
    "ItemType",
    "Item",
    "Alteration",
    "AlterationStatus",
    "AppSettings",
    "AuditLog",
    "Attendance",
    "AttendanceStatus",
    "BalanceType",
    "Base",
    "Campaign",
    "CampaignMediaType",
    "CampaignRecipient",
    "CampaignStatus",
    "Category",
    "Customer",
    "CustomerAddress",
    "CustomerBalanceAdjustment",
    "CustomerLoyaltyAdjustment",
    "DiscountRule",
    "DiscountScope",
    "DiscountType",
    "EmailProvider",
    "EmailProviderType",
    "ExchangeItem",
    "HardwareAiSettings",
    "ImageAngle",
    "LeaveRequest",
    "LeaveStatus",
    "LeaveType",
    "MessageTemplate",
    "LandingContent",
    "LegalPage",
    "Outlet",
    "PaperSize",
    "Payment",
    "Payslip",
    "PayslipStatus",
    "Permission",
    "PlatformDomainConfig",
    "PlatformEmailConfig",
    "PlatformPaymentConfig",
    "PlatformWebsiteConfig",
    "Product",
    "ProductImage",
    "ProductVariant",
    "PurchaseOrder",
    "PurchaseOrderItem",
    "RefundMode",
    "Return",
    "ReturnItem",
    "RolePermission",
    "Sale",
    "SaleItem",
    "SegmentType",
    "StaffSalary",
    "SmsProviderConfig",
    "SmsProviderType",
    "StockLevel",
    "StockMovement",
    "StockTransfer",
    "StockTransferItem",
    "SubscriptionPlan",
    "SubscriptionPlanName",
    "SubscriptionStatus",
    "Tenant",
    "User",
    "Vendor",
    "VendorProduct",
    "WhatsAppMessage",
]
