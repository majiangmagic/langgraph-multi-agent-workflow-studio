"""Tests for declarative workflow condition routing."""

from app.runtime.langgraph.adapters.routing import (
    create_state_condition_router,
)
from app.runtime.langgraph.events import WorkflowEventSink, reset_event_sink, set_event_sink


def test_condition_router_obeys_state_counter_limit():
    router = create_state_condition_router(
        path="nodes.validator.needs_repair",
        expected=True,
        counter_path="nodes.repairer.repair_attempts",
        max_iterations=1,
    )

    assert router(
        {
            "nodes": {
                "validator": {"needs_repair": True},
                "repairer": {"repair_attempts": 0},
            }
        }
    ) == "then"
    assert router(
        {
            "nodes": {
                "validator": {"needs_repair": True},
                "repairer": {"repair_attempts": 1},
            }
        }
    ) == "exhausted"
    assert router(
        {
            "nodes": {
                "validator": {"needs_repair": False},
                "repairer": {"repair_attempts": 0},
            }
        }
    ) == "otherwise"


def test_condition_router_emits_selected_edge_event():
    sink = WorkflowEventSink()
    token = set_event_sink(sink)
    try:
        router = create_state_condition_router(
            path="nodes.validator.needs_repair",
            expected=True,
            source="validator",
            then_target="repairer",
            otherwise_target="renderer",
        )
        assert router({"nodes": {"validator": {"needs_repair": True}}}) == "then"
        event = sink.queue.get_nowait()
    finally:
        reset_event_sink(token)

    assert event == {
        "object": "workflow.event",
        "type": "workflow.edge.selected",
        "from": "validator",
        "to": "repairer",
        "branch": "then",
        "iteration": 0,
        "max_iterations": None,
    }
