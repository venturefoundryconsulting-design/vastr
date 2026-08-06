from pydantic import BaseModel


class AppSettingsOut(BaseModel):
    business_name: str | None = None
    business_address: str | None = None
    business_gstin: str | None = None
    business_phone: str | None = None
    business_email: str | None = None
    invoice_footer_text: str | None = None
    show_hsn_on_documents: bool = False
    logo_url: str | None = None

    whatsapp_phone_number_id: str | None = None
    whatsapp_api_version: str | None = None
    whatsapp_token_set: bool = False


class AppSettingsUpdate(BaseModel):
    """All fields optional. Secret fields (tokens/passwords) are left unchanged
    when omitted or blank - send a non-empty string to set/replace them."""

    business_name: str | None = None
    business_address: str | None = None
    business_gstin: str | None = None
    business_phone: str | None = None
    business_email: str | None = None
    invoice_footer_text: str | None = None
    show_hsn_on_documents: bool | None = None

    whatsapp_cloud_api_token: str | None = None
    whatsapp_phone_number_id: str | None = None
    whatsapp_api_version: str | None = None


class TestSendResult(BaseModel):
    ok: bool
    detail: str


class PublicBrandingOut(BaseModel):
    """Unauthenticated subset of settings the login page needs before a user has a token."""

    business_name: str | None = None
    logo_url: str | None = None
