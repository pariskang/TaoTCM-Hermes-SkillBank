from canon_tcm_hermes.validators.protocol_assessor import assess_protocol


def test_protocol_assessment_is_honest_about_non_perfection():
    report = assess_protocol()
    assert report["claim"] == "not_perfect_all_features_research_grade"
    assert report["executable_counts"]["implemented"] > 0
    assert report["stable_promotion_allowed"] is False
    assert report["blocking_gaps_before_stable"]
    assert any(item["maturity_status"] != "mvp_complete" for item in report["items"])
