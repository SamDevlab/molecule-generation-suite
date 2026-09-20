import copy
import json
from pathlib import Path

from research_os.core.types import EvidenceLevel, GateStatus
from research_os.docking.capability import (
    CapabilityClassification,
    DockingContext,
    capability_metadata,
    classify_docking_context,
    load_profile,
    profile_identity_from_mapping,
)
from research_os.docking.claims import docking_capability_claim_gate


PROFILE_PATH = Path(__file__).parents[1] / "configs" / "docking-capability-profile-v1.json"
HISTORICAL_PROFILE_PATH = Path(__file__).parents[1] / "configs" / "docking-capability-profile-snapshots" / "b8c5c799b2035bae2796de714cc55dc4e607420e13b309b7f33792ebaf5597bb.json"


def test_profile_loads_with_deterministic_identity_and_e2_level():
    profile = load_profile(PROFILE_PATH)
    assert profile.profile_id == "research-os.docking.capability-profile.v1+1f33fae86f78827f"
    assert profile.profile_hash == "1f33fae86f78827f954597b8e0bec455e696fec560ac74f014049c0759d7f8ea"
    assert profile.evidence_level is EvidenceLevel.E2_COMPUTATIONAL


def test_historical_profile_snapshot_preserves_frozen_identity_and_sources():
    profile = load_profile(HISTORICAL_PROFILE_PATH)
    assert profile.profile_id == "research-os.docking.capability-profile.v1+b8c5c799b2035bae"
    assert profile.profile_hash == "b8c5c799b2035bae2796de714cc55dc4e607420e13b309b7f33792ebaf5597bb"
    assert profile.context_record("NON_COGNATE_HOLO_CROSSDOCKING")["evidence_source_ids"] == ["CROSSDOCK-001"]


def test_context_classification_is_explicit_and_unknown_is_out_of_domain():
    profile = load_profile(PROFILE_PATH)
    assert classify_docking_context(DockingContext.COGNATE_REDOCKING, profile) is CapabilityClassification.VALIDATED_IN_DOMAIN
    assert classify_docking_context("NON_COGNATE_HOLO_CROSSDOCKING", profile) is CapabilityClassification.PARTIALLY_VALIDATED
    assert classify_docking_context("RIGID_APO_DOCKING", profile) is CapabilityClassification.INSUFFICIENTLY_VALIDATED
    assert classify_docking_context("not-a-context", profile) is CapabilityClassification.OUT_OF_DOMAIN


def test_profile_identity_changes_for_scientific_mutations_but_not_operational_metadata():
    source = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
    base_id, base_hash = profile_identity_from_mapping(source)
    operational = copy.deepcopy(source)
    operational["operational_metadata"] = {"timestamp": "2099-01-01T00:00:00Z", "local_path": "C:/other/path", "branch": "other"}
    assert profile_identity_from_mapping(operational) == (base_id, base_hash)

    mutations = [
        ("evidence_sources", lambda value: value[0].update({"scientific_result_hash": "changed"})),
        ("contexts", lambda value: value[0].update({"claim_boundary": "changed"})),
        ("known_failure_modes", lambda value: value[0].update({"description": "changed"})),
        ("interpretation_boundaries", lambda value: value[0].update({"prohibition": "changed"})),
    ]
    for field, mutate in mutations:
        changed = copy.deepcopy(source)
        mutate(changed[field])
        assert profile_identity_from_mapping(changed)[1] != base_hash, field


def test_profile_identity_changes_for_endpoint_threshold_and_classification():
    source = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
    base_hash = profile_identity_from_mapping(source)[1]
    endpoint = copy.deepcopy(source)
    endpoint["evidence_sources"][0]["endpoint"] = "threshold changed"
    threshold = copy.deepcopy(source)
    threshold["evidence_sources"][0]["primary_performance"]["success_count"] = 7
    classification = copy.deepcopy(source)
    classification["contexts"][0]["classification"] = "PARTIALLY_VALIDATED"
    assert profile_identity_from_mapping(endpoint)[1] != base_hash
    assert profile_identity_from_mapping(threshold)[1] != base_hash
    assert profile_identity_from_mapping(classification)[1] != base_hash


def test_claim_gate_fails_closed_for_unknown_and_apo_but_allows_bounded_cognate_claim():
    profile = load_profile(PROFILE_PATH)
    unknown = docking_capability_claim_gate("computational pose localization", docking_context="missing", profile=profile)
    apo = docking_capability_claim_gate("exploratory computational result", docking_context="RIGID_APO_DOCKING", profile=profile)
    cognate = docking_capability_claim_gate("bounded computational pose-localization result", docking_context="COGNATE_REDOCKING", profile=profile)
    forbidden = docking_capability_claim_gate("measured affinity from docking score", docking_context="COGNATE_REDOCKING", profile=profile)
    assert unknown.status is GateStatus.INSUFFICIENT_EVIDENCE
    assert apo.status is GateStatus.INSUFFICIENT_EVIDENCE
    assert cognate.status is GateStatus.PASS
    assert forbidden.status is GateStatus.FAIL


def test_capability_metadata_is_machine_readable_and_preserves_limitations():
    metadata = capability_metadata("NON_COGNATE_HOLO_CROSSDOCKING", load_profile(PROFILE_PATH))
    assert metadata["capability_profile_id"].startswith("research-os.docking.capability-profile.v1+")
    assert metadata["docking_context"] == "NON_COGNATE_HOLO_CROSSDOCKING"
    assert metadata["capability_status"] == "PARTIALLY_VALIDATED"
    assert metadata["evidence_level"] == "E2_COMPUTATIONAL"
    assert metadata["validation_sources"] == ["CROSSDOCK-001", "MOLDISC-018-RECIPROCAL-HOLO"]
    assert metadata["known_limitations"]
