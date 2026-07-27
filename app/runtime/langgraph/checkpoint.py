"""Shared LangGraph checkpoint management."""

import logging
from typing import Optional

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from app.config import settings

logger = logging.getLogger(__name__)

_checkpointer_cm = None
_checkpointer: Optional[AsyncPostgresSaver] = None


async def init_checkpointer() -> Optional[AsyncPostgresSaver]:
    """Initialize the global Postgres checkpointer once per process."""

    global _checkpointer_cm, _checkpointer
    if _checkpointer is not None:
        return _checkpointer

    try:
        _checkpointer_cm = AsyncPostgresSaver.from_conn_string(
            str(settings.database_url)
        )
        _checkpointer = await _checkpointer_cm.__aenter__()
        await _checkpointer.setup()
        return _checkpointer
    except Exception as exc:
        logger.warning("LangGraph checkpointer disabled: %s", exc)
        _checkpointer_cm = None
        _checkpointer = None
        return None


async def close_checkpointer() -> None:
    """Close the global checkpointer if it was opened."""

    global _checkpointer_cm, _checkpointer
    if _checkpointer_cm is None:
        return

    await _checkpointer_cm.__aexit__(None, None, None)
    _checkpointer_cm = None
    _checkpointer = None


def get_checkpointer() -> Optional[AsyncPostgresSaver]:
    """Return the active checkpointer, if initialization already happened."""

    return _checkpointer
