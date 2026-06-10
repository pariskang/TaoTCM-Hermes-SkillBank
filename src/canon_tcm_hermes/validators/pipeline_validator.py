from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jsonschema import validate

from canon_tcm_hermes.annotators.base import ANNOTATION_FILES, SCHEMA_FILES
from canon_tcm_hermes.utils import atomic_write_json, read_jsonl, run_dir
from canon_tcm_hermes.validators.citation_validator import build_and_validate_evidence
from canon_tcm_hermes.validators.cross_genre_validator import validate_cross_genre

REQUIRED_RUN_FILES = [
    "input_rows.jsonl",
    "genre_routes.jsonl",
    "evidence/evidence_index.jsonl",
    "reports/citation_validation_report.json",
    "reports/cross_genre_validation_report.json",
    "inference/inference_config.yaml",
    "audit/audit_package.json",
    "audit/audit_queue.jsonl",
]


def validate_annotations(run_id: str, output_dir: str | Path = "outputs") -> dict[str, Any]:
    """Validate persisted annotation JSONL files against their genre schemas."""
    rd = run_dir(run_id, output_dir)
    failures: list[dict[str, Any]] = []
    counts: dict[str, int] = {}
    for genre, filename in ANNOTATION_FILES.items():
        schema = json.loads((Path("schemas") / SCHEMA_FILES[genre]).read_text(encoding="utf-8"))
        rows = read_jsonl(rd / "annotations" / filename)
        counts[genre] = len(rows)
        for index, row in enumerate(rows, start=1):
            try:
                validate(row, schema)
            except Exception as exc:
                failures.append({"genre": genre, "file": filename, "line": index, "error": str(exc)})
    report = {"annotation_counts": counts, "failed": len(failures), "failures": failures, "passed": not failures}
    atomic_write_json(rd / "reports" / "schema_validation_report.json", report)
    return report


def validate_required_outputs(run_id: str, output_dir: str | Path = "outputs", skill_id: str = "shanghan_six_formula_cluster") -> dict[str, Any]:
    rd = run_dir(run_id, output_dir)
    required = list(REQUIRED_RUN_FILES)
    required.extend(f"annotations/{filename}" for filename in ANNOTATION_FILES.values())
    required.extend([
        "graphs/knowledge_graph.json",
        "graphs/cross_genre_links.jsonl",
        "patterns/pattern_aggregations.jsonl",
        "inference/context_state_rules.jsonl",
        "reports/genre_report.json",
        "reports/counterfactual_report.json",
        "reports/ablation_report.json",
        "eval/eval_cases.jsonl",
        f"skills/{skill_id}/SKILL.md",
        f"skills/{skill_id}/manifest.json",
        f"skills/{skill_id}/references/evidence_index.jsonl",
        f"skills/{skill_id}/references/eval_cases.jsonl",
    ])
    missing = [rel for rel in required if not (rd / rel).exists()]
    report = {"required_count": len(required), "missing_count": len(missing), "missing": missing, "passed": not missing}
    atomic_write_json(rd / "reports" / "required_outputs_report.json", report)
    return report


def run_validation(run_id: str, output_dir: str | Path = "outputs", skill_id: str = "shanghan_six_formula_cluster") -> dict[str, Any]:
    schema_report = validate_annotations(run_id, output_dir)
    citation_report = build_and_validate_evidence(run_id, output_dir)
    cross_report = validate_cross_genre(run_id, output_dir)
    outputs_report = validate_required_outputs(run_id, output_dir, skill_id)
    passed = schema_report["passed"] and citation_report["failed"] == 0 and cross_report["passed"] and outputs_report["passed"]
    report = {
        "run_id": run_id,
        "passed": passed,
        "schema_validation": schema_report,
        "citation_validation": citation_report,
        "cross_genre_validation": cross_report,
        "required_outputs": outputs_report,
    }
    atomic_write_json(run_dir(run_id, output_dir) / "reports" / "validation_summary.json", report)
    return report
