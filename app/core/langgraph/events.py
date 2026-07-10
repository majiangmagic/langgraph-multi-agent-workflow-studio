"""Runtime event channel for streaming workflow progress."""

import asyncio
import contextvars
from typing import Any, Dict, Optional


WorkflowEvent = Dict[str, Any]

_current_event_sink: contextvars.ContextVar[Optional["WorkflowEventSink"]] = (
    contextvars.ContextVar("workflow_event_sink", default=None)
)


class WorkflowEventSink:
    """Per-run queue used to stream workflow progress without polluting state."""

    def __init__(self) -> None:
        self.queue: asyncio.Queue[WorkflowEvent] = asyncio.Queue()

    def emit(self, event: WorkflowEvent) -> None:
        """Emit an event from sync or async node code."""

        self.queue.put_nowait(event)

    def close(self) -> None:
        """Signal that no more progress events will be emitted."""

        self.emit({"type": "_workflow.event_stream.done"})


def set_event_sink(sink: WorkflowEventSink):
    """Bind an event sink to the current workflow run context."""

    return _current_event_sink.set(sink)


def reset_event_sink(token) -> None:
    """Restore the previous workflow event context."""

    _current_event_sink.reset(token)


def emit_event(event: WorkflowEvent) -> None:
    """Emit a progress event when the current run has a sink."""

    sink = _current_event_sink.get()
    if sink is not None:
        sink.emit(event)
