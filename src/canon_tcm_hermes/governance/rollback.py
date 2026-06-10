from __future__ import annotations

from pathlib import Path
from typing import Any

from canon_tcm_hermes.utils import atomic_write_json, run_dir


def rollback_version(run_id: str, reason: str, output_dir: str | Path = "outputs") -> dict[str, Any]:
    record = {"run_id": run_id, "rollback": True, "reason": reason, "status": "rolled_back_to_previous_stable"}
    atomic_write_json(run_dir(run_id, output_dir) / "audit" / "rollback_record.json", record)
    return record
