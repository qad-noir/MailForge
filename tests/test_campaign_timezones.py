from datetime import UTC, datetime
from zoneinfo import ZoneInfo


def test_lagos_schedule_converts_to_utc() -> None:
    local = datetime(2026, 8, 1, 9, 0, tzinfo=ZoneInfo("Africa/Lagos"))
    assert local.astimezone(UTC) == datetime(2026, 8, 1, 8, 0, tzinfo=UTC)
