from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from canon_tcm_hermes.utils import atomic_write_json, atomic_write_text, now_iso, run_dir


def _version_tuple(version: str) -> tuple[int, ...]:
    try:
        return tuple(int(part) for part in str(version).strip().split("."))
    except ValueError as exc:
        raise ValueError(f"version must be numeric dotted form (e.g. 1.2.0), got: {version!r}") from exc


def promote_version(
    run_id: str,
    expert_id: str,
    decision: str,
    output_dir: str | Path = "outputs",
    approved_version: str = "1.0.0",
    skill_id: str | None = None,
    reason: str = "",
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
