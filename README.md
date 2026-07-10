# LangGraph 多 Agent 工作流后端模板

这是一个面向二次开发的 LangGraph 多 Agent 工作流后端模板。

项目目标不是只做一个固定的 `supervisor_simple` 工作流，而是构建一套可以持续扩展的工作流系统：用 FastAPI 提供 API，用数据库管理 crew/agent/conversation/message，用 LangGraph 执行工作流，用 checkpoint 承载短期记忆，并逐步让 Agent 和 Workflow 都可以通过 DSL 生成代码骨架。

当前项目已经从“手写 supervisor demo”推进到“声明式工作流 + 声明式 Agent + 代码生成骨架”的阶段。

## 当前定位

这个仓库适合用来构建：

- 主脑 Supervisor + 多个真实子 Agent 的工作流系统
- 可通过 API 调用的多 Agent 后端
- 可持久化会话、消息、活动日志的 Agent 平台底座
- 可由 DSL 生成 Agent / Workflow 骨架的工程模板
- 未来可接可视化编排界面的工作流运行时

它不是 Dify、Flowise、Langflow 这类完整产品的替代品。它更偏代码优先、后端优先、可控性优先。

## 已有能力

- FastAPI 后端接口
- Crew / Agent / Conversation / Message 管理
- 统一聊天入口 `POST /api/chat`
- 会话创建、继续对话、删除会话
- 删除会话时清理对应 LangGraph checkpoint thread
- 默认工作流 `supervisor_simple`
- Agent 实现 `official_supervisor`
- Supervisor 内部使用官方 `langgraph-supervisor`
- 短期记忆使用 LangGraph checkpoint，挂在 workflow 层
- 工作流运行进度 SSE 事件流
- Agent DSL 代码生成器
- Workflow DSL 代码生成器
- PostgreSQL / SQLAlchemy 数据层
- 端到端测试覆盖 crew -> agents -> chat -> messages 入库

## 核心架构

```text
HTTP API
  -> Conversation / Crew / Agent services
  -> WorkflowService
  -> workflow registry
  -> declarative workflow
  -> declarative agent graph
  -> LangGraph checkpoint / events / database messages
```

当前默认工作流：

```text
supervisor_simple workflow
  node: supervisor
    agent implementation: official_supervisor
      internal node: official_supervisor
        runtime: langgraph-supervisor
```

这里要区分三个概念：

- `supervisor_simple`：工作流模板名
- `supervisor`：工作流里的节点实例名
- `official_supervisor`：Agent 实现名

同一个 Agent 实现可以被多个不同 workflow node 复用。例如一个工作流里可以有 `planner` 和 `reviewer` 两个节点，它们都使用 `official_supervisor` 实现，但读取不同的数据库 Agent 配置。

## 声明式 Workflow

工作流现在可以被机械化描述。示例见：

[examples/workflows/research_pipeline.json](examples/workflows/research_pipeline.json)

```json
{
  "version": 1,
  "kind": "workflow",
  "name": "research_pipeline",
  "entrypoint": "planner",
  "nodes": {
    "planner": {
      "agent": "official_supervisor",
      "extension": "supervisor"
    },
    "researcher": {
      "agent": "research_agent"
    },
    "reviewer": {
      "agent": "official_supervisor",
      "state_agent": "review_supervisor",
      "extension": "supervisor"
    }
  },
  "edges": [
    { "from": "planner", "to": "researcher" },
    { "from": "researcher", "to": "reviewer" },
    { "from": "reviewer", "to": "END" }
  ]
}
```

生成 workflow 骨架：

```bash
python scripts/generate_workflow.py examples/workflows/research_pipeline.json
```

默认输出到：

```text
app/core/langgraph/workflows/<workflow_name>/
  __init__.py
  graph.py
  spec.py
  state.py
```

测试中不会写真实目录，测试会把输出目录替换成临时目录。

## 声明式 Agent

Agent 也可以用 DSL 生成骨架。示例见：

[examples/agents/research_agent.json](examples/agents/research_agent.json)

```json
{
  "version": 1,
  "kind": "agent",
  "name": "research_agent",
  "display_name": "Research Agent",
  "config": {
    "prompt": "You are a research agent. Search carefully and summarize useful findings.",
    "model": "openai/gpt-4.1",
    "temperature": 0.2
  },
  "state": {
    "query": { "type": "string", "optional": true },
    "search_results": { "type": "list", "optional": true },
    "answer": { "type": "string", "optional": true }
  },
  "entrypoint": "search",
  "nodes": {
    "search": { "handler": "search_node" },
    "summarize": { "handler": "summarize_node" }
  },
  "edges": [
    { "from": "search", "to": "summarize" },
    { "from": "summarize", "to": "END" }
  ]
}
```

