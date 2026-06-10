from __future__ import annotations

from pathlib import Path
from typing import Any

from canon_tcm_hermes.governance.risk_tiering import assign_risk_tier
from canon_tcm_hermes.utils import read_jsonl, run_dir, write_jsonl


def build_audit_queue(run_id: str, output_dir: str | Path = "outputs") -> list[dict[str, Any]]:
    rd = run_dir(run_id, output_dir)
    items: list[dict[str, Any]] = []
    for pattern in read_jsonl(rd / "patterns" / "pattern_aggregations.jsonl"):
        if pattern.get("aggregation_decisions") or pattern.get("contraindications"):
            items.append({"item_id": pattern.get("pattern_id"), "item_type": "pattern", "risk_tier": assign_risk_tier(pattern), "status": "needs_review", "payload": pattern})
    write_jsonl(rd / "audit" / "audit_queue.jsonl", items)
    return items
