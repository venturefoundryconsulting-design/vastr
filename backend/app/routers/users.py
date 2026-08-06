from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_admin
from app.core.security import hash_password
from app.models.user import User
from app.schemas.user import UserCreate, UserOut, UserUpdate
from app.services.audit import log_activity

router = APIRouter(prefix="/api/users", tags=["users"])


@router.get("", response_model=list[UserOut])
def list_users(db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    return db.query(User).filter(User.tenant_id == current_user.tenant_id).order_by(User.name).all()


@router.post("", response_model=UserOut)
def create_user(
    payload: UserCreate, db: Session = Depends(get_db), current_user: User = Depends(require_admin)
):
    if db.query(User).filter(User.email == payload.email).first():
        raise HTTPException(400, "Email already registered")
    data = payload.model_dump(exclude={"password"})
    user = User(**data, hashed_password=hash_password(payload.password), tenant_id=current_user.tenant_id)
    db.add(user)
    db.flush()
    log_activity(
        db, action="user.create", tenant_id=current_user.tenant_id, user_id=current_user.id,
        entity_type="User", entity_id=user.id, details={"email": user.email, "role": user.role.value},
    )
    db.commit()
    db.refresh(user)
    return user


@router.patch("/{user_id}", response_model=UserOut)
def update_user(
    user_id: int,
    payload: UserUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    user = db.query(User).filter(User.id == user_id, User.tenant_id == current_user.tenant_id).first()
    if not user:
        raise HTTPException(404, "User not found")
    data = payload.model_dump(exclude_unset=True)
    password = data.pop("password", None)
    for field, value in data.items():
        setattr(user, field, value)
    if password:
        user.hashed_password = hash_password(password)
    log_activity(
        db, action="user.update", tenant_id=current_user.tenant_id, user_id=current_user.id,
        entity_type="User", entity_id=user.id, details={"fields": list(data.keys())},
    )
    db.commit()
    db.refresh(user)
    return user
