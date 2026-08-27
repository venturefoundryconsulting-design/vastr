"""Bill of Materials API.

Every route gates on ``require_permission`` (bom.view / bom.create / bom.edit /
bom.activate / bom.archive / bom.cost.view), never on the admin>manager>staff
rank ladder - as the Phase 3 brief requires, and because the production roles
arriving in 3F do not fit that ladder at all.
"""

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload

from app.api.deps import get_db, require_permission
from app.models.bom import Bom, BomComponent, BomComponentSubstitute, BomStatus, BomVersion
from app.models.product import Item
from app.models.uom import UnitOfMeasure
from app.models.user import User
from app.schemas.bom import (
    AvailabilityLine,
    AvailabilityOut,
    BomCreate,
    BomDetail,
    BomOut,
    ComponentOut,
    ComponentsReplace,
    CostLine,
    CostOut,
    DuplicateWarning,
    ExplosionLine,
    SubstituteOut,
    VersionCreate,
    VersionOut,
)
from app.services import bom as bom_service
from app.services.audit import log_activity

router = APIRouter(prefix="/api/boms", tags=["boms"])


# ------------------------------------------------------------------- helpers


def _component_out(c: BomComponent) -> ComponentOut:
    return ComponentOut(
        id=c.id, item_id=c.item_id,
        sku=c.item.sku if c.item else None,
        name=c.item.resolved_name if c.item else None,
        quantity=c.quantity, uom_id=c.uom_id,
        uom_code=None, scrap_pct=c.scrap_pct,
        gross_quantity=c.gross_quantity, is_optional=c.is_optional,
        sequence=c.sequence, notes=c.notes,
        substitutes=[
            SubstituteOut(
                id=s.id, item_id=s.item_id, priority=s.priority, notes=s.notes,
                sku=s.item.sku if s.item else None,
                name=s.item.resolved_name if s.item else None,
            )
            for s in c.substitutes
        ],
    )


def _version_out(v: BomVersion, *, with_components: bool = False) -> VersionOut:
    return VersionOut(
        id=v.id, bom_id=v.bom_id, version_no=v.version_no, status=v.status,
        output_quantity=v.output_quantity, output_uom_id=v.output_uom_id,
        output_uom_code=v.output_uom.code if v.output_uom else None,
        effective_from=v.effective_from, effective_to=v.effective_to,
        notes=v.notes, is_locked=v.is_locked, is_editable=v.is_editable,
        component_count=len(v.components),
        components=[_component_out(c) for c in v.components] if with_components else [],
    )


def _bom_out(b: Bom) -> BomOut:
    active = b.active_version
    return BomOut(
        id=b.id, item_id=b.item_id,
        item_sku=b.item.sku if b.item else None,
        item_name=b.item.resolved_name if b.item else None,
        name=b.name, description=b.description, notes=b.notes, is_active=b.is_active,
        active_version_no=active.version_no if active else None,
        version_count=len(b.versions),
    )


def _get_bom(db: Session, bom_id: int) -> Bom:
    b = (
        db.query(Bom)
        .options(joinedload(Bom.item), joinedload(Bom.versions).joinedload(BomVersion.components))
        .filter(Bom.id == bom_id)
        .first()
    )
    if not b:
        raise HTTPException(404, "Bill of materials not found")
    return b


def _get_version(db: Session, version_id: int) -> BomVersion:
    v = (
        db.query(BomVersion)
        .options(
            joinedload(BomVersion.components)
            .joinedload(BomComponent.substitutes)
            .joinedload(BomComponentSubstitute.item),
            joinedload(BomVersion.components).joinedload(BomComponent.item),
            joinedload(BomVersion.output_uom),
        )
        .filter(BomVersion.id == version_id)
        .first()
    )
    if not v:
        raise HTTPException(404, "BOM version not found")
    return v


def _resolve_target(db: Session, bom: Bom, version_id: int | None) -> BomVersion:
    """The version a read endpoint should act on: the one asked for, else the
    active one, else the newest."""
    if version_id:
        v = _get_version(db, version_id)
        if v.bom_id != bom.id:
            raise HTTPException(400, "That version belongs to a different bill of materials")
        return v
    target = bom.active_version or (bom.versions[-1] if bom.versions else None)
    if not target:
        raise HTTPException(400, "This bill of materials has no versions yet")
    return target


def _write_components(db: Session, version: BomVersion, payload_components) -> None:
    """Replace a draft's lines wholesale, validating each against the Item Master
    and the Phase 2 conversion engine."""
    bom_service.assert_editable(version)

    for existing in list(version.components):
        db.delete(existing)
    db.flush()

    parent_item_id = version.bom.item_id
    for index, c in enumerate(payload_components):
        item = db.get(Item, c.item_id)
        if not item:
            raise HTTPException(404, f"Item {c.item_id} not found")
        if not db.get(UnitOfMeasure, c.uom_id):
            raise HTTPException(404, f"Unit {c.uom_id} not found")

        try:
            bom_service.assert_no_cycle(db, parent_item_id, c.item_id)
            bom_service.validate_component_uom(db, item, c.uom_id)
        except bom_service.BomError as e:
            raise HTTPException(400, f"{item.sku}: {e}") from e

        row = BomComponent(
            bom_version_id=version.id, item_id=c.item_id, quantity=c.quantity,
            uom_id=c.uom_id, scrap_pct=c.scrap_pct, is_optional=c.is_optional,
            sequence=c.sequence if c.sequence else index, notes=c.notes,
        )
        db.add(row)
        db.flush()
        for s in c.substitutes:
            if not db.get(Item, s.item_id):
                raise HTTPException(404, f"Substitute item {s.item_id} not found")
            db.add(BomComponentSubstitute(
                bom_component_id=row.id, item_id=s.item_id,
                priority=s.priority, notes=s.notes,
            ))
    db.flush()


