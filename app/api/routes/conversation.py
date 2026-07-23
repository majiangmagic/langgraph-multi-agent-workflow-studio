"""
API routes for conversations and chat functionality
"""
import asyncio
from contextlib import suppress
import logging
from typing import List, Optional, Dict, Any
import uuid
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks, Request
from fastapi.responses import StreamingResponse
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langgraph.types import Command
from sqlalchemy.ext.asyncio import AsyncSession
import json

from app.db.base import async_session_factory, get_db
from app.core.config import settings
from app.models.conversation import MessageRole, MessageStatus
from app.models.activity_log import ActivityType
from app.core.langgraph.checkpoint import get_checkpointer
from app.core.langgraph.events import (
    WorkflowEventSink,
    reset_event_sink,
    set_event_sink,
)
from app.core.langgraph.workflows.registry import workflow_registry
from app.services.conversation_service import ConversationService, ActivityLogService
from app.services.crew_service import CrewService
from app.services.workflow_service import WorkflowService
from app.schemas.conversation import (
    ConversationCreate, 
    ConversationResponse, 
    ConversationUpdate,
    MessageCreate,
    MessageResponse,
    DeleteTurnResponse,
    ChatRequest,
    ChatResponse,
    UnifiedChatRequest,
    UnifiedChatResponse,
)


router = APIRouter(prefix="/conversations", tags=["conversations"])
chat_router = APIRouter(tags=["chat"])
logger = logging.getLogger(__name__)


def db_messages_to_langchain(messages) -> List[BaseMessage]:
    """Convert persisted conversation messages into workflow short-term memory."""

    converted: List[BaseMessage] = []
    for message in messages:
        content = str(message.content or "").strip()
        if not content:
            continue
        if message.status != MessageStatus.COMPLETED:
            continue
        if message.role == MessageRole.USER:
            converted.append(HumanMessage(content=content))
        elif message.role == MessageRole.ASSISTANT:
            workflow_memory = (message.meta_data or {}).get("workflow_memory")
            converted.append(
                AIMessage(
                    content=content,
                    additional_kwargs={"workflow_memory": workflow_memory}
                    if workflow_memory
                    else {},
                )
            )
        elif message.role == MessageRole.SYSTEM:
            converted.append(SystemMessage(content=content))
    return converted


async def get_short_term_history(db: AsyncSession, conversation_id: uuid.UUID) -> List[BaseMessage]:
    """Load the recent DB transcript used to seed workflow-level memory."""

    limit = max(settings.short_term_memory_turns, 1) * 2
    messages = await ConversationService.get_recent_messages(
        db=db,
        conversation_id=conversation_id,
        limit=limit,
    )
    return db_messages_to_langchain(messages)


def extract_workflow_response(final_state: Dict[str, Any]) -> str:
    """Get the last assistant-style response from a completed workflow run."""

    for node_state in reversed(list((final_state.get("nodes") or {}).values())):
        if node_state.get("answer"):
            return str(node_state["answer"])
        for message in reversed(node_state.get("messages", [])):
            if isinstance(message, AIMessage):
                return str(message.content)

    supervisor_state = get_supervisor_state(final_state)
    for message in reversed(supervisor_state.get("messages", [])):
        if isinstance(message, AIMessage):
            return str(message.content)

    return "Workflow completed without an assistant response."


def extract_workflow_memory(final_state: Dict[str, Any]) -> Dict[str, Any]:
    """提取跨轮业务状态，不保存系统提示词或模型配置。"""

    memory: Dict[str, Any] = {}
    newest_document_version = -1
    newest_ir_version = -1
    for node_state in (final_state.get("nodes") or {}).values():
        document = node_state.get("scene_document")
        if isinstance(document, dict):
            version = int(document.get("version") or 0)
            if version >= newest_document_version:
                memory["scene_document"] = document
                newest_document_version = version
        prompt_ir = node_state.get("resolved_prompt_ir")
        if not isinstance(prompt_ir, dict):
            prompt_ir = node_state.get("previous_resolved_prompt_ir")
        if isinstance(prompt_ir, dict):
            version = int(prompt_ir.get("document_version") or 0)
            if version >= newest_ir_version:
                memory["resolved_prompt_ir"] = prompt_ir
                newest_ir_version = version
        contract = node_state.get("request_contract")
        if (
            "scene_document" not in memory
            and isinstance(contract, dict)
            and contract.get("resolved_request")
        ):
            memory["request_contract"] = contract
            memory["resolved_user_request"] = (
                node_state.get("resolved_user_request")
                or contract["resolved_request"]
            )
    return memory


