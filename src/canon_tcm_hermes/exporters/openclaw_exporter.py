"""Export the Hermes package as an OpenClaw-style tool/skill bundle.

OpenClaw-style agents consume a machine-readable manifest plus a prompt
file. The bundle carries `openclaw.skill.json` (id, entrypoints, resource
inventory, safety block with the effective forbidden-term lexicon) and
`prompt.md` (the behavioral contract), with references/scripts copied
alongside so script entrypoints resolve relatively.
"""
from __future__ import annotations

from pathlib import Path

from canon_tcm_hermes.exporters.common import copy_assets, export_root, load_package, safety_policy, slug
from canon_tcm_hermes.utils import atomic_write_json, atomic_write_text


def export_openclaw_skill(run_id: str, skill_id: str, output_dir: str | Path = "outputs") -> Path:
    package = load_package(run_id, skill_id, output_dir)
    policy = safety_policy(package)
    out = export_root(run_id, "openclaw", output_dir) / slug(skill_id)
    out.mkdir(parents=True, exist_ok=True)
    manifest = {
        "schema": "openclaw.skill/v1",
        "id": slug(skill_id),
        "title": skill_id.replace("_", " ").title(),
        "description": str(package["frontmatter"].get("description", "")).strip(),
        "prompt": "prompt.md",
        "entrypoints": {
            "inference": "scripts/run_inference.py",
            "evidence_retrieval": "scripts/retrieve_evidence.py",
            "citation_validation": "scripts/validate_citation.py",
            "evidence_card": "scripts/generate_evidence_card.py",
            "counterfactual_tests": "scripts/run_counterfactual_tests.py",
        },
        "resources": [f"references/{p.name}" for p in package["references"]],
        "safety": {
            "modes": ["teaching", "clinician_assist", "patient_intake"],
            "patient_intake_allowed_outputs": ["red_flag_triage", "structured_intake", "visit_summary"],
            "forbidden_patient_terms": policy.get("forbidden_patient_terms") or [],
            "forbidden_patient_keys": policy.get("forbidden_patient_keys") or [],
            "hard_stop_tier": "T3",
        },
        "source": {
            "skill_id": skill_id,
            "run_id": run_id,
            "version": package["meta"].get("version"),
            "status": package["meta"].get("status"),
        },
    }
    atomic_write_json(out / "openclaw.skill.json", manifest)
    atomic_write_text(out / "prompt.md", package["body"].strip() + "\n")
    copy_assets(package, out)
    return out
