import csv
import uuid
from collections.abc import Iterable
from io import TextIOBase

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import CampaignRecipient
from app.db.models.enums import RecipientStatus


def safe_csv_cell(value: object) -> str:
    text = str(value)
    return f"'{text}" if text.startswith(("=", "+", "-", "@")) else text


class ReportService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def campaign_report(self, campaign_id: uuid.UUID) -> dict[str, float | int]:
        rows = (
            await self.session.execute(
                select(CampaignRecipient.status, func.count())
                .where(CampaignRecipient.campaign_id == campaign_id)
                .group_by(CampaignRecipient.status)
            )
        ).all()
        counts = {status: count for status, count in rows}
        total = sum(counts.values())
        result: dict[str, float | int] = {"total_selected": total}
        for status in RecipientStatus:
            result[status.value] = counts.get(status.value, 0)
        result["pending"] = counts.get("queued", 0) + counts.get("deferred", 0)
        denominator = max(total, 1)
        result["delivery_percentage"] = round(counts.get("delivered", 0) * 100 / denominator, 2)
        result["bounce_percentage"] = round(counts.get("bounced", 0) * 100 / denominator, 2)
        result["complaint_percentage"] = round(
            counts.get("spam_report", 0) * 100 / denominator, 2
        )
        return result

    @staticmethod
    def export_csv(report: dict[str, float | int], stream: TextIOBase) -> None:
        writer = csv.writer(stream)
        writer.writerow(["metric", "value"])
        writer.writerows((safe_csv_cell(k), safe_csv_cell(v)) for k, v in report.items())
