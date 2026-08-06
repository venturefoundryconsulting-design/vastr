import uuid

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db, require_admin
from app.core.config import settings as env_settings
from app.models.settings import AppSettings
from app.models.tenant import Tenant
from app.models.user import User
from app.schemas.settings import AppSettingsOut, AppSettingsUpdate, PublicBrandingOut
from app.services.app_settings import get_app_settings
from app.services.audit import log_activity

router = APIRouter(prefix="/api/settings", tags=["settings"], dependencies=[Depends(require_admin)])

# Unauthenticated - the login page needs the logo/business name before a user has a token.
public_router = APIRouter(prefix="/api/settings", tags=["settings"])

LOGO_TYPES = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp", "image/svg+xml": ".svg"}


def _to_out(s: AppSettings) -> AppSettingsOut:
    return AppSettingsOut(
        business_name=s.business_name,
        business_address=s.business_address,
        business_gstin=s.business_gstin,
        business_phone=s.business_phone,
        business_email=s.business_email,
        invoice_footer_text=s.invoice_footer_text,
        show_hsn_on_documents=s.show_hsn_on_documents,
        logo_url=s.logo_url,
        invoice_prefix=s.invoice_prefix,
        whatsapp_phone_number_id=s.whatsapp_phone_number_id,
        whatsapp_api_version=s.whatsapp_api_version,
        whatsapp_token_set=bool(s.whatsapp_cloud_api_token),
    )


@router.get("", response_model=AppSettingsOut)
def get_settings(db: Session = Depends(get_db)):
    return _to_out(get_app_settings(db))


@router.patch("", response_model=AppSettingsOut)
def update_settings(
    payload: AppSettingsUpdate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
):
    s = get_app_settings(db)
    changed_fields = []
    for field, value in payload.model_dump(exclude_unset=True).items():
        if value is None or value == "":
            continue
        setattr(s, field, value)
        changed_fields.append(field)
    log_activity(
        db, action="settings.update", tenant_id=s.tenant_id, user_id=current_user.id,
        entity_type="AppSettings", entity_id=s.id, details={"fields": changed_fields},
    )
    db.commit()
    db.refresh(s)
    return _to_out(s)


@router.post("/logo", response_model=AppSettingsOut)
async def upload_logo(file: UploadFile = File(...), db: Session = Depends(get_db)):
    ext = LOGO_TYPES.get(file.content_type)
    if not ext:
        raise HTTPException(400, "Only JPEG, PNG, WebP or SVG images are allowed")

    contents = await file.read()
    if len(contents) > 2 * 1024 * 1024:
        raise HTTPException(400, "Logo must be under 2MB")

    s = get_app_settings(db)
    logo_dir = env_settings.tenant_upload_dir(s.tenant_id, "branding")
    logo_dir.mkdir(parents=True, exist_ok=True)
    filename = f"logo-{uuid.uuid4().hex}{ext}"
    (logo_dir / filename).write_bytes(contents)
    branding_prefix = f"{env_settings.PUBLIC_BASE_URL}/uploads/{env_settings.tenant_relative_path(s.tenant_id, 'branding')}/"

    old_url = s.logo_url
    s.logo_url = f"{branding_prefix}{filename}"
    db.commit()
    db.refresh(s)

    if old_url and old_url.startswith(branding_prefix):
        old_path = env_settings.tenant_upload_dir(s.tenant_id, "branding", old_url.rsplit("/", 1)[-1])
        old_path.unlink(missing_ok=True)

    return _to_out(s)


@router.delete("/logo", response_model=AppSettingsOut)
def remove_logo(db: Session = Depends(get_db)):
    s = get_app_settings(db)
    branding_prefix = f"{env_settings.PUBLIC_BASE_URL}/uploads/{env_settings.tenant_relative_path(s.tenant_id, 'branding')}/"
    if s.logo_url and s.logo_url.startswith(branding_prefix):
        old_path = env_settings.tenant_upload_dir(s.tenant_id, "branding", s.logo_url.rsplit("/", 1)[-1])
        old_path.unlink(missing_ok=True)
    s.logo_url = None
    db.commit()
    db.refresh(s)
    return _to_out(s)


@public_router.get("/public", response_model=PublicBrandingOut)
def get_public_branding(db: Session = Depends(get_db)):
    s = get_app_settings(db)
    tenant = db.get(Tenant, s.tenant_id)
    return PublicBrandingOut(
        business_name=s.business_name,
        logo_url=s.logo_url,
        primary_color=tenant.primary_color if tenant else None,
    )
