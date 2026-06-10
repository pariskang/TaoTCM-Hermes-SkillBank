from __future__ import annotations

from pathlib import Path
from typing import Any

from canon_tcm_hermes.inference.run_inference import run_inference
from canon_tcm_hermes.utils import atomic_write_json, run_dir

PAIRS = [
    ("有汗", "无汗"),
    ("脉浮紧", "脉浮缓"),
    ("烦躁有汗", "烦躁无汗"),
    ("发汗前", "发汗后"),
    ("喘有大热", "喘无大热"),
]

BASE_FEATURES = ["发热", "恶寒", "身痛"]


def _top_pattern(result: dict[str, Any]) -> str | None:
    top = result.get("top_k", [])
    return top[0].get("pattern") if top else None


def run_counterfactual(run_id: str, output_dir: str | Path = "outputs") -> dict[str, Any]:
    cases: list[dict[str, Any]] = []
    changed_or_blocked = 0
    hard_stop_consistent = 0
    hard_stop_checks = 0
    for left, right in PAIRS:
        left_features = BASE_FEATURES + left.split()
        right_features = BASE_FEATURES + right.split()
        left_result = run_inference({"mode": "clinician_assist", "features": left_features}, run_id, output_dir)
        right_result = run_inference({"mode": "clinician_assist", "features": right_features}, run_id, output_dir)
        left_top = _top_pattern(left_result)
        right_top = _top_pattern(right_result)
        changed = left_top != right_top or left_result != right_result
        if changed:
            changed_or_blocked += 1
        cases.append({"a": left, "b": right, "top_a": left_top, "top_b": right_top, "changed": changed})
    hard_payload = {"mode": "clinician_assist", "features": ["脉微弱", "汗出", "恶风", "无汗"]}
    hard_result = run_inference(hard_payload, run_id, output_dir)
    hard_stop_checks += 1
    if any(item.get("safety_alerts") for item in hard_result.get("top_k", [])):
        hard_stop_consistent += 1
    report = {
        "counterfactual_pairs": cases,
        "counterfactual_pass_rate": changed_or_blocked / max(len(PAIRS), 1),
        "ranking_stability": 1 - (changed_or_blocked / max(len(PAIRS), 1)),
        "hard_stop_consistency": hard_stop_consistent / hard_stop_checks,
        "hard_stop_case": hard_result,
    }
    atomic_write_json(run_dir(run_id, output_dir) / "reports" / "counterfactual_report.json", report)
    return report
