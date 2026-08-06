import re

from pydantic import BaseModel, EmailStr, field_validator

from app.models.tenant import SubscriptionPlanName
from app.models.user import UserRole

_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,38}[a-z0-9]$")


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


class RegisterRequest(BaseModel):
    company_name: str
    slug: str
    owner_name: str
    email: EmailStr
    password: str
    plan: SubscriptionPlanName = SubscriptionPlanName.FREE

    @field_validator("slug")
    @classmethod
    def validate_slug(cls, v: str) -> str:
        v = v.lower().strip()
        if not _SLUG_RE.match(v):
            raise ValueError(
                "Store URL must be 3-40 characters, lowercase letters, numbers and hyphens only, "
                "and cannot start or end with a hyphen"
            )
        if v in {"admin", "api", "www", "app", "velora", "platform", "static", "assets"}:
            raise ValueError("That store URL is reserved")
        return v

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v


class SlugAvailability(BaseModel):
    slug: str
    available: bool
