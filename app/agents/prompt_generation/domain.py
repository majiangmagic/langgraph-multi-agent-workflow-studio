"""Domain contracts and deterministic operations for prompt generation."""

from __future__ import annotations

from copy import deepcopy
import re
from typing import Any, Dict, Iterable, List, Mapping

from pydantic import ValidationError

from app.agents.prompt_generation.models import (
    ImpactSet,
    SceneDocument,
    ScenePatch,
)


DOCUMENT_SECTIONS = (
    "participants",
    "environment",
    "composition",
    "relations",
    "requirements",
)
PATCH_OPERATIONS = {"add", "replace", "remove"}
CJK_PATTERN = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")


def contains_cjk(value: Any) -> bool:
    """Return whether text contains CJK ideographs unsuitable for current renderers."""

    return bool(CJK_PATTERN.search(str(value or "")))


def unique_text(values: Iterable[Any]) -> List[str]:
    """Return stable, non-empty text values without case-insensitive duplicates."""

    result: List[str] = []
    seen = set()
    for value in values:
        text = str(value or "").strip()
        key = text.casefold()
        if text and key not in seen:
            result.append(text)
            seen.add(key)
    return result


def text_list(value: Any) -> List[str]:
    if isinstance(value, str):
        value = [value]
    return unique_text(value if isinstance(value, list) else [])


def empty_scene_document() -> Dict[str, Any]:
    """Create the model-independent source document for a new conversation."""

    return {
        "schema_version": 2,
        "version": 0,
        "summary": "",
        "participants": {},
        "environment": {
            "location": "",
            "time": "",
            "weather": "",
            "background": [],
        },
        "composition": {
            "framing": [],
            "camera": [],
            "lighting": [],
            "style": [],
            "effects": [],
        },
        "relations": {},
        "requirements": {
            "positive": [],
            "negative": [],
            "required": [],
            "forbidden": [],
        },
        "revision_metadata": {
            "request_id": "",
            "base_document_version": 0,
            "touched_paths": [],
        },
    }


def _normalize_participants(value: Any) -> Dict[str, Dict[str, Any]]:
    if isinstance(value, list):
        value = {
            str(item.get("id") or f"character_{index}"): item
            for index, item in enumerate(value, start=1)
            if isinstance(item, dict)
        }
    if not isinstance(value, dict):
        return {}
    result: Dict[str, Dict[str, Any]] = {}
    for index, (raw_id, raw_item) in enumerate(value.items(), start=1):
        if not isinstance(raw_item, dict):
            continue
        participant_id = str(raw_id or f"character_{index}").strip()
        identity = raw_item.get("identity")
        if not isinstance(identity, dict):
            identity = {"input_name": str(identity or "").strip()}
        identity_values = {
            "input_name": str(identity.get("input_name") or "").strip(),
            "canonical_name": str(identity.get("canonical_name") or "").strip(),
            "series": str(identity.get("series") or "").strip(),
            "danbooru_tag": str(identity.get("danbooru_tag") or "").strip(),
        }
        raw_type = str(raw_item.get("type") or "").strip().lower()
        if raw_type in {"named", "named_character"}:
            participant_type = "named_character"
        elif raw_type == "character":
            participant_type = (
                "named_character" if identity_values["input_name"] else "generic_person"
            )
        elif raw_type in {"human", "person", "generic_person"}:
            participant_type = "generic_person"
        elif raw_type in {"animal", "creature"}:
            participant_type = "animal"
        elif raw_type in {"role", "actor"}:
            participant_type = "role"
        elif raw_type in {"object", "prop"}:
            participant_type = "object"
        else:
            participant_type = (
                "named_character" if identity_values["input_name"] else "generic_person"
            )
        result[participant_id] = {
            "id": participant_id,
            "type": participant_type,
            "adult": bool(raw_item.get("adult", True)),
            "identity": identity_values,
            "appearance": text_list(raw_item.get("appearance")),
            "clothing": text_list(raw_item.get("clothing")),
            "expressions": text_list(raw_item.get("expressions")),
            "poses": text_list(raw_item.get("poses")),
            "actions": text_list(raw_item.get("actions")),
        }
    return result