def extract_workflow_result(final_state: Dict[str, Any]) -> Dict[str, Any]:
    """Extract structured UI-facing result metadata from the terminal node."""

    nodes = final_state.get("nodes") or {}
    diagnostics = {
        key: value
        for key, value in {
            "editor_error": (nodes.get("scene_document_editor") or {}).get(
                "editor_error"
            ),
            "patch_error": (nodes.get("scene_document_processor") or {}).get(
                "patch_error"
            ),
            "patch_intent": (
                (nodes.get("scene_document_editor") or {}).get("patch_proposal")
                or {}
            ).get("intent"),
        }.items()
        if value
    }
    for node_state in reversed(list(nodes.values())):
        final_output = node_state.get("final_output")
        if not isinstance(final_output, dict):
            continue
        result = {
            key: final_output.get(key)
            for key in (
                "status",
                "target_model",
                "document_version",
                "clarification_request",
                "warnings",
                "unresolved_requirements",
            )
            if final_output.get(key) is not None
        }
        if diagnostics:
            result["workflow_diagnostics"] = diagnostics
        return result
    return {}


def extract_workflow_interrupt(final_state: Dict[str, Any]) -> Dict[str, Any]:
    """Return the first structured LangGraph interrupt, when execution paused."""

    interrupts = final_state.get("__interrupt__") or []
    if not interrupts:
        return {}
    current = interrupts[0]
    value = getattr(current, "value", current)
    payload = dict(value) if isinstance(value, dict) else {"question": str(value)}
    question = str(payload.get("question") or "请补充继续执行所需的信息。").strip()
    options = [
        str(option)
        for option in payload.get("options") or []
        if str(option).strip()
    ][:4]
    return {
        "id": str(getattr(current, "id", "")),
        "kind": str(payload.get("kind") or "workflow.clarification"),
        "question": question,
        "options": options,
        "context": str(payload.get("context") or ""),
    }


def extract_workflow_outcome(
    final_state: Dict[str, Any],
) -> tuple[str, Dict[str, Any], Dict[str, Any]]:
    """Extract response text, durable workflow memory, and UI result metadata."""

    workflow_memory = extract_workflow_memory(final_state)
    interrupted = extract_workflow_interrupt(final_state)
    if interrupted:
        question = interrupted["question"]
        return (
            f"需要确认：{question}",
            workflow_memory,
            {
                "status": "needs_clarification",
                "resumable": True,
                "interrupt": interrupted,
                "clarification_request": {
                    "question": question,
                    "options": interrupted["options"],
                },
            },
        )
    return (
        extract_workflow_response(final_state),
        workflow_memory,
        extract_workflow_result(final_state),
    )


def get_supervisor_state(final_state: Dict[str, Any]) -> Dict[str, Any]:
    """Read supervisor state from the current or legacy workflow shape."""

    return final_state.get("nodes", {}).get("supervisor") or final_state.get(
        "supervisor", {}
    )


def stream_data(data: Dict[str, Any]) -> str:
    """Serialize one server-sent event payload."""

    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


def iter_text_deltas(content: str, chunk_size: int = 48):
    """Split final workflow text into stable transport deltas."""

    for start in range(0, len(content), chunk_size):
        yield content[start:start + chunk_size]


def summarize_supervisor_state(supervisor_state: Dict[str, Any]) -> Dict[str, Any]:
    """Build a small, JSON-safe workflow progress summary."""

    agents = supervisor_state.get("agents") or {}
    return {
        "action": str(supervisor_state.get("action") or ""),
        "plan_steps": len((supervisor_state.get("plan") or {}).get("steps", [])),
        "agents": [
            {
                "agent_id": agent.get("agent_id") or agent_key,
                "agent_name": agent.get("agent_name"),
                "status": agent.get("status"),
                "error": agent.get("error"),
            }
            for agent_key, agent in agents.items()
        ],
    }