# ---------------------------------------------------------------------- CRUD


@router.get("", response_model=list[BomOut])
def list_boms(
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("bom.view")),
    q: str | None = Query(None, description="Matches BOM name, item SKU or item name"),
    item_id: int | None = None,
    limit: int = Query(50, le=200),
    offset: int = 0,
):
    query = db.query(Bom).options(joinedload(Bom.item), joinedload(Bom.versions))
    if item_id:
        query = query.filter(Bom.item_id == item_id)
    if q:
        like = f"%{q.strip()}%"
        query = query.join(Item, Item.id == Bom.item_id).filter(
            Bom.name.ilike(like) | Item.sku.ilike(like) | Item.name.ilike(like)
        )
    return [_bom_out(b) for b in query.order_by(Bom.name).offset(offset).limit(limit).all()]


@router.get("/{bom_id}", response_model=BomDetail)
def get_bom(
    bom_id: int, db: Session = Depends(get_db),
    _: User = Depends(require_permission("bom.view")),
):
    b = _get_bom(db, bom_id)
    detail = BomDetail(**_bom_out(b).model_dump())
    detail.versions = [_version_out(v) for v in b.versions]
    return detail


@router.post("", response_model=BomDetail, status_code=201)
def create_bom(
    payload: BomCreate, db: Session = Depends(get_db),
    user: User = Depends(require_permission("bom.create")),
):
    item = db.get(Item, payload.item_id)
    if not item:
        raise HTTPException(404, "Item not found")
    if db.query(Bom).filter(Bom.item_id == payload.item_id).first():
        raise HTTPException(
            409,
            f"{item.sku} already has a bill of materials. Add a new version to it "
            "instead of creating a second BOM.",
        )

    bom = Bom(item_id=payload.item_id, name=payload.name,
              description=payload.description, notes=payload.notes)
    db.add(bom)
    db.flush()

    version = BomVersion(
        bom_id=bom.id, version_no=1, status=BomStatus.DRAFT,
        output_quantity=payload.output_quantity, output_uom_id=payload.output_uom_id,
        created_by_id=user.id,
    )
    db.add(version)
    db.flush()
    if payload.components:
        _write_components(db, version, payload.components)

    log_activity(db, action="bom.create", tenant_id=user.tenant_id, user_id=user.id,
                 entity_type="Bom", entity_id=bom.id,
                 details={"item_sku": item.sku, "components": len(payload.components)})
    db.commit()
    return get_bom(bom.id, db, user)


# ------------------------------------------------------------------ versions


@router.get("/{bom_id}/versions", response_model=list[VersionOut])
def list_versions(
    bom_id: int, db: Session = Depends(get_db),
    _: User = Depends(require_permission("bom.view")),
):
    return [_version_out(v) for v in _get_bom(db, bom_id).versions]


@router.get("/{bom_id}/versions/{version_id}", response_model=VersionOut)
def get_version(
    bom_id: int, version_id: int, db: Session = Depends(get_db),
    _: User = Depends(require_permission("bom.view")),
):
    bom = _get_bom(db, bom_id)
    return _version_out(_resolve_target(db, bom, version_id), with_components=True)


@router.post("/{bom_id}/versions", response_model=VersionOut, status_code=201)
def create_version(
    bom_id: int, payload: VersionCreate, db: Session = Depends(get_db),
    user: User = Depends(require_permission("bom.edit")),
):
    """Start the next version. Pass copy_from_version_id to carry lines forward -
    this is how an ACTIVE (immutable) BOM gets 'edited'."""
    bom = _get_bom(db, bom_id)
    version = BomVersion(
        bom_id=bom.id, version_no=bom_service.next_version_no(db, bom.id),
        status=BomStatus.DRAFT, output_quantity=payload.output_quantity,
        output_uom_id=payload.output_uom_id, effective_from=payload.effective_from,
        effective_to=payload.effective_to, notes=payload.notes, created_by_id=user.id,
    )
    db.add(version)
    db.flush()

    if payload.copy_from_version_id:
        source = _get_version(db, payload.copy_from_version_id)
        if source.bom_id != bom.id:
            raise HTTPException(400, "Cannot copy from a different bill of materials")
        bom_service.copy_components(db, source, version)

    log_activity(db, action="bom.version.create", tenant_id=user.tenant_id, user_id=user.id,
                 entity_type="BomVersion", entity_id=version.id,
                 details={"bom_id": bom.id, "version_no": version.version_no})
    db.commit()
    return _version_out(_get_version(db, version.id), with_components=True)


