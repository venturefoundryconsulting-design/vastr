from pydantic import BaseModel, EmailStr

from app.models.user import UserRole


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class CurrentUser(BaseModel):
    id: int
    name: str
    email: EmailStr
    role: UserRole
    outlet_id: int | None = None
    tenant_id: int | None = None

    model_config = {"from_attributes": True}
