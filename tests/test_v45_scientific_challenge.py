import pytest

from research_os.impact import FalseConservatismAudit, ScientificChallenge, ScientificChallengeStatus, ScientificChallengeStore


def test_scientific_challenge_is_review_only_and_append_only():
    challenge = ScientificChallenge(
        "CH-1", "CLM-1", "DEC-1", ("EVD-1",), ("same protocol",), ("structure dependence",), (), ("independent experiment",), ("receptor identity",), ("same source",), ScientificChallengeStatus.NEEDS_EXTERNAL_VALIDATION, "run an independent compatible experiment"
    )
    assert challenge.valid
    store = ScientificChallengeStore()
    store.append(challenge)
    with pytest.raises(ValueError, match="already registered"):
        store.append(challenge)


def test_false_conservatism_audit_is_digest_bound():
    audit = FalseConservatismAudit("FCA-1", "DEC-1", "NO_DECISION", ("EVD-1",), True, "bounded deterministic evidence was sufficient", "the refusal exceeded the declared scope", "revise to bounded decision")
    assert audit.valid
    assert audit.to_dict()["false_conservatism_detected"] is True