@router.put("/{bom_id}/versions/{version_id}/components", response_model=VersionOut)
def replace_components(
    bom_id: int, version_id: int, payload: ComponentsReplace,
    db: Session = Depends(get_db), user: User = Depends(require_permission("bom.edit")),
):
    bom = _get_bom(db, bom_id)
    version = _resolve_target(db, bom, version_id)
    try:
        _write_components(db, version, payload.components)
    except bom_service.BomError as e:
        raise HTTPException(400, str(e)) from e
    log_activity(db, action="bom.components.replace", tenant_id=user.tenant_id, user_id=user.id,
                 entity_type="BomVersion", entity_id=version.id,
                 details={"count": len(payload.components)})
    db.commit()
    return _version_out(_get_version(db, version.id), with_components=True)


@router.post("/{bom_id}/versions/{version_id}/activate", response_model=VersionOut)
def activate_version(
    bom_id: int, version_id: int, db: Session = Depends(get_db),
    user: User = Depends(require_permission("bom.activate")),
):
    bom = _get_bom(db, bom_id)
    version = _resolve_target(db, bom, version_id)
    try:
        bom_service.activate(db, version)
    except bom_service.BomError as e:
        raise HTTPException(400, str(e)) from e
    log_activity(db, action="bom.activate", tenant_id=user.tenant_id, user_id=user.id,
                 entity_type="BomVersion", entity_id=version.id,
                 details={"version_no": version.version_no})
    db.commit()
    return _version_out(_get_version(db, version.id), with_components=True)


@router.post("/{bom_id}/versions/{version_id}/archive", response_model=VersionOut)
def archive_version(
    bom_id: int, version_id: int, db: Session = Depends(get_db),
    user: User = Depends(require_permission("bom.archive")),
):
    bom = _get_bom(db, bom_id)
    version = _resolve_target(db, bom, version_id)
    version.status = BomStatus.ARCHIVED
    db.flush()
    log_activity(db, action="bom.archive", tenant_id=user.tenant_id, user_id=user.id,
                 entity_type="BomVersion", entity_id=version.id, details={})
    db.commit()
    return _version_out(_get_version(db, version.id))


# ------------------------------------------------------- derived projections


@router.get("/{bom_id}/explode", response_model=list[ExplosionLine])
def explode_bom(
    bom_id: int, db: Session = Depends(get_db),
    _: User = Depends(require_permission("bom.view")),
    quantity: Decimal = Query(Decimal("1"), gt=0),
    version_id: int | None = None,
):
    version = _resolve_target(db, _get_bom(db, bom_id), version_id)
    try:
        rows = bom_service.explode(db, version, quantity)
    except bom_service.CircularBomError as e:
        raise HTTPException(400, str(e)) from e
    return [
        ExplosionLine(
            item_id=r["item_id"], sku=r["item"].sku, name=r["item"].resolved_name,
            quantity=r["quantity"], net_quantity=r["net_quantity"], scrap_pct=r["scrap_pct"],
            uom_id=r["uom_id"], is_optional=r["is_optional"],
            is_subassembly=r["is_subassembly"], level=r["level"],
        )
        for r in rows
    ]


@router.get("/{bom_id}/cost", response_model=CostOut)
def bom_cost(
    bom_id: int, db: Session = Depends(get_db),
    _: User = Depends(require_permission("bom.cost.view")),
    quantity: Decimal = Query(Decimal("1"), gt=0),
    version_id: int | None = None,
):
    version = _resolve_target(db, _get_bom(db, bom_id), version_id)
    result = bom_service.cost_version(db, version, quantity)
    return CostOut(
        quantity=quantity,
        lines=[CostLine(**line) for line in result["lines"]],
        total_cost=result["total_cost"],
    )


@router.get("/{bom_id}/availability", response_model=AvailabilityOut)
def bom_availability(
    bom_id: int, db: Session = Depends(get_db),
    _: User = Depends(require_permission("bom.view")),
    quantity: Decimal = Query(Decimal("1"), gt=0),
    outlet_id: int | None = None,
    version_id: int | None = None,
):
    """Read-only. Never reserves, never consumes - safe to call on every render."""
    version = _resolve_target(db, _get_bom(db, bom_id), version_id)
    rows = bom_service.availability(db, version, quantity, outlet_id=outlet_id)
    lines = [AvailabilityLine(**r) for r in rows]
    return AvailabilityOut(
        quantity=quantity, outlet_id=outlet_id,
        all_available=all(line.is_available for line in lines if not line.is_optional),
        lines=lines,
    )


@router.get("/{bom_id}/duplicates", response_model=list[DuplicateWarning])
def duplicate_components(
    bom_id: int, db: Session = Depends(get_db),
    _: User = Depends(require_permission("bom.view")),
    version_id: int | None = None,
):
    """Warns, never merges - two lines for the same lace may be deliberate."""
    version = _resolve_target(db, _get_bom(db, bom_id), version_id)
    return [DuplicateWarning(**d) for d in bom_service.find_duplicate_components(version.components)]
