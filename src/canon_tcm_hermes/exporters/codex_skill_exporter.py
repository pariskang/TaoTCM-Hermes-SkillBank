"""Export the Hermes package as a Codex-style agent skill.

Target layout mirrors this repository's own .agents/skills convention:
<skill>/SKILL.md plus references/ and scripts/, with an AGENTS.md entry
file that tells a Codex agent when and how to engage the skill.
"""
from __future__ import annotations

from pathlib import Path

from canon_tcm_hermes.exporters.common import copy_assets, export_root, load_package, slug
from canon_tcm_hermes.utils import atomic_write_json, atomic_write_text

AGENTS_MD = """# {title}

This directory is an auto-exported CanonTCM-Hermes skill package.

- Read `SKILL.md` first: it defines the allowed modes (teaching,
  clinician_assist, guarded patient_intake) and the required workflow.
- Ground every answer in `references/evidence_index.jsonl`; validate with
  `scripts/validate_citation.py` before citing.
- Run inference through `scripts/run_inference.py` — never rank
  formula-patterns yourself; hard-stop contraindications are enforced there.
- Patient-facing output is restricted to red-flag triage, structured
  questions, and visit summaries. The forbidden vocabulary is listed in
  `references/safety_policy.yaml`.

Source skill: {skill_id} (version {version}, status {status}).
"""


def export_codex_skill(run_id: str, skill_id: str, output_dir: str | Path = "outputs") -> Path:
    package = load_package(run_id, skill_id, output_dir)
    out = export_root(run_id, "codex", output_dir) / slug(skill_id)
    out.mkdir(parents=True, exist_ok=True)
    atomic_write_text(out / "SKILL.md", (package["dir"] / "SKILL.md").read_text(encoding="utf-8"))
    atomic_write_text(out / "AGENTS.md", AGENTS_MD.format(
        title=skill_id.replace("_", " ").title(),
        skill_id=skill_id,
        version=package["meta"].get("version"),
        status=package["meta"].get("status"),
    ))
    copy_assets(package, out)
    atomic_write_json(out / "export_manifest.json", {
        "target": "codex",
        "skill_id": skill_id,
        "run_id": run_id,
        "source_version": package["meta"].get("version"),
        "source_status": package["meta"].get("status"),
    })
    return out
