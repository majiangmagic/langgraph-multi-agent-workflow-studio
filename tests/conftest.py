"""
Test configuration and fixtures
"""
import asyncio
import pytest
import pytest_asyncio
import uuid
import os
from typing import AsyncGenerator, Dict
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient
from dotenv import load_dotenv

# Load test environment variables
load_dotenv(".env.test", override=True)
os.environ["DATABASE_SCHEMA"] = os.getenv("DATABASE_SCHEMA", "")

from app.db.base import Base, get_db
from app.main import app
from app.core.config import settings
from app.models.crew import Crew, Agent, MCPServer, MCPTool
from app.models.conversation import Conversation, Message, MessageRole, MessageStatus


# Use in-memory SQLite for local tests, PostgreSQL for CI
# Check if we're running in CI by looking# Get database URL from environment or use SQLite in-memory as default
TEST_DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

# Ensure we're using the right async driver for PostgreSQL
test_database_url = make_url(TEST_DATABASE_URL)
if test_database_url.drivername in {"postgres", "postgresql", "postgresql+asyncpg"}:
    # Use asyncpg for PostgreSQL without touching username/password text.
    TEST_DATABASE_URL = str(test_database_url.set(drivername="postgresql+asyncpg"))
    print(f"Using database URL for tests: {make_url(TEST_DATABASE_URL).render_as_string(hide_password=True)}")
else:
    print(f"Using database URL for tests: {TEST_DATABASE_URL}")


# Create a test engine and session factory
test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)
TestingSessionLocal = sessionmaker(
    bind=test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


# Override get_db with test session
async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
    """Get a test database session"""
    async with TestingSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


@pytest_asyncio.fixture
async def setup_test_db():
    """Set up a test database with tables"""
    # For SQLite in-memory, create tables and drop them after tests
    if 'sqlite' in TEST_DATABASE_URL:
        # Create all tables
        async with test_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        
        yield
        
        # Drop all tables
        async with test_engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
    else:
        # For PostgreSQL in CI, tables are created by the GitHub workflow script
        # We'll truncate tables after tests to keep the DB clean
        yield
        
        # Clean up data but keep tables
        try:
            async with test_engine.begin() as conn:
                # Get all table names
                tables = Base.metadata.tables.keys()
                for table in tables:
                    # Use truncate instead of drop
                    await conn.execute(text(f"TRUNCATE TABLE {table} CASCADE"))
        except Exception as e:
            print(f"Error cleaning up tables: {e}")
            # Continue without failing tests


@pytest_asyncio.fixture
async def db_session(setup_test_db) -> AsyncGenerator[AsyncSession, None]:
    """Yield a test database session"""
    async with TestingSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


@pytest.fixture
def test_client(db_session) -> TestClient:
    """Create a test client with test database session"""
    app.dependency_overrides[get_db] = lambda: db_session
    with TestClient(app) as client:
        yield client


@pytest.fixture
def event_loop():
    """Create an event loop for async tests"""
    policy = asyncio.get_event_loop_policy()
    loop = policy.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture
async def test_crew(db_session) -> Crew:
    """Create a test crew in the database"""
    crew = Crew(
        name="Test Crew",
        description="A crew for testing",
        settings={"test": True},
    )
    db_session.add(crew)
    await db_session.commit()
    await db_session.refresh(crew)
    return crew


@pytest_asyncio.fixture
async def test_mcp_server(db_session) -> MCPServer:
    """Create a test MCP server in the database"""
    mcp_server = MCPServer(
        name="Test MCP Server",
        url="http://test-mcp-server.example.com",
        description="A MCP server for testing",
        settings={"test": True},
    )
    db_session.add(mcp_server)
    await db_session.commit()
    await db_session.refresh(mcp_server)
    return mcp_server


@pytest_asyncio.fixture
async def test_mcp_tool(db_session, test_mcp_server) -> MCPTool:
    """Create a test MCP tool in the database"""
    tool = MCPTool(
        mcp_server_id=test_mcp_server.id,
        name="test-tool",
        description="A tool for testing",
        parameters_schema={"param1": "string", "param2": "number"},
    )
    db_session.add(tool)
    await db_session.commit()
    await db_session.refresh(tool)
    return tool


@pytest_asyncio.fixture
async def test_agent(db_session, test_crew) -> Agent:
    """Create a test agent in the database"""
    agent = Agent(
        crew_id=test_crew.id,
        name="Test Agent",
        description="An agent for testing",
        system_prompt="You are a test agent",
        model="test-model",
        is_supervisor=True,
        settings={"test": True},
    )
    db_session.add(agent)
    await db_session.commit()
    await db_session.refresh(agent)
    return agent


@pytest_asyncio.fixture
async def test_conversation(db_session, test_crew) -> Conversation:
    """Create a test conversation in the database"""
    conversation = Conversation(
        user_id="test-user",
        crew_id=test_crew.id,
        title="Test Conversation",
        meta_data={"test": True},
    )
    db_session.add(conversation)
    await db_session.commit()
    await db_session.refresh(conversation)
    return conversation


@pytest_asyncio.fixture
async def test_message(db_session, test_conversation, test_agent) -> Message:
    """Create a test message in the database"""
    message = Message(
        conversation_id=test_conversation.id,
        role=MessageRole.AGENT,
        content="This is a test message",
        agent_id=test_agent.id,
        status=MessageStatus.COMPLETED,
        meta_data={"test": True},
    )
    db_session.add(message)
    await db_session.commit()
    await db_session.refresh(message)
    return message


@pytest.fixture
def auth_headers() -> Dict[str, str]:
    """Generate test authentication headers"""
    from jose import jwt
    
    # Create a test token
    token_payload = {
        "sub": "test-user",
        "exp": 9999999999  # Far future expiration
    }
    token = jwt.encode(
        token_payload,
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm
    )
    
    return {"Authorization": f"Bearer {token}"}
