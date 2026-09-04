from __future__ import annotations

from pathlib import Path

import pytest

from research_os.campaigns import CampaignStatus
from research_os.resolution import (
    ConditionMatchStatus,
    ConditionMatcher,
    DockingReproducibilityAssessment,
    ElectrochemicalObservation,
    ExternalValidationAssessment,
    GapResolution,
    MaterialObservation,
    ResolutionStatus,
    ResolutionStore,
)
from research_os.web.server import build_default_application


def test_gap_resolution_has_required_fields_digest_and_status():
    item = GapResolution("RES-1", "GAP-1", "2026-01-01T00:00:00+00:00", "bounded attempt", ("SRC-1",), (), ("engine-1",), (), ("E0_HEURISTIC",), ("E0_HEURISTIC",), ResolutionStatus.BLOCKED, "engine unavailable")
    assert item.valid
    assert item.to_dict()["status"] == "BLOCKED"
    assert item.to_dict()["resolution_id"] == "RES-1"


def test_resolution_store_is_append_only(tmp_path: Path):
    store = ResolutionStore(tmp_path / "resolutions.sqlite")
    item = GapResolution("RES-1", "GAP-1", "2026-01-01T00:00:00+00:00", "attempt", (), (), (), (), (), (), "UNRESOLVED", "missing record")
    store.save(item)
    with pytest.raises(ValueError, match="append-only"):
        store.save(item)
    assert len(store.list(gap_id="GAP-1")) == 1
    store.close()


def test_condition_matcher_match_is_comparable():
    result = ConditionMatcher.match({"material": "316L", "temperature": "20 C"}, {"material": "316L", "temperature": "20 C"}, ("material", "temperature"))
    assert result.status is ConditionMatchStatus.MATCH
    assert result.comparable


def test_condition_matcher_partial_unknown_and_incompatible_never_compare_as_match():
    partial = ConditionMatcher.match({"material": "316L", "temperature": "UNKNOWN"}, {"material": "316L", "temperature": "20 C"}, ("material", "temperature"))
    unknown = ConditionMatcher.match({}, {}, ("material", "temperature"))
    incompatible = ConditionMatcher.match({"material": "316L"}, {"material": "7075"}, ("material",))
    assert partial.status is ConditionMatchStatus.PARTIAL_MATCH and not partial.comparable
    assert unknown.status is ConditionMatchStatus.UNKNOWN and not unknown.comparable
    assert incompatible.status is ConditionMatchStatus.INCOMPATIBLE and not incompatible.comparable


def test_material_observation_keeps_missing_fields_unknown():
    item = MaterialObservation.from_mapping({"material": "316L", "source_id": "SRC-HE", "locator": "table 1"}, observation_id="MAT-1")
    assert item.temperature == "UNKNOWN"
    assert item.value is None
    assert item.to_dict()["condition_fields"]["stress"] == "UNKNOWN"


def test_electrochemical_observation_records_units_and_missing_measurements():
    item = ElectrochemicalObservation("BATT-1", "battery-1", "SRC-BATT", cell_id="RW1", cycle_index=5, operation="discharge", temperature_c=25.0, current_a=2.0, voltage_v=3.4, time_s=10.0, units={"temperature_c": "degC", "current_a": "A", "voltage_v": "V", "time_s": "s"})
    assert item.capacity_ah is None
    assert item.complete_condition_fields == ("cell_id", "cycle_index", "operation", "temperature_c", "current_a", "voltage_v", "time_s")


def test_external_validation_assessment_blocks_same_source_promotion():
    item = ExternalValidationAssessment("aqsoldb-g", ("SRC-AQSOLDB-DATA",), "MODEL-1", "real-data-golden.v1", None, None, None, None, "SAME_SOURCE_AS_TRAINING", "NOT_ELIGIBLE_AS_EXTERNAL_TEST", "NOT_PROMOTED", ("same lineage",))
    assert item.to_dict()["promotion_decision"] == "NOT_PROMOTED"
    assert item.to_dict()["status"] == "NOT_ELIGIBLE_AS_EXTERNAL_TEST"


