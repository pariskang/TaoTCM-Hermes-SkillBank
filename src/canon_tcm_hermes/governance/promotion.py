from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

import json

from canon_tcm_hermes.utils import atomic_write_json, atomic_write_text, now_iso, read_jsonl, run_dir


def _version_tuple(version: str) -> tuple[int, ...]:
    try:
        return tuple(int(part) for part in str(version).strip().split("."))
    except ValueError as exc:
        raise ValueError(f"version must be numeric dotted form (e.g. 1.2.0), got: {version!r}") from exc


def _assert_promotion_gates(rd: Path, expert_id: str, second_expert_id: str) -> None:
    """Executable gates for the promote decision — not process conventions.

    A promote requires: a passing validation report, a plausible expert id,
    and dual sign-off when the audit queue carries T3 (hard-stop) items.
    Identity verification and digital signatures are deployment-level
    controls documented in the model card; these gates make the recorded
    decision at least internally consistent with the run's own evidence.
    """
    validation_path = rd / "reports" / "validation_summary.json"
    if not validation_path.exists():
        raise FileNotFoundError(f"validation report not found: {validation_path}; run `canon validate` before promoting")
    if not json.loads(validation_path.read_text(encoding="utf-8")).get("passed"):
        raise ValueError("promotion blocked: pipeline validation did not pass (reports/validation_summary.json)")
    if len(str(expert_id).strip()) < 2:
        raise ValueError("promotion blocked: expert_id must be a real identifier")
    t3_items = [item for item in read_jsonl(rd / "audit" / "audit_queue.jsonl") if item.get("risk_tier") == "T3"]
    if t3_items:
        if len(str(second_expert_id).strip()) < 2:
            raise ValueError(f"promotion blocked: audit queue holds {len(t3_items)} T3 item(s); a second expert sign-off (--second-expert-id) is required")
        if str(second_expert_id).strip() == str(expert_id).strip():
            raise ValueError("promotion blocked: the second expert must be a different person")


def promote_version(
    run_id: str,
    expert_id: str,
    decision: str,
    output_dir: str | Path = "outputs",
    approved_version: str = "1.0.0",
    skill_id: str | None = None,
    reason: str = "",
    second_expert_id: str = "",
) -> dict[str, Any]:
    """Record a terminal human-audit decision and, on promote, evolve the skill.

    A skill only becomes `stable` through this path — never automatically.
    On promote the skill.yaml in the run's exported skill package gets the
    approved version, stable status, and an evolution_log entry, which is
    what makes the exported Hermes skill versionable and evolvable.
    """
    if decision not in {"promote", "revise", "reject", "disputed"}:
        raise ValueError("decision must be promote|revise|reject|disputed")
    rd = run_dir(run_id, output_dir)
    audit_package = rd / "audit" / "audit_package.json"
    if not audit_package.exists():
        raise FileNotFoundError(
            f"audit package not found: {audit_package}; a terminal audit decision must "
            "review the audit package — run `canon build-audit` (or `canon all`) first"
        )
    if decision == "promote":
        _assert_promotion_gates(rd, expert_id, second_expert_id)
    meta: dict[str, Any] | None = None
    skill_yaml: Path | None = None
    if skill_id:
        skill_yaml = rd / "skills" / skill_id / "skill.yaml"
        if not skill_yaml.exists():
            raise FileNotFoundError(f"skill package not found: {skill_yaml}; run `canon build-skill` first")
        meta = yaml.safe_load(skill_yaml.read_text(encoding="utf-8")) or {}
        if decision == "promote":
            current = str(meta.get("version", "0.1.0"))
            if _version_tuple(approved_version) <= _version_tuple(current):
                raise ValueError(f"approved_version {approved_version} must be greater than current version {current}")
    record = {
        "run_id": run_id,
        "audit_decision": decision,
        "expert_id": expert_id,
        "second_expert_id": second_expert_id,
        "reason": reason,
        "approved_version": approved_version if decision == "promote" else "",
        "stable": decision == "promote",
        "timestamp": now_iso(),
    }
    atomic_write_json(rd / "audit" / "promotion_record.json", record)

    if skill_id and meta is not None and skill_yaml is not None:
        evolution = meta.setdefault("evolution", {"evolution_log": []})
        evolution.setdefault("evolution_log", []).append({
            "decision": decision,
            "expert_id": expert_id,
            "reason": reason,
            "from_version": meta.get("version", "0.1.0"),
            "to_version": approved_version if decision == "promote" else meta.get("version", "0.1.0"),
            "timestamp": record["timestamp"],
        })
        if decision == "promote":
            meta["lineage"] = dict(meta.get("lineage") or {}, parent_version=meta.get("version"))
            meta["version"] = approved_version
            meta["status"] = "stable"
        elif decision == "reject":
            meta["status"] = "rejected"
        elif decision == "disputed":
            meta["status"] = "disputed"
        else:
            meta["status"] = "revision_requested"
        atomic_write_text(skill_yaml, yaml.safe_dump(meta, allow_unicode=True, sort_keys=False))
        record["skill_yaml"] = str(skill_yaml)
    return record
