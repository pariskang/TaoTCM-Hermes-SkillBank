from __future__ import annotations

from pathlib import Path
from typing import Any

from canon_tcm_hermes.utils import read_jsonl, run_dir, write_jsonl


def build_eval_cases(run_id: str, output_dir: str | Path = "outputs") -> list[dict[str, Any]]:
    rd = run_dir(run_id, output_dir)
    cases: list[dict[str, Any]] = []
    for item in read_jsonl(rd / "annotations" / "case_templates.jsonl"):
        formulas = [i.get("formula") for i in item.get("interventions", []) if isinstance(i, dict) and i.get("formula")]
        expected_patterns = [f"{formula}证" for formula in formulas]
        auto_case = item.get("auto_generated_eval_case", {})
        cases.append({
            "case_id": item.get("case_id"),
            "eval_case_id": auto_case.get("eval_case_id") or f"EVAL_{item.get('case_id')}",
            "source_id": item.get("source_id"),
            "input_features": _extract_features(item),
            "context": {"course_day": None, "prior_interventions": []},
            "expected_formulas": formulas,
            "expected_patterns": expected_patterns,
            "gold_answer": auto_case.get("gold_answer", ""),
            "gold_answer_scope": "physician_judgment_only_not_objective_truth",
            "tests": auto_case.get("tests", []),
            "evidence": item.get("evidence"),
            "bias_flags": item.get("bias_flags", []),
        })
    write_jsonl(rd / "eval" / "eval_cases.jsonl", cases)
    return cases


def _extract_features(case: dict[str, Any]) -> list[str]:
    features: list[str] = []
    for stage in case.get("presentation_timeline", []):
        if isinstance(stage, dict):
            features.extend(stage.get("features", []))
            features.extend(stage.get("pulse", []))
    if features:
        return list(dict.fromkeys(features))
    text = (case.get("evidence") or {}).get("quote", "")
    terms = ["发热", "恶寒", "恶风", "无汗", "汗出", "身痛", "头痛", "喘", "脉浮紧", "脉微弱", "烦躁"]
    return [term for term in terms if term in text]