def test_docking_reproducibility_assessment_preserves_e2_ceiling():
    item = DockingReproducibilityAssessment("CAM-1", ("RUN-1", "RUN-2", "RUN-3"), (1, 2, 3), (-7.1, -7.0, -7.1), True, "REPRODUCED", score_spread_kcal_mol=0.1)
    assert item.reproducible
    assert item.to_dict()["evidence_level"] == "E2_COMPUTATIONAL"


def test_codex_test_provider_resolution_selection_is_catalog_bound(tmp_path: Path):
    app = build_default_application(tmp_path, oracle_mode="test")
    try:
        campaign = app.campaigns.start("P-COMB-01")
        challenge = app.campaigns.final_resolution_challenge()
        assert challenge["gap_id"] == campaign.gaps[0].gap_id
        assert challenge["scientific_evidence_created"] is False
    finally:
        app.close()


def test_pharma_gap_is_blocked_when_vina_and_openbabel_are_absent(tmp_path: Path):
    app = build_default_application(tmp_path, oracle_mode="test")
    try:
        campaign = app.campaigns.start("P-PHARMA-01")
        resolution = app.campaigns.resolve_gap(campaign.campaign_id, "GAP-PHARMA-DOCKING")
        assert resolution.status is ResolutionStatus.BLOCKED
        assert resolution.run_ids == ()
        assert resolution.assessments["docking_reproducibility"]["evidence_level"] == "E2_COMPUTATIONAL"
    finally:
        app.close()


def test_combustion_gap_runs_small_phi_campaign_without_e4_upgrade(tmp_path: Path):
    app = build_default_application(tmp_path, oracle_mode="test")
    try:
        campaign = app.campaigns.start("P-COMB-01")
        resolution = app.campaigns.resolve_gap(campaign.campaign_id, "GAP-COMB-VALIDATION")
        assert len(resolution.run_ids) == 3
        if not app.service.engine_registry.get_engine("cantera").available:
            assert resolution.status is ResolutionStatus.BLOCKED
            return
        assert resolution.status is ResolutionStatus.PARTIALLY_RESOLVED
        assert resolution.evidence_after == ("E3_PHYSICS",)
        assert resolution.assessments["cantera_trend"]["equivalence_ratios"] == [0.8, 1.0, 1.2]
    finally:
        app.close()


def test_materials_gap_stops_without_a_record_level_observation(tmp_path: Path):
    app = build_default_application(tmp_path, oracle_mode="test")
    try:
        campaign = app.campaigns.start("P-MAT-01")
        resolution = app.campaigns.resolve_gap(campaign.campaign_id, campaign.gaps[0].gap_id)
        assert resolution.status is ResolutionStatus.UNRESOLVED
        assert resolution.assessments["condition_match"]["status"] == "UNKNOWN"
        assert resolution.assessments["observation_count"] == 0
    finally:
        app.close()


def test_battery_resolution_requires_local_hashed_artifact(tmp_path: Path):
    app = build_default_application(tmp_path, oracle_mode="test")
    try:
        campaign = app.campaigns.start("P-BATT-01")
        resolution = app.campaigns.resolve_gap(campaign.campaign_id, campaign.gaps[0].gap_id)
        assert resolution.status is ResolutionStatus.BLOCKED
        assert "artifact" in resolution.remaining_gap
    finally:
        app.close()


def test_http_resolution_history_and_unresolvable_challenge(tmp_path: Path):
    app = build_default_application(tmp_path, oracle_mode="test")
    try:
        _, campaign = app.dispatch("POST", "/api/campaigns/start", {"problem_id": "P-PHARMA-01"})
        code, resolution = app.dispatch("POST", f"/api/campaigns/{campaign['campaign_id']}/gaps/GAP-PHARMA-DOCKING/resolve", {})
        assert code == 201 and resolution["status"] == "BLOCKED"
        code, history = app.dispatch("GET", f"/api/campaigns/{campaign['campaign_id']}/resolutions")
        assert code == 200 and len(history["resolutions"]) == 1
        code, challenge = app.dispatch("POST", "/api/campaigns/unresolvable-challenge", {})
        assert code == 200 and challenge["execution"] == "NOT_ATTEMPTED_BY_DESIGN"
    finally:
        app.close()
