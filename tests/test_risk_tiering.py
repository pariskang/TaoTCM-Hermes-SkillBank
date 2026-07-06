from canon_tcm_hermes.governance.risk_tiering import assign_risk_tier


def test_hard_stop_contraindication_is_t3():
    item = {"contraindications": [{"condition": ["脉微弱"], "action": "hard_stop", "risk_tier": "T3"}]}
    assert assign_risk_tier(item) == "T3"


def test_empty_contraindications_key_is_not_t3():
    # the old substring matcher tiered every pattern T3 because the key name
    # 'contraindications' always appears in str(item)
    item = {"contraindications": [], "exclusion_features": [], "aggregation_decisions": []}
    assert assign_risk_tier(item) == "T0"


def test_needs_audit_decision_is_t2():
    item = {"contraindications": [], "aggregation_decisions": [{"needs_audit": True}]}
    assert assign_risk_tier(item) == "T2"


def test_hard_exclusion_is_t2():
    item = {"exclusion_features": [{"feature": "汗出", "strength": "hard"}]}
    assert assign_risk_tier(item) == "T2"


def test_teaching_material_is_t1():
    assert assign_risk_tier({"usage": "teaching"}) == "T1"


def test_explicit_tier_never_lowered_below_structure():
    item = {"risk_tier": "T1", "contraindications": [{"action": "hard_stop"}]}
    assert assign_risk_tier(item) == "T3"
