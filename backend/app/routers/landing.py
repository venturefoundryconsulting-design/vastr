"""Public read endpoints for the marketing site (Landing page + legal pages)
plus the Super Admin CRUD that edits them - the "Landing Page settings" CMS
surface. Public endpoints always return something renderable even before a
Super Admin has ever touched these settings: empty/default field values,
which Landing.tsx merges with its own hardcoded fallback copy client-side.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_super_admin
from app.models.platform_settings import LandingContent, LegalPage
from app.schemas.landing import (
    LandingContentOut,
    LandingContentUpdate,
    LegalPageOut,
    LegalPageUpsert,
)

# Unauthenticated - the public Landing page and legal pages need this before
# any user has a token (same pattern as routers.settings.public_router).
public_router = APIRouter(tags=["landing"])

router = APIRouter(prefix="/api/admin", tags=["landing-admin"], dependencies=[Depends(require_super_admin)])


def _get_or_create_content(db: Session) -> LandingContent:
    row = db.query(LandingContent).first()
    if not row:
        row = LandingContent()
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


@public_router.get("/api/landing-content", response_model=LandingContentOut)
def get_landing_content(db: Session = Depends(get_db)):
    return _get_or_create_content(db)


@public_router.get("/api/legal/{slug}", response_model=LegalPageOut)
def get_legal_page(slug: str, db: Session = Depends(get_db)):
    row = db.query(LegalPage).filter(LegalPage.slug == slug).first()
    if not row:
        raise HTTPException(404, "This page hasn't been published yet")
    return row


@router.get("/landing-content", response_model=LandingContentOut)
def admin_get_landing_content(db: Session = Depends(get_db)):
    return _get_or_create_content(db)


@router.patch("/landing-content", response_model=LandingContentOut)
def admin_update_landing_content(payload: LandingContentUpdate, db: Session = Depends(get_db)):
    row = _get_or_create_content(db)
    for field, value in payload.model_dump(exclude_unset=True).items():
        if value is None:
            continue
        setattr(row, field, value)
    db.commit()
    db.refresh(row)
    return row


@router.get("/legal-pages", response_model=list[LegalPageOut])
def admin_list_legal_pages(db: Session = Depends(get_db)):
    return db.query(LegalPage).order_by(LegalPage.slug).all()


@router.put("/legal-pages/{slug}", response_model=LegalPageOut)
def admin_upsert_legal_page(slug: str, payload: LegalPageUpsert, db: Session = Depends(get_db)):
    row = db.query(LegalPage).filter(LegalPage.slug == slug).first()
    if not row:
        row = LegalPage(slug=slug, title=payload.title, content=payload.content)
        db.add(row)
    else:
        row.title = payload.title
        row.content = payload.content
    db.commit()
    db.refresh(row)
    return row