async def build_workflow_for_conversation(
    db: AsyncSession,
    conversation,
    user_message,
    workflow_inputs: Optional[Dict[str, Any]] = None,
):
    """Create the configured workflow and initial state for a conversation turn."""

    crew = await CrewService.get_crew(db, conversation.crew_id)
    if not crew:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Crew with ID {conversation.crew_id} not found",
        )

    workflow_type = WorkflowService.get_workflow_type(crew)
    request_context = {
        "request_id": str(user_message.id),
        "conversation_id": str(conversation.id),
        "user_id": conversation.user_id,
    }
    try:
        history_messages = await get_short_term_history(db, conversation.id)
        workflow, initial_state = WorkflowService.create_workflow_run(
            crew=crew,
            conversation_id=str(conversation.id),
            user_id=conversation.user_id,
            user_input=user_message.content,
            messages=history_messages,
            workflow_inputs=dict(workflow_inputs or {}),
            request_context=request_context,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    metadata = workflow_registry.get_metadata(workflow_type, fallback=False)
    entrypoint = str(metadata.get("entrypoint") or "")
    node_states = initial_state.get("nodes") or {}
    runtime_agent = node_states.get(entrypoint) or next(
        iter(node_states.values()), {}
    )
    return workflow, initial_state, runtime_agent


async def build_workflow_for_resume(db: AsyncSession, conversation):
    """Recreate the local graph while preserving its checkpointed pause state."""

    recent = await ConversationService.get_recent_messages(
        db, conversation.id, limit=1
    )
    pending_result = (
        (recent[-1].meta_data or {}).get("workflow_result")
        if recent and recent[-1].role == MessageRole.ASSISTANT
        else {}
    ) or {}
    if not pending_result.get("resumable"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This conversation has no interrupted workflow to resume",
        )

    crew = await CrewService.get_crew(db, conversation.crew_id)
    if not crew:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Crew with ID {conversation.crew_id} not found",
        )
    try:
        workflow = WorkflowService.create_workflow(crew)
        local_agents = WorkflowService.local_agent_configs(crew)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    metadata = workflow_registry.get_metadata(
        WorkflowService.get_workflow_type(crew), fallback=False
    )
    entrypoint = str(metadata.get("entrypoint") or "")
    runtime_agent = next(
        (
            agent
            for agent in local_agents
            if str(agent.get("id") or "").endswith(f":{entrypoint}")
        ),
        local_agents[0] if local_agents else {},
    )
    return workflow, runtime_agent


async def run_resume_turn(
    db: AsyncSession,
    conversation,
    response: Any,
) -> ChatResponse:
    """Persist a human answer and resume the same LangGraph checkpoint."""

    workflow, runtime_agent = await build_workflow_for_resume(db, conversation)
    user_message = await ConversationService.add_message(
        db=db,
        conversation_id=conversation.id,
        role=MessageRole.USER,
        content=str(response),
        status=MessageStatus.COMPLETED,
        metadata={"workflow_resume": True},
    )
    final_state = await workflow.ainvoke(
        Command(resume=response),
        config={"configurable": {"thread_id": str(conversation.id)}},
    )
    response_content, workflow_memory, workflow_result = extract_workflow_outcome(
        final_state
    )
    assistant_message = await ConversationService.add_message(
        db=db,
        conversation_id=conversation.id,
        role=MessageRole.ASSISTANT,
        content=response_content,
        parent_id=user_message.id,
        status=MessageStatus.COMPLETED,
        metadata={
            **({"workflow_memory": workflow_memory} if workflow_memory else {}),
            **({"workflow_result": workflow_result} if workflow_result else {}),
            "agent_name": runtime_agent.get("agent_name"),
        },
    )
    await ActivityLogService.log_activity(
        db=db,
        agent_name=runtime_agent.get("agent_name"),
        activity_type=ActivityType.AGENT_MESSAGE,
        description=f"Workflow resumed in conversation {conversation.id}",
        conversation_id=conversation.id,
        message_id=assistant_message.id,
    )
    return ChatResponse(message_id=assistant_message.id, content=response_content)


