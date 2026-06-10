from __future__ import annotations

from pathlib import Path
from typing import Any

from canon_tcm_hermes.utils import read_jsonl, run_dir, write_jsonl


def build_eval_cases(run_id: str, output_dir: str | Path = "outputs") -> list[dict[str, Any]]:
    rd = run_dir(run_id, output_dir)
    cases: list[dict[str, Any]] = []
    for item in read_jsonl(rd / "annotations" / "case_templates.jsonl"):
        interventions = item.get("interventions", [])
        expected_patterns = [f"{formula}证" for formula in interventions]
        cases.append({
            "case_id": item.get("case_id"),
            "source_id": item.get("source_id"),
            "input_features": _extract_features(item),
            "context": {"course_day": None, "prior_interventions": []},
            "expected_formulas": interventions,
            "expected_patterns": expected_patterns,
            "gold_answer_scope": "physician_judgment_only_not_objective_truth",
            "evidence": item.get("evidence"),
            "bias_flags": item.get("bias_flags", []),
        })
    write_jsonl(rd / "eval" / "eval_cases.jsonl", cases)
    return cases


def _extract_features(case: dict[str, Any]) -> list[str]:
    text = " ".join(case.get("presentation_timeline", []))
    terms = ["发热", "恶寒", "恶风", "无汗", "汗出", "身痛", "头痛", "喘", "脉浮紧", "脉微弱", "烦躁"]
    return [term for term in terms if term in text]
