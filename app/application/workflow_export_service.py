"""Build database-free standalone packages from registered workflows."""

from __future__ import annotations

import ast
import importlib.metadata
import io
import json
import sys
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from app.agents.catalog import resolve_workflow_agent_configs
from app.workflows.registry import workflow_registry


ROOT = Path(__file__).resolve().parents[2]
APP_DIR = ROOT / "app"
WORKFLOWS_DIR = APP_DIR / "workflows"
EXPORT_ROOT_SUFFIX = "standalone"
FORBIDDEN_MODULE_PREFIXES = (
    "app.api",
    "app.application",
    "app.infrastructure.database",
)
PACKAGE_NAMES = {
    "aiohttp": "aiohttp",
    "dotenv": "python-dotenv",
    "httpx": "httpx",
    "langchain": "langchain",
    "langchain_core": "langchain-core",
    "langchain_openai": "langchain-openai",
    "langgraph": "langgraph",
    "langgraph_supervisor": "langgraph-supervisor",
    "openai": "openai",
    "pydantic": "pydantic",
    "tenacity": "tenacity",
    "typing_extensions": "typing-extensions",
}


@dataclass(frozen=True)
class WorkflowExport:
    """One generated ZIP artifact."""

    filename: str
    content: bytes
    file_count: int


class LocalDependencyCollector:
    """Collect local ``app`` modules reachable through Python imports."""

    def __init__(self) -> None:
        self.files: set[Path] = set()
        self.external_modules: set[str] = set()
        self._processed: set[Path] = set()

    def add_tree(self, directory: Path) -> None:
        for path in sorted(directory.rglob("*")):
            if not path.is_file() or "__pycache__" in path.parts:
                continue
            if path.suffix in {".pyc", ".pyo"}:
                continue
            self.files.add(path)
            if path.suffix == ".py":
                self._scan(path)

    def add_module(self, module_name: str) -> None:
        if any(
            module_name == prefix or module_name.startswith(f"{prefix}.")
            for prefix in FORBIDDEN_MODULE_PREFIXES
        ):
            raise ValueError(
                f"Standalone export cannot include platform module '{module_name}'"
            )
        path = self._module_path(module_name)
        if path is None:
            if module_name == "app" or module_name.startswith("app."):
                return
            top_level = module_name.split(".", 1)[0]
            if top_level not in sys.stdlib_module_names and top_level != "__future__":
                self.external_modules.add(top_level)
            return
        self._add_python_file(path)

    def _add_python_file(self, path: Path) -> None:
        if path in self._processed:
            return
        self.files.add(path)
        self._processed.add(path)
        for parent in path.parents:
            if parent == ROOT:
                break
            init_path = parent / "__init__.py"
            if init_path.is_file() and init_path not in self._processed:
                self._add_python_file(init_path)
        self._scan_imports(path)

    def _scan(self, path: Path) -> None:
        if path in self._processed:
            return
        self._processed.add(path)
        self.files.add(path)
        self._scan_imports(path)

    def _scan_imports(self, path: Path) -> None:
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (OSError, SyntaxError, UnicodeError) as exc:
            raise ValueError(f"Cannot analyze Python source '{path}': {exc}") from exc

        current_module = self._module_name(path)
        current_package = (
            current_module
            if path.name == "__init__.py"
            else current_module.rpartition(".")[0]
        )
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    self.add_module(alias.name)
            elif isinstance(node, ast.ImportFrom):
                base = self._absolute_import(current_package, node.module, node.level)
                if base:
                    self.add_module(base)
                    for alias in node.names:
                        if alias.name != "*":
                            self.add_module(f"{base}.{alias.name}")

    @staticmethod
    def _absolute_import(package: str, module: str | None, level: int) -> str:
        if level == 0:
            return module or ""
        parts = package.split(".") if package else []
        keep = max(0, len(parts) - level + 1)
        prefix = parts[:keep]
        if module:
            prefix.extend(module.split("."))
        return ".".join(prefix)

    @staticmethod
    def _module_name(path: Path) -> str:
        relative = path.relative_to(ROOT)
        parts = list(relative.with_suffix("").parts)
        if parts[-1] == "__init__":
            parts.pop()
        return ".".join(parts)

    @staticmethod
    def _module_path(module_name: str) -> Path | None:
        if not module_name.startswith("app"):
            return None
        base = ROOT.joinpath(*module_name.split("."))
        module_file = base.with_suffix(".py")
        if module_file.is_file():
            return module_file
        package_file = base / "__init__.py"
        if package_file.is_file():
            return package_file
        return None


