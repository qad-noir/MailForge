import io

from fastapi import APIRouter, File, HTTPException, UploadFile
from sqlalchemy import select

from app.api.dependencies import AdminDep, SessionDep, SettingsDep
from app.db.models import Contact
from app.services.contact_service import ContactImportService

router = APIRouter(prefix="/contacts", tags=["contacts"])


@router.post("/import", dependencies=[])
async def import_contacts(
    session: SessionDep,
    settings: SettingsDep,
    _: AdminDep,
    file: UploadFile = File(...),
    dry_run: bool = False,
) -> dict[str, int]:
    data = await file.read(settings.max_csv_bytes + 1)
    if len(data) > settings.max_csv_bytes:
        raise HTTPException(413, "CSV file too large")
    try:
        stream = io.StringIO(data.decode("utf-8-sig"))
        stats = await ContactImportService(
            session, settings.max_csv_rows, settings.max_metadata_bytes
        ).import_csv(stream, dry_run=dry_run)
    except (UnicodeDecodeError, ValueError) as exc:
        raise HTTPException(422, str(exc)) from exc
    return vars(stats)


@router.get("")
async def list_contacts(
    session: SessionDep, _: AdminDep, limit: int = 100, offset: int = 0
) -> list[dict[str, object]]:
    contacts = (
        await session.scalars(
            select(Contact).order_by(Contact.created_at.desc()).limit(min(limit, 1000)).offset(offset)
        )
    ).all()
    return [
        {
            "id": contact.id,
            "email": contact.email,
            "first_name": contact.first_name,
            "last_name": contact.last_name,
            "consent_status": contact.consent_status,
            "is_active": contact.is_active,
        }
        for contact in contacts
    ]

