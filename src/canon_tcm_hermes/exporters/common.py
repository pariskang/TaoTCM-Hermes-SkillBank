"""Shared helpers for the multi-platform skill exporters.

Every exporter consumes the built Hermes skill package
(outputs/runs/<run>/skills/<skill_id>/) and converts it into a target
platform layout under outputs/runs/<run>/exports/<target>/. Exporters never
mutate the source package and never touch its governance fields — an export
is a rendering of the audited package, not a new skill version.
"""
from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import Any

import yaml

from canon_tcm_hermes.utils import ensure_dir, run_dir


def load_package(run_id: str, skill_id: str, output_dir: str | Path = "outputs") -> dict[str, Any]:
    package = run_dir(run_id, output_dir) / "skills" / skill_id
    skill_yaml = package / "skill.yaml"
    skill_md = package / "SKILL.md"
    if not skill_yaml.exists() or not skill_md.exists():
        raise FileNotFoundError(f"skill package not found or incomplete: {package}; run `canon build-skill` first")
    meta = yaml.safe_load(skill_yaml.read_text(encoding="utf-8")) or {}
    frontmatter, body = split_skill_md(skill_md.read_text(encoding="utf-8"))
    return {
        "dir": package,
        "meta": meta,
        "frontmatter": frontmatter,
        "body": body,
        "references": sorted((package / "references").glob("*")) if (package / "references").is_dir() else [],
        "scripts": sorted((package / "scripts").glob("*")) if (package / "scripts").is_dir() else [],
    }


def split_skill_md(text: str) -> tuple[dict[str, Any], str]:
    match = re.match(r"^---\n(.*?)\n---\n(.*)$", text, flags=re.DOTALL)
    if not match:
        return {}, text
    frontmatter = yaml.safe_load(match.group(1)) or {}
    return (frontmatter if isinstance(frontmatter, dict) else {}), match.group(2)


def safety_policy(package: dict[str, Any]) -> dict[str, Any]:
    for ref in package["references"]:
        if ref.name == "safety_policy.yaml":
            data = yaml.safe_load(ref.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
    return {}


def slug(skill_id: str) -> str:
    return re.sub(r"[^a-z0-9-]+", "-", skill_id.lower().replace("_", "-")).strip("-")


def export_root(run_id: str, target: str, output_dir: str | Path = "outputs") -> Path:
    return ensure_dir(run_dir(run_id, output_dir) / "exports" / target)


def copy_assets(package: dict[str, Any], destination: Path) -> None:
    for group in ("references", "scripts"):
        if package[group]:
            target = ensure_dir(destination / group)
            for path in package[group]:
                shutil.copyfile(path, target / path.name)