async def run_chat_turn(
    db: AsyncSession,
    conversation,
    message: str,
    workflow_inputs: Optional[Dict[str, Any]] = None,
) -> ChatResponse:
    """Persist a user message, run the workflow, and persist the assistant reply."""

    user_message = await ConversationService.add_message(
        db=db,
        conversation_id=conversation.id,
        role=MessageRole.USER,
        content=message,
        status=MessageStatus.COMPLETED,
        metadata={"workflow_inputs": workflow_inputs} if workflow_inputs else {},
    )

    workflow, initial_state, runtime_agent = await build_workflow_for_conversation(
        db, conversation, user_message, workflow_inputs
    )

    try:
        final_state = await workflow.ainvoke(
            initial_state,
            config={"configurable": {"thread_id": str(conversation.id)}},
        )
        response_content, workflow_memory, workflow_result = (
            extract_workflow_outcome(final_state)
        )
    except Exception as e:
        print(f"Error running supervisor workflow: {str(e)}")
        response_content = (
            "I apologize, but I encountered an issue processing your request. "
            "Please try again later."
        )
        workflow_memory = {}
        workflow_result = {}

    assistant_message = await ConversationService.add_message(
        db=db,
        conversation_id=conversation.id,
        role=MessageRole.ASSISTANT,
        content=response_content,
        parent_id=user_message.id,
        status=MessageStatus.COMPLETED,
        metadata={
            **({"workflow_memory": workflow_memory} if workflow_memory else {}),
            **({"workflow_result": workflow_result} if workflow_result else {}),
            "agent_name": runtime_agent.get("agent_name"),
        },
    )

    await ActivityLogService.log_activity(
        db=db,
        agent_name=runtime_agent.get("agent_name"),
        activity_type=ActivityType.AGENT_MESSAGE,
        description=f"Workflow responded in conversation {conversation.id}",
        conversation_id=conversation.id,
        message_id=assistant_message.id,
    )

    return ChatResponse(
        message_id=assistant_message.id,
        content=response_content,
    )


async def get_or_create_chat_conversation(
    db: AsyncSession,
    request: UnifiedChatRequest,
):
    """Return an existing conversation or create one for a unified chat request."""

    if request.conversation_id:
        conversation = await ConversationService.get_conversation(
            db, request.conversation_id
        )
        if not conversation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Conversation with ID {request.conversation_id} not found",
            )
        return conversation

    if not request.user_id or not request.crew_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="user_id and crew_id are required when conversation_id is not provided",
        )

    crew = await CrewService.get_crew(db, request.crew_id)
    if not crew:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Crew with ID {request.crew_id} not found",
        )

    return await ConversationService.create_conversation(
        db=db,
        user_id=request.user_id,
        crew_id=request.crew_id,
        title=request.title,
        metadata=request.metadata,
    )


@router.get("/", response_model=List[ConversationResponse])
async def get_conversations(
    user_id: Optional[str] = None,
    crew_id: Optional[uuid.UUID] = None,
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
):
    """Get a list of conversations with optional filters"""
    conversations = await ConversationService.get_conversations(
        db, user_id=user_id, crew_id=crew_id, skip=skip, limit=limit
    )
    return conversations


@router.post("/", response_model=ConversationResponse, status_code=status.HTTP_201_CREATED)
async def create_conversation(
    conversation: ConversationCreate,
    db: AsyncSession = Depends(get_db),
):
    """Create a new conversation"""
    # Verify the crew exists
    crew = await CrewService.get_crew(db, conversation.crew_id)
    if not crew:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Crew with ID {conversation.crew_id} not found"
        )
    
    # Create the conversation
    db_conversation = await ConversationService.create_conversation(
        db=db,
        user_id=conversation.user_id,
        crew_id=conversation.crew_id,
        title=conversation.title,
        metadata=conversation.metadata,
    )
    
    return db_conversation


