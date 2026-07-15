"""
API routes for conversations and chat functionality
"""
import asyncio
import logging
from typing import List, Optional, Dict, Any
import uuid
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks, Request
from fastapi.responses import StreamingResponse
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from sqlalchemy.ext.asyncio import AsyncSession
import json

from app.db.base import get_db
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
    """提取跨轮规范状态，不保存运行时 Prompt 或模型配置。"""

    for node_state in (final_state.get("nodes") or {}).values():
        contract = node_state.get("request_contract")
        if isinstance(contract, dict) and contract.get("resolved_request"):
            return {
                "request_contract": contract,
                "resolved_user_request": node_state.get("resolved_user_request")
                or contract["resolved_request"],
            }
    return {}


def get_supervisor_state(final_state: Dict[str, Any]) -> Dict[str, Any]:
    """Read supervisor state from the current or legacy workflow shape."""

    return final_state.get("nodes", {}).get("supervisor") or final_state.get(
        "supervisor", {}
    )


def stream_data(data: Dict[str, Any]) -> str:
    """Serialize one server-sent event payload."""

    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


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

    try:
        history_messages = await get_short_term_history(db, conversation.id)
        workflow, initial_state = WorkflowService.create_workflow_run(
            crew=crew,
            conversation_id=str(conversation.id),
            user_id=conversation.user_id,
            user_input=user_message.content,
            messages=history_messages,
            workflow_inputs=workflow_inputs,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    workflow_type = WorkflowService.get_workflow_type(crew)
    metadata = workflow_registry.get_metadata(workflow_type, fallback=False)
    entrypoint = str(metadata.get("entrypoint") or "")
    node_states = initial_state.get("nodes") or {}
    runtime_agent = node_states.get(entrypoint) or next(
        iter(node_states.values()), {}
    )
    return workflow, initial_state, runtime_agent


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
        response_content = extract_workflow_response(final_state)
        workflow_memory = extract_workflow_memory(final_state)
    except Exception as e:
        print(f"Error running supervisor workflow: {str(e)}")
        response_content = (
            "I apologize, but I encountered an issue processing your request. "
            "Please try again later."
        )
        workflow_memory = {}

    assistant_message = await ConversationService.add_message(
        db=db,
        conversation_id=conversation.id,
        role=MessageRole.ASSISTANT,
        content=response_content,
        parent_id=user_message.id,
        status=MessageStatus.COMPLETED,
        metadata={
            **({"workflow_memory": workflow_memory} if workflow_memory else {}),
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
    
    # Add user message to conversation
    user_message = await ConversationService.add_message(
        db=db,
        conversation_id=conversation_id,
        role=MessageRole.USER,
        content=chat_request.message,
        status=MessageStatus.COMPLETED,
        metadata={"workflow_inputs": chat_request.workflow_inputs}
        if chat_request.workflow_inputs
        else {},
    )

    workflow, initial_state, runtime_agent = await build_workflow_for_conversation(
        db, conversation, user_message, chat_request.workflow_inputs
    )
    
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
        content_so_far = ""
        workflow_memory = {}
        sink = WorkflowEventSink()

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
                    initial_state,
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
            workflow_task = asyncio.create_task(run_workflow())
            while True:
                event = await sink.queue.get()
                if event.get("type") == "_workflow.event_stream.done":
                    break
                yield stream_data(event)

            final_state = await workflow_task

            content_so_far = extract_workflow_response(final_state)
            workflow_memory = extract_workflow_memory(final_state)

            data = {
                "id": message_id,
                "object": "chat.completion.chunk",
                "created": int(assistant_message.created_at.timestamp()),
                "model": runtime_agent.get("model") or "local-agent",
                "choices": [
                    {
                        "delta": {"content": content_so_far},
                        "index": 0,
                        "finish_reason": None
                    }
                ]
            }
            yield stream_data(data)
            
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
            
        except Exception as e:
            logger.exception("Workflow streaming failed for conversation %s", conversation_id)
            
            # Send error message to the client
            error_msg = f"工作流执行失败：{e}"
            content_so_far = error_msg
            
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
            status=MessageStatus.COMPLETED,
            metadata={
                "final_content": content_so_far,
                "agent_name": runtime_agent.get("agent_name"),
                **({"workflow_memory": workflow_memory} if workflow_memory else {}),
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
