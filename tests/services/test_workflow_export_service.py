"""Tests for database-free standalone workflow exports."""

import io
import json
import os
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

from app.application import workflow_service as _workflow_service  # noqa: F401
from app.application.workflow_export_service import export_workflow


@pytest.mark.parametrize(
    ("workflow_name", "expected_agent_path"),
    [
        ("supervisor_simple", "app/agents/official_supervisor/nodes.py"),
        (
            "prompt_generation_workflow",
            "app/agents/prompt_generation/prompt_target_renderer/nodes.py",
        ),
    ],
)
def test_export_contains_only_standalone_runtime(
    workflow_name: str,
    expected_agent_path: str,
):
    artifact = export_workflow(workflow_name)
    root = f"{workflow_name}-standalone/"

    with zipfile.ZipFile(io.BytesIO(artifact.content)) as archive:
        names = set(archive.namelist())
        assert f"{root}{expected_agent_path}" in names
        assert f"{root}standalone_workflow/runtime.py" in names
        assert f"{root}standalone_workflow/agent_configs.json" in names
        assert f"{root}USAGE.md" in names
        assert not any(f"{root}app/api/" in name for name in names)
        assert not any(f"{root}app/application/" in name for name in names)
        assert not any(
            f"{root}app/infrastructure/database/" in name for name in names
        )
        assert not any(f"{root}frontend/" in name for name in names)

        checkpoint = archive.read(
            f"{root}app/runtime/langgraph/checkpoint.py"
        ).decode("utf-8")
        store = archive.read(f"{root}app/runtime/langgraph/store.py").decode("utf-8")
        requirements = archive.read(f"{root}requirements.txt").decode("utf-8")
        usage = archive.read(f"{root}USAGE.md").decode("utf-8")
        runtime_source = archive.read(
            f"{root}standalone_workflow/runtime.py"
        ).decode("utf-8")
        cli_source = archive.read(
            f"{root}standalone_workflow/__main__.py"
        ).decode("utf-8")
        configs = json.loads(
            archive.read(f"{root}standalone_workflow/agent_configs.json")
        )

        assert "MemorySaver" in checkpoint
        assert "Postgres" not in checkpoint
        assert "return None" in store
        assert "fastapi" not in requirements.lower()
        assert "sqlalchemy" not in requirements.lower()
        assert "Workflow 参数" in usage
        assert "workflow_input_defaults" in runtime_source
        assert "/set key=value" in cli_source
        assert configs

        for name in names:
            if name.endswith(".py"):
                compile(archive.read(name), name, "exec")


def test_export_rejects_unknown_workflow():
    with pytest.raises(KeyError):
        export_workflow("missing_workflow")


def test_exported_runtime_applies_defaults_and_overrides(tmp_path: Path):
    artifact = export_workflow("prompt_generation_workflow")
    with zipfile.ZipFile(io.BytesIO(artifact.content)) as archive:
        archive.extractall(tmp_path)

    package_root = tmp_path / "prompt_generation_workflow-standalone"
    script = """
import json
from standalone_workflow import WorkflowRuntime, workflow_input_defaults

defaults = workflow_input_defaults()
runtime = WorkflowRuntime(
    thread_id="test-thread",
    workflow_inputs={"target_model": "sdxl"},
)
print(json.dumps({
    "defaults": defaults,
    "runtime_inputs": runtime.workflow_inputs,
}))
"""
    environment = {
        **os.environ,
        "OPENROUTER_API_KEY": "test-key",
    }
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=package_root,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)

    assert payload["defaults"]["prompt_strategy"] == "expressive"
    assert payload["defaults"]["target_model"] == "nai_v4"
    assert payload["runtime_inputs"]["prompt_strategy"] == "expressive"
    assert payload["runtime_inputs"]["target_model"] == "sdxl"

    usage = package_root.joinpath("USAGE.md").read_text(encoding="utf-8")
    assert "| target_model |" in usage
    assert "nai_v4" in usage