@router.get("/{conversation_id}", response_model=ConversationResponse)
async def get_conversation(
    conversation_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Get a specific conversation by ID"""
    conversation = await ConversationService.get_conversation(db, conversation_id)
    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conversation with ID {conversation_id} not found"
        )
    
    return conversation


@router.put("/{conversation_id}", response_model=ConversationResponse)
async def update_conversation(
    conversation_id: uuid.UUID,
    conversation_update: ConversationUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update a conversation"""
    updated_conversation = await ConversationService.update_conversation(
        db=db,
        conversation_id=conversation_id,
        title=conversation_update.title,
        metadata=conversation_update.metadata,
        is_active=conversation_update.is_active,
    )
    
    if not updated_conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conversation with ID {conversation_id} not found"
        )
    
    return updated_conversation


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(
    conversation_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Delete a conversation"""
    success = await ConversationService.delete_conversation(db, conversation_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conversation with ID {conversation_id} not found"
        )
    checkpointer = get_checkpointer()
    if checkpointer is not None:
        await checkpointer.adelete_thread(str(conversation_id))
    return None


@router.delete("/{conversation_id}/turns/latest", response_model=DeleteTurnResponse)
async def delete_latest_turn(
    conversation_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Delete the latest user turn and its following assistant/agent messages."""

    deleted_messages = await ConversationService.delete_latest_turn(db, conversation_id)
    if deleted_messages < 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conversation with ID {conversation_id} not found",
        )
    if deleted_messages == 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Conversation has no user turn to delete",
        )

    checkpointer = get_checkpointer()
    if checkpointer is not None:
        await checkpointer.adelete_thread(str(conversation_id))

    return DeleteTurnResponse(deleted_messages=deleted_messages)


