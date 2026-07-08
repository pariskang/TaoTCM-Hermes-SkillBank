"""Dependency-driven planner.

Plans are recomputed from the CURRENT artifact state on every loop
iteration: satisfied steps disappear, missing prerequisites pull their
producers in, and a failed step's artifacts simply stay missing so the
next replan retries the frontier. This makes the plan dynamic (resume,
partial reruns, injected artifacts all just work) instead of a hardcoded
stage list.
"""
from __future__ import annotations

from canon_tcm_hermes.agent.state import AgentState
from canon_tcm_hermes.agent.tool_registry import TOOLS, ToolSpec, artifact_satisfied

# goal -> target artifacts that must exist for the goal to be satisfied
GOALS: dict[str, tuple[str, ...]] = {
    "annotate_corpus": ("annotations/clause_templates.jsonl", "reports/genre_report.json"),
    "evidence_ready": ("evidence/evidence_index.jsonl", "reports/citation_validation_report.json"),
    "eval_ready": ("reports/ablation_report.json", "reports/counterfactual_report.json", "reports/attribution_report.json", "reports/conformal_report.json"),
    "skill_package": (
        "skills/{skill_id}/skill.yaml", "audit/audit_package.json", "reports/validation_summary.json",
        "reports/ablation_report.json", "reports/attribution_report.json", "reports/conformal_report.json",
        "reports/protocol_assessment_report.json", "reports/model_card.md",
    ),
}


def goal_targets(goal: str) -> tuple[str, ...]:
    if goal not in GOALS:
        raise ValueError(f"unknown goal {goal!r}; supported: {sorted(GOALS)}")
    return GOALS[goal]


def _producer(artifact: str) -> ToolSpec | None:
    for tool in TOOLS.values():
        if artifact in tool.produces:
            return tool
    return None


def plan(state: AgentState) -> list[str]:
    """Topologically-ordered tool names needed to satisfy the goal now."""
    needed: list[str] = []
    visiting: set[str] = set()

    def resolve(artifact: str) -> None:
        # satisfied = exists AND valid (a failed validation summary does not
        # count, so the validation gate is re-run instead of skipped)
        if artifact_satisfied(state, artifact):
            return
        tool = _producer(artifact)
        if tool is None:
            raise ValueError(f"no registered tool produces required artifact {artifact!r}")
        if tool.name in needed:
            return
        if tool.name in visiting:
            raise ValueError(f"dependency cycle at tool {tool.name!r}")
        visiting.add(tool.name)
        for requirement in tool.requires:
            resolve(requirement)
        visiting.discard(tool.name)
        if tool.name not in needed:
            needed.append(tool.name)

    for target in goal_targets(state.goal):
        resolve(target)
    return needed
