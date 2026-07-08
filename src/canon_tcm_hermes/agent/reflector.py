"""Reflector: turns observations into the next loop decision.

Decisions: continue | retry | abort | pause_for_human. Warnings are
recorded in state (and memory) instead of being lost in logs.
"""
from __future__ import annotations

from dataclasses import dataclass

from canon_tcm_hermes.agent.executor import StepResult
from canon_tcm_hermes.agent.policies import Policies
from canon_tcm_hermes.agent.state import AgentState


@dataclass
class Reflection:
    decision: str  # continue|retry|abort|pause_for_human
    reason: str
    warnings: list[str]


def reflect(state: AgentState, step: StepResult, observation: dict, policies: Policies) -> Reflection:
    warnings: list[str] = []
    if observation.get("annotation_errors", 0) >= policies.annotation_error_warn_threshold:
        warnings.append(f"{observation['annotation_errors']} annotation errors recorded (see errors/annotation_errors.jsonl)")
    if observation.get("citation_failures", 0) >= policies.citation_failure_warn_threshold:
        warnings.append(f"{observation['citation_failures']} citation verification failures")
    if policies.empty_core_warn and observation.get("empty_core_patterns", 0) > 0:
        warnings.append(f"{observation['empty_core_patterns']} empty-core pattern(s) excluded from inference, queued for audit")

    if not step.ok:
        attempts = state.step_attempts.get(step.tool, 0)
        # dedicated sentinel type — an OS PermissionError must NOT be
        # mistaken for a governance checkpoint
        if isinstance(step.error, str) and step.error.startswith("HumanApprovalRequired"):
            return Reflection("pause_for_human", f"tool {step.tool} requires a human decision: {step.error}", warnings)
        if attempts < policies.max_attempts_per_step:
            return Reflection("retry", f"step {step.tool} failed ({step.error}); attempt {attempts + 1}/{policies.max_attempts_per_step}", warnings)
        return Reflection("abort", f"step {step.tool} exhausted retries: {step.error}", warnings)

    missing = [a for a, exists in observation.get("artifacts_produced", {}).items() if not exists]
    if missing:
        attempts = state.step_attempts.get(step.tool, 0)
        if attempts < policies.max_attempts_per_step:
            return Reflection("retry", f"step {step.tool} reported success but artifacts missing: {missing}", warnings)
        return Reflection("abort", f"step {step.tool} cannot materialize artifacts: {missing}", warnings)

    if policies.hard_stop_on_validation_failure and observation.get("validation_passed") is False:
        return Reflection("abort", "pipeline validation failed — see reports/validation_summary.json", warnings)

    return Reflection("continue", f"step {step.tool} verified", warnings)
