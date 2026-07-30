import pytest

from app.core.security import UnsubscribeTokenService


def test_unsubscribe_token_round_trip() -> None:
    service = UnsubscribeTokenService("test-secret")
    token = service.create("contact-id", "user@example.com")
    claims = service.verify(token)
    assert claims.contact_id == "contact-id"
    assert claims.email_normalized == "user@example.com"


def test_unsubscribe_token_rejects_tampering() -> None:
    service = UnsubscribeTokenService("test-secret")
    token = service.create("contact-id", "user@example.com")
    with pytest.raises(ValueError):
        service.verify(token + "tampered")
