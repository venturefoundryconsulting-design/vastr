from pydantic import BaseModel

from app.models.whatsapp import WhatsAppMessageStatus


class WhatsAppSendResult(BaseModel):
    whatsapp_link: str
    status: WhatsAppMessageStatus
    message_id: int
    provider_message_id: str | None = None
    note: str
