import uuid
from abc import ABC, abstractmethod
from datetime import UTC, datetime, timedelta
from typing import cast

from sqlalchemy import or_, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Campaign, CampaignRecipient, Contact, Suppression
from app.db.models.enums import CampaignStatus, ConsentStatus, RecipientStatus


class QueueBackend(ABC):
    @abstractmethod
    async def claim(self, worker_id: str, batch_size: int) -> list[CampaignRecipient]: ...


class PostgresQueueBackend(QueueBackend):
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def claim(self, worker_id: str, batch_size: int) -> list[CampaignRecipient]:
        now = datetime.now(UTC)
        statement = (
            select(CampaignRecipient)
            .join(Campaign)
            .where(
                CampaignRecipient.status.in_(
                    [RecipientStatus.QUEUED.value, RecipientStatus.DEFERRED.value]
                ),
                or_(
                    CampaignRecipient.next_attempt_at.is_(None),
                    CampaignRecipient.next_attempt_at <= now,
                ),
                Campaign.status.in_([CampaignStatus.QUEUED.value, CampaignStatus.SENDING.value]),
            )
            .order_by(CampaignRecipient.next_attempt_at, CampaignRecipient.created_at)
            .limit(batch_size)
            .with_for_update(skip_locked=True, of=CampaignRecipient)
        )
        recipients = list((await self.session.scalars(statement)).all())
        for recipient in recipients:
            recipient.status = RecipientStatus.PROCESSING.value
            recipient.claimed_at = now
            recipient.processing_started_at = now
            recipient.claimed_by = worker_id
        await self.session.commit()
        return recipients

    async def recover_stale(self, timeout_seconds: int) -> int:
        result = cast(
            CursorResult[tuple[()]],
            await self.session.execute(
                update(CampaignRecipient)
                .where(
                    CampaignRecipient.status == RecipientStatus.PROCESSING.value,
                    CampaignRecipient.processing_started_at
                    < datetime.now(UTC) - timedelta(seconds=timeout_seconds),
                )
                .values(
                    status=RecipientStatus.QUEUED.value,
                    claimed_at=None,
                    claimed_by=None,
                    processing_started_at=None,
                )
            ),
        )
        await self.session.commit()
        return result.rowcount

    async def acquire_rate_slot(self, campaign_id: uuid.UUID) -> datetime:
        campaign = await self.session.scalar(
            select(Campaign).where(Campaign.id == campaign_id).with_for_update()
        )
        if campaign is None:
            raise ValueError("Campaign not found")
        now = datetime.now(UTC)
        slot = max(now, campaign.next_send_at or now)
        interval = timedelta(seconds=3600 / campaign.sending_rate_per_hour)
        campaign.next_send_at = slot + interval
        await self.session.commit()
        return slot

    async def is_eligible(self, recipient: CampaignRecipient) -> bool:
        return bool(
            await self.session.scalar(
                select(Contact.id)
                .outerjoin(Suppression, Suppression.email_normalized == Contact.email_normalized)
                .where(
                    Contact.id == recipient.contact_id,
                    Contact.is_active.is_(True),
                    Contact.consent_status == ConsentStatus.OPTED_IN.value,
                    Suppression.id.is_(None),
                )
            )
        )
