"""A single call site for "send this tenant a notification on channel X",
routing to whichever already-tenant-scoped provider backs that channel
(app.services.email / app.services.sms / app.services.whatsapp - all built
in earlier phases, nothing about how they send is duplicated here).

Nothing currently calls this - existing features (receipt sharing, campaign
sends) still call their own service module directly, unchanged. This exists
so a future notification trigger (e.g. "email the tenant owner when a
subscription is about to expire") has one obvious place to plug into rather
than reaching into service internals or duplicating provider-selection logic.
"""

from sqlalchemy.orm import Session

from app.notifications.channel import NotificationChannel
from app.services import email as email_service
from app.services import sms as sms_service
from app.services import whatsapp as whatsapp_service
from app.services.app_settings import get_app_settings


class NotificationNotConfigured(Exception):
    pass


def send_notification(
    db: Session,
    channel: NotificationChannel,
    *,
    to: str,
    body: str,
    subject: str | None = None,
) -> None:
    if channel == NotificationChannel.EMAIL:
        try:
            email_service.send_email(db, to, subject or "Notification", body)
        except email_service.EmailNotConfigured as exc:
            raise NotificationNotConfigured(str(exc)) from exc
    elif channel == NotificationChannel.SMS:
        try:
            sms_service.send_sms(db, to, body)
        except sms_service.SmsNotConfigured as exc:
            raise NotificationNotConfigured(str(exc)) from exc
    elif channel == NotificationChannel.WHATSAPP:
        app_settings = get_app_settings(db)
        if not whatsapp_service.is_cloud_api_configured(app_settings):
            raise NotificationNotConfigured("WhatsApp Cloud API is not configured for this tenant")
        whatsapp_service.send_via_cloud_api(app_settings, to, body)
    elif channel == NotificationChannel.PUSH:
        # No push provider exists yet (see features.md) - this is the
        # intended plug-in point once one is added, not a bug.
        raise NotImplementedError("Push notifications aren't available yet")
    else:
        raise ValueError(f"Unknown notification channel: {channel}")
