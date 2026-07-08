"""Episodic agent memory: append-only event log per run.

Every plan/act/observe/reflect event lands in agent/memory.jsonl with a
timestamp, giving the loop persistent, inspectable memory across restarts
(the state file holds the summary; this holds the history).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from canon_tcm_hermes.utils import append_jsonl, now_iso, read_jsonl, run_dir


class EpisodicMemory:
    def __init__(self, run_id: str, output_dir: str | Path = "outputs") -> None:
        self.path = run_dir(run_id, output_dir) / "agent" / "memory.jsonl"

    def record(self, kind: str, payload: dict[str, Any]) -> None:
        append_jsonl(self.path, [{"at": now_iso(), "kind": kind, **payload}])

    def events(self, kind: str | None = None) -> list[dict[str, Any]]:
        events = read_jsonl(self.path)
        return [e for e in events if kind is None or e.get("kind") == kind]
