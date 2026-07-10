"""LangGraph node implementations for the supervisor agent."""

import json
from typing import Any, Dict

from langchain_core.messages import AIMessage, HumanMessage

from app.agents.supervisor import supervisor_agent
from app.agents.supervisor.state import SupervisorAction, SupervisorState
from app.core.langgraph.events import emit_event


def format_plan_summary(plan: Dict[str, Any]) -> str:
    """Format the plan as useful supervisor conversation context."""

    steps = [
        f"{index}. {step['agent']}: {step['task']}"
        for index, step in enumerate(plan.get("steps", []), start=1)
    ]
    return "Task plan:\n" + "\n".join(steps)


def format_result_summary(results: list[str]) -> str:
    """Format delegated results as useful supervisor conversation context."""

    if not results:
        return "Execution results: no delegated agent results were produced."
    return "Execution results:\n" + "\n".join(results)


def find_unknown_plan_agents(
    plan: Dict[str, Any], agent_names: list[str]
) -> list[str]:
    """Return plan agent names that are not available in the current state."""

    known_agents = set(agent_names)
    unknown_agents = {
        step.get("agent")
        for step in plan.get("steps", [])
        if step.get("agent") not in known_agents
    }
    return sorted(agent for agent in unknown_agents if agent)


def agent_has_task(agent: Dict[str, Any], task: str) -> bool:
    """Return whether this task has already been assigned to the agent."""

    return any(
        isinstance(message, HumanMessage) and message.content == task
        for message in agent["messages"]
    )


def last_assigned_task(agent: Dict[str, Any]) -> str:
    """Return the most recent task assigned to an agent."""

    for message in reversed(agent["messages"]):
        if isinstance(message, HumanMessage):
            return str(message.content)
    return ""


def emit_node_started(node: str) -> None:
    """Emit a supervisor node start event."""

    emit_event(
        {
            "object": "workflow.event",
            "type": "workflow.node.started",
            "scope": "supervisor",
            "node": node,
        }
    )


def emit_node_completed(node: str, state: SupervisorState) -> None:
    """Emit a small, JSON-safe supervisor node completion event."""

    agents = state.get("agents") or {}
    emit_event(
        {
            "object": "workflow.event",
            "type": "workflow.node.completed",
            "scope": "supervisor",
            "node": node,
            "summary": {
                "action": str(state.get("action") or ""),
                "plan_steps": len((state.get("plan") or {}).get("steps", [])),
                "agents": [
                    {
                        "agent_id": agent.get("agent_id") or agent_key,
                        "agent_name": agent.get("agent_name"),
                        "status": agent.get("status"),
                        "error": agent.get("error"),
                    }
                    for agent_key, agent in agents.items()
                ],
            },
        }
    )


class AnalyzeInputNode:
    """Use the supervisor agent to choose the next action."""

    def __call__(self, state: SupervisorState) -> Dict[str, Any]:
        emit_node_started("analyze_input")
        user_input = state["user_input"]
        if not user_input:
            emit_node_completed("analyze_input", state)
            return state

        action = SupervisorAction(supervisor_agent.decide_action(user_input))
        new_state = {
            **state,
            "messages": state["messages"] + [HumanMessage(content=user_input)],
            "action": action,
        }
        emit_node_completed("analyze_input", new_state)
        return new_state


class AnswerDirectlyNode:
    """Use the supervisor agent to answer without delegation."""

    def __call__(self, state: SupervisorState) -> Dict[str, Any]:
        emit_node_started("answer_directly")
        response = supervisor_agent.answer_directly(state["messages"])
        new_state = {
            **state,
            "messages": state["messages"] + [response],
            "action": None,
        }
        emit_node_completed("answer_directly", new_state)
        return new_state


