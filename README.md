# LangGraph Multi-Agent Workflow Template

一个轻量、代码优先的 LangGraph 多 Agent 工作流后端模板。

这个项目不是 Dify / Flowise / Langflow 那种大平台，也不是生产级成品。它的定位更直接：用 FastAPI、PostgreSQL 和 LangGraph 搭一个能看懂、能改、能继续扩展的多 Agent workflow backend。

当前已经打通了 API、数据库、Supervisor workflow、SSE 进度事件和端到端测试。真实子 Agent 执行器、MCP 工具闭环和 Alembic 迁移还在后续路线里。

## What It Does

- 提供 FastAPI 后端接口
- 管理 crew、agent、conversation、message
- 支持统一聊天入口 `POST /api/chat`
- 将 chat 请求接入 `supervisor_simple` LangGraph workflow
- 支持 workflow 运行进度事件流
- 使用 PostgreSQL 作为主数据库
- 提供 SQLAlchemy 模型和 service 层
- 包含端到端测试：创建 crew/agent -> chat -> message 入库

## Current Architecture

```text
HTTP API
  -> Conversation / Crew / Agent services
  -> WorkflowService
  -> supervisor_simple workflow
  -> supervisor agent graph
  -> messages / activity logs
```

`supervisor_simple` 当前是默认 workflow。它内部运行一个 supervisor agent graph：

```text
analyze_input
  -> answer_directly
  -> create_plan
  -> assign_tasks
  -> check_status
  -> combine_results
```

简单问题会由 Supervisor 直接回答。复杂问题会进入计划和任务分配流程。

目前还没有真实 `AgentExecutor`，所以当任务分配给子 Agent 后，`check_status` 会明确返回错误，而不是用默认 LLM 假装子 Agent 已经执行。

## API

已挂载的主要接口：

```text
GET    /api/health

GET    /api/crews/
POST   /api/crews/
GET    /api/crews/{crew_id}
PUT    /api/crews/{crew_id}
DELETE /api/crews/{crew_id}

GET    /api/agents/
POST   /api/agents/
GET    /api/agents/{agent_id}
PUT    /api/agents/{agent_id}
DELETE /api/agents/{agent_id}

GET    /api/conversations/
POST   /api/conversations/
GET    /api/conversations/{conversation_id}
PUT    /api/conversations/{conversation_id}
DELETE /api/conversations/{conversation_id}
GET    /api/conversations/{conversation_id}/messages
POST   /api/conversations/{conversation_id}/messages
POST   /api/conversations/{conversation_id}/chat
POST   /api/conversations/{conversation_id}/chat/stream

POST   /api/chat
```

`POST /api/chat` 是推荐入口：

- 如果传 `conversation_id`，继续已有会话。
- 如果不传 `conversation_id`，需要传 `user_id` 和 `crew_id`，后端会先创建会话再发送消息。
- 响应会返回 `conversation_id`，方便前端继续对话。

## Streaming Events

`POST /api/conversations/{conversation_id}/chat/stream` 会返回 SSE。

它现在不是 token-by-token streaming，而是 workflow progress event stream。也就是说，前端可以看到 workflow 跑到了哪一步：

```text
workflow.started
workflow.node.started
workflow.node.completed
workflow.task.assigned
workflow.agent.error
workflow.completed
chat.completion.chunk
[DONE]
```

事件流通过独立的 runtime event channel 实现，不污染 LangGraph state。

```text
node -> emit_event(...) -> WorkflowEventSink -> /chat/stream -> SSE
```

## Project Structure

```text
app/
  agents/
    supervisor/              # Supervisor agent graph, state, nodes, prompts
  api/
    routes/
      conversation.py        # Conversation and chat APIs
      crew.py                # Crew and Agent APIs
      storage.py             # Storage APIs, not yet mounted
  core/
    langgraph/
      events.py              # Runtime workflow event sink
      workflows/
        registry.py          # Workflow registry
        supervisor_simple/   # Current default workflow
        adapters/            # Agent graph / workflow adapter
  db/                        # SQLAlchemy base and session
  models/                    # Crew, Agent, Conversation, ActivityLog
  schemas/                   # Pydantic schemas
  services/                  # Crew, Conversation, Workflow, AI Provider

database/
  schema.sql                 # PostgreSQL schema archive

tests/
  api/
    test_chat_e2e.py         # End-to-end API workflow test
  services/
```

## Quick Start

### 1. Create environment

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure env

```bash
copy .env.example .env
```

Required values:

```env
DATABASE_URL="postgresql://postgres:postgres@localhost:5432/multiagent_db"
DATABASE_SCHEMA="public"
OPENROUTER_API_KEY="..."
JWT_SECRET_KEY="change-me"
```

### 3. Initialize database

There is no Alembic migration flow yet. For local development, create tables from SQLAlchemy metadata or import `database/schema.sql`.

### 4. Run server

```bash
uvicorn app.main:app --reload
```

Docs:

```text
http://localhost:8000/api/docs
http://localhost:8000/api/redoc
```

## Minimal Flow

1. Create a crew.
2. Create a supervisor agent for that crew.
3. Create one or more worker agents.
4. Call `POST /api/chat`.
5. Inspect persisted messages with `GET /api/conversations/{conversation_id}/messages`.

The E2E test covers this path without calling a real model.

## Tests

```bash
pytest
```

Current test coverage includes:

- crew service
- agent service
- conversation/chat API
- workflow-backed chat path
- SSE workflow progress events
- end-to-end crew -> agents -> chat -> messages persistence

## Current Limits

- No real `AgentExecutor` yet.
- Worker agents do not actually execute delegated tasks yet.
- MCP tool execution is not wired into agent execution yet.
- `chat/stream` emits workflow progress events, not token-by-token model output.
- Alembic migrations are not set up as the main schema workflow yet.
- Auth/security is still starter-level.
- Storage routes exist but are not mounted in `app/main.py`.

## Roadmap

- Add a real `AgentExecutor`.
- Load worker agent config by `agent_id`.
- Support simple LLM agent execution first.
- Add MCP tool execution.
- Support worker agents backed by their own LangGraph graphs.
- Upgrade stream events with agent started/completed and tool call events.
- Add Alembic migrations.
- Add trace persistence for workflow events.
- Harden auth, errors, and deployment config.

## Positioning

This repository is best treated as a lightweight backend template for building a controllable LangGraph multi-agent workflow system.

It is not trying to replace full platforms like Dify, Flowise, or Langflow. The goal is smaller and more code-first:

```text
clear backend structure
explicit workflow registry
simple agent/workflow composition
database-backed conversations
observable workflow progress
easy to fork and modify
```

## License

MIT
