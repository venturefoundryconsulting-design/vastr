"""Platform-level configuration - not scoped to any tenant (no TenantMixin).

These are Super Admin-only singletons (one row each, id=1, get-or-create like
app.models.settings.AppSettings but without a tenant_id) plus two small
reference/log tables (LegalPage, Payment). They back the "Global Settings",
"Landing Page settings" and billing surfaces of the Super Admin portal.
"""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.mixins import TimestampMixin


class PlatformEmailConfig(Base, TimestampMixin):
    """SMTP settings used for system emails (signup verification, password
    reset) - separate from the per-tenant EmailProvider table in
    app.models.integrations, which tenants use to email their own customers.
    """

    __tablename__ = "platform_email_config"

    id: Mapped[int] = mapped_column(primary_key=True)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=False)

    smtp_host: Mapped[str | None] = mapped_column(String(255), default=None)
    smtp_port: Mapped[int | None] = mapped_column(Integer, default=None)
    smtp_username: Mapped[str | None] = mapped_column(String(255), default=None)
    smtp_password: Mapped[str | None] = mapped_column(String(500), default=None)
    smtp_use_tls: Mapped[bool] = mapped_column(Boolean, default=True)
    sender_name: Mapped[str | None] = mapped_column(String(120), default=None)
    sender_email: Mapped[str | None] = mapped_column(String(255), default=None)

    last_test_status: Mapped[str | None] = mapped_column(String(20), default=None)
    last_test_at: Mapped["datetime | None"] = mapped_column(DateTime(timezone=True), default=None)
    last_test_error: Mapped[str | None] = mapped_column(String(500), default=None)


class PlatformPaymentConfig(Base, TimestampMixin):
    """Razorpay credentials for the platform's own billing (tenants paying
    Vastr for their subscription) - a single merchant account for the whole
    platform, configured once here, not per-tenant."""

    __tablename__ = "platform_payment_config"

    id: Mapped[int] = mapped_column(primary_key=True)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    is_live: Mapped[bool] = mapped_column(Boolean, default=False)

    razorpay_key_id: Mapped[str | None] = mapped_column(String(120), default=None)
    razorpay_key_secret: Mapped[str | None] = mapped_column(String(255), default=None)
    razorpay_webhook_secret: Mapped[str | None] = mapped_column(String(255), default=None)

    last_test_status: Mapped[str | None] = mapped_column(String(20), default=None)
    last_test_at: Mapped["datetime | None"] = mapped_column(DateTime(timezone=True), default=None)
    last_test_error: Mapped[str | None] = mapped_column(String(500), default=None)


class PlatformWebsiteConfig(Base, TimestampMixin):
    """General site-identity settings - support contact, footer, social
    links - surfaced on the public Landing page and legal pages."""

    __tablename__ = "platform_website_config"

    id: Mapped[int] = mapped_column(primary_key=True)
    site_name: Mapped[str] = mapped_column(String(120), default="Vastr")
    support_email: Mapped[str | None] = mapped_column(String(255), default=None)
    support_phone: Mapped[str | None] = mapped_column(String(30), default=None)
    footer_text: Mapped[str | None] = mapped_column(String(300), default=None)
    # {"twitter": "...", "linkedin": "...", "instagram": "..."} - optional, sparse.
    social_links: Mapped[dict] = mapped_column(JSONB, default=dict)


class PlatformDomainConfig(Base, TimestampMixin):
    """Sub-domain policy for new stores (yourstore.<base_domain>) - the base
    domain string and the reserved-slug blocklist enforced at registration
    (see schemas.auth.RegisterRequest.validate_slug)."""

    __tablename__ = "platform_domain_config"

    id: Mapped[int] = mapped_column(primary_key=True)
    base_domain: Mapped[str] = mapped_column(String(120), default="vastr.space")
    # List[str] of slugs that can never be claimed by a store, beyond the
    # hardcoded baseline in schemas.auth - editable so Super Admin can extend
    # it (e.g. after a support/marketing page ships at a given path) without
    # a code deploy.
    reserved_slugs: Mapped[list] = mapped_column(JSONB, default=list)


class LandingContent(Base, TimestampMixin):
    """Singleton CMS content for the public Landing page - Super Admin edits
    this via the Landing Page settings screen; Landing.tsx fetches it through
    the public GET endpoint and falls back to hardcoded defaults if this row
    doesn't exist yet or a field is blank, so an un-configured platform still
    renders a complete page."""

    __tablename__ = "landing_content"

    id: Mapped[int] = mapped_column(primary_key=True)
    hero_eyebrow: Mapped[str | None] = mapped_column(String(120), default=None)
    hero_title_line1: Mapped[str | None] = mapped_column(String(120), default=None)
    hero_title_highlight: Mapped[str | None] = mapped_column(String(120), default=None)
    hero_subtitle: Mapped[str | None] = mapped_column(String(500), default=None)
    hero_cta_primary: Mapped[str | None] = mapped_column(String(60), default=None)
    hero_cta_secondary: Mapped[str | None] = mapped_column(String(60), default=None)
    # Each a JSON list of small objects - see schemas.landing for shape.
    value_strip: Mapped[list] = mapped_column(JSONB, default=list)
    features: Mapped[list] = mapped_column(JSONB, default=list)
    how_it_works: Mapped[list] = mapped_column(JSONB, default=list)
    faqs: Mapped[list] = mapped_column(JSONB, default=list)


class LegalPage(Base, TimestampMixin):
    """Terms of Service / Privacy Policy / etc - editable plain-text pages,
    one row per slug, rendered at /legal/{slug} on the public site."""

    __tablename__ = "legal_pages"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(60), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(120))
    content: Mapped[str] = mapped_column(Text, default="")


class Payment(Base, TimestampMixin):
    """One row per Razorpay order created for a tenant's subscription -
    created in 'created' status when the checkout is opened, updated to
    'paid' once app.services.razorpay verifies the payment signature, or
    left as 'created'/'failed' otherwise. tenant_id is a plain FK (not
    TenantMixin): a Payment can be created mid-signup before the tenant's
    own request-scoped tenant context exists.
    """

    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int | None] = mapped_column(ForeignKey("tenants.id"), index=True, default=None)
    plan: Mapped[str] = mapped_column(String(30))
    amount: Mapped[float] = mapped_column(Numeric(10, 2))
    currency: Mapped[str] = mapped_column(String(10), default="INR")
    status: Mapped[str] = mapped_column(String(20), default="created", index=True)

    razorpay_order_id: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    razorpay_payment_id: Mapped[str | None] = mapped_column(String(80), default=None)
    razorpay_signature: Mapped[str | None] = mapped_column(String(255), default=None)
