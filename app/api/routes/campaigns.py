import uuid
from types import SimpleNamespace

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from app.api.dependencies import AdminDep, SessionDep
from app.db.models import Campaign
from app.schemas import CampaignCreate, CampaignRead, PreviewRequest, ScheduleRequest
from app.services.campaign_service import CampaignService
from app.services.report_service import ReportService
from app.services.template_service import TemplateService

router = APIRouter(prefix="/campaigns", tags=["campaigns"])


@router.post("", response_model=CampaignRead)
async def create_campaign(
    body: CampaignCreate, session: SessionDep, _: AdminDep
) -> Campaign:
    try:
        return await CampaignService(session).create(**body.model_dump(mode="json"))
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("", response_model=list[CampaignRead])
async def list_campaigns(session: SessionDep, _: AdminDep) -> list[Campaign]:
    return list((await session.scalars(select(Campaign).order_by(Campaign.created_at.desc()))).all())


@router.get("/{campaign_id}", response_model=CampaignRead)
async def get_campaign(
    campaign_id: uuid.UUID, session: SessionDep, _: AdminDep
) -> Campaign:
    try:
        return await CampaignService(session).get(campaign_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.post("/{campaign_id}/preview")
async def preview(
    campaign_id: uuid.UUID, body: PreviewRequest, session: SessionDep, _: AdminDep
) -> dict[str, str]:
    campaign = await CampaignService(session).get(campaign_id)
    contact = SimpleNamespace(
        email=str(body.recipient), first_name=body.first_name, last_name=body.last_name
    )
    rendered = TemplateService().render(
        subject=campaign.subject,
        html=campaign.html_template,
        text=campaign.text_template,
        contact=contact,
        campaign=campaign,
        unsubscribe_url="https://example.invalid/unsubscribe/preview",
    )
    return vars(rendered)


@router.post("/{campaign_id}/schedule", response_model=CampaignRead)
async def schedule(
    campaign_id: uuid.UUID, body: ScheduleRequest, session: SessionDep, _: AdminDep
) -> Campaign:
    try:
        return await CampaignService(session).schedule(campaign_id, body.start_at, "api")
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.post("/{campaign_id}/{action}", response_model=CampaignRead)
async def transition(
    campaign_id: uuid.UUID, action: str, session: SessionDep, _: AdminDep
) -> Campaign:
    if action not in {"pause", "resume", "cancel"}:
        raise HTTPException(404)
    try:
        return await CampaignService(session).transition(campaign_id, action, "api")
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.get("/{campaign_id}/report")
async def report(
    campaign_id: uuid.UUID, session: SessionDep, _: AdminDep
) -> dict[str, float | int]:
    return await ReportService(session).campaign_report(campaign_id)

