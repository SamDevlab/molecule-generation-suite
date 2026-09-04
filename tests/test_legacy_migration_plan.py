from research_os.legacy import LegacyTargetClass, classify_legacy_target


def test_rdkit_properties_are_marked_deterministic():
    assert classify_legacy_target("Score_QED").target_class == LegacyTargetClass.DETERMINISTIC
    assert classify_legacy_target("TPSA").target_class == LegacyTargetClass.DETERMINISTIC
    assert classify_legacy_target("Peso_Molar").target_class == LegacyTargetClass.DETERMINISTIC


def test_historical_isp_proxy_is_quarantined():
    item = classify_legacy_target("AERO_Impulso_Espec_Teorico")
    assert item.target_class == LegacyTargetClass.HEURISTIC_REVIEW
    assert item.action == "quarantine_and_rederive_from_physics_or_experiment"


def test_empirical_admet_like_target_can_remain_ml_candidate():
    assert classify_legacy_target("experimental_solubility").target_class == LegacyTargetClass.MODEL_CANDIDATE
