"""Public API for the prompt_impact_router agent."""


def __getattr__(name: str):
    if name == "create_graph":
        from app.agents.prompt_generation.prompt_impact_router.graph import create_graph

        return create_graph
    raise AttributeError(name)


__all__ = [
    "create_graph",
]
