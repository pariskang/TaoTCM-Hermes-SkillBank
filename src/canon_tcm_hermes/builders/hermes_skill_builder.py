from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import yaml

from canon_tcm_hermes.utils import atomic_write_json, atomic_write_text, ensure_dir, project_root, read_jsonl, run_dir

SKILL_MD = """---
name: {name}
description: Use for evidence-grounded teaching and clinician-assist reasoning over classical Chinese medicine formula-pattern clusters. Includes clause retrieval, formula-pattern comparison, context-state reasoning, contraindication checks, and evidence cards. Do not use for patient-facing diagnosis or prescription.
---

# {title} Skill

## Scope

This skill supports:
- teaching mode
- clinician_assist mode
- evidence retrieval
- formula-pattern comparison
- contraindication checking
- context-state reasoning

## Never use for

- direct patient diagnosis
- patient-facing syndrome suggestion
- formula recommendation to patient
- dosage recommendation
- self-medication advice

## Required workflow

1. Identify mode.
2. If patient_intake, use only red-flag triage and structured intake.
3. If teaching or clinician_assist, retrieve evidence first.
4. Validate citations.
5. Normalize features.
6. Run inference_config.
7. Generate evidence cards.
8. Run safety checker.
9. Output uncertainty and missing information.
"""

SCRIPT_TEMPLATES = {
    "retrieve_evidence.py": """#!/usr/bin/env python3
from __future__ import annotations
import argparse, json
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("query", nargs="?", default="")
parser.add_argument("--references", default=str(Path(__file__).resolve().parents[1] / "references"))
args = parser.parse_args()
path = Path(args.references) / "evidence_index.jsonl"
for line in path.read_text(encoding="utf-8").splitlines():
    item = json.loads(line)
    if not args.query or args.query in item.get("quote", "") or args.query in item.get("source_id", ""):
        print(json.dumps(item, ensure_ascii=False))
""",
    "validate_citation.py": """#!/usr/bin/env python3
from __future__ import annotations
import argparse, json
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--references", default=str(Path(__file__).resolve().parents[1] / "references"))
args = parser.parse_args()
failures = []
for line in (Path(args.references) / "evidence_index.jsonl").read_text(encoding="utf-8").splitlines():
    item = json.loads(line)
    if item.get("verification_status") != "verified":
        failures.append(item)
print(json.dumps({"failed": len(failures), "failures": failures}, ensure_ascii=False, indent=2))
raise SystemExit(1 if failures else 0)
""",
    "run_inference.py": """#!/usr/bin/env python3
from __future__ import annotations
import argparse, json

from canon_tcm_hermes.inference.run_inference import run_inference

parser = argparse.ArgumentParser()
parser.add_argument("--run-id", required=True)
parser.add_argument("--mode", default="clinician_assist")
parser.add_argument("--features", default="")
parser.add_argument("--output-dir", default="outputs")
args = parser.parse_args()
payload = {"mode": args.mode, "features": [x for x in args.features.split(",") if x]}
print(json.dumps(run_inference(payload, args.run_id, args.output_dir), ensure_ascii=False, indent=2))
""",
    "run_counterfactual_tests.py": """#!/usr/bin/env python3
from __future__ import annotations
import argparse, json
from canon_tcm_hermes.eval.run_counterfactual_tests import run_counterfactual

parser = argparse.ArgumentParser()
parser.add_argument("--run-id", required=True)
parser.add_argument("--output-dir", default="outputs")
args = parser.parse_args()
print(json.dumps(run_counterfactual(args.run_id, args.output_dir), ensure_ascii=False, indent=2))
""",
    "generate_evidence_card.py": """#!/usr/bin/env python3
from __future__ import annotations
import argparse, json
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("evidence_id")
parser.add_argument("--references", default=str(Path(__file__).resolve().parents[1] / "references"))
args = parser.parse_args()
for line in (Path(args.references) / "evidence_index.jsonl").read_text(encoding="utf-8").splitlines():
    item = json.loads(line)
    if item.get("evidence_id") == args.evidence_id:
        card = {"quote": item.get("quote"), "source_id": item.get("source_id"), "evidence_level": item.get("evidence_level"), "verification_status": item.get("verification_status")}
        print(json.dumps(card, ensure_ascii=False, indent=2))
        break
else:
    raise SystemExit(f"Evidence not found: {args.evidence_id}")
""",
}


