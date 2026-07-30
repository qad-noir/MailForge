from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SendGridResult:
    status_code: int
    headers: dict[str, str]
    provider_message_id: str | None


class SendGridError(Exception):
    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        retryable: bool = False,
        retry_after: float | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.retryable = retryable
        self.retry_after = retry_after
        self.headers = headers or {}


def safe_attempt_payload(payload: dict[str, Any]) -> dict[str, Any]:
    personalizations = payload.get("personalizations", [])
    recipients = sum(len(item.get("to", [])) for item in personalizations)
    return {
        "recipient_count": recipients,
        "from_domain": str(payload.get("from", {}).get("email", "")).partition("@")[2],
        "has_html": any(item.get("type") == "text/html" for item in payload.get("content", [])),
        "has_text": any(item.get("type") == "text/plain" for item in payload.get("content", [])),
        "custom_args": personalizations[0].get("custom_args", {}) if personalizations else {},
    }

