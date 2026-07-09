"""
API routes for conversations and chat functionality
"""
from typing import List, Optional, Dict, Any
import uuid
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks, Request
from fastapi.responses import StreamingResponse
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from sqlalchemy.ext.asyncio import AsyncSession
import json

from app.db.base import get_db
from app.models.conversation import MessageRole, MessageStatus
from app.models.activity_log import ActivityType
from app.services.conversation_service import ConversationService, ActivityLogService
from app.services.crew_service import CrewService, AgentService
from app.services.workflow_service import WorkflowService
from app.schemas.crew import CrewResponse, AgentResponse
from app.schemas.conversation import (
    ConversationCreate, 
    ConversationResponse, 
    ConversationUpdate,
    MessageCreate,
    MessageResponse,
    ChatRequest,
    ChatResponse,
    UnifiedChatRequest,
    UnifiedChatResponse,
)


router = APIRouter(prefix="/conversations", tags=["conversations"])
chat_router = APIRouter(tags=["chat"])


def agent_to_workflow_config(agent) -> Dict[str, Any]:
    """Convert a DB agent model into the workflow's simple agent config."""

    return {
        "id": str(agent.id),
        "name": agent.name,
        "description": agent.description,
        "system_prompt": agent.system_prompt,
        "model": agent.model,
        "temperature": agent.temperature,
        "tools": [],
    }


def message_to_langchain_message(message):
    """Convert a stored conversation message into a LangChain message."""

    if message.role == MessageRole.USER:
        return HumanMessage(content=message.content)
    if message.role in (MessageRole.ASSISTANT, MessageRole.AGENT):
        return AIMessage(content=message.content)
    if message.role == MessageRole.SYSTEM:
        return SystemMessage(content=message.content)
    return None


def extract_workflow_response(final_state: Dict[str, Any]) -> str:
    """Get the last supervisor AI message from a completed workflow run."""

    supervisor_state = final_state.get("supervisor", {})
    for message in reversed(supervisor_state.get("messages", [])):
        if isinstance(message, AIMessage):
            return str(message.content)

    return "Workflow completed without an assistant response."


async def build_workflow_for_conversation(
    db: AsyncSession,
    conversation,
    user_message,
):
    """Create the configured workflow and initial state for a conversation turn."""

    crew = await CrewService.get_crew(db, conversation.crew_id)
    if not crew:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Crew with ID {conversation.crew_id} not found",
        )

    agents = await AgentService.get_agents(db, crew_id=crew.id)
    supervisor = next((agent for agent in agents if agent.is_supervisor), None)
    if not supervisor:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"No supervisor agent found for crew {crew.id}",
        )

    messages = await ConversationService.get_messages(db, conversation.id)
    history_messages = []
    for message in messages:
        if message.id == user_message.id:
            continue

        langchain_message = message_to_langchain_message(message)
        if langchain_message is not None:
            history_messages.append(langchain_message)

    delegated_agents = [
        agent_to_workflow_config(agent)
        for agent in agents
        if not agent.is_supervisor
    ]
    workflow, initial_state = WorkflowService.create_workflow_run(
        crew=crew,
        agents=delegated_agents,
        conversation_id=str(conversation.id),
        messages=history_messages[-10:],
        user_input=user_message.content,
        system_prompt=supervisor.system_prompt,
    )

    return workflow, initial_state, supervisor


