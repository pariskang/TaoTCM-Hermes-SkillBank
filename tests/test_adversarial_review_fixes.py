"""Regression tests for the defects confirmed by the adversarial review."""
import json

import pytest

from canon_tcm_hermes.agent.executor import StepResult
from canon_tcm_hermes.agent.planner import plan
from canon_tcm_hermes.agent.policies import Policies
from canon_tcm_hermes.agent.reflector import reflect
from canon_tcm_hermes.agent.state import AgentState
from canon_tcm_hermes.builders.pattern_aggregator import _contraindications_from_clauses, _prohibition_targets
from canon_tcm_hermes.inference.run_inference import run_inference


def _safety_clause(quote, formula, features):
    return {
        "clause_subtype": "contraindication",
        "conclusion": {"formula": formula, "raw": quote},
        "evidence": {"quote": quote},
        "features_present": features,
        "pulse_features": [],
        "risk_tier": "T3",
        "segment_id": "SEG::X",
    }


def test_contraindication_attaches_across_script_variants():
    # traditional-script prohibition must reach the simplified pattern
    clause = _safety_clause("太陽病，脈微弱，汗出惡風者，不可服麻黃湯。", "麻黃湯", ["汗出", "恶风", "脉微弱"])
    rules = _contraindications_from_clauses("麻黄汤", [clause])
    assert rules and rules[0]["action"] == "hard_stop"


def test_contraindication_does_not_hit_recommended_alternative():
    # contrast clause: 桂枝汤 prohibited, 麻黄汤 RECOMMENDED — the rule must
    # attach only to the prohibited formula
    quote = "脉浮紧，发热，无汗者，不可与桂枝汤，宜麻黄汤。"
    clause = _safety_clause(quote, "桂枝汤", ["发热", "无汗", "脉浮紧"])
    assert _prohibition_targets(quote) == ["桂枝汤"]
    assert _contraindications_from_clauses("桂枝汤", [clause])
    assert _contraindications_from_clauses("麻黄汤", [clause]) == []


def test_unknown_inference_mode_fails_closed():
    with pytest.raises(ValueError, match="unknown inference mode"):
        run_inference({"mode": "Patient_Intake", "features": ["发热"]})
    with pytest.raises(ValueError, match="unknown inference mode"):
        run_inference({"mode": "patient", "features": ["发热"]})


def test_failed_validation_summary_does_not_satisfy_planner(tmp_path):
    state = AgentState.load_or_create("r_gate", "skill_package", "in.xlsx", "skill_a", tmp_path / "outputs")
    report_dir = tmp_path / "outputs" / "runs" / "r_gate" / "reports"
    report_dir.mkdir(parents=True)
    (report_dir / "validation_summary.json").write_text('{"passed": false}', encoding="utf-8")
    assert "validate_run" in plan(state)
    (report_dir / "validation_summary.json").write_text('{"passed": true}', encoding="utf-8")
    assert "validate_run" not in plan(state)


def test_resume_resets_retry_budget(tmp_path):
    out = tmp_path / "outputs"
    state = AgentState.load_or_create("r_budget", "skill_package", "", "skill_a", out)
    state.step_attempts["annotate"] = 5
    state.status = "failed"
    state.save()
    resumed = AgentState.load_or_create("r_budget", "skill_package", "", "skill_a", out)
    assert resumed.step_attempts == {}


def test_agent_status_preserves_persisted_goal(tmp_path):
    from canon_tcm_hermes.agent.loop import agent_status

    out = tmp_path / "outputs"
    state = AgentState.load_or_create("r_goal", "annotate_corpus", "", "my_custom_skill", out)
    state.status = "done"
    state.save()
    status = agent_status("r_goal", out)
    assert status["goal"] == "annotate_corpus"
    assert status["skill_id"] == "my_custom_skill"
    assert status["status"] == "done"
    # peeking must not rewrite the persisted state
    assert AgentState.peek("r_goal", out).status == "done"


def test_os_permission_error_is_not_a_human_checkpoint(tmp_path):
    state = AgentState.load_or_create("r_perm", "skill_package", "", "skill_a", tmp_path / "outputs")
    os_error = StepResult(tool="annotate", ok=False, error="PermissionError: [Errno 13] Permission denied: '/x'")
    assert reflect(state, os_error, {}, Policies()).decision == "retry"
    sentinel = StepResult(tool="promote", ok=False, error="HumanApprovalRequired: promote requires a human expert decision")
    assert reflect(state, sentinel, {}, Policies()).decision == "pause_for_human"


def test_rollback_leaves_no_mixed_package(tmp_path):
    import yaml

    from canon_tcm_hermes.builders.hermes_skill_builder import build_skill
    from canon_tcm_hermes.governance.promotion import promote_version
    from canon_tcm_hermes.governance.rollback import rollback_version

    out = tmp_path / "outputs"
    build_skill("r1", "skill_a", out)
    audit = out / "runs" / "r1" / "audit"
    audit.mkdir(parents=True, exist_ok=True)
    (audit / "audit_package.json").write_text("{}", encoding="utf-8")
    reports = out / "runs" / "r1" / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    (reports / "validation_summary.json").write_text('{"passed": true}', encoding="utf-8")
    promote_version("r1", "expert_x", "promote", out, approved_version="1.0.0", skill_id="skill_a")
    package = build_skill("r2", "skill_a", out)
    stray = package / "references" / "current_only_artifact.jsonl"
    stray.write_text("{}", encoding="utf-8")
    rollback_version("r2", "expert_x", "bad build", "skill_a", out)
    assert not stray.exists(), "current-only files must not survive the restore"
    assert (package.parent / "skill_a.pre_rollback" / "references" / "current_only_artifact.jsonl").exists()
    restored = yaml.safe_load((package / "skill.yaml").read_text(encoding="utf-8"))
    assert restored["status"] == "stable_rolled_back"
    # a rolled-back package is expert-audited content: rebuild must refuse
    with pytest.raises(RuntimeError, match="expert-audited"):
        build_skill("r2", "skill_a", out)
