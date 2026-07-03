"""Supervisor agent capabilities used by orchestrated workflows."""

import json
from typing import Any, Dict, List

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage

from app.agents.supervisor.prompts import (
    AGENT_TASK_PROMPT_TEMPLATE,
    ANALYZE_INPUT_PROMPT,
    COMBINE_RESULTS_PROMPT,
    DIRECT_ANSWER_PROMPT,
    PLAN_PROMPT_TEMPLATE,
)
from app.services.ai_provider import ai_provider


class SupervisorAgent:
    """Decision-making agent used by orchestration workflows."""

    def __init__(
        self,
        decision_model: str = "gpt-4-turbo",
        worker_model: str = "gpt-3.5-turbo",
    ) -> None:
        self.decision_model = decision_model
        self.worker_model = worker_model

    def _model(self, model_name: str):
        return ai_provider.get_model(model_name)

    def decide_action(self, user_input: str) -> str:
        """Decide whether to answer directly or create a plan."""

        response = self._model(self.decision_model).invoke(
            [
                SystemMessage(content=ANALYZE_INPUT_PROMPT),
                HumanMessage(content=user_input),
            ]
        )
        if "ACTION: ANSWER_DIRECTLY" in response.content.upper():
            return "answer_directly"
        return "create_plan"

    def answer_directly(self, messages: List[BaseMessage]) -> BaseMessage:
        """Generate a direct answer without task delegation."""

        return self._model(self.decision_model).invoke(
            [SystemMessage(content=DIRECT_ANSWER_PROMPT), *messages]
        )

    def create_plan(self, user_input: str, agent_names: List[str]) -> Dict[str, Any]:
        """Create and parse a JSON execution plan."""

        prompt = PLAN_PROMPT_TEMPLATE.format(agent_names=", ".join(agent_names))
        response = self._model(self.decision_model).invoke(
            [
                SystemMessage(content=prompt),
                HumanMessage(content=user_input),
            ]
        )
        content = response.content
        if "```json" in content and "```" in content.split("```json", 1)[1]:
            json_str = content.split("```json", 1)[1].split("```", 1)[0]
        elif "```" in content and "```" in content.split("```", 1)[1]:
            json_str = content.split("```", 1)[1].split("```", 1)[0]
        else:
            json_str = content
        return json.loads(json_str)

    def run_agent_task(
        self,
        agent_name: str,
        task: str,
        messages: List[BaseMessage],
    ) -> BaseMessage:
        """Run a delegated task for an agent.

        This remains a placeholder execution path until concrete agent runners are added.
        """

        return self._model(self.worker_model).invoke(
            [
                SystemMessage(
                    content=AGENT_TASK_PROMPT_TEMPLATE.format(agent_name=agent_name)
                ),
                *messages[-5:],
            ]
        )

    def combine_results(
        self,
        user_input: str,
        plan: Dict[str, Any] | None,
        results: List[str],
    ) -> BaseMessage:
        """Combine delegated agent results into a final response."""

        prompt = f"""Original user request: {user_input}

Plan goal: {plan["goal"] if plan and "goal" in plan else "No specific goal"}

Agent results:
{''.join(results)}

Based on these results, provide a comprehensive response to the user's original request."""

        return self._model(self.decision_model).invoke(
            [
                SystemMessage(content=COMBINE_RESULTS_PROMPT),
                HumanMessage(content=prompt),
            ]
        )


supervisor_agent = SupervisorAgent()