def _read_skill_meta(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        meta = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError:
        return None
    return meta if isinstance(meta, dict) else None


def _latest_promoted_parent(skill_id: str, output_dir: str | Path, exclude_run: str) -> dict[str, Any] | None:
    """Find the most recently promoted (stable) package for skill_id across runs."""
    runs_root = Path(output_dir) / "runs"
    if not runs_root.is_dir():
        return None
    best_key = ""
    best: dict[str, Any] | None = None
    for candidate in sorted(runs_root.iterdir()):
        if not candidate.is_dir() or candidate.name == exclude_run:
            continue
        meta = _read_skill_meta(candidate / "skills" / skill_id / "skill.yaml")
        if not meta or meta.get("status") != "stable":
            continue
        log = (meta.get("evolution") or {}).get("evolution_log") or []
        promoted_at = next((entry.get("timestamp", "") for entry in reversed(log) if entry.get("decision") == "promote"), "")
        key = f"{promoted_at}|{candidate.name}"
        if best is None or key > best_key:
            best_key, best = key, {"run_id": candidate.name, "version": meta.get("version")}
    return best


def build_skill(run_id: str, skill_id: str, output_dir: str | Path = "outputs") -> Path:
    """Export the skill package for a run.

    Governance rules: a package already promoted to `stable` is never
    overwritten (rebuilding would silently replace expert-audited content);
    rebuilding an unpromoted package preserves its evolution_log and in-run
    lineage; a fresh package links its lineage to the most recently promoted
    run of the same skill.
    """
    rd = run_dir(run_id, output_dir)
    out = ensure_dir(rd / "skills" / skill_id)
    existing = _read_skill_meta(out / "skill.yaml")
    if existing and existing.get("status") in {"stable", "stable_rolled_back"}:
        raise RuntimeError(
            f"refusing to overwrite expert-audited skill package {out / 'skill.yaml'} "
            f"(status={existing.get('status')}, version={existing.get('version')}); "
            "rebuild under a new --run-id, or remove the package directory to force a rebuild"
        )
    parent = _latest_promoted_parent(skill_id, output_dir, exclude_run=run_id)
    refs = ensure_dir(out / "references")
    scripts = ensure_dir(out / "scripts")
    name = skill_id.replace("_", "-")
    atomic_write_text(out / "SKILL.md", SKILL_MD.format(name=name, title=skill_id.replace("_", " ").title()))
    skill_meta = {
        "skill_id": skill_id,
        "run_id": run_id,
        "protocol_version": "v5.0",
        "version": (existing or {}).get("version") or "0.1.0",
        "status": "auto_generated_requires_audit",
        "lineage": {
            "built_from_run": run_id,
            "parent_version": ((existing or {}).get("lineage") or {}).get("parent_version"),
            "parent_run": parent["run_id"] if parent else None,
            "parent_stable_version": parent["version"] if parent else None,
        },
        "evolution": {
            "loop": [
                "add or revise rows in data.xlsx",
                "canon all --input data.xlsx --run-id <new-run>",
                "canon diff --run-id <new-run> --baseline <last-promoted-run>",
                "review audit_package.json (delta_since_baseline scopes the review)",
                "canon promote --run-id <new-run> --skill-id " + skill_id + " --decision promote --expert-id <id>",
            ],
            "evolution_log": ((existing or {}).get("evolution") or {}).get("evolution_log") or [],
        },
    }
    atomic_write_text(out / "skill.yaml", yaml.safe_dump(skill_meta, allow_unicode=True, sort_keys=False))
    copies = [("annotations/clause_templates.jsonl", "clause_templates.jsonl"), ("patterns/pattern_aggregations.jsonl", "pattern_aggregations.jsonl"), ("inference/context_state_rules.jsonl", "context_state_rules.jsonl"), ("evidence/evidence_index.jsonl", "evidence_index.jsonl"), ("inference/inference_config.yaml", "inference_config.yaml"), ("eval/eval_cases.jsonl", "eval_cases.jsonl")]
    all_ann = []
    for p in (rd / "annotations").glob("*.jsonl"):
        all_ann += read_jsonl(p)
    atomic_write_text(refs / "annotated_fragments.jsonl", "".join(json.dumps(x, ensure_ascii=False) + "\n" for x in all_ann))
    for src, dst in copies:
        sp = rd / src
        if sp.exists():
            shutil.copyfile(sp, refs / dst)
    from canon_tcm_hermes.inference.run_inference import patient_forbidden_keys, patient_forbidden_terms

    safety_policy = {
        "patient_intake": {
            "show_syndrome": False,
            "show_formula": False,
            "show_dosage": False,
            "show_treatment_principle": False,
        },
        # effective lexicon at build time: built-in floor + configs/patient_safety_lexicon.yaml
        "forbidden_patient_terms": patient_forbidden_terms(),
        "forbidden_patient_keys": patient_forbidden_keys(),
    }
    atomic_write_text(refs / "safety_policy.yaml", yaml.safe_dump(safety_policy, allow_unicode=True, sort_keys=False))
    guideline = project_root() / "docs" / "genre_guideline_v1.0.md"
    if guideline.exists():
        shutil.copyfile(guideline, refs / "genre_guideline.md")
    for script_name, script in SCRIPT_TEMPLATES.items():
        script_path = scripts / script_name
        atomic_write_text(script_path, script)
        script_path.chmod(0o755)
    atomic_write_json(out / "manifest.json", {"skill_id": skill_id, "run_id": run_id, "references": sorted(p.name for p in refs.glob("*")), "scripts": sorted(p.name for p in scripts.glob("*"))})
    return out