def _agent_directories(metadata: dict[str, Any]) -> list[Path]:
    names = {
        str(node.get("agent") or node.get("name") or "").strip()
        for node in metadata.get("nodes") or []
    }
    found: dict[str, Path] = {}
    for manifest_path in APP_DIR.joinpath("agents").rglob("config_defaults.json"):
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        name = str(manifest.get("name") or "").strip()
        if name in names:
            found[name] = manifest_path.parent
    missing = sorted(names - found.keys())
    if missing:
        raise ValueError(f"Missing local Agent packages: {', '.join(missing)}")
    return [found[name] for name in sorted(found)]


def _standalone_config() -> str:
    return '''"""Environment-only settings for the standalone workflow."""

import os
from dataclasses import dataclass

from dotenv import load_dotenv


load_dotenv()


@dataclass(frozen=True)
class Settings:
    openrouter_api_key: str = os.getenv("OPENROUTER_API_KEY", "")
    openrouter_base_url: str = os.getenv(
        "OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"
    )
    openai_api_key: str | None = os.getenv("OPENAI_API_KEY")
    llm_default_model: str = os.getenv("LLM_DEFAULT_MODEL", "gpt-5.4")
    llm_supervisor_model: str = os.getenv("LLM_SUPERVISOR_MODEL", "gpt-5.5")
    llm_request_timeout_seconds: float = float(
        os.getenv("LLM_REQUEST_TIMEOUT_SECONDS", "75")
    )
    short_term_memory_turns: int = int(os.getenv("SHORT_TERM_MEMORY_TURNS", "10"))
    long_term_memory_enabled: bool = False
    long_term_memory_limit: int = 0


settings = Settings()
'''


def _standalone_checkpoint() -> str:
    return '''"""Process-local short-term LangGraph checkpoint."""

from langgraph.checkpoint.memory import MemorySaver


_checkpointer = MemorySaver()


async def init_checkpointer():
    return _checkpointer


async def close_checkpointer() -> None:
    return None


def get_checkpointer():
    return _checkpointer
'''


def _standalone_store() -> str:
    return '''"""Long-term memory is intentionally disabled in standalone exports."""


async def init_store():
    return None


async def close_store() -> None:
    return None


def get_store():
    return None
'''


