"""Tests for bounded persistent activity logging."""

import pytest
from sqlalchemy import select

from app.core.config import settings
from app.models.activity_log import ActivityLog, ActivityType
from app.services.conversation_service import ActivityLogService


@pytest.mark.asyncio
async def test_activity_logs_keep_only_newest_configured_rows(
    db_session,
    monkeypatch,
):
    monkeypatch.setattr(settings, "activity_log_max_rows", 3)

    for index in range(5):
        await ActivityLogService.log_activity(
            db=db_session,
            activity_type=ActivityType.CUSTOM,
            description=f"log-{index}",
        )

    logs = list(
        (
            await db_session.execute(
                select(ActivityLog).order_by(ActivityLog.created_at)
            )
        ).scalars()
    )

    assert len(logs) == 3
    assert {log.description for log in logs} == {"log-2", "log-3", "log-4"}