async def run_chat_turn(
    db: AsyncSession,
    conversation,
    message: str,
) -> ChatResponse:
    """Persist a user message, run the workflow, and persist the assistant reply."""

    user_message = await ConversationService.add_message(
        db=db,
        conversation_id=conversation.id,
        role=MessageRole.USER,
        content=message,
        status=MessageStatus.COMPLETED,
    )

    workflow, initial_state, supervisor = await build_workflow_for_conversation(
        db, conversation, user_message
    )

    try:
        final_state = await workflow.ainvoke(initial_state)
        response_content = extract_workflow_response(final_state)
    except Exception as e:
        print(f"Error running supervisor workflow: {str(e)}")
        response_content = (
            "I apologize, but I encountered an issue processing your request. "
            "Please try again later."
        )

    assistant_message = await ConversationService.add_message(
        db=db,
        conversation_id=conversation.id,
        role=MessageRole.ASSISTANT,
        content=response_content,
        agent_id=supervisor.id,
        parent_id=user_message.id,
        status=MessageStatus.COMPLETED,
    )

    await ActivityLogService.log_activity(
        db=db,
        agent_id=supervisor.id,
        activity_type=ActivityType.AGENT_MESSAGE,
        description=f"Supervisor responded in conversation {conversation.id}",
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
    return None


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
        agent_id=message.agent_id,
        parent_id=message.parent_id,
        status=message.status,
        metadata=message.metadata,
    )
    
    # Log activity if it's an agent message
    if message.role == MessageRole.AGENT and message.agent_id:
        await ActivityLogService.log_activity(
            db=db,
            agent_id=message.agent_id,
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

    return await run_chat_turn(db, conversation, chat_request.message)


@chat_router.post("/chat", response_model=UnifiedChatResponse)
async def unified_chat(
    chat_request: UnifiedChatRequest,
    db: AsyncSession = Depends(get_db),
):
    """Create a conversation when needed, then send one chat message."""

    conversation = await get_or_create_chat_conversation(db, chat_request)
    chat_response = await run_chat_turn(db, conversation, chat_request.message)
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
    )

    workflow, initial_state, supervisor = await build_workflow_for_conversation(
        db, conversation, user_message
    )
    
    # Create a placeholder for assistant message
    assistant_message = await ConversationService.add_message(
        db=db,
        conversation_id=conversation_id,
        role=MessageRole.ASSISTANT,
        content="",
        agent_id=supervisor.id,
        parent_id=user_message.id,
        status=MessageStatus.PROCESSING,
    )
    
    # Stream the configured workflow result as SSE.
    async def stream_response():
        message_id = str(assistant_message.id)
        content_so_far = ""
        
        try:
            final_state = await workflow.ainvoke(initial_state)
            content_so_far = extract_workflow_response(final_state)

            data = {
                "id": message_id,
                "object": "chat.completion.chunk",
                "created": int(assistant_message.created_at.timestamp()),
                "model": supervisor.model,
                "choices": [
                    {
                        "delta": {"content": content_so_far},
                        "index": 0,
                        "finish_reason": None
                    }
                ]
            }
            yield f"data: {json.dumps(data)}\n\n"
            
            # Send final chunk with finish_reason: "stop"
            data = {
                "id": message_id,
                "object": "chat.completion.chunk",
                "created": int(assistant_message.created_at.timestamp()),
                "model": supervisor.model,
                "choices": [
                    {
                        "delta": {},
                        "index": 0,
                        "finish_reason": "stop"
                    }
                ]
            }
            yield f"data: {json.dumps(data)}\n\n"
            
        except Exception as e:
            # Log the error
            print(f"Error during streaming response: {str(e)}")
            
            # Send error message to the client
            error_msg = "I apologize, but I encountered an issue processing your request. Please try again later."
            content_so_far = error_msg
            
            # Format error as a streaming chunk
            data = {
                "id": message_id,
                "object": "chat.completion.chunk",
                "created": int(assistant_message.created_at.timestamp()),
                "model": supervisor.model,
                "choices": [
                    {
                        "delta": {"content": error_msg},
                        "index": 0,
                        "finish_reason": "error"
                    }
                ]
            }
            yield f"data: {json.dumps(data)}\n\n"
            
            # Send final chunk
            data = {
                "id": message_id,
                "object": "chat.completion.chunk",
                "created": int(assistant_message.created_at.timestamp()),
                "model": supervisor.model,
                "choices": [
                    {
                        "delta": {},
                        "index": 0,
                        "finish_reason": "stop"
                    }
                ]
            }
            yield f"data: {json.dumps(data)}\n\n"
        
        # After streaming is complete (whether success or error), update the message in the database
        
        # Update the message in the database with the complete content
        await ConversationService.update_message_status(
            db=db,
            message_id=assistant_message.id,
            status=MessageStatus.COMPLETED,
            metadata={"final_content": content_so_far}
        )
        
        # Update the message content
        assistant_message.content = content_so_far
        await db.commit()
        
        # Log the activity
        await ActivityLogService.log_activity(
            db=db,
            agent_id=supervisor.id,
            activity_type=ActivityType.AGENT_MESSAGE,
            description=f"Supervisor responded in conversation {conversation_id} (streaming)",
            conversation_id=conversation_id,
            message_id=assistant_message.id,
        )
        
        yield "data: [DONE]\n\n"
    
    return StreamingResponse(
        stream_response(),
        media_type="text/event-stream"
    )
