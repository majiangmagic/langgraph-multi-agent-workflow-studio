# Agent Workflow Kit

可编排智能体后端骨架。用 FastAPI 提供 API，用 PostgreSQL 保存业务数据，用 LangGraph 执行工作流，用 checkpoint 和 store 管理运行记忆，用 SSE 观察工作流执行过程。

它适合想直接改代码、接数据库、接前端、继续扩展 Agent 和 Workflow 的后端项目。

## 核心能力

- FastAPI 后端接口
- Crew / Conversation / Message 管理
- 统一聊天入口 `POST /api/chat`
- 会话创建、继续对话、删除会话
- PostgreSQL / SQLAlchemy 数据层
- LangGraph workflow 执行
- LangGraph checkpoint 短期记忆
- LangGraph store 长期记忆
- SSE 工作流进度事件
- Agent 代码骨架生成器
- Workflow 代码骨架生成器
- Agent / Workflow DSL 可视化设计器
- 按用户轮回溯会话并同步重置 checkpoint
- 端到端测试覆盖 crew -> workflow -> chat -> messages 入库

## 架构概览

```text
HTTP API
  -> Conversation / Crew services
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

Agent 可以按目录分组。`name` 是本地 registry 和 workflow 使用的逻辑名，`package` 是代码所在目录：

```json
{
  "kind": "agent",
  "name": "research_agent",
  "package": "research/research_agent"
}
```

生成后目录为：

```text
app/agents/research/research_agent/
```

Agent 定义和默认配置来自 DSL 生成的本地代码及 `config_defaults.json`。
workflow 运行时按 registry metadata 解析这些本地 manifest，并把配置注入节点 state：

```python
state["system_prompt"]
state["model"]
state["temperature"]
```

数据库不保存、也不覆盖内置 Agent 的 prompt、model 或 settings。Crew 的
`workflow_type` 只记录它选择了哪个本地 workflow；如果该 workflow
已从本地删除，Crew 仍会出现在 API 和页面中，但 `workflow_missing=true`，且不能运行，
直到用户主动切换到现有 workflow。

### 定义与运行数据边界

| 内容 | 来源 |
| --- | --- |
| Workflow 列表、图定义、UI metadata | 本地 workflow registry / DSL 生成代码 |
| Agent 节点、prompt、model、settings | 本地 Agent manifest / DSL 生成代码 |
| Crew 选择的 workflow | 数据库 `crews.workflow_type` |
| Conversation、Message、checkpoint、长期记忆 | 数据库 |
| 文件和工具连接 | 数据库 |

样例 Crew 只创建 Crew 和 workflow 选择，不会复制一组内置 Agent 到数据库。

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

Workflow 节点可以通过 `agent_package` 引用分组 Agent：

```json
{
  "researcher": {
    "agent": "research_agent",
    "agent_package": "research/research_agent"
  }
}
```

也可以使用简写：

```json
{
  "researcher": {
    "agent": "research/research_agent"
  }
}
```

两种写法都会把节点状态里的 Agent 名保持为 `research_agent`。

Workflow 还可以声明通用 UI 控件。控件值通过 `workflow_inputs` 进入全局
workflow state，并自动注入每个 Agent 节点：

```json
{
  "ui": {
    "controls": [
      {
        "key": "prompt_strategy",
        "label": "提示策略",
        "type": "segmented",
        "default": "expressive",
        "options": [
          { "value": "expressive", "label": "积极扩写" },
          { "value": "faithful", "label": "保守还原" }
        ]
      }
    ]
  }
}
```

目前支持 `select` 和 `segmented`。节点通过
`state["workflow_inputs"]["prompt_strategy"]` 读取，不需要把控制参数拼进用户消息。

生成器输出的是可读、可改、可继续维护的 Python 代码。

### DSL 设计器

Web 工作台右上角的代码图标可以打开 DSL 设计器。设计器支持：

- 在 Agent 和 Workflow DSL 之间切换
- 拖动节点、创建连接、编辑节点属性
- 图形画布与 JSON DSL 双向同步
- 调用现有生成器校验、保存并刷新代码骨架

生成代码是显式操作。刷新 Agent 骨架时，节点名不变会保留对应业务代码块；
DSL 删除节点时，对应业务代码块也会被删除，页面会在生成前要求确认。
生成成功后，新 Agent 会注册到本地 Agent registry，新 Workflow 会注册到本地
Workflow registry；前端随后重新读取 registry，无需写数据库或重启服务。

## 记忆

短期记忆使用 LangGraph checkpoint，挂在 workflow 层。

```python
config={"configurable": {"thread_id": str(conversation.id)}}
```

同一个 `conversation_id` 会复用同一个 checkpoint thread。

页面可从任意一条用户消息开始回溯。回溯会删除该消息及其后的数据库消息，
同时删除该会话的 checkpoint；下一次运行会从保留的数据库历史重新构造短期记忆。

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

普通与流式聊天接口都接受可选的结构化工作流参数：

```json
{
  "message": "生成一张图",
  "workflow_inputs": {
    "target_model": "nai_v4",
    "prompt_strategy": "faithful"
  }
}
```

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
DATABASE_URL="postgresql://postgres:postgres@localhost:5432/sesame_agent_workflow_kit"
DATABASE_SCHEMA="public"
ACTIVITY_LOG_MAX_ROWS=1000
OPENROUTER_API_KEY="..."
JWT_SECRET_KEY="change-me"
```

### 3. 初始化数据库

```text
database/schema.sql
```

### 4. 启动服务

前端使用 React、TypeScript 和 Vite。首次运行或修改前端后先构建：

```bash
cd frontend
pnpm install
pnpm build
cd ..
```

```bash
python -m app.main
```

Windows 下请使用这个项目入口启动，它会使用 Psycopg 异步 checkpoint 所需的
Selector 事件循环。默认服务地址为 `http://127.0.0.1:8765`。

生产构建输出到 `app/web/dist`，由 FastAPI 在同一地址提供。前端独立开发时：

```bash
cd frontend
pnpm dev
```

Vite 使用 `http://127.0.0.1:5173`，并将 `/api` 代理到
`http://127.0.0.1:8765`。

接口文档：

```text
http://localhost:8765/api/docs
http://localhost:8765/api/redoc
```

## 最小使用流程

1. 用 DSL 生成并注册本地 Agent 和 Workflow，或使用已有定义
2. 创建 Crew，并在 `workflow_type` 中选择 workflow
3. 调用 `POST /api/chat`
4. 使用返回的 `conversation_id` 继续对话
5. 用 `GET /api/conversations/{conversation_id}/messages` 查看消息

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
- 本地 Agent manifest 与数据库配置隔离
- missing workflow 展示与运行拦截
- 端到端 crew -> workflow -> chat -> messages 入库

## License

MIT