def _normalize_relations(
    value: Any, participant_ids: Iterable[str] = ()
) -> Dict[str, Dict[str, Any]]:
    if isinstance(value, list):
        value = {
            str(item.get("id") or f"relation_{index}"): item
            for index, item in enumerate(value, start=1)
            if isinstance(item, dict)
        }
    if not isinstance(value, dict):
        return {}
    result: Dict[str, Dict[str, Any]] = {}
    known_participants = set(participant_ids)
    for index, (raw_id, raw_item) in enumerate(value.items(), start=1):
        if not isinstance(raw_item, dict):
            continue
        relation_id = str(raw_id or f"relation_{index}").strip()
        subject = str(raw_item.get("subject") or "").strip()
        object_value = str(raw_item.get("object") or "").strip()
        result[relation_id] = {
            "id": relation_id,
            "subject": subject,
            "predicate": str(raw_item.get("predicate") or "").strip(),
            "object": object_value,
            "instrument": str(raw_item.get("instrument") or "").strip(),
            "source": str(raw_item.get("source") or "").strip(),
            "body_region": str(raw_item.get("body_region") or "").strip(),
            "details": text_list(raw_item.get("details")),
            "subject_kind": str(
                raw_item.get("subject_kind")
                or ("participant" if subject in known_participants else "external")
            ),
            "object_kind": str(
                raw_item.get("object_kind")
                or ("participant" if object_value in known_participants else "external")
            ),
        }
    return result


def normalize_scene_document(value: Any, version: int | None = None) -> Dict[str, Any]:
    """Normalize model output into the stable SceneDocument contract."""

    source = value if isinstance(value, dict) else {}
    document = empty_scene_document()
    document["version"] = int(
        version if version is not None else source.get("version") or 0
    )
    document["summary"] = str(source.get("summary") or "").strip()
    document["participants"] = _normalize_participants(source.get("participants"))

    environment = source.get("environment") or {}
    if isinstance(environment, dict):
        document["environment"] = {
            "location": str(environment.get("location") or "").strip(),
            "time": str(environment.get("time") or "").strip(),
            "weather": str(environment.get("weather") or "").strip(),
            "background": text_list(environment.get("background")),
        }

    composition = source.get("composition") or {}
    if isinstance(composition, dict):
        document["composition"] = {
            key: text_list(composition.get(key))
            for key in ("framing", "camera", "lighting", "style", "effects")
        }

    document["relations"] = _normalize_relations(
        source.get("relations"), document["participants"].keys()
    )
    requirements = source.get("requirements") or {}
    if isinstance(requirements, dict):
        document["requirements"] = {
            key: text_list(requirements.get(key))
            for key in ("positive", "negative", "required", "forbidden")
        }
    revision = source.get("revision_metadata") or {}
    if isinstance(revision, dict):
        document["revision_metadata"] = {
            "request_id": str(revision.get("request_id") or "").strip(),
            "base_document_version": int(
                revision.get("base_document_version") or 0
            ),
            "touched_paths": text_list(revision.get("touched_paths")),
        }
    identity_keys = {
        str(value or "").strip().casefold()
        for participant in document["participants"].values()
        for value in (participant.get("identity") or {}).values()
        if value
    }
    for key in ("positive", "required"):
        document["requirements"][key] = [
            value
            for value in document["requirements"][key]
            if value.casefold() not in identity_keys
        ]
    return SceneDocument.model_validate(document).model_dump(mode="python")


def parse_pointer(path: str) -> List[str]:
    """Parse a restricted RFC 6901-style path."""

    if path in {"", "/"}:
        return []
    if not path.startswith("/"):
        raise ValueError(f"Patch path must start with '/': {path}")
    return [segment.replace("~1", "/").replace("~0", "~") for segment in path[1:].split("/")]


