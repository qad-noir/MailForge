import hmac
from dataclasses import dataclass
from hashlib import sha256

from itsdangerous import BadSignature, URLSafeSerializer


@dataclass(frozen=True)
class UnsubscribeClaims:
    contact_id: str
    email_normalized: str


class UnsubscribeTokenService:
    def __init__(self, secret: str) -> None:
        self.serializer = URLSafeSerializer(secret, salt="lead-sender-unsubscribe-v1")

    def create(self, contact_id: str, email_normalized: str) -> str:
        return self.serializer.dumps({"cid": contact_id, "email": email_normalized})

    def verify(self, token: str) -> UnsubscribeClaims:
        try:
            data = self.serializer.loads(token)
        except BadSignature as exc:
            raise ValueError("Invalid unsubscribe token") from exc
        if not isinstance(data, dict) or not data.get("cid") or not data.get("email"):
            raise ValueError("Invalid unsubscribe token payload")
        return UnsubscribeClaims(str(data["cid"]), str(data["email"]))


def verify_admin_token(provided: str, expected: str) -> bool:
    return hmac.compare_digest(provided, expected)


def deterministic_event_id(raw: bytes) -> str:
    return f"fallback:{sha256(raw).hexdigest()}"

