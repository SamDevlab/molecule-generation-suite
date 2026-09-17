import pytest

from research_os.impact import ResearchImpactReview, ResearchImpactReviewStore


def test_impact_review_is_append_only_and_digest_bound():
    review = ResearchImpactReview(
        "IMPR-1",
        "PROG-1",
        {"claims": ["CLM-OLD"], "decisions": []},
        {"claims": ["CLM-OLD"], "decisions": ["DEC-NEW"]},
        ("IMP-1",),
        ("decision changed",),
        ("evidence level",),
        ("identical rerun",),
        (),
        "acquire matched external validation",
    )
    assert review.valid
    store = ResearchImpactReviewStore()
    store.append(review)
    with pytest.raises(ValueError, match="already registered"):
        store.append(review)


def test_impact_review_does_not_require_a_magic_score():
    review = ResearchImpactReview("IMPR-2", "PROG-2", {}, {}, (), (), ("nothing changed",), (), ("external blocker",), "wait for eligible source")
    assert review.valid
    assert "score" not in review.to_dict()
