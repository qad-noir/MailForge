from types import SimpleNamespace

import pytest

from app.services.template_service import TemplateService


def test_campaign_requires_unsubscribe_in_both_parts() -> None:
    with pytest.raises(ValueError, match="HTML"):
        TemplateService().validate_marketing_templates("<p>Hello</p>", "{{ unsubscribe_url }}")
    with pytest.raises(ValueError, match="Text"):
        TemplateService().validate_marketing_templates(
            "<a href='{{ unsubscribe_url }}'>Unsubscribe</a>", "Hello"
        )


def test_html_rendering_escapes_contact_data() -> None:
    service = TemplateService()
    rendered = service.render(
        subject="Hello {{ contact.first_name }}",
        html="<p>{{ contact.first_name }}</p><a href='{{ unsubscribe_url }}'>Leave</a>",
        text="Hello {{ contact.first_name }} {{ unsubscribe_url }}",
        contact=SimpleNamespace(first_name="<script>", last_name="", email="a@example.com"),
        campaign=SimpleNamespace(name="News"),
        unsubscribe_url="https://example.com/u/token",
    )
    assert "&lt;script&gt;" in rendered.html
    assert "<script>" in rendered.text
