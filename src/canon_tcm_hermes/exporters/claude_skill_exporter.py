"""Export the Hermes package as a Claude (Agent) Skill directory.

Target layout follows the Claude skill contract: a directory named after
the skill containing SKILL.md whose YAML frontmatter carries `name`
(lowercase hyphenated, <=64 chars) and `description` (<=1024 chars), plus
any supporting files. References and scripts are copied verbatim.
"""
from __future__ import annotations

from pathlib import Path

import yaml

from canon_tcm_hermes.exporters.common import copy_assets, export_root, load_package, slug
from canon_tcm_hermes.utils import atomic_write_json, atomic_write_text


def export_claude_skill(run_id: str, skill_id: str, output_dir: str | Path = "outputs") -> Path:
    package = load_package(run_id, skill_id, output_dir)
    name = slug(skill_id)[:64]
    description = str(package["frontmatter"].get("description", "")).strip()[:1024]
    out = export_root(run_id, "claude", output_dir) / name
    out.mkdir(parents=True, exist_ok=True)
    frontmatter = {"name": name, "description": description}
    atomic_write_text(out / "SKILL.md", "---\n" + yaml.safe_dump(frontmatter, allow_unicode=True, sort_keys=False) + "---\n" + package["body"])
    copy_assets(package, out)
    atomic_write_json(out / "export_manifest.json", {
        "target": "claude",
        "skill_id": skill_id,
        "run_id": run_id,
        "source_version": package["meta"].get("version"),
        "source_status": package["meta"].get("status"),
    })
    return out
