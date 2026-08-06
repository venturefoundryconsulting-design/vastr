from pydantic import BaseModel, EmailStr

from app.models.user import UserRole


class UserBase(BaseModel):
    name: str
    email: EmailStr
    role: UserRole = UserRole.OUTLET_STAFF
    outlet_id: int | None = None


class UserCreate(UserBase):
    password: str


class UserUpdate(BaseModel):
    name: str | None = None
    role: UserRole | None = None
    outlet_id: int | None = None
    is_active: bool | None = None
    password: str | None = None


class UserOut(UserBase):
    id: int
    is_active: bool

    model_config = {"from_attributes": True}
