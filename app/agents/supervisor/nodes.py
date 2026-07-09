"""LangGraph node implementations for the supervisor agent."""

import json
from typing import Any, Dict

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from app.agents.supervisor import supervisor_agent
from app.agents.supervisor.state import SupervisorAction, SupervisorState
from app.services.ai_provider import ai_provider


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


class AnalyzeInputNode:
    """Use the supervisor agent to choose the next action."""

    def __call__(self, state: SupervisorState) -> Dict[str, Any]:
        user_input = state["user_input"]
        if not user_input:
            return state

        action = SupervisorAction(supervisor_agent.decide_action(user_input))
        return {
            **state,
            "messages": state["messages"] + [HumanMessage(content=user_input)],
            "action": action,
        }


class AnswerDirectlyNode:
    """Use the supervisor agent to answer without delegation."""

    def __call__(self, state: SupervisorState) -> Dict[str, Any]:
        response = supervisor_agent.answer_directly(state["messages"])
        return {
            **state,
            "messages": state["messages"] + [response],
            "action": None,
        }


class CreatePlanNode:
    """Use the supervisor agent to create a JSON execution plan."""

    def __call__(self, state: SupervisorState) -> Dict[str, Any]:
        agent_names = [agent["agent_name"] for agent in state["agents"].values()]
        if not agent_names:
            return {
                **state,
                "plan": {"steps": []},
                "action": SupervisorAction.COMBINE_RESULTS,
            }

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
                return {
                    **state,
                    "messages": state["messages"] + [AIMessage(content=error)],
                    "plan": {**plan, "steps": [], "error": error},
                    "action": SupervisorAction.COMBINE_RESULTS,
                }

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


class AssignTasksNode:
    """Assign the next pending plan step to an available agent."""

    def __call__(self, state: SupervisorState) -> Dict[str, Any]:
        plan = state["plan"]
        if not plan or not plan.get("steps"):
            return {
                **state,
                "action": SupervisorAction.COMBINE_RESULTS,
            }

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
            return {
                **state,
                "agents": updated_agents,
                "action": SupervisorAction.COMBINE_RESULTS
                if not any_working or (all_assigned and all_complete)
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
            "error": None,
        }

        return {
            **state,
            "agents": updated_agents,
            "action": SupervisorAction.CHECK_STATUS,
        }


class CheckStatusNode:
    """Execute delegated agent tasks and update their status."""

    def __call__(self, state: SupervisorState) -> Dict[str, Any]:
        working_agents = {
            agent_key: agent
            for agent_key, agent in state["agents"].items()
            if agent["status"] == "working"
        }
        if not working_agents:
            if state.get("action") == SupervisorAction.COMBINE_RESULTS:
                return state
            return {
                **state,
                "action": SupervisorAction.ASSIGN_TASKS,
            }

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
                continue

            try:
                model = ai_provider.get_model()
                response = model.invoke(
                    [
                        SystemMessage(
                            content=(
                                f"You are {agent['agent_name']}, a specialized "
                                "AI agent. Complete the assigned task."
                            )
                        ),
                        *agent["messages"],
                    ]
                )
                response_content = str(response.content)
                previous_response = ""
                if agent.get("results") and agent["results"].get("response"):
                    previous_response = agent["results"]["response"] + "\n\n"

                updated_agents[agent_key] = {
                    **updated_agents[agent_key],
                    "status": "complete",
                    "results": {
                        "response": previous_response
                        + f"Task: {task}\nResult: {response_content}"
                    },
                    "messages": updated_agents[agent_key]["messages"] + [response],
                    "error": None,
                }
            except Exception as exc:
                error = f"{agent['agent_name']} failed to execute task: {str(exc)}"
                updated_agents[agent_key] = {
                    **updated_agents[agent_key],
                    "status": "error",
                    "results": {"error": error},
                    "messages": updated_agents[agent_key]["messages"]
                    + [AIMessage(content=error)],
                    "error": error,
                }

        return {
            **state,
            "agents": updated_agents,
            "action": SupervisorAction.ASSIGN_TASKS,
        }


class CombineResultsNode:
    """Use the supervisor agent to combine all agent results."""

    def __call__(self, state: SupervisorState) -> Dict[str, Any]:
        results = []
        errors = []
        for agent in state["agents"].values():
            if agent["results"] and agent["results"].get("response"):
                results.append(f"{agent['agent_name']}: {agent['results']['response']}")
            elif agent["results"] and agent["results"].get("error"):
                errors.append(f"{agent['agent_name']}: {agent['results']['error']}")

        if not results:
            if state["plan"] and state["plan"].get("error"):
                return {
                    **state,
                    "messages": state["messages"]
                    + [AIMessage(content=state["plan"]["error"])],
                    "action": None,
                }

            content = (
                "No available agent completed the task successfully."
                if state["agents"]
                else "No delegated agents are available for this task."
            )
            if errors:
                content += "\n\nErrors:\n" + "\n".join(errors)
            return {
                **state,
                "messages": state["messages"] + [AIMessage(content=content)],
                "action": None,
            }

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


analyze_input = AnalyzeInputNode()
answer_directly = AnswerDirectlyNode()
create_plan = CreatePlanNode()
assign_tasks = AssignTasksNode()
check_status = CheckStatusNode()
combine_results = CombineResultsNode()
