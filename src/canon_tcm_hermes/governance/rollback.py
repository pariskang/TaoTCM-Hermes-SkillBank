"""Rollback: actually restore the previous stable skill package.

The current run's package must carry cross-run lineage (parent_run /
parent_stable_version, written by build_skill). Rollback copies the parent
stable package's files over the current package, appends a rollback entry
to the evolution log, and records an audit artifact — it never fabricates
a stable state that did not exist.
"""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import yaml

from canon_tcm_hermes.utils import atomic_write_json, atomic_write_text, now_iso, run_dir


def rollback_version(run_id: str, expert_id: str, reason: str = "", skill_id: str = "shanghan_six_formula_cluster", output_dir: str | Path = "outputs") -> dict[str, Any]:
    rd = run_dir(run_id, output_dir)
    package = rd / "skills" / skill_id
    skill_yaml = package / "skill.yaml"
    if not skill_yaml.exists():
        raise FileNotFoundError(f"skill package not found: {skill_yaml}")
    meta = yaml.safe_load(skill_yaml.read_text(encoding="utf-8")) or {}
    lineage = meta.get("lineage") or {}
    parent_run = lineage.get("parent_run")
    parent_version = lineage.get("parent_stable_version")
    if not parent_run or not parent_version:
        raise ValueError("no promoted parent run in lineage — nothing stable to roll back to")
    parent_package = Path(output_dir) / "runs" / parent_run / "skills" / skill_id
    parent_meta = yaml.safe_load((parent_package / "skill.yaml").read_text(encoding="utf-8")) if (parent_package / "skill.yaml").exists() else None
    if not parent_meta or parent_meta.get("status") != "stable":
        raise ValueError(f"parent package is not stable: {parent_package}")

    # snapshot the defective package for forensics, then restore the parent
    # stable package EXACTLY — leftover current-only files would otherwise
    # produce a mixed package masquerading as the restored stable state
    backup = package.parent / f"{skill_id}.pre_rollback"
    if backup.exists():
        shutil.rmtree(backup)
    shutil.move(str(package), str(backup))
    shutil.copytree(parent_package, package)

    restored = yaml.safe_load((package / "skill.yaml").read_text(encoding="utf-8")) or {}
    evolution = restored.setdefault("evolution", {"evolution_log": []})
    evolution.setdefault("evolution_log", []).append({
        "decision": "rollback",
        "expert_id": expert_id,
        "reason": reason,
        "from_version": meta.get("version"),
        "to_version": parent_meta.get("version"),
        "restored_from_run": parent_run,
        "timestamp": now_iso(),
    })
    restored["status"] = "stable_rolled_back"
    atomic_write_text(package / "skill.yaml", yaml.safe_dump(restored, allow_unicode=True, sort_keys=False))

    record = {
        "run_id": run_id,
        "skill_id": skill_id,
        "rollback": True,
        "expert_id": expert_id,
        "reason": reason,
        "rolled_back_from_version": meta.get("version"),
        "restored_run": parent_run,
        "restored_version": parent_meta.get("version"),
        "defective_package_backup": str(backup),
        "timestamp": now_iso(),
    }
    atomic_write_json(rd / "audit" / "rollback_record.json", record)
    return record
