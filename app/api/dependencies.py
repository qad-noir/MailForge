from typing import Annotated

from fastapi import Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.security import verify_admin_token
from app.db.session import get_session

SessionDep = Annotated[AsyncSession, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]


async def require_admin(
    settings: SettingsDep, authorization: Annotated[str | None, Header()] = None
) -> None:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Bearer token required")
    if not verify_admin_token(authorization[7:], settings.admin_api_token):
        raise HTTPException(403, "Invalid bearer token")


AdminDep = Annotated[None, Depends(require_admin)]

