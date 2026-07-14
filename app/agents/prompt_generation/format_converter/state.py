"""State schema for the prompt_format_converter agent."""

from typing import Any, Dict, List, Optional, TypedDict

from langchain_core.messages import BaseMessage


class PromptFormatConverterState(TypedDict):
    """Runtime state for this generated agent."""

    agent_id: str
    agent_name: str
    description: Optional[str]
    system_prompt: Optional[str]
    model: Optional[str]
    temperature: float
    tools: List[Dict[str, Any]]
    messages: List[BaseMessage]
    user_input: Optional[str]

    # 下面是 DSL 声明的业务状态字段。
    draft_prompt: Optional[str]
    negative_prompt: Optional[str]
    target_model: Optional[str]
    formatted_prompt: Optional[str]
    final_output: Optional[Dict[str, Any]]
