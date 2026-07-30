import asyncio
import json
import uuid
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import typer
from rich.console import Console
from rich.table import Table

from app.core.config import get_settings
from app.db.session import SessionFactory
from app.integrations.sendgrid.client import SendGridClient
from app.schemas import CampaignCreate
from app.services.campaign_service import CampaignService
from app.services.contact_service import ContactImportService
from app.services.report_service import ReportService
from app.services.template_service import TemplateService

app = typer.Typer(help="Permission-based bulk email campaign service.")
contacts_app = typer.Typer()
campaign_app = typer.Typer()
app.add_typer(contacts_app, name="contacts")
app.add_typer(campaign_app, name="campaign")
console = Console()


@contacts_app.command("import")
def import_contacts(
    csv_file: Path,
    email_column: str = "email",
    first_name_column: str = "first_name",
    last_name_column: str = "last_name",
    consent_column: str = "consent_status",
    consent_source_column: str = "consent_source",
    consent_date_column: str = "consent_date",
    dry_run: bool = False,
) -> None:
    async def command() -> None:
        settings = get_settings()
        if csv_file.stat().st_size > settings.max_csv_bytes:
            raise typer.BadParameter("CSV file exceeds configured size limit")
        async with SessionFactory() as session:
            with csv_file.open(encoding="utf-8-sig", newline="") as stream:
                stats = await ContactImportService(
                    session, settings.max_csv_rows, settings.max_metadata_bytes
                ).import_csv(
                    stream,
                    email_column=email_column,
                    first_name_column=first_name_column,
                    last_name_column=last_name_column,
                    consent_column=consent_column,
                    consent_source_column=consent_source_column,
                    consent_date_column=consent_date_column,
                    dry_run=dry_run,
                )
                console.print_json(json.dumps(vars(stats)))

    asyncio.run(command())


@campaign_app.command("create")
def create_campaign(
    name: str,
    subject: str,
    html_template: Path,
    text_template: Path,
    from_name: str,
    from_email: str,
    timezone: str = "UTC",
    rate: int = 1000,
    batch_size: int = 100,
    reply_to: str | None = None,
) -> None:
    async def command() -> None:
        body = CampaignCreate(
            name=name,
            subject=subject,
            html_template=html_template.read_text(encoding="utf-8"),
            text_template=text_template.read_text(encoding="utf-8"),
            from_name=from_name,
            from_email=from_email,
            reply_to=reply_to,
            timezone=timezone,
            sending_rate_per_hour=rate,
            batch_size=batch_size,
        )
        async with SessionFactory() as session:
            campaign = await CampaignService(session).create(**body.model_dump(mode="json"))
            console.print(f"Created campaign [bold]{campaign.id}[/bold]")

    asyncio.run(command())


@campaign_app.command("preview")
def preview(campaign_id: uuid.UUID, recipient: str) -> None:
    async def command() -> None:
        async with SessionFactory() as session:
            campaign = await CampaignService(session).get(campaign_id)
            rendered = TemplateService().render(
                subject=campaign.subject,
                html=campaign.html_template,
                text=campaign.text_template,
                contact=SimpleNamespace(email=recipient, first_name="Test", last_name="Recipient"),
                campaign=campaign,
                unsubscribe_url="https://example.invalid/unsubscribe/preview",
            )
            console.print(rendered.text)

    asyncio.run(command())


@campaign_app.command("test-send")
def test_send(campaign_id: uuid.UUID, recipient: str) -> None:
    async def command() -> None:
        settings = get_settings()
        async with SessionFactory() as session:
            campaign = await CampaignService(session).get(campaign_id)
            rendered = TemplateService().render(
                subject=campaign.subject,
                html=campaign.html_template,
                text=campaign.text_template,
                contact=SimpleNamespace(email=recipient, first_name="Test", last_name="Recipient"),
                campaign=campaign,
                unsubscribe_url="https://example.invalid/unsubscribe/test",
            )
            payload = {
                "personalizations": [{"to": [{"email": recipient}]}],
                "from": {"email": campaign.from_email, "name": campaign.from_name},
                "subject": f"[TEST] {rendered.subject}",
                "content": [
                    {"type": "text/plain", "value": rendered.text},
                    {"type": "text/html", "value": rendered.html},
                ],
            }
            client = SendGridClient(settings.sendgrid_api_key)
            try:
                result = await client.send(payload)
                console.print(f"Accepted test message: {result.provider_message_id or 'no ID'}")
            finally:
                await client.close()

    asyncio.run(command())


@campaign_app.command("schedule")
def schedule(campaign_id: uuid.UUID, start_at: str) -> None:
    async def command() -> None:
        async with SessionFactory() as session:
            campaign = await CampaignService(session).schedule(
                campaign_id, datetime.fromisoformat(start_at), "cli"
            )
            console.print(f"Scheduled for UTC: {campaign.scheduled_at}")

    asyncio.run(command())


def _transition_command(campaign_id: uuid.UUID, action: str) -> None:
    async def command() -> None:
        async with SessionFactory() as session:
            campaign = await CampaignService(session).transition(campaign_id, action, "cli")
            console.print(f"Campaign status: {campaign.status}")

    asyncio.run(command())


@campaign_app.command("pause")
def pause(campaign_id: uuid.UUID) -> None:
    _transition_command(campaign_id, "pause")


@campaign_app.command("resume")
def resume(campaign_id: uuid.UUID) -> None:
    _transition_command(campaign_id, "resume")


@campaign_app.command("cancel")
def cancel(campaign_id: uuid.UUID) -> None:
    _transition_command(campaign_id, "cancel")


@campaign_app.command("status")
def status(campaign_id: uuid.UUID) -> None:
    async def command() -> None:
        async with SessionFactory() as session:
            campaign = await CampaignService(session).get(campaign_id)
            console.print_json(
                json.dumps(
                    {
                        "id": str(campaign.id),
                        "name": campaign.name,
                        "status": campaign.status,
                        "scheduled_at": str(campaign.scheduled_at),
                    }
                )
            )

    asyncio.run(command())


@campaign_app.command("report")
def report(campaign_id: uuid.UUID, export: Path | None = None) -> None:
    async def command() -> None:
        async with SessionFactory() as session:
            data = await ReportService(session).campaign_report(campaign_id)
            if export:
                with export.open("w", encoding="utf-8", newline="") as stream:
                    ReportService.export_csv(data, stream)
                console.print(f"Exported {export}")
                return
            table = Table("Metric", "Value")
            for key, value in data.items():
                table.add_row(key, str(value))
            console.print(table)

    asyncio.run(command())


if __name__ == "__main__":
    app()
