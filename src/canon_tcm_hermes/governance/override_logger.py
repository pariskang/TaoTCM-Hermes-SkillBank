"""Physician override log: tamper-evident, append-only audit trail.

Each record carries a timestamp, the active model configuration, a hash of
the overridden payload, a reason taxonomy category, and a hash chain
(record_hash includes the previous record's hash).

Threat-model limitations (documented, not hidden): the chain detects
in-place edits and mid-chain deletions, but NOT tail truncation (removing
the newest records leaves a valid prefix), and it uses no secret key — an
attacker with write access can regenerate the whole chain. Production
deployments should anchor the latest record_hash externally (e.g. a
write-once store or signed timestamping) and serialize concurrent writers.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from canon_tcm_hermes.utils import append_jsonl, now_iso, read_jsonl, run_dir, sha1_text

REASON_CATEGORIES = {"clinical_judgment", "missing_information", "patient_preference", "safety_concern", "other"}


def log_override(
    run_id: str,
    physician_id: str,
    reason: str,
    payload: dict[str, Any],
    reason_category: str = "clinical_judgment",
    output_dir: str | Path = "outputs",
) -> dict[str, Any]:
    if reason_category not in REASON_CATEGORIES:
        raise ValueError(f"reason_category must be one of {sorted(REASON_CATEGORIES)}")
    if not physician_id or not reason:
        raise ValueError("physician_id and reason are required for an override record")
    path = run_dir(run_id, output_dir) / "audit" / "override_log.jsonl"
    previous = read_jsonl(path)
    previous_hash = previous[-1].get("record_hash", "") if previous else ""
    record = {
        "run_id": run_id,
        "physician_id": physician_id,
        "reason": reason,
        "reason_category": reason_category,
        "payload_hash": sha1_text(json.dumps(payload, ensure_ascii=False, sort_keys=True)),
        "payload": payload,
        "model": os.getenv("LITELLM_MODEL", "") or "heuristic",
        "timestamp": now_iso(),
        "previous_record_hash": previous_hash,
    }
    record["record_hash"] = sha1_text(json.dumps({k: v for k, v in record.items() if k != "record_hash"}, ensure_ascii=False, sort_keys=True))
    append_jsonl(path, [record])
    return record


def verify_override_chain(run_id: str, output_dir: str | Path = "outputs") -> bool:
    """Replay the hash chain; False means a record was edited in place or a
    mid-chain record removed. Tail truncation is NOT detectable without an
    external anchor of the latest record_hash (see module docstring)."""
    records = read_jsonl(run_dir(run_id, output_dir) / "audit" / "override_log.jsonl")
    previous_hash = ""
    for record in records:
        expected = sha1_text(json.dumps({k: v for k, v in record.items() if k != "record_hash"}, ensure_ascii=False, sort_keys=True))
        if record.get("record_hash") != expected or record.get("previous_record_hash") != previous_hash:
            return False
        previous_hash = record["record_hash"]
    return True