class CreatePlanNode:
    """Use the supervisor agent to create a JSON execution plan."""

    def __call__(self, state: SupervisorState) -> Dict[str, Any]:
        emit_node_started("create_plan")
        agent_names = [agent["agent_name"] for agent in state["agents"].values()]
        if not agent_names:
            new_state = {
                **state,
                "plan": {"steps": []},
                "action": SupervisorAction.COMBINE_RESULTS,
            }
            emit_node_completed("create_plan", new_state)
            return new_state

        try:
            plan = supervisor_agent.create_plan(state["user_input"] or "", agent_names)
            unknown_agents = find_unknown_plan_agents(plan, agent_names)
            if unknown_agents:
                error = (
                    "The execution plan referenced unavailable agents: "
                    f"{', '.join(unknown_agents)}. "
                    "Available agents: "
                    f"{', '.join(agent_names)}."
                )
                new_state = {
                    **state,
                    "messages": state["messages"] + [AIMessage(content=error)],
                    "plan": {**plan, "steps": [], "error": error},
                    "action": SupervisorAction.COMBINE_RESULTS,
                }
                emit_node_completed("create_plan", new_state)
                return new_state

            new_state = {
                **state,
                "messages": state["messages"]
                + [AIMessage(content=format_plan_summary(plan))],
                "plan": plan,
                "action": SupervisorAction.ASSIGN_TASKS,
            }
            emit_node_completed("create_plan", new_state)
            return new_state
        except (json.JSONDecodeError, KeyError) as exc:
            new_state = {
                **state,
                "messages": state["messages"]
                + [AIMessage(content=f"Failed to create a valid plan: {str(exc)}")],
                "action": SupervisorAction.ANSWER_DIRECTLY,
            }
            emit_node_completed("create_plan", new_state)
            return new_state


class AssignTasksNode:
    """Assign the next pending plan step to an available agent."""

    def __call__(self, state: SupervisorState) -> Dict[str, Any]:
        emit_node_started("assign_tasks")
        plan = state["plan"]
        if not plan or not plan.get("steps"):
            new_state = {
                **state,
                "action": SupervisorAction.COMBINE_RESULTS,
            }
            emit_node_completed("assign_tasks", new_state)
            return new_state

        updated_agents = {**state["agents"]}
        agent_name_to_key = {
            agent["agent_name"]: agent_key
            for agent_key, agent in state["agents"].items()
        }

        next_step = None
        for step in plan["steps"]:
            agent_key = agent_name_to_key.get(step["agent"])
            if (
                agent_key
                and state["agents"][agent_key]["status"] in ("idle", "complete")
                and not agent_has_task(state["agents"][agent_key], step["task"])
            ):
                next_step = step
                break

        if not next_step:
            plan_steps = [
                step for step in plan["steps"] if agent_name_to_key.get(step["agent"])
            ]
            all_assigned = all(
                agent_has_task(
                    updated_agents[agent_name_to_key[step["agent"]]], step["task"]
                )
                for step in plan_steps
            )
            all_complete = all(
                updated_agents[agent_name_to_key[step["agent"]]]["status"] == "complete"
                for step in plan_steps
            )
            any_working = any(
                updated_agents[agent_name_to_key[step["agent"]]]["status"] == "working"
                for step in plan_steps
            )
            new_state = {
                **state,
                "agents": updated_agents,
                "action": SupervisorAction.COMBINE_RESULTS
                if not any_working or (all_assigned and all_complete)
                else SupervisorAction.CHECK_STATUS,
            }
            emit_node_completed("assign_tasks", new_state)
            return new_state

        agent_name = next_step["agent"]
        task = next_step["task"]
        agent_key = agent_name_to_key[agent_name]
        emit_event(
            {
                "object": "workflow.event",
                "type": "workflow.task.assigned",
                "scope": "supervisor",
                "agent_id": agent_key,
                "agent_name": agent_name,
                "task": task,
            }
        )
        updated_agents[agent_key] = {
            **updated_agents[agent_key],
            "status": "working",
            "messages": updated_agents[agent_key]["messages"]
            + [HumanMessage(content=task)],
            "error": None,
        }

        new_state = {
            **state,
            "agents": updated_agents,
            "action": SupervisorAction.CHECK_STATUS,
        }
        emit_node_completed("assign_tasks", new_state)
        return new_state


