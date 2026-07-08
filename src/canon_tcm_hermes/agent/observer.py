"""Observer: reads the world (run artifacts) after each action.

Observations are facts, not judgments — the reflector interprets them.
"""
from __future__ import annotations

import json
from typing import Any

from canon_tcm_hermes.agent.state import AgentState
from canon_tcm_hermes.agent.tool_registry import TOOLS, artifact_exists
from canon_tcm_hermes.utils import read_jsonl, run_dir


def observe(state: AgentState, tool_name: str) -> dict[str, Any]:
    rd = run_dir(state.run_id, state.output_dir)
    tool = TOOLS[tool_name]
    observation: dict[str, Any] = {
        "tool": tool_name,
        "artifacts_produced": {a.format(skill_id=state.skill_id): artifact_exists(state, a) for a in tool.produces},
    }
    errors_path = rd / "errors" / "annotation_errors.jsonl"
    if errors_path.exists():
        observation["annotation_errors"] = len(read_jsonl(errors_path))
    citation_path = rd / "reports" / "citation_validation_report.json"
    if citation_path.exists():
        citation = json.loads(citation_path.read_text(encoding="utf-8"))
        observation["citation_failures"] = len(citation.get("failures", []))
        observation["citation_verified_rate"] = citation.get("verified_rate")
    patterns_path = rd / "patterns" / "pattern_aggregations.jsonl"
    if patterns_path.exists():
        patterns = read_jsonl(patterns_path)
        observation["patterns"] = len(patterns)
        observation["empty_core_patterns"] = sum(1 for p in patterns if not p.get("core_features"))
    validation_path = rd / "reports" / "validation_summary.json"
    if validation_path.exists():
        observation["validation_passed"] = bool(json.loads(validation_path.read_text(encoding="utf-8")).get("passed"))
    return observation
