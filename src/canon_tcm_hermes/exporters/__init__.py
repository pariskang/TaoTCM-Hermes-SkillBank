"""Multi-platform skill exporters.

`export_skill_targets` fans one built Hermes package out to the platform
formats configured in configs/export_targets.yaml. Exports are renderings
of the audited package: they never modify skill.yaml or its governance
state.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from canon_tcm_hermes.exporters.claude_skill_exporter import export_claude_skill
from canon_tcm_hermes.exporters.codex_skill_exporter import export_codex_skill
from canon_tcm_hermes.exporters.lobechat_exporter import export_lobechat_agent
from canon_tcm_hermes.exporters.openclaw_exporter import export_openclaw_skill
from canon_tcm_hermes.utils import project_root

EXPORTERS = {
    "claude": export_claude_skill,
    "codex": export_codex_skill,
    "openclaw": export_openclaw_skill,
    "lobechat": export_lobechat_agent,
}


def configured_targets(config_path: str | Path | None = None) -> list[str]:
    path = Path(config_path or project_root() / "configs" / "export_targets.yaml")
    if not path.exists():
        return sorted(EXPORTERS)
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    targets = [t for t in (data.get("targets") or []) if t in EXPORTERS]
    return targets or sorted(EXPORTERS)


def export_skill_targets(run_id: str, skill_id: str, targets: list[str] | None = None, output_dir: str | Path = "outputs") -> dict[str, str]:
    chosen = targets if targets else configured_targets()
    unknown = [t for t in chosen if t not in EXPORTERS]
    if unknown:
        raise ValueError(f"unknown export targets: {unknown}; supported: {sorted(EXPORTERS)}")
    return {target: str(EXPORTERS[target](run_id, skill_id, output_dir)) for target in chosen}
