"""Sends scheduled campaigns once they come due.

There's no task queue (Celery/RQ) or cron in this deployment - the whole app is a single
FastAPI process, so a simple in-process asyncio poller is the right fit: it only works
while the backend process is running, which matches how this app is actually run. If this
ever moves to multiple worker processes, campaigns could be sent more than once (this
poller doesn't claim a distributed lock) - not a concern for the current single-process setup.
"""

import asyncio
import logging
from datetime import datetime, timezone

from app.core.database import SessionLocal
from app.core.tenant_context import tenant_scope
from app.models.campaign import Campaign, CampaignStatus
from app.models.whatsapp import WhatsAppMessageStatus
from app.services.app_settings import get_app_settings
from app.services.campaigns import resolve_segment, send_campaign
from app.services.whatsapp import is_cloud_api_configured
from app.schemas.campaign import SegmentParams

logger = logging.getLogger(__name__)

POLL_INTERVAL_SECONDS = 60


def send_due_campaigns() -> int:
    """Sends every scheduled campaign whose time has come. Returns how many were sent."""
    db = SessionLocal()
    sent = 0
    try:
        # This poller serves every tenant, so the lookup itself runs unscoped
        # (no tenant context set) - each campaign is then processed inside its
        # own tenant_scope so segment resolution / recipient creation /
        # app_settings all resolve to the right tenant, never another's.
        due = (
            db.query(Campaign)
            .filter(Campaign.status == CampaignStatus.SCHEDULED, Campaign.scheduled_at <= datetime.now(timezone.utc))
            .all()
        )
        for campaign in due:
            try:
                with tenant_scope(campaign.tenant_id):
                    segment_params = SegmentParams(
                        segment_type=campaign.segment_type,
                        segment_tag=campaign.segment_tag,
                        segment_category_id=campaign.segment_category_id,
                        segment_brand=campaign.segment_brand,
                        segment_days=campaign.segment_days,
                    )
                    customers = resolve_segment(db, segment_params)
                    app_settings = get_app_settings(db)
                    recipients = send_campaign(db, campaign, customers, app_settings)
                    campaign.recipient_count = len(recipients)
                    campaign.sent_count = sum(1 for r in recipients if r.status == WhatsAppMessageStatus.SENT)
                    campaign.status = (
                        CampaignStatus.FAILED
                        if recipients and campaign.sent_count == 0 and is_cloud_api_configured(app_settings)
                        else CampaignStatus.SENT
                    )
                    db.commit()
                    sent += 1
            except Exception:
                logger.exception("Failed to send scheduled campaign %s", campaign.id)
                db.rollback()
    finally:
        db.close()
    return sent


async def campaign_scheduler_loop() -> None:
    while True:
        try:
            await asyncio.to_thread(send_due_campaigns)
        except Exception:
            logger.exception("Campaign scheduler poll failed")
        await asyncio.sleep(POLL_INTERVAL_SECONDS)
