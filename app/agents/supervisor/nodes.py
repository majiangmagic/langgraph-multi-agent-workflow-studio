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
                    "执行计划包含不存在的 Agent："
                    f"{', '.join(unknown_agents)}。"
                    "可用 Agent："
                    f"{', '.join(agent_names)}。"
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
    """Assign the next pending plan step to an idle agent."""

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


class CheckStatusNode:
    """Check delegated task status without simulating agent execution."""

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
            updated_agents[agent_key] = {
                **updated_agents[agent_key],
                "status": "error",
                "messages": updated_agents[agent_key]["messages"]
                + [
                    AIMessage(
                        content=(
                            f"{agent['agent_name']} 已收到任务，但当前 Workflow "
                            "还没有接入这个真实 Agent 的执行节点。"
                        )
                    )
                ],
            }

        return {
            **state,
            "agents": updated_agents,
            "action": SupervisorAction.COMBINE_RESULTS,
        }


class CombineResultsNode:
    """Use the supervisor agent to combine all agent results."""

    def __call__(self, state: SupervisorState) -> Dict[str, Any]:
        results = []
        for agent in state["agents"].values():
            if agent["results"]:
                results.append(f"{agent['agent_name']}: {agent['results']['response']}")

        if not results:
            if state["plan"] and state["plan"].get("error"):
                return {
                    **state,
                    "messages": state["messages"]
                    + [AIMessage(content=state["plan"]["error"])],
                    "action": None,
                }

            content = (
                "当前 Workflow 尚未接入真实 Agent 执行节点，无法执行这个任务。"
                if state["agents"]
                else "没有符合要求的 Agent，无法执行这个任务。"
            )
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
