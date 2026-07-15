# Agent Workflow Kit

一个面向二次开发的本地优先多 Agent 工作流平台。

项目使用 FastAPI 提供 API，使用 LangGraph 编排 Workflow 与 Agent 子图，使用
PostgreSQL 保存 Crew、会话、消息、checkpoint 和长期记忆，并提供 React 工作台、
SSE 执行事件和 Agent/Workflow DSL 代码生成器。

它的目标不是只实现一个 Supervisor，而是提供一套可机械生成、可继续手写业务逻辑、
可被 API 和页面直接使用的工作流工程骨架。

## 当前能力

- 本地 Agent manifest 与 Workflow registry
- 原生 LangGraph Workflow 和多节点 Agent 子图
- `langgraph-supervisor` 官方监管者运行时适配
- JSON DSL 生成 Agent/Workflow Python 骨架
- 浏览器内 Agent/Workflow DSL 可视化设计器
- Crew 选择工作流，Conversation 负责持续对话
- 普通聊天与 SSE 流式执行事件
- PostgreSQL checkpoint 短期记忆
- PostgreSQL store 长期记忆
- 删除最后一轮、从指定用户消息回溯
- 动态工作流 UI metadata 与结构化 `workflow_inputs`
- Prompt 生成实战工作流，支持 NAI V3/V4、SDXL、Illustrious、Pony 和 Flux
- 测试覆盖 DSL 生成、registry、数据库边界、会话和完整聊天链路

## 核心架构

```text
React 工作台 / HTTP API
        |
        v
Crew（只记录选择的 workflow_type）
        |
        v
WorkflowService
  |- Workflow registry：查找本地 Workflow
  |- Agent catalog：读取本地 config_defaults.json
  `- State builder：构造本轮 WorkflowState
        |
        v
LangGraph Workflow
  |- Agent 子图
  |- checkpoint / store
  `- workflow events
        |
        v
PostgreSQL
  |- Crew / Conversation / Message
  |- LangGraph checkpoint
  `- LangGraph long-term store
```

Workflow 不需要知道节点的业务语义，只负责节点、连接和运行适配。每个 Agent 子图内部
决定轮到自己时执行哪些节点和业务代码。

## 定义与数据边界

项目采用明确的“本地定义、数据库运行”边界：

| 内容 | 权威来源 |
| --- | --- |
| Workflow 列表、连接关系、UI metadata | 本地 Workflow registry / 生成代码 |
| Agent 节点、prompt、model、temperature、state schema | 本地 Agent DSL / manifest / 代码 |
| Crew 选择的 Workflow | 数据库 `crews.workflow_type` |
| Conversation、Message、活动日志 | 数据库业务表 |
| 短期运行状态 | LangGraph PostgreSQL checkpoint |
| 长期记忆 | LangGraph PostgreSQL store |

数据库不保存内置 Agent 定义，也不覆盖本地 prompt 或 model。新增 Agent 和 Workflow 时，
不需要创建数据库记录或同步一份定义到数据库。

如果某个 Crew 引用的 Workflow 已从本地删除，Crew 仍会显示，并返回
`workflow_missing=true`，但在用户切换到有效 Workflow 前不能运行。

## 内置工作流

### `supervisor_simple`

最小监管者示例：

```text
supervisor_simple workflow
  `- node: supervisor
       `- agent: official_supervisor
            `- runtime: langgraph-supervisor
```

这里的三个名称属于不同层级：

- `supervisor_simple`：Workflow 名称
- `supervisor`：Workflow 节点名称
- `official_supervisor`：可复用的 Agent 实现名称

### `prompt_generation_workflow`

完整的多 Agent 实战链路：

```text
监管规划
  -> 口语理解
  -> 需求分析
  -> 人物生成 ┐
     场景生成 ├-> Prompt 汇总 -> 模型格式优化
     附加生成 ┘
```

口语理解节点维护跨轮请求契约，需求分析将完整要求拆给并行生成器，生成器查询并验证
Danbooru 标签，汇总节点合并原子标签与描述性短语，最后按目标模型输出格式。页面提供：

- `积极扩写`：允许补充有助于画面的次要细节
- `保守还原`：优先保持用户明确要求，减少额外扩写
- NAI V3/V4、SDXL、Illustrious、Pony、Flux 目标格式

## Agent DSL

Agent DSL 描述稳定节点、连接、额外 state 字段和默认运行配置：

```json
{
  "version": 1,
  "kind": "agent",
  "name": "research_agent",
  "package": "research/research_agent",
  "display_name": "Research Agent",
  "config": {
    "prompt": "You are a research agent.",
    "model": "openai/gpt-4.1",
    "temperature": 0.2
  },
  "state": {
    "query": { "type": "string", "optional": true },
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

生成命令：

```bash
python scripts/generate_agent.py examples/agents/research_agent.json
```

输出目录：

```text
app/agents/research/research_agent/
  __init__.py
  config_defaults.json
  graph.py
  nodes.py
  spec.py
  state.py