def _runner_source(
    workflow_name: str,
    factory_module: str,
    factory_name: str,
    state_builder_name: str,
) -> str:
    return f'''"""Public runtime API for the exported workflow."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import uuid4

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.types import Command

from {factory_module} import {factory_name}
from app.workflows.{workflow_name}.state import {state_builder_name}


ROOT = Path(__file__).resolve().parent
AGENT_CONFIGS = json.loads((ROOT / "agent_configs.json").read_text(encoding="utf-8"))
WORKFLOW_METADATA = json.loads((ROOT / "workflow.json").read_text(encoding="utf-8"))


def workflow_controls() -> list[dict[str, Any]]:
    """Return the controls declared by this workflow's UI metadata."""

    ui = WORKFLOW_METADATA.get("ui") or {{}}
    return [control for control in (ui.get("controls") or []) if control.get("key")]


def workflow_input_defaults() -> dict[str, Any]:
    """Mirror the platform UI's default-value rules without requiring the UI."""

    defaults = {{}}
    for control in workflow_controls():
        key = str(control["key"])
        options = control.get("options") or []
        if "default" in control:
            defaults[key] = control.get("default")
        elif options:
            first = options[0]
            defaults[key] = first.get("value") if isinstance(first, dict) else first
        else:
            defaults[key] = ""
    return defaults


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {{str(key): _json_safe(item) for key, item in value.items()}}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    if hasattr(value, "model_dump"):
        return _json_safe(value.model_dump())
    return str(value)


def extract_output(state: dict[str, Any]) -> Any:
    nodes = state.get("nodes") or {{}}
    for node in reversed(WORKFLOW_METADATA.get("nodes") or []):
        node_state = nodes.get(node.get("name")) or {{}}
        for key in ("final_output", "answer", "formatted_prompt", "results", "output"):
            value = node_state.get(key)
            if value not in (None, "", [], {{}}):
                return _json_safe(value)
    return _json_safe(state)


class WorkflowRuntime:
    """In-process workflow runtime with non-persistent short-term memory."""

    def __init__(
        self,
        thread_id: str | None = None,
        workflow_inputs: dict[str, Any] | None = None,
    ) -> None:
        self.thread_id = thread_id or str(uuid4())
        self.graph = {factory_name}(crew_id="standalone", agents=AGENT_CONFIGS)
        self.history = []
        self.workflow_inputs = {{
            **workflow_input_defaults(),
            **dict(workflow_inputs or {{}}),
        }}

    def set_workflow_input(self, key: str, value: Any) -> None:
        """Set one persistent input used by subsequent turns."""

        key = key.strip()
        if not key:
            raise ValueError("Workflow input key cannot be empty")
        controls = {{str(item["key"]): item for item in workflow_controls()}}
        control = controls.get(key)
        options = (control or {{}}).get("options") or []
        allowed = [
            str(item.get("value") if isinstance(item, dict) else item)
            for item in options
        ]
        if allowed and str(value) not in allowed:
            raise ValueError(
                f"Invalid value for {{key}}: {{value}}. Allowed: {{', '.join(allowed)}}"
            )
        self.workflow_inputs[key] = value

    def reset_workflow_input(self, key: str) -> None:
        """Reset one input to its declared default, or remove an undeclared input."""

        defaults = workflow_input_defaults()
        if key in defaults:
            self.workflow_inputs[key] = defaults[key]
        else:
            self.workflow_inputs.pop(key, None)

    async def ainvoke(
        self,
        user_input: str,
        workflow_inputs: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        user_message = HumanMessage(content=user_input)
        max_messages = 20
        effective_inputs = {{
            **self.workflow_inputs,
            **dict(workflow_inputs or {{}}),
        }}
        state = {state_builder_name}(
            crew_id="standalone",
            agents=AGENT_CONFIGS,
            user_id="standalone-user",
            conversation_id=self.thread_id,
            messages=[*self.history[-max_messages:], user_message],
            user_input=user_input,
            workflow_inputs=effective_inputs,
            request_context={{"request_id": str(uuid4()), "thread_id": self.thread_id}},
        )
        config = {{"configurable": {{"thread_id": self.thread_id}}, "recursion_limit": 100}}
        result = await self.graph.ainvoke(state, config=config)
        while result.get("__interrupt__"):
            interrupt_item = result["__interrupt__"][0]
            payload = getattr(interrupt_item, "value", interrupt_item)
            question = payload.get("question") if isinstance(payload, dict) else str(payload)
            answer = input(f"{{question}}\\n> ").strip()
            result = await self.graph.ainvoke(Command(resume=answer), config=config)
        output = extract_output(result)
        self.history.extend([user_message, AIMessage(content=json.dumps(output, ensure_ascii=False))])
        self.history = self.history[-max_messages:]
        return result
'''


