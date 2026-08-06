"""Tenant self-service: a tenant's own users viewing/editing their own
Tenant row. Distinct from app.routers.admin, which is the Super Admin's
cross-tenant view - this router only ever touches the caller's own tenant
(derived from their JWT, never from a path parameter), and never exposes
subscription_plan/subscription_status for editing - those are Super Admin
only.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db, require_admin
from app.models.tenant import Tenant
from app.models.user import User
from app.schemas.tenant import TenantSelfOut, TenantSelfUpdate
from app.services.audit import log_activity

router = APIRouter(prefix="/api/tenant", tags=["tenant"])


@router.get("/me", response_model=TenantSelfOut)
def get_my_tenant(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if user.tenant_id is None:
        raise HTTPException(404, "This account is not a member of a tenant")
    tenant = db.get(Tenant, user.tenant_id)
    if not tenant:
        raise HTTPException(404, "Tenant not found")
    return tenant


@router.patch("/me", response_model=TenantSelfOut)
def update_my_tenant(
    payload: TenantSelfUpdate, db: Session = Depends(get_db), user: User = Depends(require_admin)
):
    tenant = db.get(Tenant, user.tenant_id)
    if not tenant:
        raise HTTPException(404, "Tenant not found")
    changed = payload.model_dump(exclude_unset=True)
    for field, value in changed.items():
        setattr(tenant, field, value)
    log_activity(
        db, action="tenant.self_update", tenant_id=tenant.id, user_id=user.id,
        entity_type="Tenant", entity_id=tenant.id, details={"fields": list(changed.keys())},
    )
    db.commit()
    db.refresh(tenant)
    return tenant
