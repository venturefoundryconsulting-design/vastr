from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db, require_admin
from app.models.outlet import Outlet
from app.schemas.outlet import OutletCreate, OutletOut, OutletUpdate

router = APIRouter(prefix="/api/outlets", tags=["outlets"])


@router.get("", response_model=list[OutletOut])
def list_outlets(db: Session = Depends(get_db), _=Depends(get_current_user)):
    return db.query(Outlet).order_by(Outlet.name).all()


@router.post("", response_model=OutletOut, dependencies=[Depends(require_admin)])
def create_outlet(payload: OutletCreate, db: Session = Depends(get_db)):
    if db.query(Outlet).filter(Outlet.code == payload.code).first():
        raise HTTPException(400, "Outlet code already exists")
    outlet = Outlet(**payload.model_dump())
    db.add(outlet)
    db.commit()
    db.refresh(outlet)
    return outlet


@router.patch("/{outlet_id}", response_model=OutletOut, dependencies=[Depends(require_admin)])
def update_outlet(outlet_id: int, payload: OutletUpdate, db: Session = Depends(get_db)):
    outlet = db.get(Outlet, outlet_id)
    if not outlet:
        raise HTTPException(404, "Outlet not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(outlet, field, value)
    db.commit()
    db.refresh(outlet)
    return outlet