def _main_source() -> str:
    return '''"""Interactive command-line runner."""

import argparse
import asyncio
import json

from standalone_workflow.runtime import (
    WorkflowRuntime,
    extract_output,
    workflow_controls,
)


def apply_assignment(runtime: WorkflowRuntime, assignment: str) -> None:
    key, separator, value = assignment.partition("=")
    if not separator or not key.strip():
        raise ValueError("参数格式必须是 key=value")
    runtime.set_workflow_input(key, value)


def show_config(runtime: WorkflowRuntime) -> None:
    print("当前 Workflow 参数：")
    if not runtime.workflow_inputs:
        print("  （无）")
        return
    for key, value in runtime.workflow_inputs.items():
        print(f"  {key}={value}")


def configure_inputs(runtime: WorkflowRuntime) -> None:
    controls = workflow_controls()
    if not controls:
        return
    print("\\n配置 Workflow 参数，直接回车保留当前值：")
    for control in controls:
        key = str(control["key"])
        label = str(control.get("label") or key)
        current = runtime.workflow_inputs.get(key, "")
        options = control.get("options") or []
        if options:
            choices = []
            for option in options:
                if isinstance(option, dict):
                    value = option.get("value")
                    option_label = option.get("label") or value
                else:
                    value = option
                    option_label = option
                choices.append(f"{value} ({option_label})")
            print(f"  可选：{', '.join(choices)}")
        value = input(f"{label} [{current}]: ").strip()
        if value:
            try:
                runtime.set_workflow_input(key, value)
            except ValueError as exc:
                print(f"  参数错误：{exc}，保留 {current}")


def print_help() -> None:
    print(
        "命令：\\n"
        "  /config              查看当前 Workflow 参数\\n"
        "  /set key=value       修改后续请求使用的参数\\n"
        "  /reset key           恢复参数默认值\\n"
        "  /help                查看命令\\n"
        "  /exit                退出"
    )


async def main() -> None:
    parser = argparse.ArgumentParser(description="Run the exported LangGraph workflow")
    parser.add_argument("--thread-id", help="固定短期记忆线程标识")
    parser.add_argument(
        "--set",
        dest="assignments",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="设置 Workflow 参数，可重复使用",
    )
    parser.add_argument(
        "--no-configure",
        action="store_true",
        help="跳过启动时的交互参数配置",
    )
    args = parser.parse_args()
    runtime = WorkflowRuntime(thread_id=args.thread_id)
    for assignment in args.assignments:
        try:
            apply_assignment(runtime, assignment)
        except ValueError as exc:
            parser.error(str(exc))
    if not args.no_configure:
        configure_inputs(runtime)
    print("\\nStandalone LangGraph workflow 已启动。输入 /help 查看命令。")
    while True:
        text = input("You> ").strip()
        if text.lower() in {"/exit", "/quit"}:
            return
        if text == "/help":
            print_help()
            continue
        if text == "/config":
            show_config(runtime)
            continue
        if text.startswith("/set "):
            try:
                apply_assignment(runtime, text.removeprefix("/set ").strip())
                show_config(runtime)
            except ValueError as exc:
                print(f"参数错误：{exc}")
            continue
        if text.startswith("/reset "):
            runtime.reset_workflow_input(text.removeprefix("/reset ").strip())
            show_config(runtime)
            continue
        if not text:
            continue
        state = await runtime.ainvoke(text)
        print(json.dumps(extract_output(state), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
'''