def validate_patch_proposal(value: Any, current_version: int) -> Dict[str, Any]:
    """Validate untrusted LLM patch data without executing arbitrary code."""

    if not isinstance(value, dict):
        raise ValueError("PatchProposal must be an object")
    try:
        patch = ScenePatch.model_validate(value)
    except ValidationError as exc:
        raise ValueError(f"Invalid PatchProposal: {exc}") from exc
    base_version = patch.base_version
    if base_version != current_version:
        raise ValueError(
            f"Patch base_version {base_version} does not match {current_version}"
        )
    operations = patch.operations
    normalized = []
    for operation in operations:
        op = operation.op
        path = operation.path.strip()
        parse_pointer(path)
        normalized.append(
            {
                "op": op,
                "path": path,
                **({"value": deepcopy(operation.value)} if op != "remove" else {}),
                "evidence": operation.evidence.strip(),
            }
        )
    return {
        "request_id": patch.request_id,
        "base_version": base_version,
        "intent": patch.intent.strip(),
        "operations": normalized,
        "touched_paths": list(patch.touched_paths),
        "clarification": patch.clarification,
        "detected_entities": [
            item.model_dump(mode="python") for item in patch.detected_entities
        ],
    }


def _resolve_parent(document: Any, segments: List[str]) -> tuple[Any, str]:
    if not segments:
        return None, ""
    current = document
    for segment in segments[:-1]:
        if isinstance(current, dict):
            if segment not in current:
                raise ValueError(f"Patch path does not exist: {segment}")
            current = current[segment]
        elif isinstance(current, list):
            current = current[int(segment)]
        else:
            raise ValueError("Patch path traverses a scalar value")
    return current, segments[-1]


def apply_patch_proposal(
    current: Mapping[str, Any], proposal: Mapping[str, Any]
) -> Dict[str, Any]:
    """Apply validated operations transactionally and return a new document version."""

    working: Any = deepcopy(dict(current))
    operations = proposal.get("operations") or []
    previous_participant_ids = set((current.get("participants") or {}).keys())
    for operation in operations:
        op = operation["op"]
        segments = parse_pointer(operation["path"])
        if not segments:
            if op == "remove":
                working = empty_scene_document()
            else:
                if not isinstance(operation.get("value"), dict):
                    raise ValueError("Root SceneDocument replacement must be an object")
                working = deepcopy(operation["value"])
            continue
        parent, key = _resolve_parent(working, segments)
        if isinstance(parent, dict):
            if op == "remove":
                if key not in parent:
                    raise ValueError(f"Patch remove path does not exist: {operation['path']}")
                del parent[key]
            else:
                if op == "replace" and key not in parent:
                    raise ValueError(f"Patch replace path does not exist: {operation['path']}")
                parent[key] = deepcopy(operation["value"])
        elif isinstance(parent, list):
            if key == "-" and op == "add":
                parent.append(deepcopy(operation["value"]))
            else:
                index = int(key)
                if op == "remove":
                    parent.pop(index)
                elif op == "add":
                    parent.insert(index, deepcopy(operation["value"]))
                else:
                    parent[index] = deepcopy(operation["value"])
        else:
            raise ValueError("Patch target parent is not a container")

    removed_participant_ids = previous_participant_ids - set(
        (working.get("participants") or {}).keys()
    )
    next_participant_ids = set((working.get("participants") or {}).keys())
    for entity in proposal.get("detected_entities") or []:
        if (
            entity.get("entity_type") == "named_character"
            and entity.get("bound_id") not in next_participant_ids
        ):
            raise ValueError(
                f"Named character '{entity.get('source_text')}' is not bound to a participant"
            )
    for relation_id, relation in (working.get("relations") or {}).items():
        for field in ("subject", "object"):
            if str(relation.get(field) or "") in removed_participant_ids:
                raise ValueError(
                    f"Relation '{relation_id}' references missing participant "
                    f"'{relation.get(field)}'"
                )
    next_version = int(current.get("version") or 0) + (1 if operations else 0)
    working["revision_metadata"] = {
        "request_id": str(proposal.get("request_id") or ""),
        "base_document_version": int(proposal.get("base_version") or 0),
        "touched_paths": list(proposal.get("touched_paths") or []),
    }
    result = normalize_scene_document(working, version=next_version)
    validate_scene_document(result)
    return result


def validate_scene_document(document: Mapping[str, Any]) -> None:
    """Validate the complete typed SceneDocument contract."""

    try:
        SceneDocument.model_validate(document)
    except ValidationError as exc:
        raise ValueError(f"Invalid SceneDocument: {exc}") from exc


def _identity_tokens(document: Mapping[str, Any]) -> List[str]:
    values = []
    for participant in (document.get("participants") or {}).values():
        identity = participant.get("identity") or {}
        values.extend(
            identity.get(key)
            for key in ("input_name", "canonical_name", "danbooru_tag")
        )
    return unique_text(values)


