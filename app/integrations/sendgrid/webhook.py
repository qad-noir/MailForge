import hashlib
import json
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import CampaignRecipient, EmailEvent
from app.db.models.enums import RecipientStatus, SuppressionType
from app.services.contact_service import normalize_email
from app.services.suppression_service import SuppressionService

EVENT_STATUS = {
    "processed": RecipientStatus.ACCEPTED.value,
    "delivered": RecipientStatus.DELIVERED.value,
    "deferred": RecipientStatus.DEFERRED.value,
    "bounce": RecipientStatus.BOUNCED.value,
    "dropped": RecipientStatus.DROPPED.value,
    "unsubscribe": RecipientStatus.UNSUBSCRIBED.value,
    "group_unsubscribe": RecipientStatus.UNSUBSCRIBED.value,
    "spamreport": RecipientStatus.SPAM_REPORT.value,
}


class WebhookService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def process(self, events: list[dict[str, Any]]) -> int:
        inserted = 0
        for event in events:
            event_id = str(
                event.get("sg_event_id")
                or "fallback:"
                + hashlib.sha256(
                    json.dumps(event, sort_keys=True, separators=(",", ":")).encode()
                ).hexdigest()
            )
            email = normalize_email(str(event.get("email", "")))
            recipient_id = self._uuid(event.get("campaign_recipient_id"))
            campaign_id = self._uuid(event.get("campaign_id"))
            message_id = event.get("sg_message_id")
            if not recipient_id and message_id:
                recipient_id = await self.session.scalar(
                    select(CampaignRecipient.id).where(
                        CampaignRecipient.provider_message_id == message_id
                    )
                )
            result = await self.session.execute(
                insert(EmailEvent)
                .values(
                    provider_event_id=event_id,
                    provider_message_id=message_id,
                    campaign_id=campaign_id,
                    campaign_recipient_id=recipient_id,
                    event_type=str(event.get("event", "unknown")),
                    email_normalized=email,
                    timestamp=datetime.fromtimestamp(
                        int(event.get("timestamp", 0)), UTC
                    ),
                    raw_event=event,
                    created_at=datetime.now(UTC),
                )
                .on_conflict_do_nothing(index_elements=["provider_event_id"])
                .returning(EmailEvent.id)
            )
            if result.scalar_one_or_none() is None:
                continue
            inserted += 1
            event_type = str(event.get("event", ""))
            if recipient_id and event_type in EVENT_STATUS:
                recipient = await self.session.get(CampaignRecipient, recipient_id)
                if recipient:
                    recipient.status = EVENT_STATUS[event_type]
                    if event_type not in {"processed", "deferred"}:
                        recipient.completed_at = datetime.now(UTC)
            suppression_type = self._suppression_type(event)
            if suppression_type:
                await self.session.flush()
                await SuppressionService(self.session).suppress(
                    email, suppression_type, "sendgrid_webhook", provider_event_id=event_id
                )
        await self.session.commit()
        return inserted

    @staticmethod
    def _suppression_type(event: dict[str, Any]) -> SuppressionType | None:
        event_type = event.get("event")
        if event_type in {"unsubscribe", "group_unsubscribe"}:
            return SuppressionType.UNSUBSCRIBE
        if event_type == "spamreport":
            return SuppressionType.SPAM_REPORT
        if event_type == "bounce" and str(event.get("type", "")).lower() == "bounce":
            return SuppressionType.HARD_BOUNCE
        return None

    @staticmethod
    def _uuid(value: Any) -> uuid.UUID | None:
        try:
            return uuid.UUID(str(value)) if value else None
        except ValueError:
            return None

