import json
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from app.api.dependencies import SessionDep, SettingsDep
from app.integrations.sendgrid.signature import verify_signature
from app.integrations.sendgrid.webhook import WebhookService

router = APIRouter(prefix="/webhooks/sendgrid", tags=["webhooks"])


@router.post("/events", status_code=202)
async def events(
    request: Request, session: SessionDep, settings: SettingsDep
) -> dict[str, int]:
    body = await request.body()
    signature = request.headers.get("x-twilio-email-event-webhook-signature", "")
    timestamp = request.headers.get("x-twilio-email-event-webhook-timestamp", "")
    if settings.sendgrid_webhook_verification_key:
        if not verify_signature(
            settings.sendgrid_webhook_verification_key, body, signature, timestamp
        ):
            raise HTTPException(401, "Invalid webhook signature")
    elif settings.webhook_signature_required and settings.app_env == "production":
        raise HTTPException(503, "Webhook verification key is not configured")
    try:
        payload: Any = json.loads(body)
        if not isinstance(payload, list):
            raise ValueError("Expected an event array")
        inserted = await WebhookService(session).process(payload)
    except (json.JSONDecodeError, ValueError) as exc:
        raise HTTPException(422, str(exc)) from exc
    return {"accepted": len(payload), "inserted": inserted}