@router.delete(
    "/{conversation_id}/turns/from/{message_id}",
    response_model=DeleteTurnResponse,
)
async def rewind_conversation(
    conversation_id: uuid.UUID,
    message_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Rewind a conversation to immediately before the selected user turn."""

    deleted_messages = await ConversationService.delete_from_message(
        db, conversation_id, message_id
    )
    if deleted_messages < 0:
        raise HTTPException(status_code=404, detail="Conversation not found")
    if deleted_messages == 0:
        raise HTTPException(
            status_code=409,
            detail="The selected message is not a user turn in this conversation",
        )

    checkpointer = get_checkpointer()
    if checkpointer is not None:
        await checkpointer.adelete_thread(str(conversation_id))
    return DeleteTurnResponse(deleted_messages=deleted_messages)


@router.get("/{conversation_id}/messages", response_model=List[MessageResponse])
async def get_messages(
    conversation_id: uuid.UUID,
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
):
    """Get messages for a specific conversation"""
    # Verify conversation exists
    conversation = await ConversationService.get_conversation(db, conversation_id)
    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conversation with ID {conversation_id} not found"
        )
    
    messages = await ConversationService.get_messages(
        db, conversation_id, skip=skip, limit=limit
    )
    return messages


@router.post("/{conversation_id}/messages", response_model=MessageResponse, status_code=status.HTTP_201_CREATED)
async def add_message(
    conversation_id: uuid.UUID,
    message: MessageCreate,
    db: AsyncSession = Depends(get_db),
):
    """Add a message to a conversation"""
    # Verify conversation exists
    conversation = await ConversationService.get_conversation(db, conversation_id)
    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conversation with ID {conversation_id} not found"
        )
    
    # Add the message
    db_message = await ConversationService.add_message(
        db=db,
        conversation_id=conversation_id,
        role=message.role,
        content=message.content,
        parent_id=message.parent_id,
        status=message.status,
        metadata=message.metadata,
    )
    
    # Log activity if it's an agent message
    if message.role == MessageRole.AGENT:
        agent_name = str(message.metadata.get("agent_name") or "local_agent")
        await ActivityLogService.log_activity(
            db=db,
            agent_name=agent_name,
            activity_type=ActivityType.AGENT_MESSAGE,
            description=f"Agent sent message in conversation {conversation_id}",
            conversation_id=conversation_id,
            message_id=db_message.id,
            details={"content_length": len(message.content)}
        )
    
    return db_message


@router.post("/{conversation_id}/chat", response_model=ChatResponse)
async def chat(
    conversation_id: uuid.UUID,
    chat_request: ChatRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """Send a message to the crew and get a response"""
    # Verify conversation exists
    conversation = await ConversationService.get_conversation(db, conversation_id)
    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conversation with ID {conversation_id} not found"
        )

    if chat_request.resume:
        return await run_resume_turn(db, conversation, chat_request.message)
    return await run_chat_turn(
        db, conversation, chat_request.message, chat_request.workflow_inputs
    )


@chat_router.post("/chat", response_model=UnifiedChatResponse)
async def unified_chat(
    chat_request: UnifiedChatRequest,
    db: AsyncSession = Depends(get_db),
):
    """Create a conversation when needed, then send one chat message."""

    conversation = await get_or_create_chat_conversation(db, chat_request)
    chat_response = await run_chat_turn(
        db, conversation, chat_request.message, chat_request.workflow_inputs
    )
    return UnifiedChatResponse(
        conversation_id=conversation.id,
        message_id=chat_response.message_id,
        content=chat_response.content,
    )


@router.post("/{conversation_id}/chat/stream")
async def chat_stream(
    conversation_id: uuid.UUID,
    chat_request: ChatRequest,
    db: AsyncSession = Depends(get_db),
):
    """Send a message to the crew and get a streaming response"""
    # Verify conversation exists
    conversation = await ConversationService.get_conversation(db, conversation_id)
    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conversation with ID {conversation_id} not found"
        )
    
    resume_runtime = None
    if chat_request.resume:
        resume_runtime = await build_workflow_for_resume(db, conversation)

    # Persist both ordinary turns and human-in-the-loop resume answers.
    user_message = await ConversationService.add_message(
        db=db,
        conversation_id=conversation_id,
        role=MessageRole.USER,
        content=chat_request.message,
        status=MessageStatus.COMPLETED,
        metadata={
            **(
                {"workflow_inputs": chat_request.workflow_inputs}
                if chat_request.workflow_inputs
                else {}
            ),
            **({"workflow_resume": True} if chat_request.resume else {}),
        },
    )

    if chat_request.resume:
        assert resume_runtime is not None
        workflow, runtime_agent = resume_runtime
        workflow_input: Any = Command(resume=chat_request.message)
    else:
        workflow, initial_state, runtime_agent = await build_workflow_for_conversation(
            db, conversation, user_message, chat_request.workflow_inputs
        )
        workflow_input = initial_state
    
    # Create a placeholder for assistant message
    assistant_message = await ConversationService.add_message(
        db=db,
        conversation_id=conversation_id,
        role=MessageRole.ASSISTANT,
        content="",
        parent_id=user_message.id,
        status=MessageStatus.PROCESSING,
    )
    
    # Stream the configured workflow result as SSE.
    async def stream_response():
        message_id = str(assistant_message.id)
        run_id = str(uuid.uuid4())
        sequence = 0
        content_so_far = ""
        workflow_memory = {}
        workflow_result = {}
        stream_failed = False
        workflow_task = None
        sink = WorkflowEventSink()

        def protocol_event(event_type: str, **payload: Any) -> Dict[str, Any]:
            nonlocal sequence
            sequence += 1
            return {
                "id": f"{run_id}:{sequence}",
                "object": "agent.workflow.stream",
                "version": "1.0",
                "type": event_type,
                "run_id": run_id,
                "conversation_id": str(conversation_id),
                "message_id": message_id,
                "sequence": sequence,
                **payload,
            }

        async def run_workflow():
            token = set_event_sink(sink)
            try:
                sink.emit(
                    {
                        "id": message_id,
                        "object": "workflow.event",
                        "type": "workflow.started",
                        "conversation_id": str(conversation_id),
                    }
                )
                final = await workflow.ainvoke(
                    workflow_input,
                    config={"configurable": {"thread_id": str(conversation_id)}},
                )
                sink.emit(
                    {
                        "id": message_id,
                        "object": "workflow.event",
                        "type": "workflow.completed",
                        "summary": summarize_supervisor_state(
                            get_supervisor_state(final)
                        ),
                    }
                )
                return final
            except Exception as exc:
                sink.emit(
                    {
                        "id": message_id,
                        "object": "workflow.event",
                        "type": "workflow.error",
                        "error": str(exc),
                    }
                )
                raise
            finally:
                reset_event_sink(token)
                sink.close()
        
        try:
            yield stream_data(protocol_event("run.started"))
            yield stream_data(
                protocol_event(
                    "message.started",
                    message={"id": message_id, "role": "assistant", "status": "processing"},
                )
            )
            workflow_task = asyncio.create_task(run_workflow())
            while True:
                event = await sink.queue.get()
                if event.get("type") == "_workflow.event_stream.done":
                    break
                yield stream_data(protocol_event("workflow.progress", event=event))
                yield stream_data(event)

            final_state = await workflow_task

            content_so_far, workflow_memory, workflow_result = (
                extract_workflow_outcome(final_state)
            )

            for delta in iter_text_deltas(content_so_far):
                yield stream_data(protocol_event("message.delta", delta=delta))
                data = {
                    "id": message_id,
                    "object": "chat.completion.chunk",
                    "created": int(assistant_message.created_at.timestamp()),
                    "model": runtime_agent.get("model") or "local-agent",
                    "choices": [
                        {
                            "delta": {"content": delta},
                            "index": 0,
                            "finish_reason": None
                        }
                    ]
                }
                yield stream_data(data)
                await asyncio.sleep(0)

            yield stream_data(
                protocol_event(
                    "message.completed",
                    status="completed",
                    metadata={"workflow_result": workflow_result},
                )
            )
            yield stream_data(protocol_event("run.completed"))
            
            # Send final chunk with finish_reason: "stop"
            data = {
                "id": message_id,
                "object": "chat.completion.chunk",
                "created": int(assistant_message.created_at.timestamp()),
                "model": runtime_agent.get("model") or "local-agent",
                "choices": [
                    {
                        "delta": {},
                        "index": 0,
                        "finish_reason": "stop"
                    }
                ]
            }
            yield stream_data(data)
            
        except asyncio.CancelledError:
            if workflow_task is not None and not workflow_task.done():
                workflow_task.cancel()
                with suppress(asyncio.CancelledError):
                    await workflow_task

            async def persist_cancelled_message() -> None:
                async with async_session_factory() as cancel_db:
                    cancelled_message = await ConversationService.update_message_status(
                        db=cancel_db,
                        message_id=assistant_message.id,
                        status=MessageStatus.FAILED,
                        metadata={
                            "final_content": content_so_far,
                            "agent_name": runtime_agent.get("agent_name"),
                            "stream_protocol": "agent.workflow.stream/1.0",
                            "stream_status": "cancelled",
                        },
                    )
                    if cancelled_message is not None:
                        cancelled_message.content = content_so_far
                    await cancel_db.commit()

            persist_task = asyncio.create_task(persist_cancelled_message())
            with suppress(asyncio.CancelledError):
                await asyncio.shield(persist_task)
            raise
        except Exception as e:
            stream_failed = True
            logger.exception("Workflow streaming failed for conversation %s", conversation_id)
            
            # Send error message to the client
            error_msg = f"工作流执行失败：{e}"
            content_so_far = error_msg
            yield stream_data(protocol_event("run.failed", error=str(e)))
            yield stream_data(protocol_event("message.delta", delta=error_msg))
            yield stream_data(
                protocol_event("message.completed", status="failed", error=str(e))
            )
            
            # Format error as a streaming chunk
            data = {
                "id": message_id,
                "object": "chat.completion.chunk",
                "created": int(assistant_message.created_at.timestamp()),
                "model": runtime_agent.get("model") or "local-agent",
                "choices": [
                    {
                        "delta": {"content": error_msg},
                        "index": 0,
                        "finish_reason": "error"
                    }
                ]
            }
            yield stream_data(data)
            
            # Send final chunk
            data = {
                "id": message_id,
                "object": "chat.completion.chunk",
                "created": int(assistant_message.created_at.timestamp()),
                "model": runtime_agent.get("model") or "local-agent",
                "choices": [
                    {
                        "delta": {},
                        "index": 0,
                        "finish_reason": "stop"
                    }
                ]
            }
            yield stream_data(data)
        
        # After streaming is complete (whether success or error), update the message in the database
        
        # Update the message in the database with the complete content
        await ConversationService.update_message_status(
            db=db,
            message_id=assistant_message.id,
            status=MessageStatus.FAILED if stream_failed else MessageStatus.COMPLETED,
            metadata={
                "final_content": content_so_far,
                "agent_name": runtime_agent.get("agent_name"),
                "stream_protocol": "agent.workflow.stream/1.0",
                **({"workflow_memory": workflow_memory} if workflow_memory else {}),
                **({"workflow_result": workflow_result} if workflow_result else {}),
            }
        )
        
        # Update the message content
        assistant_message.content = content_so_far
        await db.commit()
        
        # Log the activity
        await ActivityLogService.log_activity(
            db=db,
            agent_name=runtime_agent.get("agent_name"),
            activity_type=ActivityType.AGENT_MESSAGE,
            description=f"Workflow responded in conversation {conversation_id} (streaming)",
            conversation_id=conversation_id,
            message_id=assistant_message.id,
        )
        
        yield "data: [DONE]\n\n"
    
    return StreamingResponse(
        stream_response(),
        media_type="text/event-stream"
    )
