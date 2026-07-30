import uuid

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy import select

from app.api.dependencies import SessionDep, SettingsDep
from app.core.security import UnsubscribeTokenService
from app.db.models import Contact
from app.db.models.enums import SuppressionType
from app.services.suppression_service import SuppressionService

router = APIRouter(tags=["unsubscribe"])


async def perform_unsubscribe(
    token: str, session: SessionDep, settings: SettingsDep
) -> HTMLResponse:
    try:
        claims = UnsubscribeTokenService(settings.unsubscribe_signing_secret).verify(token)
        contact = await session.scalar(
            select(Contact).where(
                Contact.id == uuid.UUID(claims.contact_id),
                Contact.email_normalized == claims.email_normalized,
            )
        )
    except (ValueError, TypeError) as exc:
        raise HTTPException(400, "Invalid unsubscribe link") from exc
    if contact:
        await SuppressionService(session).suppress(
            contact.email_normalized, SuppressionType.UNSUBSCRIBE, "unsubscribe_link"
        )
    return HTMLResponse(
        "<!doctype html><title>Unsubscribed</title>"
        "<h1>You have been unsubscribed</h1><p>No further marketing email will be sent.</p>"
    )


@router.get("/unsubscribe/{token}", response_class=HTMLResponse)
async def unsubscribe_get(token: str, session: SessionDep, settings: SettingsDep) -> HTMLResponse:
    return await perform_unsubscribe(token, session, settings)


@router.post("/unsubscribe/{token}", response_class=HTMLResponse)
async def unsubscribe_post(token: str, session: SessionDep, settings: SettingsDep) -> HTMLResponse:
    return await perform_unsubscribe(token, session, settings)
