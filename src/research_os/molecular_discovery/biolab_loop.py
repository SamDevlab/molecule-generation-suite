"""Bounded Biolab next-action composition for the Molecular Discovery vertical.

The loop is deliberately domain-specific and decision-oriented.  It does not
execute docking, generate molecules, create evidence, or promote an evidence
level.  It composes the existing Research OS prioritization and external
evidence contracts and returns an auditable recommendation.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
from typing import Any, Mapping, Sequence

from research_os.external_evidence import ExternalEvidenceUpdate
from research_os.prioritization import PriorityRecommendation, ResearchPriorityAssessment, ResearchPriorityQueue


ACTION_TYPES = ("COMPUTE", "EXTERNAL_EVIDENCE", "EXPERIMENT", "STOP")
EVIDENCE_ORDER = {
    "TEST_SYNTHETIC": -1,
    "E0_HEURISTIC": 0,
    "E1_ML": 1,
    "E2_COMPUTATIONAL": 2,
    "E3_PHYSICS": 3,
    "E4_CURATED_EXPERIMENTAL": 4,
    "E5_VALIDATED_EXPERIMENTAL": 5,
}
OPEN_GAP_STATES = {"OPEN", "REGISTERED", "UNRESOLVED", "BLOCKED"}


def _tuple(values: Sequence[Any] | None) -> tuple[Any, ...]:
    return tuple(values or ())


def _mapping_tuple(values: Sequence[Mapping[str, Any]] | None) -> tuple[dict[str, Any], ...]:
    normalized: list[dict[str, Any]] = []
    for value in values or ():
        if isinstance(value, Mapping):
            normalized.append(dict(value))
        elif hasattr(value, "to_dict"):
            normalized.append(dict(value.to_dict()))
        else:
            normalized.append(dict(asdict(value)))
    return tuple(normalized)


def _level(value: Any) -> str:
    return getattr(value, "value", str(value))


def _max_evidence(levels: Sequence[str]) -> str | None:
    return max(levels, key=lambda value: EVIDENCE_ORDER.get(_level(value), -1), default=None)


@dataclass(frozen=True)
class BiolabScientificState:
    """Minimal scientific state consumed by the Molecular Discovery loop."""

    current_program: str
    current_evidence_levels: tuple[str, ...] = ()
    open_gaps: tuple[dict[str, Any], ...] = ()
    available_capabilities: tuple[str, ...] = ()
    external_dependencies: tuple[dict[str, Any], ...] = ()
    experiment_status: str = "AWAITING_EXTERNAL_PROTOCOL_OR_QUOTE"
    new_experimental_evidence_ids: tuple[str, ...] = ()
    affected_claim_ids: tuple[str, ...] = ()
    affected_gap_ids: tuple[str, ...] = ()
    superseded_assumptions: tuple[str, ...] = ()
    new_uncertainties: tuple[str, ...] = ()
    open_questions: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "current_evidence_levels", tuple(_level(item) for item in self.current_evidence_levels))
        object.__setattr__(self, "open_gaps", _mapping_tuple(self.open_gaps))
        object.__setattr__(self, "available_capabilities", tuple(str(item) for item in self.available_capabilities))
        object.__setattr__(self, "external_dependencies", _mapping_tuple(self.external_dependencies))
        for name in (
            "new_experimental_evidence_ids",
            "affected_claim_ids",
            "affected_gap_ids",
            "superseded_assumptions",
            "new_uncertainties",
            "open_questions",
        ):
            object.__setattr__(self, name, tuple(str(item) for item in getattr(self, name)))
        if not self.current_program.strip():
            raise ValueError("current_program is required")

    @property
    def highest_local_evidence(self) -> str | None:
        return _max_evidence(self.current_evidence_levels)

    @property
    def has_new_external_information(self) -> bool:
        if self.new_experimental_evidence_ids:
            return True
        return any(bool(item.get("new_external_information")) for item in self.external_dependencies)

    @property
    def decision_relevant_gaps(self) -> tuple[dict[str, Any], ...]:
        return tuple(item for item in self.open_gaps if str(item.get("status", "OPEN")) in OPEN_GAP_STATES)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["highest_local_evidence"] = self.highest_local_evidence
        data["has_new_external_information"] = self.has_new_external_information
        data["decision_relevant_gaps"] = [dict(item) for item in self.decision_relevant_gaps]
        return data


@dataclass(frozen=True)
class BiolabActionCandidate:
    """One proposed next action represented in the generic priority contract."""

    action_id: str
    action: str
    label: str
    candidate_question_id: str
    target_gap: str
    current_evidence: tuple[str, ...]
    target_evidence: tuple[str, ...]
    scientific_relevance: str
    expected_information_gain: str
    resolvability: str
    redundancy_risk: str
    required_engine_state: tuple[str, ...]
    required_dataset_state: tuple[str, ...]
    required_source_state: tuple[str, ...]
    external_dependency: str | None
    execution_scope: str
    safety_status: str
    recommendation: str
    rationale: str

    def __post_init__(self) -> None:
        if self.action not in ACTION_TYPES:
            raise ValueError(f"unsupported Biolab action: {self.action}")

    def to_assessment(self) -> ResearchPriorityAssessment:
        return ResearchPriorityAssessment(
            assessment_id=self.action_id,
            candidate_question_id=self.candidate_question_id,
            candidate_gap_id=self.target_gap,
            scientific_relevance=self.scientific_relevance,
            current_evidence=self.current_evidence,
            target_evidence=self.target_evidence,
            resolvability=self.resolvability,
            expected_information_gain=self.expected_information_gain,
            redundancy_risk=self.redundancy_risk,
            required_engine_state=self.required_engine_state,
            required_dataset_state=self.required_dataset_state,
            required_source_state=self.required_source_state,
            external_dependency=self.external_dependency,
            execution_scope=self.execution_scope,
            safety_status=self.safety_status,
            recommendation=self.recommendation,
            rationale=self.rationale,
        )

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["assessment"] = self.to_assessment().to_dict()
        return data


@dataclass(frozen=True)
class BiolabDecision:
    selected_action: str
    reason: str
    target_gap: str | None
    required_evidence: str | None
    current_evidence: str | None
    blocked_actions: tuple[str, ...] = ()
    stop_reason: str | None = None
    next_external_requirement: str | None = None
    status: str = "READY"
    computational_continuation_allowed: bool = True
    next_generation_allowed: bool = False
    assessments: tuple[dict[str, Any], ...] = ()
    priority_queue: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        if self.selected_action not in ACTION_TYPES:
            raise ValueError(f"unsupported selected action: {self.selected_action}")
        object.__setattr__(self, "blocked_actions", tuple(self.blocked_actions))
        object.__setattr__(self, "assessments", _mapping_tuple(self.assessments))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class BiolabLoopSnapshot:
    state: BiolabScientificState
    candidates: tuple[BiolabActionCandidate, ...]
    decision: BiolabDecision
    loop_version: str = "v0.1"

    def to_dict(self) -> dict[str, Any]:
        return {
            "loop_version": self.loop_version,
            "state": self.state.to_dict(),
            "candidates": [item.to_dict() for item in self.candidates],
            "decision": self.decision.to_dict(),
        }


def _gap_value(gap: Mapping[str, Any], key: str, default: Any = None) -> Any:
    return gap.get(key, default)


def _primary_gap(state: BiolabScientificState) -> dict[str, Any] | None:
    gaps = list(state.decision_relevant_gaps)
    if not gaps:
        return None
    order = {"GAP-EXPERIMENTAL-SOLUBILITY": 0, "GAP-EXPERIMENTAL-TARGET-ACTIVITY": 1, "GAP-EXPERIMENTAL-BINDING-VALIDATION": 2}
    return min(gaps, key=lambda item: (order.get(str(item.get("gap_id")), 99), str(item.get("gap_id", ""))))


def _build_candidates(state: BiolabScientificState, gap: Mapping[str, Any]) -> tuple[BiolabActionCandidate, ...]:
    gap_id = str(gap.get("gap_id"))
    required = _level(gap.get("required_evidence", "E4_CURATED_EXPERIMENTAL"))
    current = state.highest_local_evidence or "E0_HEURISTIC"
    requires_external = EVIDENCE_ORDER.get(required, 0) > EVIDENCE_ORDER.get(current, 0)
    compute_unblocked = state.has_new_external_information and bool(gap.get("computational_blocker", False))
    computational_continuation_allowed = not requires_external or compute_unblocked
    common = {
        "target_gap": gap_id,
        "current_evidence": (current,),
        "target_evidence": (required,),
        "scientific_relevance": str(gap.get("scientific_relevance", "decision-changing evidence for the active Biolab question")),
        "required_engine_state": (),
        "required_dataset_state": (),
        "required_source_state": (),
        "safety_status": "WITHIN_SCOPE",
    }
    return (
        BiolabActionCandidate(
            action_id="BIO-ACTION-A",
            action="COMPUTE",
            label="repeat/expand docking",
            candidate_question_id="ACTION-A-MORE-DOCKING",
            expected_information_gain="decision-relevant gain is low while the evidence ceiling remains E2",
            resolvability="bounded computationally",
            redundancy_risk="high same-level repetition",
            external_dependency=None,
            execution_scope="Molecular Discovery E2 computation only",
            recommendation="LOW_INFORMATION_GAIN" if not compute_unblocked else "SECONDARY",
            rationale="Existing MOLDISC-016 through MOLDISC-018 results already characterize the local docking boundary; new external information would be required to reopen this route.",
            **common,
        ),
        BiolabActionCandidate(
            action_id="BIO-ACTION-B",
            action="COMPUTE",
            label="pose-basin / reranking analysis",
            candidate_question_id="ACTION-B-POSE-BASIN",
            expected_information_gain="diagnostic rather than decision-changing",
            resolvability="bounded computationally",
            redundancy_risk="same-level explanation of an already characterized result",
            external_dependency=None,
            execution_scope="Molecular Discovery E2 diagnostic only",
            recommendation="DEFER",
            rationale="A pose diagnostic can explain E2 behavior but cannot substitute for the missing physical solubility measurement.",
            **common,
        ),
        BiolabActionCandidate(
            action_id="BIO-ACTION-C",
            action="COMPUTE",
            label="generate another molecular series",
            candidate_question_id="ACTION-C-NEW-SERIES",
            expected_information_gain="not interpretable before physical feedback",
            resolvability="blocked by evidence gate",
            redundancy_risk="would expand the open loop",
            external_dependency="REAL_E4_EXPERIMENTAL_FEEDBACK_REQUIRED",
            execution_scope="Molecular generation is not opened by this state",
            recommendation="BLOCKED",
            rationale="Generation cannot be selected as a default continuation while the next decision-changing evidence requires E4.",
            **common,
        ),
        BiolabActionCandidate(
            action_id="BIO-ACTION-D",
            action="EXPERIMENT",
            label="prepare physical solubility experiment",
            candidate_question_id="ACTION-D-SOLUBILITY-EXPERIMENT",
            expected_information_gain="directly addresses the highest open evidence gap",
            resolvability="actionable through an attributable external laboratory",
            redundancy_risk="low; this is a new evidence class",
            external_dependency="AWAITING_EXTERNAL_PROTOCOL_OR_QUOTE",
            execution_scope="vendor-neutral external BIOEXP-001 package",
            recommendation="PRIORITIZE_NOW",
            rationale="The frozen four-member panel is ready for external protocol, procurement and measurement; this is the first decision-changing evidence class beyond local E2.",
            **common,
        ),
    )


def evaluate_next_action(state: BiolabScientificState) -> BiolabLoopSnapshot:
    """Evaluate one bounded next action without executing it."""

    gap = _primary_gap(state)
    if gap is None:
        decision = BiolabDecision(
            selected_action="STOP",
            reason="No open decision-relevant gap is registered in the current scientific state.",
            target_gap=None,
            required_evidence=None,
            current_evidence=state.highest_local_evidence,
            stop_reason="NO_OPEN_DECISION_RELEVANT_GAPS",
            status="STOPPED",
            computational_continuation_allowed=False,
            next_generation_allowed=False,
        )
        return BiolabLoopSnapshot(state, (), decision)

    candidates = _build_candidates(state, gap)
    assessments = tuple(item.to_assessment() for item in candidates)
    queue = ResearchPriorityQueue.from_assessments(assessments, queue_id="BIO-LAB-PRIORITY-v0.1")
    selected_assessment = queue.assessment(queue.entries[0].candidate_question_id)
    selected = next(item for item in candidates if item.action_id == selected_assessment.assessment_id)
    required = _level(gap.get("required_evidence", "E4_CURATED_EXPERIMENTAL"))
    current = state.highest_local_evidence
    requires_external = EVIDENCE_ORDER.get(required, 0) > EVIDENCE_ORDER.get(current or "", -1)
    computational_continuation_allowed = not requires_external or state.has_new_external_information and bool(gap.get("computational_blocker", False))
    blocked = tuple(item.action for item in candidates if item.recommendation in {"BLOCKED", "LOW_INFORMATION_GAIN"})
    stop_reason = "EXPERIMENTAL_VALIDATION_REQUIRED" if selected.action == "EXPERIMENT" and requires_external and not state.new_experimental_evidence_ids else None
    status = "STOPPED" if stop_reason else "READY"
    decision = BiolabDecision(
        selected_action=selected.action,
        reason=selected.rationale,
        target_gap=selected.target_gap,
        required_evidence=required,
        current_evidence=current,
        blocked_actions=tuple(dict.fromkeys(blocked)),
        stop_reason=stop_reason,
        next_external_requirement=selected.external_dependency,
        status=status,
        computational_continuation_allowed=computational_continuation_allowed,
        next_generation_allowed=False,
        assessments=tuple(item.to_dict() for item in candidates),
        priority_queue=queue.to_dict(),
    )
    return BiolabLoopSnapshot(state, candidates, decision)


def apply_e4_feedback(state: BiolabScientificState, update: ExternalEvidenceUpdate | Mapping[str, Any]) -> BiolabScientificState:
    """Return a new state after a validated E4 update; never mutates evidence."""

    record = update.to_dict() if isinstance(update, ExternalEvidenceUpdate) else dict(update)
    evidence_ids = tuple(str(item) for item in record.get("evidence_ids", ()))
    gap_ids = tuple(str(item) for item in record.get("affected_gap_ids", ()))
    existing_ids = tuple(dict.fromkeys((*state.new_experimental_evidence_ids, *evidence_ids)))
    levels = tuple(dict.fromkeys((*state.current_evidence_levels, "E4_CURATED_EXPERIMENTAL")))
    gaps: list[dict[str, Any]] = []
    for gap in state.open_gaps:
        item = dict(gap)
        if str(item.get("gap_id")) in gap_ids:
            item["status"] = "EVIDENCE_RECEIVED"
            item["evidence_ids"] = list(dict.fromkeys((*item.get("evidence_ids", ()), *evidence_ids)))
        gaps.append(item)
    return replace(
        state,
        current_evidence_levels=levels,
        open_gaps=tuple(gaps),
        experiment_status="E4_RESULT_INGESTED",
        new_experimental_evidence_ids=existing_ids,
        affected_claim_ids=tuple(
            dict.fromkeys(
                (*state.affected_claim_ids, *(str(item) for item in record.get("affected_claim_ids", ())))
            )
        ),
        affected_gap_ids=tuple(dict.fromkeys((*state.affected_gap_ids, *gap_ids))),
        open_questions=tuple(dict.fromkeys((*state.open_questions, "Reassess the next scientific action using the newly ingested E4 result."))),
    )


def default_moldisc018_state() -> BiolabScientificState:
    """Create the frozen first state used by MOLDISC-019."""

    return BiolabScientificState(
        current_program="MOLDISC-018",
        current_evidence_levels=("E2_COMPUTATIONAL",),
        open_gaps=(
            {"gap_id": "GAP-EXPERIMENTAL-SOLUBILITY", "question": "What is the measured solubility of the frozen Biolab panel?", "required_evidence": "E4_CURATED_EXPERIMENTAL", "scientific_relevance": "first physical feedback for the active panel", "status": "OPEN"},
            {"gap_id": "GAP-EXPERIMENTAL-TARGET-ACTIVITY", "question": "Does the panel show biochemical target activity?", "required_evidence": "E4_CURATED_EXPERIMENTAL", "scientific_relevance": "target activity remains unmeasured", "status": "OPEN"},
            {"gap_id": "GAP-EXPERIMENTAL-BINDING-VALIDATION", "question": "Can binding be validated experimentally?", "required_evidence": "E4_CURATED_EXPERIMENTAL", "scientific_relevance": "binding remains unresolved", "status": "OPEN"},
        ),
        available_capabilities=("E2_COMPUTATIONAL", "EXTERNAL_EVIDENCE", "EXPERIMENT"),
        external_dependencies=({"dependency": "BIOEXP-001", "status": "AWAITING_EXTERNAL_PROTOCOL_OR_QUOTE"},),
        experiment_status="AWAITING_EXTERNAL_PROTOCOL_OR_QUOTE",
    )


__all__ = [
    "ACTION_TYPES",
    "BiolabScientificState",
    "BiolabActionCandidate",
    "BiolabDecision",
    "BiolabLoopSnapshot",
    "apply_e4_feedback",
    "default_moldisc018_state",
    "evaluate_next_action",
]
