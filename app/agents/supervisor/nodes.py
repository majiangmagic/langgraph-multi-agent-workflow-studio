"""LangGraph node implementations for the supervisor agent."""

import json
from typing import Any, Dict

from langchain_core.messages import AIMessage, HumanMessage

from app.agents.supervisor import supervisor_agent
from app.agents.supervisor.state import SupervisorAction, SupervisorState


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


def analyze_input(state: SupervisorState) -> Dict[str, Any]:
    """Use the supervisor agent to choose the next action."""

    user_input = state["user_input"]
    if not user_input:
        return state

    action = SupervisorAction(supervisor_agent.decide_action(user_input))
    return {
        **state,
        "messages": state["messages"] + [HumanMessage(content=user_input)],
        "action": action,
    }


def answer_directly(state: SupervisorState) -> Dict[str, Any]:
    """Use the supervisor agent to answer without delegation."""

    response = supervisor_agent.answer_directly(state["messages"])
    return {
        **state,
        "messages": state["messages"] + [response],
        "action": None,
    }


def create_plan(state: SupervisorState) -> Dict[str, Any]:
    """Use the supervisor agent to create a JSON execution plan."""

    agent_names = [agent["agent_name"] for agent in state["agents"].values()]

    try:
        plan = supervisor_agent.create_plan(state["user_input"] or "", agent_names)
        return {
            **state,
            "messages": state["messages"]
            + [AIMessage(content=format_plan_summary(plan))],
            "plan": plan,
            "action": SupervisorAction.ASSIGN_TASKS,
        }
    except (json.JSONDecodeError, KeyError) as exc:
        return {
            **state,
            "messages": state["messages"]
            + [AIMessage(content=f"Failed to create a valid plan: {str(exc)}")],
            "action": SupervisorAction.ANSWER_DIRECTLY,
        }


def assign_tasks(state: SupervisorState) -> Dict[str, Any]:
    """Assign the next pending plan step to an idle agent."""

    plan = state["plan"]
    if not plan or not plan.get("steps"):
        return state

    updated_agents = {**state["agents"]}
    agent_name_to_key = {
        agent["agent_name"]: agent_key for agent_key, agent in state["agents"].items()
    }

    next_step = None
    for step in plan["steps"]:
        agent_key = agent_name_to_key.get(step["agent"])
        if agent_key and state["agents"][agent_key]["status"] == "idle":
            next_step = step
            break

    if not next_step:
        all_complete = all(
            agent["status"] == "complete"
            for agent in updated_agents.values()
            if any(step["agent"] == agent["agent_name"] for step in plan["steps"])
        )
        return {
            **state,
            "agents": updated_agents,
            "action": SupervisorAction.COMBINE_RESULTS
            if all_complete
            else SupervisorAction.CHECK_STATUS,
        }

    agent_name = next_step["agent"]
    task = next_step["task"]
    agent_key = agent_name_to_key[agent_name]
    updated_agents[agent_key] = {
        **updated_agents[agent_key],
        "status": "working",
        "messages": updated_agents[agent_key]["messages"]
        + [HumanMessage(content=task)],
    }

    return {
        **state,
        "agents": updated_agents,
        "action": SupervisorAction.CHECK_STATUS,
    }


def check_status(state: SupervisorState) -> Dict[str, Any]:
    """Process working agents and update their results."""

    working_agents = {
        agent_key: agent
        for agent_key, agent in state["agents"].items()
        if agent["status"] == "working"
    }
    if not working_agents:
        return {
            **state,
            "action": SupervisorAction.ASSIGN_TASKS,
        }

    updated_agents = {**state["agents"]}

    for agent_key, agent in working_agents.items():
        task = next(
            (
                msg.content
                for msg in reversed(agent["messages"])
                if isinstance(msg, HumanMessage)
            ),
            None,
        )
        if not task:
            continue

        try:
            response = supervisor_agent.run_agent_task(
                agent_name=agent["agent_name"],
                task=task,
                messages=agent["messages"],
            )
            updated_agents[agent_key] = {
                **updated_agents[agent_key],
                "status": "complete",
                "messages": updated_agents[agent_key]["messages"] + [response],
                "results": {"task": task, "response": response.content},
            }
        except Exception as exc:
            updated_agents[agent_key] = {
                **updated_agents[agent_key],
                "status": "error",
                "messages": updated_agents[agent_key]["messages"]
                + [AIMessage(content=f"Error: {str(exc)}")],
            }

    return {
        **state,
        "agents": updated_agents,
        "action": SupervisorAction.ASSIGN_TASKS,
    }


def combine_results(state: SupervisorState) -> Dict[str, Any]:
    """Use the supervisor agent to combine all agent results."""

    results = []
    for agent in state["agents"].values():
        if agent["results"]:
            results.append(f"{agent['agent_name']}: {agent['results']['response']}")

    try:
        response = supervisor_agent.combine_results(
            user_input=state["user_input"] or "",
            plan=state["plan"],
            results=results,
        )
        return {
            **state,
            "messages": state["messages"]
            + [AIMessage(content=format_result_summary(results)), response],
            "action": None,
        }
    except Exception as exc:
        return {
            **state,
            "messages": state["messages"]
            + [AIMessage(content=f"Error combining results: {str(exc)}")],
            "action": None,
        }
