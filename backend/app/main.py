import asyncio
import contextlib

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.core.config import settings
from app.core.tenant_context import register_tenant_isolation
from app.middleware.tenant import TenantContextMiddleware
from app.services.campaign_scheduler import campaign_scheduler_loop
from app.routers import (
    ai_import,
    mrp,
    goods_receipts,
    made_to_order,
    quality,
    workforce,
    material_flow,
    production_orders,
    boms,
    admin,
    alterations,
    auth,
    billing,
    campaigns,
    customers,
    dashboard,
    discounts,
    hardware,
    hrm,
    integrations,
    inventory,
    landing,
    outlets,
    payroll,
    platform_settings,
    products,
    purchase_orders,
    reports,
    returns,
    sales,
    settings as settings_router,
    tenant as tenant_router,
    transfers,
    users,
    vendors,
    webhooks,
    items,
)

@contextlib.asynccontextmanager
async def lifespan(_: FastAPI):
    task = asyncio.create_task(campaign_scheduler_loop())
    yield
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task


app = FastAPI(title=settings.PROJECT_NAME, lifespan=lifespan)
register_tenant_isolation()

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(TenantContextMiddleware)

app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(users.router)
app.include_router(outlets.router)
app.include_router(products.router)
app.include_router(products.categories_router)
app.include_router(inventory.router)
app.include_router(vendors.router)
app.include_router(purchase_orders.router)
app.include_router(transfers.router)
app.include_router(customers.router)
app.include_router(sales.router)
app.include_router(returns.router)
app.include_router(discounts.router)
app.include_router(campaigns.router)
app.include_router(campaigns.templates_router)
app.include_router(webhooks.router)
app.include_router(reports.router)
app.include_router(alterations.router)
app.include_router(dashboard.router)
app.include_router(settings_router.router)
app.include_router(settings_router.public_router)
app.include_router(integrations.router)
app.include_router(hardware.router)
app.include_router(hrm.router)
app.include_router(payroll.router)
app.include_router(tenant_router.router)
app.include_router(billing.router)
app.include_router(platform_settings.router)
app.include_router(landing.router)
app.include_router(landing.public_router)
app.include_router(boms.router)
app.include_router(production_orders.router)
app.include_router(material_flow.router)
app.include_router(workforce.router)
app.include_router(quality.router)
app.include_router(made_to_order.router)
app.include_router(goods_receipts.router)
app.include_router(ai_import.router)
app.include_router(mrp.router)
app.include_router(items.router)
app.include_router(items.uom_router)

settings.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=settings.UPLOAD_DIR), name="uploads")


@app.get("/api/health")
def health():
    return {"status": "ok"}
