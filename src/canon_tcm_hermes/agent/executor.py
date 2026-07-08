"""Executor: runs one tool against the current state, capturing outcome."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from canon_tcm_hermes.agent.state import AgentState
from canon_tcm_hermes.agent.tool_registry import ToolSpec


@dataclass
class StepResult:
    tool: str
    ok: bool
    error: str | None = None
    result_summary: str = ""


def execute(tool: ToolSpec, state: AgentState) -> StepResult:
    try:
        result: Any = tool.run(state)
    except Exception as exc:  # noqa: BLE001 — the reflector decides what failures mean
        return StepResult(tool=tool.name, ok=False, error=f"{type(exc).__name__}: {exc}")
    summary = ""
    if isinstance(result, dict):
        summary = ", ".join(f"{k}={v}" for k, v in list(result.items())[:4] if isinstance(v, (int, float, str, bool)))
    return StepResult(tool=tool.name, ok=True, result_summary=summary[:300])
