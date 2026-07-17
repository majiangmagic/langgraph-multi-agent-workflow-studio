"""Business nodes for the prompt_consistency_validator agent."""

from typing import Any, Dict

from langchain_core.runnables import RunnableConfig

from app.agents.prompt_generation.prompt_consistency_validator.state import PromptConsistencyValidatorState

# 本文件由 scripts/generate_agent.py 刷新骨架。
# 中文注意：
# - 只在 <agent-node ...> 代码块内部编写业务逻辑。
# - 节点名是 DSL 的稳定标识；节点名不变，刷新时保留对应代码块。
# - 新 DSL 删除某个节点名时，对应代码块会被删除，不会因为里面有人写过代码而保留。

# <agent-node name="validate_prompt">
def _term_key(value: Any) -> str:
    return " ".join(str(value or "").strip().casefold().replace("_", " ").split())


def validate_prompt_node(
    state: PromptConsistencyValidatorState,
    config: RunnableConfig | None = None,
) -> Dict[str, Any]:
    """Validate PromptIR against document and target-language invariants."""

    from langchain_core.messages import AIMessage

    from app.agents.prompt_generation.domain import collect_required_paths, contains_cjk
    from app.agents.prompt_generation.models import ValidationIssue, ValidationReport

    document = state.get("scene_document") or {}
    prompt_ir = state.get("resolved_prompt_ir") or {}
    positive = prompt_ir.get("positive_terms") or []
    negative = prompt_ir.get("compiled_negative_terms") or []
    positive_keys = {
        _term_key(item.get("value")) for item in positive if isinstance(item, dict)
    }
    negative_keys = {
        _term_key(item.get("value")) for item in negative if isinstance(item, dict)
    }
    conflicts = sorted(key for key in positive_keys & negative_keys if key)
    covered = set(prompt_ir.get("covered_paths") or [])
    required_paths = collect_required_paths(document)
    missing_paths = [path for path in required_paths if path not in covered]
    removed = [
        _term_key(value)
        for value in (state.get("impact_set") or {}).get("removed_identity_terms") or []
        if value
    ]
    residual_terms = [
        item.get("value")
        for item in positive
        if isinstance(item, dict)
        and any(
            old == _term_key(item.get("value")) or old in _term_key(item.get("value"))
            for old in removed
        )
    ]
    non_english_items = [
        item
        for item in [*positive, *negative]
        if isinstance(item, dict) and contains_cjk(item.get("value"))
    ]
    participant_ids = set((document.get("participants") or {}).keys())
    orphan_identity_terms = [
        item.get("value")
        for item in prompt_ir.get("identity_terms") or []
        if isinstance(item, dict)
        and item.get("participant_id")
        and item.get("participant_id") not in participant_ids
    ]

    issues = []
    if missing_paths:
        issues.append(
            ValidationIssue(
                code="missing_required_paths",
                severity="recoverable",
                message="Prompt IR does not cover all required scene facts.",
                affected_paths=missing_paths,
                suggested_action="repair_missing_paths",
            )
        )
    if conflicts:
        issues.append(
            ValidationIssue(
                code="positive_negative_conflict",
                severity="recoverable",
                message="A semantic term appears in both prompt polarities.",
                suggested_action="remove_conflicting_terms",
            )
        )
    if residual_terms:
        issues.append(
            ValidationIssue(
                code="removed_identity_residue",
                severity="recoverable",
                message="Prompt IR contains a removed character identity.",
                suggested_action="remove_identity_residue",
            )
        )
    if non_english_items:
        issues.append(
            ValidationIssue(
                code="non_target_language",
                severity="recoverable",
                message="Prompt IR contains non-English renderer phrases.",
                affected_paths=[
                    str(item.get("source_path") or "") for item in non_english_items
                ],
                suggested_action="normalize_prompt_language",
            )
        )
    if orphan_identity_terms:
        issues.append(
            ValidationIssue(
                code="unbound_identity_term",
                severity="blocking",
                message="An identity term is not bound to a scene participant.",
            )
        )

    report_model = ValidationReport(
        valid=not issues,
        issues=issues,
        missing_paths=missing_paths,
        conflicting_terms=conflicts,
        removed_identity_residue=residual_terms,
        required_path_count=len(required_paths),
        covered_path_count=len(covered),
    )
    report = report_model.model_dump(mode="python")
    report.update(
        {
            "issue_codes": [issue.code for issue in issues],
            "non_target_language_terms": [
                item.get("value") for item in non_english_items
            ],
            "orphan_identity_terms": orphan_identity_terms,
            "blocked": report_model.blocked,
        }
    )
    return {
        "validation_report": report,
        "needs_repair": report_model.needs_repair and not report_model.blocked,
        "has_blocking_errors": report_model.blocked,
        "messages": [
            AIMessage(
                content=(
                    "Prompt IR consistency check passed."
                    if not issues
                    else f"Found {len(issues)} consistency issues."
                ),
                name="prompt_consistency_validator",
            )
        ],
    }
# </agent-node>
