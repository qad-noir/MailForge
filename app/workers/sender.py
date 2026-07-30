import asyncio
import logging
import random
import signal
import socket
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import typer
from sqlalchemy import select

from app.core.config import get_settings
from app.core.security import UnsubscribeTokenService
from app.db.models import Campaign, CampaignRecipient, Contact, SendAttempt
from app.db.models.enums import CampaignStatus, RecipientStatus
from app.db.session import SessionFactory
from app.integrations.sendgrid.client import SendGridClient
from app.integrations.sendgrid.models import SendGridError, safe_attempt_payload
from app.services.queue_service import PostgresQueueBackend
from app.services.template_service import TemplateService

app = typer.Typer()
logger = logging.getLogger(__name__)


def calculate_backoff(attempt: int, base: float = 2, cap: float = 3600) -> float:
    return float(min(cap, base * (2 ** max(0, attempt - 1))) * random.uniform(0.5, 1.5))


class SenderWorker:
    def __init__(self, worker_id: str, batch_size: int, poll_interval: float) -> None:
        self.worker_id = worker_id
        self.batch_size = batch_size
        self.poll_interval = poll_interval
        self.settings = get_settings()
        self.stop_event = asyncio.Event()
        self.client = SendGridClient(self.settings.sendgrid_api_key)

    async def run(self) -> None:
        async with SessionFactory() as session:
            await PostgresQueueBackend(session).recover_stale(
                self.settings.worker_stale_timeout_seconds
            )
        while not self.stop_event.is_set():
            async with SessionFactory() as session:
                recipients = await PostgresQueueBackend(session).claim(
                    self.worker_id, self.batch_size
                )
            if not recipients:
                try:
                    await asyncio.wait_for(self.stop_event.wait(), self.poll_interval)
                except TimeoutError:
                    pass
                continue
            for recipient in recipients:
                if self.stop_event.is_set():
                    break
                await self.process(recipient.id)
        await self.client.close()

    async def process(self, recipient_id: uuid.UUID) -> None:
        async with SessionFactory() as session:
            recipient = await session.scalar(
                select(CampaignRecipient).where(CampaignRecipient.id == recipient_id).options()
            )
            if recipient is None:
                return
            campaign = await session.get(Campaign, recipient.campaign_id)
            contact = await session.get(Contact, recipient.contact_id)
            queue = PostgresQueueBackend(session)
            if (
                campaign is None
                or contact is None
                or campaign.status
                not in {CampaignStatus.QUEUED.value, CampaignStatus.SENDING.value}
                or not await queue.is_eligible(recipient)
            ):
                recipient.status = RecipientStatus.SUPPRESSED.value
                recipient.completed_at = datetime.now(UTC)
                await session.commit()
                return
            slot = await queue.acquire_rate_slot(campaign.id)
            delay = (slot - datetime.now(UTC)).total_seconds()
            if delay > 0:
                await asyncio.sleep(delay)
            token = UnsubscribeTokenService(self.settings.unsubscribe_signing_secret).create(
                str(contact.id), contact.email_normalized
            )
            unsubscribe_url = f"{self.settings.app_base_url}/unsubscribe/{token}"
            rendered = TemplateService().render(
                subject=campaign.subject,
                html=campaign.html_template,
                text=campaign.text_template,
                contact=contact,
                campaign=campaign,
                unsubscribe_url=unsubscribe_url,
            )
            payload = self._payload(campaign, contact, recipient, rendered, unsubscribe_url)
            recipient.attempt_count += 1
            attempt = SendAttempt(
                campaign_recipient_id=recipient.id,
                attempt_number=recipient.attempt_count,
                request_payload=safe_attempt_payload(payload),
                started_at=datetime.now(UTC),
            )
            session.add(attempt)
            await session.commit()
            try:
                result = await self.client.send(payload)
                recipient.status = RecipientStatus.ACCEPTED.value
                recipient.sent_at = datetime.now(UTC)
                recipient.provider_message_id = result.provider_message_id
                attempt.response_status = result.status_code
                attempt.response_headers = {
                    k: v
                    for k, v in result.headers.items()
                    if k.lower() in {"x-message-id", "retry-after", "date"}
                }
                attempt.provider_message_id = result.provider_message_id
                attempt.retryable = False
            except SendGridError as exc:
                await self._handle_error(recipient, attempt, exc)
            attempt.completed_at = datetime.now(UTC)
            await session.commit()

    async def _handle_error(
        self, recipient: CampaignRecipient, attempt: SendAttempt, exc: SendGridError
    ) -> None:
        attempt.response_status = exc.status_code
        attempt.error_type = type(exc).__name__
        attempt.error_message = str(exc)[:2000]
        attempt.retryable = exc.retryable
        recipient.last_error = str(exc)[:2000]
        if exc.retryable and recipient.attempt_count < self.settings.max_send_attempts:
            delay = exc.retry_after or calculate_backoff(recipient.attempt_count)
            recipient.status = RecipientStatus.DEFERRED.value
            recipient.next_attempt_at = datetime.now(UTC) + timedelta(seconds=delay)
        else:
            recipient.status = RecipientStatus.FAILED.value
            recipient.completed_at = datetime.now(UTC)

    @staticmethod
    def _payload(
        campaign: Campaign,
        contact: Contact,
        recipient: CampaignRecipient,
        rendered: Any,
        unsubscribe_url: str,
    ) -> dict[str, Any]:
        return {
            "personalizations": [
                {
                    "to": [{"email": contact.email}],
                    "custom_args": {
                        "campaign_id": str(campaign.id),
                        "campaign_recipient_id": str(recipient.id),
                    },
                    "headers": {
                        "List-Unsubscribe": f"<{unsubscribe_url}>",
                        "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
                    },
                }
            ],
            "from": {"email": campaign.from_email, "name": campaign.from_name},
            "reply_to": {"email": campaign.reply_to} if campaign.reply_to else None,
            "subject": rendered.subject,
            "content": [
                {"type": "text/plain", "value": rendered.text},
                {"type": "text/html", "value": rendered.html},
            ],
        }


async def run(worker_id: str, batch_size: int, poll_interval: float) -> None:
    worker = SenderWorker(worker_id, batch_size, poll_interval)
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, worker.stop_event.set)
        except NotImplementedError:
            signal.signal(sig, lambda *_: worker.stop_event.set())
    await worker.run()


@app.command()
def main(
    worker_id: str = typer.Option(f"{socket.gethostname()}-{uuid.uuid4().hex[:8]}", "--worker-id"),
    batch_size: int = typer.Option(100, "--batch-size", min=1),
    poll_interval: float = typer.Option(2, "--poll-interval", min=0.1),
) -> None:
    asyncio.run(run(worker_id, batch_size, poll_interval))


if __name__ == "__main__":
    app()
