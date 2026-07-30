import uuid
from datetime import UTC, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import utc_now
from app.db.models import AuditLog, Campaign, CampaignRecipient
from app.db.models.enums import CampaignStatus, RecipientStatus
from app.services.template_service import TemplateService


class CampaignService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, **values: object) -> Campaign:
        TemplateService().validate_marketing_templates(
            str(values["html_template"]), str(values["text_template"])
        )
        campaign = Campaign(**values)
        self.session.add(campaign)
        await self.session.commit()
        await self.session.refresh(campaign)
        return campaign

    async def get(self, campaign_id: uuid.UUID, *, lock: bool = False) -> Campaign:
        statement = select(Campaign).where(Campaign.id == campaign_id)
        if lock:
            statement = statement.with_for_update()
        campaign = await self.session.scalar(statement)
        if campaign is None:
            raise ValueError("Campaign not found")
        return campaign

    async def schedule(self, campaign_id: uuid.UUID, local_time: datetime, actor: str) -> Campaign:
        campaign = await self.get(campaign_id, lock=True)
        if campaign.status not in {CampaignStatus.DRAFT.value, CampaignStatus.PAUSED.value}:
            raise ValueError(f"Cannot schedule campaign in {campaign.status} state")
        TemplateService().validate_marketing_templates(
            campaign.html_template, campaign.text_template
        )
        try:
            zone = ZoneInfo(campaign.timezone)
        except ZoneInfoNotFoundError as exc:
            raise ValueError(f"Unknown IANA timezone: {campaign.timezone}") from exc
        aware = local_time.replace(tzinfo=zone) if local_time.tzinfo is None else local_time
        previous = campaign.status
        campaign.scheduled_at = aware.astimezone(UTC)
        campaign.status = CampaignStatus.SCHEDULED.value
        self._audit(campaign.id, "schedule", previous, campaign.status, actor)
        await self.session.commit()
        return campaign

    async def transition(self, campaign_id: uuid.UUID, action: str, actor: str) -> Campaign:
        campaign = await self.get(campaign_id, lock=True)
        previous = campaign.status
        if action == "pause" and previous in {
            CampaignStatus.QUEUED.value,
            CampaignStatus.SENDING.value,
        }:
            campaign.status = CampaignStatus.PAUSED.value
            campaign.paused_at = utc_now()
        elif action == "resume" and previous == CampaignStatus.PAUSED.value:
            campaign.status = CampaignStatus.QUEUED.value
            campaign.paused_at = None
        elif action == "cancel" and previous not in {
            CampaignStatus.COMPLETED.value,
            CampaignStatus.CANCELLED.value,
        }:
            campaign.status = CampaignStatus.CANCELLED.value
            await self.session.execute(
                update(CampaignRecipient)
                .where(
                    CampaignRecipient.campaign_id == campaign.id,
                    CampaignRecipient.status == RecipientStatus.QUEUED.value,
                )
                .values(status=RecipientStatus.CANCELLED.value, completed_at=utc_now())
            )
        else:
            raise ValueError(f"Cannot {action} campaign in {previous} state")
        self._audit(campaign.id, action, previous, campaign.status, actor)
        await self.session.commit()
        return campaign

    def _audit(
        self, campaign_id: uuid.UUID, action: str, previous: str, new: str, actor: str
    ) -> None:
        self.session.add(
            AuditLog(
                campaign_id=campaign_id,
                action=action,
                previous_status=previous,
                new_status=new,
                actor=actor,
                created_at=datetime.now(UTC),
            )
        )

