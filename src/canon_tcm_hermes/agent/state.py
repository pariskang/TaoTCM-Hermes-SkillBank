"""Persistent agent state: the single source of truth for a run's loop.

State survives process restarts (outputs/runs/<run>/agent/state.json), so
an interrupted agent resumes from its last observation instead of
restarting the pipeline — task self-recovery per the agent review.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from canon_tcm_hermes.utils import atomic_write_json, now_iso, run_dir


@dataclass
class AgentState:
    run_id: str
    goal: str
    input_path: str
    skill_id: str
    output_dir: str
    status: str = "planning"  # planning|running|paused_for_human|done|failed
    plan: list[str] = field(default_factory=list)
    completed_steps: list[str] = field(default_factory=list)
    step_attempts: dict[str, int] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    failure_reason: str | None = None
    human_checkpoint: str | None = None
    created_at: str = field(default_factory=now_iso)
    updated_at: str = field(default_factory=now_iso)

    @property
    def state_path(self) -> Path:
        return run_dir(self.run_id, self.output_dir) / "agent" / "state.json"

    def save(self) -> None:
        self.updated_at = now_iso()
        atomic_write_json(self.state_path, asdict(self))

    @classmethod
    def peek(cls, run_id: str, output_dir: str | Path = "outputs") -> "AgentState | None":
        """Read persisted state without mutating goal/skill_id/status."""
        path = run_dir(run_id, output_dir) / "agent" / "state.json"
        if not path.exists():
            return None
        data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in data.items() if k in known})

    @classmethod
    def load_or_create(cls, run_id: str, goal: str, input_path: str, skill_id: str, output_dir: str | Path = "outputs") -> "AgentState":
        state = cls.peek(run_id, output_dir)
        if state is not None:
            state.goal = goal
            state.input_path = input_path or state.input_path
            state.skill_id = skill_id
            if state.status in {"done", "failed"}:
                # a finished loop restarted with the same run id continues
                # from its artifacts; reopen with a FRESH retry budget —
                # lifetime attempt counters must not starve resumed runs
                state.status = "planning"
                state.failure_reason = None
                state.step_attempts = {}
            return state
        return cls(run_id=run_id, goal=goal, input_path=input_path, skill_id=skill_id, output_dir=str(output_dir))
