"""Public API for the prompt_writer agent."""


def __getattr__(name: str):
    if name == "create_graph":
        from app.agents.prompt_generation.prompt_writer.graph import create_graph

        return create_graph
    raise AttributeError(name)


__all__ = [
    "create_graph",
]