class CheckStatusNode:
    """Check delegated task status until real agent execution is connected."""

    def __call__(self, state: SupervisorState) -> Dict[str, Any]:
        emit_node_started("check_status")
        working_agents = {
            agent_key: agent
            for agent_key, agent in state["agents"].items()
            if agent["status"] == "working"
        }
        if not working_agents:
            if state.get("action") == SupervisorAction.COMBINE_RESULTS:
                emit_node_completed("check_status", state)
                return state
            new_state = {
                **state,
                "action": SupervisorAction.ASSIGN_TASKS,
            }
            emit_node_completed("check_status", new_state)
            return new_state

        updated_agents = {**state["agents"]}

        for agent_key, agent in working_agents.items():
            task = last_assigned_task(agent)
            if not task:
                error = f"{agent['agent_name']} has no assigned task to execute."
                updated_agents[agent_key] = {
                    **updated_agents[agent_key],
                    "status": "error",
                    "results": {"error": error},
                    "messages": updated_agents[agent_key]["messages"]
                    + [AIMessage(content=error)],
                    "error": error,
                }
                emit_event(
                    {
                        "object": "workflow.event",
                        "type": "workflow.agent.error",
                        "scope": "supervisor",
                        "agent_id": agent_key,
                        "agent_name": agent["agent_name"],
                        "error": error,
                    }
                )
                continue

            error = (
                f"{agent['agent_name']} received task '{task}', but no real "
                "agent executor is connected for delegated task execution yet."
            )
            updated_agents[agent_key] = {
                **updated_agents[agent_key],
                "status": "error",
                "results": {"error": error},
                "messages": updated_agents[agent_key]["messages"]
                + [AIMessage(content=error)],
                "error": error,
            }
            emit_event(
                {
                    "object": "workflow.event",
                    "type": "workflow.agent.error",
                    "scope": "supervisor",
                    "agent_id": agent_key,
                    "agent_name": agent["agent_name"],
                    "task": task,
                    "error": error,
                }
            )

        new_state = {
            **state,
            "agents": updated_agents,
            "action": SupervisorAction.ASSIGN_TASKS,
        }
        emit_node_completed("check_status", new_state)
        return new_state


class CombineResultsNode:
    """Use the supervisor agent to combine all agent results."""

    def __call__(self, state: SupervisorState) -> Dict[str, Any]:
        emit_node_started("combine_results")
        results = []
        errors = []
        for agent in state["agents"].values():
            if agent["results"] and agent["results"].get("response"):
                results.append(f"{agent['agent_name']}: {agent['results']['response']}")
            elif agent["results"] and agent["results"].get("error"):
                errors.append(f"{agent['agent_name']}: {agent['results']['error']}")

        if not results:
            if state["plan"] and state["plan"].get("error"):
                new_state = {
                    **state,
                    "messages": state["messages"]
                    + [AIMessage(content=state["plan"]["error"])],
                    "action": None,
                }
                emit_node_completed("combine_results", new_state)
                return new_state

            content = (
                "No available agent completed the task successfully."
                if state["agents"]
                else "No delegated agents are available for this task."
            )
            if errors:
                content += "\n\nErrors:\n" + "\n".join(errors)
            new_state = {
                **state,
                "messages": state["messages"] + [AIMessage(content=content)],
                "action": None,
            }
            emit_node_completed("combine_results", new_state)
            return new_state

        try:
            response = supervisor_agent.combine_results(
                user_input=state["user_input"] or "",
                plan=state["plan"],
                results=results,
            )
            new_state = {
                **state,
                "messages": state["messages"]
                + [AIMessage(content=format_result_summary(results)), response],
                "action": None,
            }
            emit_node_completed("combine_results", new_state)
            return new_state
        except Exception as exc:
            new_state = {
                **state,
                "messages": state["messages"]
                + [AIMessage(content=f"Error combining results: {str(exc)}")],
                "action": None,
            }
            emit_node_completed("combine_results", new_state)
            return new_state


analyze_input = AnalyzeInputNode()
answer_directly = AnswerDirectlyNode()
create_plan = CreatePlanNode()
assign_tasks = AssignTasksNode()
check_status = CheckStatusNode()
combine_results = CombineResultsNode()
