"""The agent loop: Plan → Act → Observe → Reflect, until goal or human.

Differences from the fixed `canon all` pipeline:
- the plan is recomputed from live artifact state each iteration
  (resume/self-recovery: interrupted runs continue where they stopped);
- every step is observed and reflected on; failures retry under policy,
  then abort with a recorded reason instead of half-finishing;
- T3 decisions (promotion) always pause for a human — the loop can reach
  audit-ready, never stable;
- state and episodic memory persist under outputs/runs/<run>/agent/.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from canon_tcm_hermes.agent.executor import execute
from canon_tcm_hermes.agent.memory import EpisodicMemory
from canon_tcm_hermes.agent.observer import observe
from canon_tcm_hermes.agent.planner import goal_targets, plan
from canon_tcm_hermes.agent.policies import Policies
from canon_tcm_hermes.agent.reflector import reflect
from canon_tcm_hermes.agent.state import AgentState
from canon_tcm_hermes.agent.tool_registry import TOOLS, artifact_satisfied


def run_agent(
    run_id: str,
    goal: str = "skill_package",
    input_path: str = "",
    skill_id: str = "shanghan_six_formula_cluster",
    output_dir: str | Path = "outputs",
    policies: Policies | None = None,
    verbose: bool = True,
) -> AgentState:
    policies = policies or Policies()
    state = AgentState.load_or_create(run_id, goal, input_path, skill_id, output_dir)
    memory = EpisodicMemory(run_id, output_dir)
    memory.record("goal", {"goal": goal, "targets": list(goal_targets(goal))})

    for iteration in range(1, policies.max_loop_iterations + 1):
        current_plan = plan(state)
        state.plan = current_plan
        if not current_plan:
            state.status = "done"
            state.save()
            memory.record("done", {"iterations": iteration, "completed_steps": state.completed_steps})
            _say(verbose, f"[agent] goal '{goal}' satisfied after {iteration - 1} action(s)")
            return state

        step_name = current_plan[0]
        tool = TOOLS[step_name]
        if tool.needs_human or step_name in policies.never_autonomous:
            state.status = "paused_for_human"
            state.human_checkpoint = step_name
            state.save()
            memory.record("pause_for_human", {"tool": step_name, "reason": "policy: requires human decision"})
            _say(verbose, f"[agent] paused: step '{step_name}' requires a human decision")
            return state

        state.status = "running"
        state.step_attempts[step_name] = state.step_attempts.get(step_name, 0) + 1
        state.save()
        memory.record("plan", {"iteration": iteration, "plan": current_plan})
        _say(verbose, f"[agent] {iteration:02d} act: {step_name} — {tool.description}")

        result = execute(tool, state)
        observation = observe(state, step_name)
        reflection = reflect(state, result, observation, policies)
        memory.record("act", {"tool": step_name, "ok": result.ok, "error": result.error, "summary": result.result_summary})
        memory.record("observe", {"tool": step_name, **{k: v for k, v in observation.items() if k != "tool"}})
        memory.record("reflect", {"tool": step_name, "decision": reflection.decision, "reason": reflection.reason, "warnings": reflection.warnings})

        for warning in reflection.warnings:
            if warning not in state.warnings:
                state.warnings.append(warning)

        if reflection.decision == "continue":
            if step_name not in state.completed_steps:
                state.completed_steps.append(step_name)
            state.save()
            continue
        if reflection.decision == "retry":
            _say(verbose, f"[agent]    retry: {reflection.reason}")
            state.save()
            continue
        if reflection.decision == "pause_for_human":
            state.status = "paused_for_human"
            state.human_checkpoint = step_name
            state.save()
            _say(verbose, f"[agent] paused: {reflection.reason}")
            return state
        state.status = "failed"
        state.failure_reason = reflection.reason
        state.save()
        memory.record("failed", {"reason": reflection.reason})
        _say(verbose, f"[agent] failed: {reflection.reason}")
        return state

    # the final step may have succeeded on the last allowed iteration —
    # check goal satisfaction once more before declaring budget exhaustion
    if not plan(state):
        state.status = "done"
        state.save()
        memory.record("done", {"iterations": policies.max_loop_iterations, "completed_steps": state.completed_steps})
        return state
    state.status = "failed"
    state.failure_reason = f"loop budget exhausted ({policies.max_loop_iterations} iterations)"
    state.save()
    memory.record("failed", {"reason": state.failure_reason})
    return state


def agent_status(run_id: str, output_dir: str | Path = "outputs") -> dict[str, Any]:
    # read-only: report against the run's PERSISTED goal and skill_id
    state = AgentState.peek(run_id, output_dir)
    if state is None:
        return {"run_id": run_id, "status": "not_started", "completed_steps": [], "remaining_plan": [], "warnings": [], "human_checkpoint": None, "goal_satisfied": False, "targets": {}}
    remaining = plan(state)
    return {
        "run_id": run_id,
        "goal": state.goal,
        "skill_id": state.skill_id,
        "status": state.status,
        "completed_steps": state.completed_steps,
        "remaining_plan": remaining,
        "warnings": state.warnings,
        "human_checkpoint": state.human_checkpoint,
        "goal_satisfied": not remaining,
        "targets": {t.format(skill_id=state.skill_id): artifact_satisfied(state, t) for t in goal_targets(state.goal)},
    }


def _say(verbose: bool, message: str) -> None:
    if verbose:
        print(message)