生成 Agent 骨架：

```bash
python scripts/generate_agent.py examples/agents/research_agent.json
```

默认输出到：

```text
app/agents/<agent_name>/
  __init__.py
  graph.py
  spec.py
  state.py
  nodes.py
  config_defaults.json
```

`config.prompt / model / temperature` 是数据库配置的默认种子，不是业务代码里的硬编码 prompt。运行时 workflow 会把数据库里的 Agent 配置注入到 state，业务节点可以读取：

```python
state["system_prompt"]
state["model"]
state["temperature"]
```

### 节点刷新规则

生成器会在 `nodes.py` 里生成中文注释，并按 DSL 节点名维护代码块：

- 节点名不变：刷新骨架时保留对应业务逻辑
- DSL 新增节点：追加新的节点骨架
- DSL 删除节点：删除对应代码块，即使里面有人写过业务代码
- 节点名是稳定 ID，不要随意改名

这意味着 DSL 是结构源头，业务逻辑写在节点代码块里。

## 短期记忆

短期记忆使用官方 LangGraph checkpoint，并挂在 workflow 层，而不是某个单独 Agent 私有层。

调用 workflow 时使用 conversation id 作为 checkpoint thread：

```python
config={"configurable": {"thread_id": str(conversation.id)}}
```

因此同一个 `conversation_id` 的多轮对话会复用同一个 checkpoint thread。程序重启后，如果 checkpoint 后端仍在，就可以继续会话。

数据库中的 message 仍然保留，用于产品层展示、审计、检索和活动记录；短期运行态主要由 checkpoint 承担。

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
- 不传 `conversation_id`：需要传 `user_id` 和 `crew_id`，后端会先创建会话再发送消息
- 响应会返回 `conversation_id`，前端可继续对话

## 流式事件

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

事件流通过独立运行时事件通道实现，不写进 LangGraph state：

```text
node -> emit_event(...) -> WorkflowEventSink -> /chat/stream -> SSE
```

## 目录结构

```text
app/
  agents/
    declarative.py              # AgentDefinition / AgentNodeSpec / Agent compiler
    official_supervisor/        # 官方 supervisor 引擎适配 Agent
  api/
    routes/
      conversation.py           # Conversation 和 chat API
      crew.py                   # Crew 和 Agent API
      storage.py                # Storage API
  core/
    langgraph/
      checkpoint.py             # LangGraph checkpoint 后端
      events.py                 # workflow event sink
      workflows/
        declarative.py          # WorkflowDefinition / WorkflowNodeSpec / Workflow compiler
        registry.py             # Workflow registry
        adapters/               # Agent graph / supervisor adapter
        supervisor_simple/      # 默认 workflow
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

至少需要配置：

```env
DATABASE_URL="postgresql://postgres:postgres@localhost:5432/multiagent_db"
DATABASE_SCHEMA="public"
OPENROUTER_API_KEY="..."
JWT_SECRET_KEY="change-me"
```

### 3. 初始化数据库

可以使用 [database/schema.sql](database/schema.sql) 初始化 PostgreSQL schema，也可以在本地开发时使用 SQLAlchemy metadata 建表。

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

1. 创建一个 crew
2. 给 crew 创建名为 `supervisor` 的 Agent 配置
3. 可选：创建其他 worker Agent 配置
4. 调用 `POST /api/chat`
5. 使用返回的 `conversation_id` 继续对话
6. 用 `GET /api/conversations/{conversation_id}/messages` 查看入库消息
7. 删除 conversation 时，对应 checkpoint thread 会被清理

当前真实 worker Agent executor 还没有全面接入。如果 `official_supervisor` 决定委派给某个尚未接入真实 executor 的 Agent，系统会诚实返回该 Agent 尚未连接真实执行器，而不会伪造执行结果。

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
- Agent DSL generator
- Workflow DSL generator
- 端到端 crew -> agents -> chat -> messages 入库

## 下一步方向

- 将 DSL 的 prompt/model/temperature 同步到数据库 Agent 配置
- 增加更多真实 Agent executor
- 支持 workflow 条件边和路由节点
- 将 workflow DSL 作为未来可视化编排界面的导出格式
- 移除旧的 `is_supervisor` 单主控假设，让流程图完全由节点和连接关系表达

## 许可证

MIT
