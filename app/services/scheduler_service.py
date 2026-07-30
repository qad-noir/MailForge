from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Campaign, CampaignRecipient, Contact, Suppression
from app.db.models.enums import CampaignStatus, ConsentStatus


class SchedulerService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def process_due(self) -> int:
        now = datetime.now(UTC)
        campaigns = list(
            (
                await self.session.scalars(
                    select(Campaign)
                    .where(
                        Campaign.status.in_(
                            [CampaignStatus.SCHEDULED.value, CampaignStatus.QUEUEING.value]
                        ),
                        Campaign.scheduled_at <= now,
                    )
                    .with_for_update(skip_locked=True)
                )
            ).all()
        )
        processed = 0
        for campaign in campaigns:
            campaign.status = CampaignStatus.QUEUEING.value
            await self.session.flush()
            contact_ids = (
                await self.session.stream_scalars(
                    select(Contact.id)
                    .outerjoin(
                        Suppression, Suppression.email_normalized == Contact.email_normalized
                    )
                    .where(
                        Contact.is_active.is_(True),
                        Contact.consent_status == ConsentStatus.OPTED_IN.value,
                        Suppression.id.is_(None),
                    )
                    .execution_options(yield_per=campaign.batch_size)
                )
            )
            batch: list[dict[str, object]] = []
            async for contact_id in contact_ids:
                batch.append(
                    {
                        "campaign_id": campaign.id,
                        "contact_id": contact_id,
                        "status": "queued",
                        "scheduled_at": campaign.scheduled_at or now,
                        "created_at": now,
                        "updated_at": now,
                    }
                )
                if len(batch) >= campaign.batch_size:
                    await self._insert_batch(batch)
                    batch = []
            if batch:
                await self._insert_batch(batch)
            campaign.status = CampaignStatus.QUEUED.value
            processed += 1
        await self.session.commit()
        return processed

    async def _insert_batch(self, rows: list[dict[str, object]]) -> None:
        await self.session.execute(
            insert(CampaignRecipient)
            .values(rows)
            .on_conflict_do_nothing(index_elements=["campaign_id", "contact_id"])
        )

