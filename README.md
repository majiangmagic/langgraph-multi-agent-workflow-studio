# Agent Workflow Kit

可编排智能体后端骨架。用 FastAPI 提供 API，用 PostgreSQL 保存业务数据，用 LangGraph 执行工作流，用 checkpoint 和 store 管理运行记忆，用 SSE 观察工作流执行过程。

它适合想直接改代码、接数据库、接前端、继续扩展 Agent 和 Workflow 的后端项目。

## 核心能力

- FastAPI 后端接口
- Crew / Agent / Conversation / Message 管理
- 统一聊天入口 `POST /api/chat`
- 会话创建、继续对话、删除会话
- PostgreSQL / SQLAlchemy 数据层
- LangGraph workflow 执行
- LangGraph checkpoint 短期记忆
- LangGraph store 长期记忆
- SSE 工作流进度事件
- Agent 代码骨架生成器
- Workflow 代码骨架生成器
- 端到端测试覆盖 crew -> agents -> chat -> messages 入库

## 架构概览

```text
HTTP API
  -> Conversation / Crew / Agent services
  -> WorkflowService
  -> workflow registry
  -> LangGraph workflow
  -> Agent graph
  -> checkpoint / store / events / database messages
```

默认工作流：

```text
supervisor_simple workflow
  node: supervisor
    agent implementation: official_supervisor
      runtime: langgraph-supervisor
```

三个名字分别表示不同层级：

- `supervisor_simple`：工作流名称
- `supervisor`：工作流里的节点名称
- `official_supervisor`：Agent 实现名称

同一个 Agent 实现可以在不同 workflow node 中复用。节点名称负责表达流程位置，Agent 实现负责提供运行逻辑。

## Workflow

Workflow 使用原生 LangGraph 语法组织，目录在：

```text
app/core/langgraph/workflows/
```

默认工作流：

```text
app/core/langgraph/workflows/supervisor_simple/
  __init__.py
  graph.py
  state.py
```

`graph.py` 负责定义 LangGraph 节点和边，`state.py` 负责构造初始 workflow state。

## Agent

Agent 实现目录在：

```text
app/agents/
```

内置 Agent：

```text
app/agents/official_supervisor/
```

Agent 配置来自数据库，workflow 运行时会把对应配置注入到节点 state：

```python
state["system_prompt"]
state["model"]
state["temperature"]
```

## 代码生成

可以用 JSON 描述生成 Agent / Workflow 骨架。

Agent 示例：

[examples/agents/research_agent.json](examples/agents/research_agent.json)

```bash
python scripts/generate_agent.py examples/agents/research_agent.json
```

Workflow 示例：

[examples/workflows/research_pipeline.json](examples/workflows/research_pipeline.json)

```bash
python scripts/generate_workflow.py examples/workflows/research_pipeline.json
```

生成器输出的是可读、可改、可继续维护的 Python 代码。

## 记忆

短期记忆使用 LangGraph checkpoint，挂在 workflow 层。

```python
config={"configurable": {"thread_id": str(conversation.id)}}
```

同一个 `conversation_id` 会复用同一个 checkpoint thread。

长期记忆使用 LangGraph store，按用户隔离：

```text
("memories", user_id)
```

当前写入策略是显式写入：Agent state 中出现 `memory_write` 时才会落库。

## 事件流

`POST /api/conversations/{conversation_id}/chat/stream` 返回 SSE。

事件示例：

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

事件流通过独立运行时事件通道传递：

```text
node -> emit_event(...) -> WorkflowEventSink -> /chat/stream -> SSE
```

## API

主要接口：

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

推荐入口是 `POST /api/chat`：

- 传 `conversation_id`：继续已有会话
- 不传 `conversation_id`：传 `user_id` 和 `crew_id` 创建新会话并发送消息
- 响应会返回 `conversation_id`

## 目录结构

```text
app/
  agents/
    declarative.py
    official_supervisor/
  api/
    routes/
      conversation.py
      crew.py
      storage.py
  core/
    langgraph/
      checkpoint.py
      events.py
      store.py
      workflows/
        declarative.py
        registry.py
        adapters/
        supervisor_simple/
  db/
  models/
  schemas/
  services/

examples/
  agents/
  workflows/

scripts/
  generate_agent.py
  generate_workflow.py

tests/
  api/
  services/
  scripts/
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

常用配置：

```env
DATABASE_URL="postgresql://postgres:postgres@localhost:5432/multiagent_db"
DATABASE_SCHEMA="public"
OPENROUTER_API_KEY="..."
JWT_SECRET_KEY="change-me"
```

### 3. 初始化数据库

```text
database/schema.sql
```

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

1. 创建 crew
2. 给 crew 创建名为 `supervisor` 的 Agent 配置
3. 创建需要参与协作的 Agent 配置
4. 调用 `POST /api/chat`
5. 使用返回的 `conversation_id` 继续对话
6. 用 `GET /api/conversations/{conversation_id}/messages` 查看消息

## 测试

```bash
pytest
```

当前测试覆盖：

- crew service
- agent service
- conversation/chat API
- SSE workflow event
- LangGraph checkpoint 会话链路
- LangGraph store 长期记忆链路
- Agent generator
- Workflow generator
- 端到端 crew -> agents -> chat -> messages 入库

## License

MIT
