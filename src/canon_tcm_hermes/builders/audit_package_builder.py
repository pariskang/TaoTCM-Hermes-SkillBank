from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from canon_tcm_hermes.governance.audit_queue import build_audit_queue
from canon_tcm_hermes.utils import atomic_write_json, read_jsonl, run_dir


def build_audit_package(run_id: str, skill_id: str = "shanghan_six_formula_cluster", output_dir: str | Path = "outputs") -> dict[str, Any]:
    rd = run_dir(run_id, output_dir)
    routes = read_jsonl(rd / "genre_routes.jsonl")
    patterns = read_jsonl(rd / "patterns" / "pattern_aggregations.jsonl")
    cases = read_jsonl(rd / "annotations" / "case_templates.jsonl")
    citation = _read_json(rd / "reports" / "citation_validation_report.json")
    counter = _read_json(rd / "reports" / "counterfactual_report.json")
    cross = _read_json(rd / "reports" / "cross_genre_validation_report.json")
    ablation = _read_json(rd / "reports" / "ablation_report.json")
    queue = build_audit_queue(run_id, output_dir)
    counts = Counter(segment["genre"] for route in routes for segment in route.get("genre_segmentation", []))
    package = {
        "run_id": run_id,
        "skill_id": skill_id,
        "protocol_version": "v5.0",
        "build_summary": {
            "source_rows": len(read_jsonl(rd / "input_rows.jsonl")),
            "segments": sum(len(route.get("genre_segmentation", [])) for route in routes),
            "genre_counts": dict(counts),
            "pattern_count": len(patterns),
            "eval_case_count": len(cases),
            "citation_verified_rate": citation.get("verified_rate", 0),
            "counterfactual_pass_rate": counter.get("counterfactual_pass_rate", 0),
            "ablation_status": ablation.get("status", "unknown"),
        },
        "items_requiring_review": {
            "audit_queue_count": len(queue),
            "genre_misclassification_suspects": [route for route in routes if route.get("genre_uncertain")],
            "citation_failures": citation.get("failures", []),
            "cross_genre_inconsistencies": cross.get("inconsistencies", []),
            "cross_genre_warnings": cross.get("warnings", []),
            "unstable_rankings": [case for case in counter.get("counterfactual_pairs", []) if case.get("changed")],
            "T3_safety_rules": [pattern for pattern in patterns if pattern.get("contraindications")],
            "school_divergence_cases": [],
            "aggregation_decisions": [decision for pattern in patterns for decision in pattern.get("aggregation_decisions", []) if decision.get("needs_audit")],
        },
        "audit_queue_path": "audit/audit_queue.jsonl",
        "recommended_decision": "promote_to_terminal_human_audit",
    }
    atomic_write_json(rd / "audit" / "audit_package.json", package)
    return package


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))
