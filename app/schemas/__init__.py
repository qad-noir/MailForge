from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class CampaignCreate(BaseModel):
    name: str = Field(max_length=255)
    subject: str = Field(max_length=998)
    from_name: str = Field(max_length=255)
    from_email: EmailStr
    reply_to: EmailStr | None = None
    html_template: str
    text_template: str
    timezone: str = "UTC"
    sending_rate_per_hour: int = Field(gt=0, le=100_000)
    batch_size: int = Field(default=100, gt=0, le=10_000)


class CampaignRead(CampaignCreate):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    status: str
    scheduled_at: datetime | None


class ScheduleRequest(BaseModel):
    start_at: datetime


class PreviewRequest(BaseModel):
    recipient: EmailStr
    first_name: str = "Test"
    last_name: str = "Recipient"

