import csv
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from io import TextIOBase
from typing import Any

from email_validator import EmailNotValidError, validate_email
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Contact, Suppression
from app.db.models.enums import ConsentStatus


def normalize_email(value: str) -> str:
    try:
        result = validate_email(value.strip(), check_deliverability=False)
    except EmailNotValidError as exc:
        raise ValueError(str(exc)) from exc
    return result.normalized.lower()


@dataclass
class ImportStats:
    imported: int = 0
    updated: int = 0
    duplicated: int = 0
    invalid: int = 0
    suppressed: int = 0
    missing_consent: int = 0


class ContactImportService:
    def __init__(self, session: AsyncSession, max_rows: int, max_metadata_bytes: int) -> None:
        self.session = session
        self.max_rows = max_rows
        self.max_metadata_bytes = max_metadata_bytes

    async def import_csv(
        self,
        stream: TextIOBase,
        *,
        email_column: str = "email",
        first_name_column: str = "first_name",
        last_name_column: str = "last_name",
        consent_column: str = "consent_status",
        consent_source_column: str = "consent_source",
        consent_date_column: str = "consent_date",
        dry_run: bool = False,
    ) -> ImportStats:
        stats = ImportStats()
        seen: set[str] = set()
        reader = csv.DictReader(stream)
        for row_number, row in enumerate(reader, start=1):
            if row_number > self.max_rows:
                raise ValueError(f"CSV row limit of {self.max_rows} exceeded")
            try:
                email = normalize_email(row.get(email_column, ""))
            except ValueError:
                stats.invalid += 1
                continue
            if email in seen:
                stats.duplicated += 1
                continue
            seen.add(email)
            if row.get(consent_column, "").strip().lower() != ConsentStatus.OPTED_IN.value:
                stats.missing_consent += 1
                continue
            if await self.session.scalar(
                select(Suppression.id).where(Suppression.email_normalized == email)
            ):
                stats.suppressed += 1
                continue
            contact = await self.session.scalar(
                select(Contact).where(Contact.email_normalized == email)
            )
            if contact and (
                contact.consent_status == ConsentStatus.UNSUBSCRIBED.value or not contact.is_active
            ):
                stats.suppressed += 1
                continue
            known = {
                email_column,
                first_name_column,
                last_name_column,
                consent_column,
                consent_source_column,
                consent_date_column,
            }
            metadata: dict[str, Any] = {k: v for k, v in row.items() if k not in known and v}
            if len(json.dumps(metadata).encode()) > self.max_metadata_bytes:
                stats.invalid += 1
                continue
            consent_date = self._parse_date(row.get(consent_date_column))
            if contact:
                contact.email = row.get(email_column, email).strip()
                contact.first_name = row.get(first_name_column) or contact.first_name
                contact.last_name = row.get(last_name_column) or contact.last_name
                contact.contact_metadata = metadata
                contact.consent_source = row.get(consent_source_column) or contact.consent_source
                contact.consent_date = consent_date or contact.consent_date
                contact.consent_status = ConsentStatus.OPTED_IN.value
                contact.is_active = True
                stats.updated += 1
            else:
                self.session.add(
                    Contact(
                        email=row.get(email_column, email).strip(),
                        email_normalized=email,
                        first_name=row.get(first_name_column) or None,
                        last_name=row.get(last_name_column) or None,
                        contact_metadata=metadata,
                        consent_status=ConsentStatus.OPTED_IN.value,
                        consent_source=row.get(consent_source_column) or None,
                        consent_date=consent_date,
                        is_active=True,
                    )
                )
                stats.imported += 1
            if row_number % 500 == 0:
                await self.session.flush()
        if dry_run:
            await self.session.rollback()
        else:
            await self.session.commit()
        return stats

    @staticmethod
    def _parse_date(value: str | None) -> datetime | None:
        if not value:
            return None
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)

