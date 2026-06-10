from __future__ import annotations

from pathlib import Path
from typing import Any

from canon_tcm_hermes.utils import atomic_write_json, run_dir


def promote_version(run_id: str, expert_id: str, decision: str, output_dir: str | Path = "outputs", approved_version: str = "1.0.0") -> dict[str, Any]:
    if decision not in {"promote", "revise", "reject", "disputed"}:
        raise ValueError("decision must be promote|revise|reject|disputed")
    record = {"run_id": run_id, "audit_decision": decision, "expert_id": expert_id, "approved_version": approved_version if decision == "promote" else "", "stable": decision == "promote"}
    atomic_write_json(run_dir(run_id, output_dir) / "audit" / "promotion_record.json", record)
    return record