```

生成器负责非业务骨架，开发者在 `nodes.py` 的 `<agent-node ...>` 代码块内实现业务逻辑。
节点名是稳定标识：

- DSL 仍包含同名节点时，再次生成会保留其业务代码块
- DSL 删除节点时，对应业务代码块会被删除，即使其中已有手写代码
- 修改节点名等价于删除旧节点并新增节点

因此，DSL 生成的骨架加上节点业务逻辑，就是一个完整可复用的 Agent 子图。

## Workflow DSL

Workflow DSL 只描述 Agent 实例、连接、适配方式和页面 metadata：

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
      "agent": "research_agent",
      "agent_package": "research/research_agent"
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

生成命令：

```bash
python scripts/generate_workflow.py examples/workflows/research_pipeline.json
```

输出位于 `app/core/langgraph/workflows/<workflow_name>/`。生成的 `graph.py` 会注册
Workflow，`state.py` 会根据节点和本地 Agent manifest 机械构造初始状态。

常用节点 extension：

- `pipeline_context`：将上游业务字段注入当前 Agent 节点
- `supervisor`：接入官方监管者及长期记忆适配
- `supervisor_planner`：只使用监管者做规划，后续由固定 DSL 边执行

Workflow 节点可通过 `config` 覆盖本地 Agent manifest 的 prompt/model 等默认值，
这种覆盖仍属于本地 Workflow 定义，不进入数据库。

### 动态页面参数

Workflow DSL 的 `ui.controls` 可声明页面控件：

```json
{
  "ui": {
    "title": "图像提示词工作流",
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

当前支持 `select` 和 `segmented`。值通过 `workflow_inputs` 进入全局 state，并注入
每个 Agent 节点；前端执行链、标题、说明和控件都随当前 Workflow metadata 变化。

## DSL 设计器

Web 工作台右上角的代码按钮可打开 DSL 设计器。它支持：

- Agent / Workflow DSL 切换
- 创建、读取、校验和保存本地 JSON DSL
- 拖动节点、创建连接、编辑属性
- 图形画布与 JSON 源码双向同步
- 调用生成器刷新 Python 骨架

写文件和生成代码接口只允许本机请求。生成后服务会使 Python import cache 失效并重新
加载对应模块，新 Agent/Workflow 会直接进入本地 registry，不需要写数据库或重启服务。

## State 与记忆

### 工作流 State

通用 WorkflowState 包含：

```text
nodes             每个 Workflow 节点的 Agent state
agents            当前 Workflow 可用的本地 Agent 配置
user_id           用户标识
crew_id           Crew 标识
conversation_id   会话标识
user_input        本轮输入
workflow_inputs   页面/API 传入的结构化参数
```

每轮开始会重置所有节点的临时业务输出，避免 checkpoint 中上一轮的中间结果覆盖本轮
数据；消息历史和显式工作流记忆仍会保留。

### 短期记忆

短期记忆由两部分协作：

1. LangGraph checkpoint 使用 `conversation_id` 作为 `thread_id` 保存工作流运行状态
2. 数据库 Message 保存可审计的对话历史，并在新一轮为 Workflow 重建最近消息窗口

默认窗口为最近 10 轮，可通过 `SHORT_TERM_MEMORY_TURNS` 调整。数据库消息是回溯后
重建上下文的稳定来源，checkpoint 是运行时状态来源。

### 长期记忆

长期记忆使用 LangGraph PostgreSQL store，namespace 为：

```text
("memories", user_id)
```

当前通过 Supervisor extension 接入。只有 Agent state 明确输出 `memory_write` 时才写入，
不会自动把所有对话永久保存为记忆。可通过 `LONG_TERM_MEMORY_ENABLED` 和
`LONG_TERM_MEMORY_LIMIT` 控制。

### 删除与回溯

- 删除会话：删除业务消息并清理对应 checkpoint thread
- 删除最后一轮：删除最后一条用户消息及其后的 Assistant 消息，并清理 checkpoint
- 从这里回溯：删除所选用户消息及其后全部消息，并清理 checkpoint

下一次发送消息时，系统从仍保留的数据库消息重新构造短期上下文。

## 聊天执行流程

推荐使用统一入口 `POST /api/chat`。

创建会话并发送首条消息：

```json
{
  "user_id": "user-1",
  "crew_id": "<crew-uuid>",
  "title": "第一次对话",
  "message": "分析这个需求",
  "workflow_inputs": {}
}
```

继续已有会话：

```json
{
  "conversation_id": "<conversation-uuid>",
  "message": "继续，并调整上一轮结果"
}
```

响应始终返回 `conversation_id`、`message_id` 和 `content`。

也可以先创建 Conversation，再调用：

```text
POST /api/conversations/{conversation_id}/chat
POST /api/conversations/{conversation_id}/chat/stream
```

流式接口会发送 Workflow 事件和 OpenAI 风格的 `chat.completion.chunk`，最后发送
`[DONE]`。常见事件包括：

```text
workflow.started
workflow.node.started
workflow.node.completed
workflow.task.assigned
workflow.agent.error
workflow.completed
```

## API 概览

```text
GET    /api/health

GET    /api/workflows/
POST   /api/workflows/{workflow_name}/sample-crew

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
DELETE /api/conversations/{conversation_id}/turns/latest
DELETE /api/conversations/{conversation_id}/turns/from/{message_id}

POST   /api/chat

GET    /api/dsl/{agent|workflow}
GET    /api/dsl/{agent|workflow}/{name}
POST   /api/dsl/{agent|workflow}/validate
PUT    /api/dsl/{agent|workflow}/{name}
POST   /api/dsl/{agent|workflow}/{name}/generate
```

Swagger：`http://127.0.0.1:8765/api/docs`

## 数据库

版本库包含：

- `database/schema.sql`：新数据库的完整业务表结构
- `database/migrations/001_local_agent_runtime.sql`
- `database/migrations/002_remove_database_agents.sql`

迁移脚本将 `workflow_type` 移入 Crew，保留日志和消息中的 Agent 来源，然后删除旧的
数据库 Agent 表。LangGraph checkpoint/store 自有表由启动时的 `setup()` 创建。

真实 Crew、会话、消息、checkpoint 和长期记忆不会提交到 Git。

活动日志按总条数限制，默认最多保留 1000 条，服务启动和新增日志时都会清理最旧记录。

## 快速开始

### 1. 安装后端依赖

需要 Python 3.10+ 和 PostgreSQL。

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 2. 配置环境变量

```powershell
Copy-Item .env.example .env
```

至少配置：

```env
DATABASE_URL="postgresql://postgres:postgres@localhost:5432/sesame_agent_workflow_kit"
DATABASE_SCHEMA="public"
OPENROUTER_BASE_URL="https://openrouter.ai/api/v1"
OPENROUTER_API_KEY="..."
JWT_SECRET_KEY="change-me"
```

常用可选项：

```env
SHORT_TERM_MEMORY_TURNS=10
LONG_TERM_MEMORY_ENABLED=true
LONG_TERM_MEMORY_LIMIT=5
ACTIVITY_LOG_MAX_ROWS=1000
LLM_DEFAULT_MODEL="gpt-5.4"
LLM_SUPERVISOR_MODEL="gpt-5.5"
LLM_REQUEST_TIMEOUT_SECONDS=75
```

`OPENROUTER_BASE_URL` 可以指向兼容 OpenAI Chat Completions 的网关或模型服务。

### 3. 初始化数据库

新数据库执行：

```powershell
psql -d sesame_agent_workflow_kit -f database/schema.sql
```

旧数据库按顺序执行 `database/migrations/` 中的迁移脚本。迁移前请先备份数据库。

### 4. 构建前端

```powershell
cd frontend
pnpm install
pnpm build
cd ..
```

构建结果写入 `app/web/dist`，由 FastAPI 在同一端口提供。

### 5. 启动服务

```powershell
python -m app.main
```

默认地址：`http://127.0.0.1:8765`

Windows 下应使用 `python -m app.main`，入口会配置 Psycopg 异步 checkpoint 所需的
Selector 事件循环。

前端独立开发：

```powershell
cd frontend
pnpm dev
```

Vite 地址为 `http://127.0.0.1:5173`，并将 `/api` 代理到后端 `8765` 端口。

## 目录结构

```text
app/
  agents/
    catalog.py
    declarative.py
    official_supervisor/
    prompt_generation/
  api/routes/
  core/langgraph/
    checkpoint.py
    events.py
    store.py
    workflows/
      adapters/
      prompt_generation_workflow/
      supervisor_simple/
  db/
  models/
  schemas/
  services/
  web/dist/

database/
  migrations/
  schema.sql

examples/
  agents/
  workflows/

frontend/
  src/

scripts/
  generate_agent.py
  generate_workflow.py

tests/
  api/
  scripts/
  services/
```

## 测试

```powershell
pytest -q
```

当前测试覆盖：

- Crew、Conversation 和 Chat API
- SSE Workflow 事件
- 删除最后一轮与指定消息回溯
- 本地 Agent manifest 与数据库定义隔离
- missing Workflow 展示与运行拦截
- Agent/Workflow DSL 校验和代码生成
- LangGraph checkpoint 与 store 适配
- 多轮节点临时状态隔离
- Prompt 生成工作流
- Crew -> Workflow -> Chat -> Message 入库端到端链路

## 当前边界

- DSL 设计器是本地开发工具，写文件/生成接口不面向远程生产环境开放
- 生成器负责可维护骨架，不会自动生成具体业务节点实现
- 长期记忆目前由 Supervisor extension 显式读写，并非所有 Agent 自动写入
- Workflow registry 位于当前 Python 进程内，多进程部署需要统一代码发布和进程重载策略
- 认证、权限、多租户和远程 DSL 发布流程仍需要按实际部署环境补充

## License

MIT
