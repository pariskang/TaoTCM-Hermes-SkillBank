import json

import pytest

from canon_tcm_hermes.agent import TOOLS, agent_status, run_agent
from canon_tcm_hermes.agent.executor import execute
from canon_tcm_hermes.agent.planner import plan
from canon_tcm_hermes.agent.policies import Policies
from canon_tcm_hermes.agent.reflector import reflect
from canon_tcm_hermes.agent.executor import StepResult
from canon_tcm_hermes.agent.state import AgentState


def test_planner_orders_by_dependencies(tmp_path):
    state = AgentState.load_or_create("r_plan", "skill_package", "in.xlsx", "skill_a", tmp_path / "outputs")
    steps = plan(state)
    assert steps[0] == "load_excel"
    assert steps.index("annotate") > steps.index("route_genre")
    assert steps.index("build_skill") > steps.index("build_eval_cases")
    assert steps.index("validate_run") > steps.index("eval_ablation")
    assert "promote" not in steps  # goals never include the human decision


def test_agent_reaches_goal_and_self_recovers(tmp_path):
    from canon_tcm_hermes.demo_data import make_demo

    xlsx = make_demo(tmp_path / "demo.xlsx")
    out = tmp_path / "outputs"
    state = run_agent("r_agent", input_path=str(xlsx), output_dir=out, verbose=False)
    assert state.status == "done"
    status = agent_status("r_agent", out)
    assert status["goal_satisfied"] is True and status["remaining_plan"] == []

    # interrupt recovery: remove two artifacts, replan runs exactly those steps
    (out / "runs" / "r_agent" / "reports" / "model_card.md").unlink()
    (out / "runs" / "r_agent" / "reports" / "conformal_report.json").unlink()
    status = agent_status("r_agent", out)
    assert set(status["remaining_plan"]) == {"conformal", "model_card"}
    state = run_agent("r_agent", input_path=str(xlsx), output_dir=out, verbose=False)
    assert state.status == "done"

    # episodic memory recorded the loop
    memory = (out / "runs" / "r_agent" / "agent" / "memory.jsonl").read_text(encoding="utf-8").splitlines()
    kinds = {json.loads(line)["kind"] for line in memory}
    assert {"goal", "plan", "act", "observe", "reflect", "done"} <= kinds


def test_promote_is_never_autonomous(tmp_path):
    assert TOOLS["promote"].needs_human is True
    state = AgentState.load_or_create("r_gate", "skill_package", "", "skill_a", tmp_path / "outputs")
    result = execute(TOOLS["promote"], state)
    assert result.ok is False and "human expert" in (result.error or "")
    reflection = reflect(state, result, {"artifacts_produced": {}}, Policies())
    assert reflection.decision == "pause_for_human"


def test_reflector_aborts_after_retry_budget(tmp_path):
    state = AgentState.load_or_create("r_ref", "skill_package", "", "skill_a", tmp_path / "outputs")
    failing = StepResult(tool="annotate", ok=False, error="ValueError: boom")
    policies = Policies()
    state.step_attempts["annotate"] = 1
    assert reflect(state, failing, {}, policies).decision == "retry"
    state.step_attempts["annotate"] = policies.max_attempts_per_step
    assert reflect(state, failing, {}, policies).decision == "abort"


def test_reflector_hard_stops_on_validation_failure(tmp_path):
    state = AgentState.load_or_create("r_val", "skill_package", "", "skill_a", tmp_path / "outputs")
    ok = StepResult(tool="validate_run", ok=True)
    reflection = reflect(state, ok, {"artifacts_produced": {}, "validation_passed": False}, Policies())
    assert reflection.decision == "abort"
