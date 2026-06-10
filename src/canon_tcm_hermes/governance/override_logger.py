from __future__ import annotations

from pathlib import Path
from typing import Any

from canon_tcm_hermes.utils import append_jsonl, run_dir


def log_override(run_id: str, physician_id: str, reason: str, payload: dict[str, Any], output_dir: str | Path = "outputs") -> dict[str, Any]:
    record = {"run_id": run_id, "physician_id": physician_id, "reason": reason, "payload": payload}
    append_jsonl(run_dir(run_id, output_dir) / "audit" / "override_log.jsonl", [record])
    return record