def _readme(workflow_name: str) -> str:
    return f"""# {workflow_name} 独立 LangGraph 包

本包由 LangGraph Multi-Agent Workflow Studio 自动导出，只包含工作流、相关 Agent、业务模块和最小运行时。

## 能力边界

- 不包含前端、FastAPI、数据库模型或平台服务。
- 使用 LangGraph `MemorySaver` 保存进程内短期状态。
- 不启用长期记忆；进程退出后短期状态自动清空。
- Agent 配置与 Workflow 元数据已快照到包内，不需要数据库同步。
- Workflow 参数会自动读取声明的默认值；详见 `USAGE.md`。

## 运行

```powershell
python -m venv .venv
.venv\\Scripts\\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
python -m standalone_workflow
```

启动时会根据 Workflow 的 `ui.controls` 询问参数。也可以使用
`python -m standalone_workflow --no-configure --set key=value` 跳过交互配置。

请在 `.env` 中填写模型 API Key 和地址。完整参数和运行说明见 `USAGE.md`。
也可以作为 Python 模块调用：

```python
import asyncio
from standalone_workflow import WorkflowRuntime, extract_output

async def main():
    runtime = WorkflowRuntime(
        thread_id="demo",
        workflow_inputs={{"target_model": "nai_v4"}},
    )
    state = await runtime.ainvoke(
        "你的任务",
    )
    print(extract_output(state))

asyncio.run(main())
```
"""


def _usage_guide(
    workflow_name: str,
    metadata: dict[str, Any],
    agent_configs: list[dict[str, Any]],
) -> str:
    """Build workflow-specific CLI, Python, parameter, and provider guidance."""

    controls = list((metadata.get("ui") or {}).get("controls") or [])
    defaults: dict[str, Any] = {}
    rows = []
    for control in controls:
        key = str(control.get("key") or "").strip()
        if not key:
            continue
        options = control.get("options") or []
        if "default" in control:
            default = control.get("default")
        elif options:
            first = options[0]
            default = first.get("value") if isinstance(first, dict) else first
        else:
            default = ""
        defaults[key] = default
        option_values = [
            str(option.get("value") if isinstance(option, dict) else option)
            for option in options
        ]
        rows.append(
            "| "
            + " | ".join(
                [
                    key.replace("|", "\\|"),
                    str(control.get("label") or key).replace("|", "\\|"),
                    str(control.get("type") or "text").replace("|", "\\|"),
                    str(default).replace("|", "\\|"),
                    ", ".join(option_values).replace("|", "\\|") or "-",
                ]
            )
            + " |"
        )
    controls_section = (
        "\n".join(
            [
                "| Key | 名称 | 类型 | 默认值 | 可选值 |",
                "| --- | --- | --- | --- | --- |",
                *rows,
            ]
        )
        if rows
        else "此 Workflow 没有声明 `ui.controls`，运行时不需要额外参数。"
    )

    model_rows = []
    seen_models: set[tuple[str, str]] = set()
    for config in agent_configs:
        agent_name = str(config.get("name") or config.get("source_agent") or "agent")
        model = str(config.get("model") or "使用 LLM_DEFAULT_MODEL")
        item = (agent_name, model)
        if item in seen_models:
            continue
        seen_models.add(item)
        model_rows.append(f"| {agent_name} | {model} |")
    models_section = (
        "\n".join(
            [
                "| Agent | 模型 |",
                "| --- | --- |",
                *model_rows,
            ]
        )
        if model_rows
        else "此 Workflow 没有导出的 Agent 模型配置。"
    )
    example_inputs = json.dumps(defaults, ensure_ascii=False, indent=4).replace(
        "\n", "\n        "
    )
    first_assignment = next(iter(defaults.items()), ("key", "value"))

    return f"""# {workflow_name} 使用说明

## 1. 安装

```powershell
python -m venv .venv
.venv\\Scripts\\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

编辑 `.env`，至少填写实际模型提供商需要的 API Key 和 OpenAI-compatible Base URL。
API Key 不会由平台导出。

## 2. Workflow 参数

参数来自导出时 Workflow metadata 的 `ui.controls`：

{controls_section}

没有显式传值时，`WorkflowRuntime` 会自动使用上表默认值。单次 `ainvoke()` 传入的值
优先级最高，只覆盖当前调用；`runtime.set_workflow_input()` 设置的值会用于后续多轮。

## 3. 命令行运行

```powershell
python -m standalone_workflow
```

启动时会逐项询问上表参数，直接回车保留默认值。也可以跳过启动配置：

```powershell
python -m standalone_workflow --no-configure --set {first_assignment[0]}={first_assignment[1]}
```

运行中的命令：

```text
/config              查看当前参数
/set key=value       修改后续请求使用的参数
/reset key           恢复参数默认值
/help                查看命令
/exit                退出
```

同一次进程中的 `thread_id`、LangGraph `MemorySaver` 和最近消息共同提供短期记忆；
退出程序后状态清空，不会写入数据库。

## 4. Python 调用

```python
import asyncio

from standalone_workflow import WorkflowRuntime, extract_output


async def main():
    runtime = WorkflowRuntime(
        thread_id="example-thread",
        workflow_inputs={example_inputs},
    )
    state = await runtime.ainvoke("你的任务")
    print(extract_output(state))


asyncio.run(main())
```

临时覆盖某一次调用：

```python
state = await runtime.ainvoke(
    "下一轮任务",
    workflow_inputs={{"{first_assignment[0]}": "{first_assignment[1]}"}},
)
```

## 5. 模型与提供商

{models_section}

导出包包含工作流实际引用的模型适配代码和 Python SDK 依赖。当前通用适配层使用
`langchain-openai` 的 `ChatOpenAI`，因此支持 OpenAI-compatible API：

```env
OPENROUTER_API_KEY=your-key
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
LLM_DEFAULT_MODEL=gpt-5.4
LLM_SUPERVISOR_MODEL=gpt-5.5
LLM_REQUEST_TIMEOUT_SECONDS=75
```

变量名称沿用平台兼容协议；`OPENROUTER_BASE_URL` 可以替换为其他兼容服务地址。
远程模型、模型权重、API Key 和提供商账户不会打包。

## 6. 包内文件

- `standalone_workflow/runtime.py`：可嵌入的独立运行 API
- `standalone_workflow/workflow.json`：Workflow metadata 与参数声明
- `standalone_workflow/agent_configs.json`：Agent 配置快照
- `standalone_workflow/workflow.dsl.json`：原始 DSL（存在时）
- `app/`：工作流实际引用的 Agent、业务模块与最小适配层
- `requirements.txt`：根据最终导出源码计算的 Python 依赖
"""


