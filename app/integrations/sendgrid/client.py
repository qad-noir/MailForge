import email.utils
from datetime import UTC, datetime
from typing import Any

import httpx

from app.integrations.sendgrid.models import SendGridError, SendGridResult

RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


def classify_retryable(status_code: int | None, network_error: bool = False) -> bool:
    return network_error or status_code in RETRYABLE_STATUS_CODES


def parse_retry_after(value: str | None, now: datetime | None = None) -> float | None:
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        try:
            parsed = email.utils.parsedate_to_datetime(value)
            return max(0.0, (parsed - (now or datetime.now(UTC))).total_seconds())
        except (TypeError, ValueError):
            return None


class SendGridClient:
    def __init__(self, api_key: str, client: httpx.AsyncClient | None = None) -> None:
        self.api_key = api_key
        self.client = client or httpx.AsyncClient(
            base_url="https://api.sendgrid.com", timeout=httpx.Timeout(20)
        )
        self._owns_client = client is None

    async def send(self, payload: dict[str, Any]) -> SendGridResult:
        try:
            response = await self.client.post(
                "/v3/mail/send",
                json=payload,
                headers={"Authorization": f"Bearer {self.api_key}"},
            )
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            raise SendGridError(str(exc), retryable=True) from exc
        headers = dict(response.headers)
        if response.status_code >= 400:
            message = response.text[:1000]
            raise SendGridError(
                message,
                status_code=response.status_code,
                retryable=classify_retryable(response.status_code),
                retry_after=parse_retry_after(response.headers.get("retry-after")),
                headers=headers,
            )
        return SendGridResult(
            status_code=response.status_code,
            headers=headers,
            provider_message_id=response.headers.get("x-message-id"),
        )

    async def close(self) -> None:
        if self._owns_client:
            await self.client.aclose()
