import pytest

from research_os.external_evidence import ExternalValidationCampaign, ExternalValidationCampaignStore, ValidationCampaignStatus


def test_external_validation_campaign_keeps_independence_and_digest():
    campaign = ExternalValidationCampaign(
        "VAL-1",
        "CLM-1",
        ("EVD-1",),
        "independent compatible measured target and molecule identity",
        ("SRC-EXT-1",),
        ("DATA-EXT-1",),
        ({"source_id": "SRC-EXT-1", "status": "INDEPENDENT", "overlap_count": 0},),
        "SRC-EXT-1",
        {"target_units": "log10(mol/L)", "model_frozen": True},
        {"MAE": 1.2, "OOD_fraction": 1.0},
        ("REV-1",),
        (),
        ValidationCampaignStatus.FAILED_VALIDATION,
    )
    assert campaign.valid
    store = ExternalValidationCampaignStore()
    store.append(campaign)
    with pytest.raises(ValueError, match="already registered"):
        store.append(campaign)


def test_completed_external_campaign_requires_selected_source():
    with pytest.raises(ValueError, match="selected source"):
        ExternalValidationCampaign(
            "VAL-2", "CLM-2", (), "compatible validation", (), (), (), None, {}, {}, (), (), ValidationCampaignStatus.VALIDATED
        )


def test_no_eligible_campaign_may_preserve_candidates_without_result_source():
    campaign = ExternalValidationCampaign(
        "VAL-3", "CLM-3", (), "overlap and unit audit", ("SRC-CANDIDATE",), ("DATA-CANDIDATE",), ({"status": "UNKNOWN"},), None, {}, {"reason": "overlap unresolved"}, (), (), ValidationCampaignStatus.NO_ELIGIBLE_EXTERNAL_DATA
    )
    assert campaign.valid and campaign.selected_validation_source is None
