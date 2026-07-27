"""Typed domain contracts for the prompt-generation workflow."""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class DomainModel(BaseModel):
    """Base contract that rejects misspelled LLM fields."""

    model_config = ConfigDict(extra="forbid")


class CharacterIdentity(DomainModel):
    input_name: str = ""
    canonical_name: str = ""
    series: str = ""
    danbooru_tag: str = ""


class Participant(DomainModel):
    id: str
    label: str = ""
    type: Literal[
        "named_character",
        "generic_person",
        "animal",
        "role",
        "object",
    ] = "generic_person"
    adult: bool = True
    identity: CharacterIdentity = Field(default_factory=CharacterIdentity)
    appearance: List[str] = Field(default_factory=list)
    clothing: List[str] = Field(default_factory=list)
    expressions: List[str] = Field(default_factory=list)
    poses: List[str] = Field(default_factory=list)
    actions: List[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def named_character_has_name(self) -> "Participant":
        if self.type == "named_character" and not self.identity.input_name.strip():
            raise ValueError("named_character requires identity.input_name")
        return self


class Environment(DomainModel):
    location: str = ""
    time: str = ""
    weather: str = ""
    background: List[str] = Field(default_factory=list)


class Composition(DomainModel):
    framing: List[str] = Field(default_factory=list)
    camera: List[str] = Field(default_factory=list)
    lighting: List[str] = Field(default_factory=list)
    style: List[str] = Field(default_factory=list)
    effects: List[str] = Field(default_factory=list)


class MotionSpec(DomainModel):
    type: str = ""
    axis: str = ""
    direction: str = ""
    speed: str = ""


class ContactSpec(DomainModel):
    surface: str = ""
    direction: str = ""
    pressure: str = ""


class SpatialSpec(DomainModel):
    placement: List[str] = Field(default_factory=list)
    orientation: str = ""
    relative_position: str = ""
    motion: MotionSpec = Field(default_factory=MotionSpec)
    contact: ContactSpec = Field(default_factory=ContactSpec)
    pose_analogy: str = ""


class Relation(DomainModel):
    id: str
    subject: str = ""
    predicate: str = ""
    object: str = ""
    instrument: str = ""
    source: str = ""
    body_region: str = ""
    details: List[str] = Field(default_factory=list)
    spatial: SpatialSpec = Field(default_factory=SpatialSpec)
    subject_kind: Literal["participant", "external"] = "external"
    object_kind: Literal["participant", "external"] = "external"


class Requirements(DomainModel):
    positive: List[str] = Field(default_factory=list)
    negative: List[str] = Field(default_factory=list)
    required: List[str] = Field(default_factory=list)
    forbidden: List[str] = Field(default_factory=list)


class RevisionMetadata(DomainModel):
    request_id: str = ""
    base_document_version: int = 0
    touched_paths: List[str] = Field(default_factory=list)


class SceneDocument(DomainModel):
    schema_version: int = 3
    version: int = 0
    summary: str = ""
    participants: Dict[str, Participant] = Field(default_factory=dict)
    environment: Environment = Field(default_factory=Environment)
    composition: Composition = Field(default_factory=Composition)
    relations: Dict[str, Relation] = Field(default_factory=dict)
    requirements: Requirements = Field(default_factory=Requirements)
    revision_metadata: RevisionMetadata = Field(default_factory=RevisionMetadata)

    @model_validator(mode="after")
    def references_are_bound(self) -> "SceneDocument":
        participant_ids = set(self.participants)
        for relation in self.relations.values():
            for endpoint, kind in (
                (relation.subject, relation.subject_kind),
                (relation.object, relation.object_kind),
            ):
                if kind == "participant" and endpoint not in participant_ids:
                    raise ValueError(
                        f"relation {relation.id!r} references missing participant {endpoint!r}"
                    )
        return self


class PatchOperation(DomainModel):
    op: Literal["add", "replace", "remove"]
    path: str
    value: Any = None
    evidence: str = ""


class DetectedEntity(DomainModel):
    source_text: str
    entity_type: Literal["named_character", "generic_person", "animal", "role", "object", "location"]
    bound_id: str = ""


class ScenePatch(DomainModel):
    request_id: str = ""
    base_version: int
    intent: str = "edit"
    operations: List[PatchOperation] = Field(default_factory=list, max_length=64)
    touched_paths: List[str] = Field(default_factory=list)
    clarification: Optional[str] = None
    clarification_options: List[str] = Field(default_factory=list, max_length=4)
    detected_entities: List[DetectedEntity] = Field(default_factory=list)
    rejected_enrichment_ids: List[str] = Field(default_factory=list, max_length=32)
    add_positive_constraints: List[str] = Field(default_factory=list, max_length=16)
    add_negative_constraints: List[str] = Field(default_factory=list, max_length=16)
    removed_constraint_ids: List[str] = Field(default_factory=list, max_length=32)

    @model_validator(mode="after")
    def values_match_operations(self) -> "ScenePatch":
        for operation in self.operations:
            if operation.op != "remove" and operation.value is None:
                raise ValueError(f"Patch operation {operation.op!r} requires value")
        if not self.touched_paths:
            self.touched_paths = [operation.path for operation in self.operations]
        unbound = [
            entity.source_text
            for entity in self.detected_entities
            if entity.entity_type == "named_character" and not entity.bound_id.strip()
        ]
        if unbound and not self.clarification:
            raise ValueError(
                "named characters require participant bindings: " + ", ".join(unbound)
            )
        return self


class SceneCoverageAudit(DomainModel):
    complete: bool = True
    missing_facts: List[str] = Field(default_factory=list, max_length=16)
    reason: str = ""


class ImpactSet(DomainModel):
    identity_changed: bool = False
    visual_changed: bool = False
    identity_changed_participant_ids: List[str] = Field(default_factory=list)
    identity_deleted_participant_ids: List[str] = Field(default_factory=list)
    participant_visual_changed_ids: List[str] = Field(default_factory=list)
    environment_changed: bool = False
    composition_changed: bool = False
    relations_changed: bool = False
    requirements_changed: bool = False
    removed_identity_terms: List[str] = Field(default_factory=list)
    invalidated_artifacts: List[str] = Field(default_factory=list)
    touched_paths: List[str] = Field(default_factory=list)
    changed_document_version: int = 0


class PromptTerm(DomainModel):
    value: str
    kind: str = "descriptive_phrase"
    polarity: Literal["positive", "negative"] = "positive"
    source_path: str
    participant_id: str = ""
    provenance: str = ""
    inferred: bool = False

    @field_validator("value")
    @classmethod
    def value_is_not_empty(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("PromptTerm.value cannot be empty")
        return value


class PromptIR(DomainModel):
    document_version: int
    identity_terms: List[PromptTerm] = Field(default_factory=list)
    atomic_terms: List[PromptTerm] = Field(default_factory=list)
    relation_terms: List[PromptTerm] = Field(default_factory=list)
    negative_terms: List[PromptTerm] = Field(default_factory=list)
    positive_terms: List[PromptTerm] = Field(default_factory=list)
    compiled_negative_terms: List[PromptTerm] = Field(default_factory=list)
    covered_paths: List[str] = Field(default_factory=list)
    identity_tag_records: List[Dict[str, Any]] = Field(default_factory=list)
    identity_tag_resolutions: List[Dict[str, Any]] = Field(default_factory=list)
    identity_tag_adjudication: Dict[str, Any] = Field(default_factory=dict)
    visual_tag_records: List[Dict[str, Any]] = Field(default_factory=list)
    visual_tag_resolutions: List[Dict[str, Any]] = Field(default_factory=list)
    visual_tag_adjudication: Dict[str, Any] = Field(default_factory=dict)
    danbooru_tag_records: List[Dict[str, Any]] = Field(default_factory=list)
    repair_overlay: Dict[str, Any] = Field(default_factory=dict)
    enrichment_overlay: Dict[str, Any] = Field(default_factory=dict)
    constraint_overlay: Dict[str, Any] = Field(default_factory=dict)


class ValidationIssue(DomainModel):
    code: str
    severity: Literal["warning", "recoverable", "blocking"]
    message: str
    affected_paths: List[str] = Field(default_factory=list)
    suggested_action: str = ""


class ValidationReport(DomainModel):
    valid: bool
    issues: List[ValidationIssue] = Field(default_factory=list)
    missing_paths: List[str] = Field(default_factory=list)
    conflicting_terms: List[str] = Field(default_factory=list)
    removed_identity_residue: List[str] = Field(default_factory=list)
    required_path_count: int = 0
    covered_path_count: int = 0

    @property
    def needs_repair(self) -> bool:
        return any(issue.severity == "recoverable" for issue in self.issues)

    @property
    def blocked(self) -> bool:
        return any(issue.severity == "blocking" for issue in self.issues)


class PromptResult(DomainModel):
    status: Literal["valid", "degraded", "failed", "needs_clarification"]
    positive_prompt: Optional[str] = None
    negative_prompt: Optional[str] = None
    target_model: str
    warnings: List[str] = Field(default_factory=list)
    unresolved_requirements: List[str] = Field(default_factory=list)
    document_version: int = 0


class IdentityProposal(DomainModel):
    participant_id: str
    input_name: str
    canonical_name: str = ""
    series: str = ""
    danbooru_tag_candidates: List[str] = Field(default_factory=list)


class IdentityExtraction(DomainModel):
    identities: List[IdentityProposal] = Field(default_factory=list)


class IdentityDecision(DomainModel):
    participant_id: str
    action: Literal["select", "retry", "name_only"]
    selected_tag: str = ""
    retry_candidates: List[str] = Field(default_factory=list)
    canonical_name: str = ""
    reason: str = ""


class IdentityAdjudication(DomainModel):
    decisions: List[IdentityDecision] = Field(default_factory=list)


class AtomicVisualFact(DomainModel):
    fact_id: str = ""
    source_path: str
    candidates: List[str] = Field(default_factory=list)
    fallback_phrase: str
    inferred: bool = False


class RelationVisualFact(DomainModel):
    fact_id: str = ""
    source_path: str
    phrase: str
    inferred: bool = False


class NegativeVisualFact(DomainModel):
    fact_id: str = ""
    source_path: str
    phrase: str


class VisualExtraction(DomainModel):
    atomic_facts: List[AtomicVisualFact] = Field(default_factory=list)
    relation_facts: List[RelationVisualFact] = Field(default_factory=list)
    negative_facts: List[NegativeVisualFact] = Field(default_factory=list)


class VisualTagDecision(DomainModel):
    fact_index: int
    action: Literal["select", "retry", "phrase_only"]
    selected_tags: List[str] = Field(default_factory=list)
    retry_candidates: List[str] = Field(default_factory=list)
    preserve_phrase: bool = True
    preserved_phrase: str = ""
    reason: str = ""


class VisualTagAdjudication(DomainModel):
    decisions: List[VisualTagDecision] = Field(default_factory=list)


class RepairTerm(DomainModel):
    value: str
    source_path: str
    kind: str = "repair_phrase"


class RepairOverlay(DomainModel):
    document_version: int = 0
    depends_on_paths: List[str] = Field(default_factory=list)
    add_positive: List[RepairTerm] = Field(default_factory=list)
    add_negative: List[RepairTerm] = Field(default_factory=list)
    remove_positive: List[str] = Field(default_factory=list)
    remove_negative: List[str] = Field(default_factory=list)
