from app.core.database import Base
from app.models.alteration import Alteration, AlterationStatus
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
from app.models.hardware import HardwareAiSettings
from app.models.hrm import Attendance, AttendanceStatus, LeaveRequest, LeaveStatus, LeaveType
from app.models.integrations import EmailProvider, EmailProviderType, SmsProviderConfig, SmsProviderType
from app.models.inventory import StockLevel, StockMovement
from app.models.outlet import Outlet, PaperSize
from app.models.payroll import Payslip, PayslipStatus, StaffSalary
from app.models.product import Category, ImageAngle, Product, ProductImage, ProductVariant
from app.models.purchase import PurchaseOrder, PurchaseOrderItem
from app.models.returns import ExchangeItem, RefundMode, Return, ReturnItem
from app.models.sale import Sale, SaleItem
from app.models.settings import AppSettings
from app.models.tenant import SubscriptionPlanName, SubscriptionStatus, Tenant
from app.models.transfer import StockTransfer, StockTransferItem
from app.models.user import User
from app.models.vendor import Vendor, VendorProduct
from app.models.whatsapp import WhatsAppMessage

__all__ = [
    "Alteration",
    "AlterationStatus",
    "AppSettings",
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
    "Outlet",
    "PaperSize",
    "Payslip",
    "PayslipStatus",
    "Product",
    "ProductImage",
    "ProductVariant",
    "PurchaseOrder",
    "PurchaseOrderItem",
    "RefundMode",
    "Return",
    "ReturnItem",
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
    "SubscriptionPlanName",
    "SubscriptionStatus",
    "Tenant",
    "User",
    "Vendor",
    "VendorProduct",
    "WhatsAppMessage",
]