def compute_impact_set(
    previous: Mapping[str, Any], current: Mapping[str, Any]
) -> Dict[str, Any]:
    """Compute deterministic invalidation scopes for incremental resolution."""

    previous_participants = previous.get("participants") or {}
    current_participants = current.get("participants") or {}
    previous_identity = {
        key: (value.get("type"), value.get("identity") or {})
        for key, value in previous_participants.items()
    }
    current_identity = {
        key: (value.get("type"), value.get("identity") or {})
        for key, value in current_participants.items()
    }
    identity_changed_ids = sorted(
        key
        for key in set(previous_identity) | set(current_identity)
        if previous_identity.get(key) != current_identity.get(key)
    )
    deleted_ids = sorted(set(previous_participants) - set(current_participants))
    identity_changed = bool(identity_changed_ids)
    def visual_projection(document: Mapping[str, Any]) -> Dict[str, Any]:
        participants = {
            participant_id: {
                key: value
                for key, value in participant.items()
                if key != "identity"
            }
            for participant_id, participant in (
                document.get("participants") or {}
            ).items()
        }
        return {
            "participants": participants,
            **{
                key: document.get(key)
                for key in DOCUMENT_SECTIONS
                if key != "participants"
            },
        }

    visual_previous = visual_projection(previous)
    visual_current = visual_projection(current)
    visual_changed = visual_previous != visual_current
    old_tokens = _identity_tokens(previous)
    new_keys = {value.casefold() for value in _identity_tokens(current)}
    participant_visual_changed_ids = sorted(
        participant_id
        for participant_id in set(previous_participants) | set(current_participants)
        if {
            key: value
            for key, value in previous_participants.get(participant_id, {}).items()
            if key != "identity"
        }
        != {
            key: value
            for key, value in current_participants.get(participant_id, {}).items()
            if key != "identity"
        }
    )
    impact = {
        "identity_changed": identity_changed,
        "visual_changed": visual_changed,
        "identity_changed_participant_ids": identity_changed_ids,
        "identity_deleted_participant_ids": deleted_ids,
        "participant_visual_changed_ids": participant_visual_changed_ids,
        "environment_changed": previous.get("environment") != current.get("environment"),
        "composition_changed": previous.get("composition") != current.get("composition"),
        "relations_changed": previous.get("relations") != current.get("relations"),
        "requirements_changed": previous.get("requirements") != current.get("requirements"),
        "removed_identity_terms": [
            value for value in old_tokens if value.casefold() not in new_keys
        ],
        "invalidated_artifacts": [
            *(["identity_resolution"] if identity_changed else []),
            *(["visual_resolution"] if visual_changed else []),
        ],
        "touched_paths": list(
            (current.get("revision_metadata") or {}).get("touched_paths") or []
        ),
        "changed_document_version": current.get("version"),
    }
    return ImpactSet.model_validate(impact).model_dump(mode="python")


def collect_required_paths(document: Mapping[str, Any]) -> List[str]:
    """List semantic source paths that should produce prompt material."""

    paths: List[str] = []
    for participant_id, participant in (document.get("participants") or {}).items():
        if (participant.get("identity") or {}).get("input_name"):
            paths.append(f"/participants/{participant_id}/identity")
        for key in ("appearance", "clothing", "expressions", "poses", "actions"):
            for index, _ in enumerate(participant.get(key) or []):
                paths.append(f"/participants/{participant_id}/{key}/{index}")
    environment = document.get("environment") or {}
    for key in ("location", "time", "weather"):
        if environment.get(key):
            paths.append(f"/environment/{key}")
    for index, _ in enumerate(environment.get("background") or []):
        paths.append(f"/environment/background/{index}")
    for key, values in (document.get("composition") or {}).items():
        for index, _ in enumerate(values or []):
            paths.append(f"/composition/{key}/{index}")
    for relation_id in (document.get("relations") or {}):
        paths.append(f"/relations/{relation_id}")
    requirements = document.get("requirements") or {}
    for key in ("positive", "required"):
        for index, _ in enumerate(requirements.get(key) or []):
            paths.append(f"/requirements/{key}/{index}")
    return paths
