# LangGraph 多 Agent 工作流模板

这是一个正在二次开发中的 LangGraph 多 Agent 后端项目。项目目标是构建一个可扩展的 Agent 工作流后端：可以注册和运行不同类型的 workflow，可以通过 FastAPI 对外提供会话接口，也可以逐步接入多种真实 Agent 执行形态。

当前版本不是完整产品，也不是最终架构定型版。它更像一个可继续演进的后端骨架：目前已经把 `chat` 接到了 `supervisor_simple` 工作流，并开始补“主脑 Supervisor + 多个真实子 Agent”的执行链；但这个 Supervisor 工作流只是当前已有的一种 workflow，不是项目的唯一目标。AgentExecutor、MCP 工具闭环、数据库迁移、完整 API 路由挂载等能力还需要继续完善。

## 当前状态

目前主应用只挂载了会话路由：

```python
app.include_router(conversation.router, prefix="/api")
```

也就是说，当前可直接通过 FastAPI 主应用访问的核心接口主要是：

- `GET /api/health`
- `GET /api/conversations`
- `POST /api/conversations`
- `GET /api/conversations/{conversation_id}`
- `PUT /api/conversations/{conversation_id}`
- `DELETE /api/conversations/{conversation_id}`
- `GET /api/conversations/{conversation_id}/messages`
- `POST /api/conversations/{conversation_id}/messages`
- `POST /api/conversations/{conversation_id}/chat`
- `POST /api/conversations/{conversation_id}/chat/stream`
- `POST /api/chat`

`crew.py`、`storage.py` 等路由文件已经存在，但还没有在 `app/main.py` 中正式挂载到主应用。

`POST /api/chat` 是统一聊天入口：如果请求里带 `conversation_id`，就继续已有会话；如果没有 `conversation_id`，则需要提供 `user_id` 和 `crew_id`，后端会先创建会话再发送第一条消息。响应会返回 `conversation_id`，方便前端继续对话。

## 工作流架构

当前已经接入 API 的主工作流是 `supervisor_simple`：

```text
POST /api/conversations/{conversation_id}/chat
  -> Conversation API
  -> WorkflowService
  -> supervisor_simple workflow
  -> supervisor agent graph
  -> 写回 assistant message
```

Supervisor 内部节点如下：

```text
analyze_input
  -> answer_directly
  -> create_plan
  -> assign_tasks
  -> check_status
  -> combine_results
```

当前逻辑：

- 简单问题由 Supervisor 直接回答。
- 复杂问题由 Supervisor 创建执行计划。
- 执行计划会校验是否引用了不存在的 Agent。
- 命中可用 Agent 后，会把任务写入该 Agent 的 delegated state。
- `check_status` 会执行被分配任务的 Agent，并把结果写入 `results`。
- `combine_results` 汇总子 Agent 结果并生成最终回复。

Workflow 的 initial state 现在由 workflow 自己的 `state_builder` 构造。Conversation API 只负责收集通用上下文，例如 `conversation_id`、最近消息、用户输入和 agents 列表；具体如何把短期记忆放进每个 agent 的 `messages`，由对应 workflow 决定。

## Delegated Agent State

Supervisor 侧只保存调度需要的信息，不保存 Agent 定义快照。

当前结构重点是：

```python
{
    "agent_id": "...",
    "agent_name": "...",
    "messages": [],
    "status": "idle | working | complete | error",
    "results": None,
    "error": None,
    "tools": [],
}
```

刻意不保存：

- `system_prompt`
- `model`
- `temperature`

这些属于 Agent 定义，后续应由独立 `AgentExecutor` 根据 `agent_id` 从数据库、registry 或配置中心读取。这样未来子 Agent 可以是单次 LLM 调用，也可以是多节点 LangGraph、MCP Agent、Browser Agent 或 Code Agent。

## 重要限制

当前还有几个关键限制：

1. `chat/stream` 目前已经走 workflow，但仍是 workflow 完成后一次性输出结果，还不是节点事件级或 token 级 workflow event stream。
2. 子 Agent 执行逻辑还在 Supervisor 节点里，后续应该抽成独立 `AgentExecutor`。
3. 当前子 Agent 执行仍是简化版 LLM 调用，尚未支持多节点 Agent Graph。
4. MCP 工具模型和服务代码存在，但还没有形成完整的 Agent 工具调用闭环。
5. 数据库迁移尚未完成，Alembic 还需要补。
6. 主应用没有挂载全部 API router。
7. 测试以 mock 和服务层测试为主，完整集成测试还不足。

## 目录结构

```text
app/
  agents/
    supervisor/              # Supervisor agent 的状态、节点、路由和 prompt
  api/
    routes/
      conversation.py        # 当前主应用已挂载的会话 API
      crew.py                # Crew/Agent API，尚未在 main.py 挂载
      storage.py             # Storage API，尚未在 main.py 挂载
  core/
    langgraph/
      workflows/
        supervisor_simple/   # 当前默认工作流
        adapters/            # Agent graph 与 workflow state 的适配层
  db/                        # SQLAlchemy base/session
  models/                    # Crew、Agent、Conversation、ActivityLog 等模型
  schemas/                   # Pydantic schema
  services/                  # Crew、Conversation、Workflow、AI Provider 等服务
```

## 安装和运行

建议使用 Python 3.10+。

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

复制环境变量模板：

```bash
copy .env.example .env
```

按需配置：

- `DATABASE_URL`
- `OPENROUTER_BASE_URL`
- `OPENROUTER_API_KEY`
- `OPENAI_API_KEY`
- `JWT_SECRET_KEY`
- `R2_*`

启动服务：

```bash
uvicorn app.main:app --reload
```

接口文档：

- Swagger UI: `http://localhost:8000/api/docs`
- ReDoc: `http://localhost:8000/api/redoc`

## 当前推荐开发路线

下一阶段建议优先做这些事：

1. 挂载 `crew.py`、`storage.py` 等已有 router，让 API 闭环可用。
2. 增加数据库迁移，保证本地和部署环境能稳定初始化。
3. 抽象 `AgentExecutor`，让 Supervisor 不直接关心 Agent 怎么执行。
4. 让 `AgentExecutor` 支持通过 `agent_id` 加载真实 Agent 配置。
5. 支持子 Agent 自己是多节点 LangGraph。
6. 接入 MCP tools，并把工具调用过程纳入 Agent 执行链。
7. 把 `chat/stream` 从一次性 SSE 输出升级成真正的 workflow 事件流。
8. 补集成测试，覆盖从创建 crew/agent/conversation 到 chat 的完整路径。

## 项目定位

这个项目当前适合：

- 继续开发 LangGraph 多 Agent 后端。
- 扩展多种 workflow 的注册、选择和运行能力。
- 研究当前 Supervisor 工作流如何接入 FastAPI。
- 作为主脑调度多个真实 Agent 的早期实现之一。

暂时不适合：

- 直接作为生产级多 Agent 平台使用。
- 直接暴露公网使用。
- 在没有补数据库迁移、鉴权、完整路由和测试前承担关键业务。
