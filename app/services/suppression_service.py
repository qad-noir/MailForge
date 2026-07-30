from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import CampaignRecipient, Contact, Suppression
from app.db.models.enums import ConsentStatus, RecipientStatus, SuppressionType


class SuppressionService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def suppress(
        self,
        email_normalized: str,
        suppression_type: SuppressionType,
        source: str,
        reason: str | None = None,
        provider_event_id: str | None = None,
    ) -> None:
        statement = (
            insert(Suppression)
            .values(
                email_normalized=email_normalized,
                suppression_type=suppression_type.value,
                source=source,
                reason=reason,
                provider_event_id=provider_event_id,
                created_at=datetime.now(UTC),
            )
            .on_conflict_do_update(
                index_elements=[Suppression.email_normalized],
                set_={
                    "suppression_type": suppression_type.value,
                    "source": source,
                    "reason": reason,
                    "provider_event_id": provider_event_id,
                },
            )
        )
        await self.session.execute(statement)
        contact = await self.session.scalar(
            select(Contact).where(Contact.email_normalized == email_normalized)
        )
        if contact:
            contact.is_active = False
            if suppression_type == SuppressionType.UNSUBSCRIBE:
                contact.consent_status = ConsentStatus.UNSUBSCRIBED.value
            recipient_status = (
                RecipientStatus.UNSUBSCRIBED.value
                if suppression_type == SuppressionType.UNSUBSCRIBE
                else RecipientStatus.SUPPRESSED.value
            )
            await self.session.execute(
                update(CampaignRecipient)
                .where(
                    CampaignRecipient.contact_id == contact.id,
                    CampaignRecipient.status == RecipientStatus.QUEUED.value,
                )
                .values(status=recipient_status, completed_at=datetime.now(UTC))
            )
        await self.session.commit()
