"""Shared LangGraph long-term store management."""

import logging
from typing import Optional

from langgraph.store.postgres import PostgresStore

from app.core.config import settings

logger = logging.getLogger(__name__)

_store_cm = None
_store: Optional[PostgresStore] = None


async def init_store() -> Optional[PostgresStore]:
    """Initialize the global Postgres store once per process."""

    global _store_cm, _store
    if _store is not None:
        return _store

    try:
        _store_cm = PostgresStore.from_conn_string(str(settings.database_url))
        _store = _store_cm.__enter__()
        _store.setup()
        return _store
    except Exception as exc:
        logger.warning("LangGraph store disabled: %s", exc)
        _store_cm = None
        _store = None
        return None


async def close_store() -> None:
    """Close the global store if it was opened."""

    global _store_cm, _store
    if _store_cm is None:
        return

    _store_cm.__exit__(None, None, None)
    _store_cm = None
    _store = None


def get_store() -> Optional[PostgresStore]:
    """Return the active long-term store, if initialization already happened."""

    return _store
