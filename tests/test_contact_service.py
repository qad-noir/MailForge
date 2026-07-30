import pytest

from app.services.contact_service import normalize_email


def test_normalize_email() -> None:
    assert normalize_email("  User@Example.COM ") == "user@example.com"


@pytest.mark.parametrize("value", ["", "missing-at.example.com", "@example.com"])
def test_invalid_email(value: str) -> None:
    with pytest.raises(ValueError):
        normalize_email(value)

