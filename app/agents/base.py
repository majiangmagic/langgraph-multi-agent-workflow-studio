"""Base protocol for executable agents."""

from typing import Any, Dict, Protocol


class AgentRunner(Protocol):
    """Interface implemented by concrete agent runners."""

    async def run(self, task: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """Run an agent task and return structured results."""