def _requirements(external_modules: Iterable[str]) -> str:
    packages = {
        PACKAGE_NAMES.get(module, module.replace("_", "-"))
        for module in external_modules
        if module not in sys.stdlib_module_names and module != "__future__"
    }
    packages.update({"langgraph", "langchain-core", "python-dotenv"})
    lines = []
    for package in sorted(packages, key=str.lower):
        try:
            version = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            lines.append(package)
        else:
            lines.append(f"{package}=={version}")
    return "\n".join(lines) + "\n"


def _external_modules_from_sources(sources: Iterable[str]) -> set[str]:
    """Read third-party imports from the final source text written to the ZIP."""

    modules: set[str] = set()
    for source in sources:
        tree = ast.parse(source)
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                names = [node.module]
            for name in names:
                top_level = name.split(".", 1)[0]
                if (
                    top_level != "app"
                    and top_level != "standalone_workflow"
                    and top_level != "__future__"
                    and top_level not in sys.stdlib_module_names
                ):
                    modules.add(top_level)
    return modules


def export_workflow(workflow_name: str) -> WorkflowExport:
    """Export one registered workflow as a self-contained ZIP archive."""

    if workflow_name not in workflow_registry.names():
        raise KeyError(workflow_name)
    workflow_dir = WORKFLOWS_DIR / workflow_name
    if not workflow_dir.joinpath("graph.py").is_file():
        raise ValueError(f"Workflow source directory '{workflow_dir}' is missing")

    spec = workflow_registry.get_spec(workflow_name, fallback=False)
    metadata = workflow_registry.get_metadata(workflow_name, fallback=False)
    factory_module = spec.factory.__module__
    factory_name = spec.factory.__name__
    if spec.state_builder is None:
        raise ValueError(f"Workflow '{workflow_name}' has no initial-state builder")

    collector = LocalDependencyCollector()
    collector.add_tree(workflow_dir)
    for agent_dir in _agent_directories(metadata):
        collector.add_tree(agent_dir)
    collector.add_module(factory_module)

    agent_configs = resolve_workflow_agent_configs(metadata)
    dsl_path = workflow_dir / "workflow.dsl.json"
    root_name = f"{workflow_name}-{EXPORT_ROOT_SUFFIX}"
    replacements = {
        Path("app/config.py"): _standalone_config(),
        Path("app/runtime/langgraph/checkpoint.py"): _standalone_checkpoint(),
        Path("app/runtime/langgraph/store.py"): _standalone_store(),
    }
    generated = {
        Path("standalone_workflow/__init__.py"): (
            "from standalone_workflow.runtime import "
            "WorkflowRuntime, extract_output, workflow_controls, "
            "workflow_input_defaults\n\n"
            "__all__ = [\"WorkflowRuntime\", \"extract_output\", "
            "\"workflow_controls\", \"workflow_input_defaults\"]\n"
        ),
        Path("standalone_workflow/__main__.py"): _main_source(),
        Path("standalone_workflow/runtime.py"): _runner_source(
            workflow_name,
            factory_module,
            factory_name,
            spec.state_builder.__name__,
        ),
        Path("standalone_workflow/agent_configs.json"): json.dumps(
            agent_configs, ensure_ascii=False, indent=2
        ) + "\n",
        Path("standalone_workflow/workflow.json"): json.dumps(
            {"name": workflow_name, **metadata}, ensure_ascii=False, indent=2
        ) + "\n",
        Path("README.md"): _readme(workflow_name),
        Path("USAGE.md"): _usage_guide(
            workflow_name,
            metadata,
            agent_configs,
        ),
        Path(".env.example"): (
            "OPENROUTER_API_KEY=\n"
            "OPENROUTER_BASE_URL=https://openrouter.ai/api/v1\n"
            "LLM_DEFAULT_MODEL=gpt-5.4\n"
            "LLM_SUPERVISOR_MODEL=gpt-5.5\n"
            "LLM_REQUEST_TIMEOUT_SECONDS=75\n"
            "SHORT_TERM_MEMORY_TURNS=10\n"
        ),
    }
    if dsl_path.is_file():
        generated[Path("standalone_workflow/workflow.dsl.json")] = (
            dsl_path.read_text(encoding="utf-8")
        )

    final_python_sources = []
    for source in collector.files:
        if source.suffix != ".py":
            continue
        relative = source.relative_to(ROOT)
        final_python_sources.append(
            replacements.get(relative) or source.read_text(encoding="utf-8")
        )
    final_python_sources.extend(
        content for path, content in generated.items() if path.suffix == ".py"
    )
    generated[Path("requirements.txt")] = _requirements(
        _external_modules_from_sources(final_python_sources)
    )

    buffer = io.BytesIO()
    written: set[Path] = set()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for source in sorted(collector.files):
            relative = source.relative_to(ROOT)
            if relative in replacements:
                content = replacements[relative].encode("utf-8")
            else:
                content = source.read_bytes()
            archive.writestr(f"{root_name}/{relative.as_posix()}", content)
            written.add(relative)
        for relative, content in {**replacements, **generated}.items():
            if relative in written:
                continue
            archive.writestr(f"{root_name}/{relative.as_posix()}", content.encode("utf-8"))
            written.add(relative)

    return WorkflowExport(
        filename=f"{root_name}.zip",
        content=buffer.getvalue(),
        file_count=len(written),
    )
