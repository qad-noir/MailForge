from dataclasses import dataclass
from typing import Any

from jinja2 import Environment, StrictUndefined, select_autoescape

REQUIRED_UNSUBSCRIBE_PLACEHOLDER = "{{ unsubscribe_url }}"


@dataclass(frozen=True)
class RenderedEmail:
    subject: str
    html: str
    text: str


class TemplateService:
    def __init__(self) -> None:
        self.html_environment = Environment(
            autoescape=select_autoescape(default=True), undefined=StrictUndefined
        )
        self.text_environment = Environment(autoescape=False, undefined=StrictUndefined)

    def validate_marketing_templates(self, html: str, text: str) -> None:
        if REQUIRED_UNSUBSCRIBE_PLACEHOLDER not in html:
            raise ValueError("HTML template must contain {{ unsubscribe_url }}")
        if REQUIRED_UNSUBSCRIBE_PLACEHOLDER not in text:
            raise ValueError("Text template must contain {{ unsubscribe_url }}")
        self.html_environment.parse(html)
        self.text_environment.parse(text)

    def render(
        self,
        *,
        subject: str,
        html: str,
        text: str,
        contact: Any,
        campaign: Any,
        unsubscribe_url: str,
    ) -> RenderedEmail:
        context = {
            "contact": contact,
            "campaign": campaign,
            "unsubscribe_url": unsubscribe_url,
        }
        return RenderedEmail(
            subject=self.text_environment.from_string(subject).render(context),
            html=self.html_environment.from_string(html).render(context),
            text=self.text_environment.from_string(text).render(context),
        )

