"""Public API for the prompt_danbooru_query agent."""


def __getattr__(name: str):
    if name == "create_graph":
        from app.agents.prompt_generation.danbooru_query.graph import create_graph

        return create_graph
    raise AttributeError(name)


__all__ = [
    "create_graph",
]
