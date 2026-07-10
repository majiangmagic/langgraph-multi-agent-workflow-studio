# LangGraph 多 Agent 工作流后端模板

这是一个轻量、代码优先的 LangGraph 多 Agent 工作流后端模板。

项目提供一套清晰的后端骨架：用 FastAPI 提供 API，用 PostgreSQL 保存会话和配置，用 LangGraph 执行工作流，用事件流观察运行过程。整体设计偏工程化，方便继续扩展自己的 Agent、Workflow 和工具调用能力。

## 当前能力

- FastAPI 后端接口
- Crew / Agent / Conversation / Message 管理
- 统一聊天入口 `POST /api/chat`
- `chat` 请求接入 `supervisor_simple` 工作流
- Supervisor 内部使用官方 `langgraph-supervisor` 引擎
- 工作流运行进度事件流
- PostgreSQL 主数据库
- SQLAlchemy 模型和 service 层
- 端到端测试：创建 crew/agent -> chat -> message 入库

## 当前架构

```text
HTTP API
  -> Conversation / Crew / Agent services
  -> WorkflowService
  -> supervisor_simple workflow
  -> supervisor agent graph
  -> messages / activity logs
```

`supervisor_simple` 是当前默认工作流。它内部运行一个 supervisor agent graph：

```text
supervisor_simple workflow
  -> supervisor shell graph
  -> official langgraph-supervisor runtime
  -> delegated agent graph adapters
```

也就是说，项目保留自己的 API、数据库、workflow registry、state adapter 和事件流外壳；Supervisor 的内部编排交给官方 `langgraph-supervisor`。当前 worker agent 还没有真实 `AgentExecutor`，因此如果官方 Supervisor 决定委派任务，系统会诚实返回“该 agent 尚未接入真实 executor”，不会伪造执行结果。

## API 接口

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

- 传 `conversation_id`：继续已有会话。
- 不传 `conversation_id`：需要传 `user_id` 和 `crew_id`，后端会先创建会话再发送消息。
- 响应会返回 `conversation_id`，方便前端继续对话。

## 流式事件

`POST /api/conversations/{conversation_id}/chat/stream` 返回 SSE。

前端可以通过事件流观察工作流运行过程：

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

事件流通过独立的运行时事件通道实现，不污染 LangGraph state：

```text
node -> emit_event(...) -> WorkflowEventSink -> /chat/stream -> SSE
```

## 目录结构

```text
app/
  agents/
    supervisor/              # Supervisor shell、official runtime adapter、state
  api/
    routes/
      conversation.py        # Conversation 和 chat API
      crew.py                # Crew 和 Agent API
      storage.py             # Storage API
  core/
    langgraph/
      events.py              # 运行时 workflow event sink
      workflows/
        registry.py          # Workflow registry
        supervisor_simple/   # 当前默认工作流
        adapters/            # Agent graph / workflow adapter
  db/                        # SQLAlchemy base 和 session
  models/                    # Crew、Agent、Conversation、ActivityLog
  schemas/                   # Pydantic schemas
  services/                  # Crew、Conversation、Workflow、AI Provider

database/
  schema.sql                 # PostgreSQL schema 归档

tests/
  api/
    test_chat_e2e.py         # 端到端 API 工作流测试
  services/
```

## 快速开始

### 1. 创建环境

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

### 2. 配置环境变量

```bash
copy .env.example .env
```

至少需要配置：

```env
DATABASE_URL="postgresql://postgres:postgres@localhost:5432/multiagent_db"
DATABASE_SCHEMA="public"
OPENROUTER_API_KEY="..."
JWT_SECRET_KEY="change-me"
```

### 3. 初始化数据库

可以使用 `database/schema.sql` 初始化 PostgreSQL schema，也可以在本地开发时用 SQLAlchemy metadata 创建表。

### 4. 启动服务

```bash
uvicorn app.main:app --reload
```

接口文档：

```text
http://localhost:8000/api/docs
http://localhost:8000/api/redoc
```

## 最小使用流程

1. 创建一个 crew。
2. 给 crew 创建一个 supervisor agent。
3. 给 crew 创建一个或多个 worker agent。
4. 调用 `POST /api/chat`。
5. 用 `GET /api/conversations/{conversation_id}/messages` 查看入库消息。

端到端测试覆盖了这条路径，并且不会调用真实模型。

## 测试

```bash
pytest
```

当前测试覆盖：

- crew service
- agent service
- conversation/chat API
- 接入 workflow 的 chat 路径
- SSE 工作流进度事件
- 端到端 crew -> agents -> chat -> messages 入库

## 项目定位

这个仓库适合作为一个可控的 LangGraph 多 Agent 工作流后端模板。

它不试图替代 Dify、Flowise、Langflow 这类完整平台。目标更小，也更代码优先：

```text
清晰的后端结构
显式 workflow registry
简单的 agent/workflow 组合方式
数据库持久化会话
可观察的工作流进度
方便 fork 和二次开发
```

## 许可证

MIT
