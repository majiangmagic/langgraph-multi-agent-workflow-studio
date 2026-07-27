"""Shared LangGraph exceptions."""


class WorkflowNotFoundError(ValueError):
    """Raised when a requested workflow is not registered."""
