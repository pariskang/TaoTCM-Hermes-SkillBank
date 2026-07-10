from __future__ import annotations

from pathlib import Path
from typing import Any

from canon_tcm_hermes.inference.run_inference import run_inference
from canon_tcm_hermes.utils import atomic_write_json, run_dir

# feature-list pairs: Chinese has no whitespace, so compound flips must be
# explicit lists — "烦躁有汗".split() was silently one unmapped token
PAIRS: list[tuple[list[str], list[str]]] = [
    (["有汗"], ["无汗"]),
    (["脉浮紧"], ["脉浮缓"]),
    (["烦躁", "汗出"], ["烦躁", "无汗"]),
    (["发汗前"], ["发汗后"]),
    (["喘", "有大热"], ["喘", "无大热"]),
]

# a coherent 太阳表实 presentation that clears the core-coverage gate, so
# flips measure the engine's sensitivity rather than the gate's floor
BASE_FEATURES = ["发热", "头痛", "喘"]


def _top_pattern(result: dict[str, Any]) -> str | None:
    top = result.get("top_k", [])
    return top[0].get("pattern") if top else None


def _ranking(result: dict[str, Any]) -> list[tuple[str, str, float]]:
    """Comparable ranking signature: (pattern, support_level, score).

    Comparing whole result dicts is meaningless — they echo the input
    features, so every counterfactual pair would trivially count as
    "changed". The score IS the engine's assessment, so a flip that moves
    it counts as a real reaction even within one support level.
    """
    return [(item.get("pattern", ""), item.get("support_level", ""), float(item.get("score", 0.0))) for item in result.get("top_k", [])]


def run_counterfactual(run_id: str, output_dir: str | Path = "outputs") -> dict[str, Any]:
    cases: list[dict[str, Any]] = []
    changed_count = 0
    for left, right in PAIRS:
        left_features = BASE_FEATURES + left
        right_features = BASE_FEATURES + right
        left_result = run_inference({"mode": "clinician_assist", "features": left_features}, run_id, output_dir)
        right_result = run_inference({"mode": "clinician_assist", "features": right_features}, run_id, output_dir)
        left_top = _top_pattern(left_result)
        right_top = _top_pattern(right_result)
        changed = _ranking(left_result) != _ranking(right_result)
        if changed:
            changed_count += 1
        cases.append({"a": left, "b": right, "top_a": left_top, "top_b": right_top, "ranking_a": _ranking(left_result), "ranking_b": _ranking(right_result), "changed": changed})
    # a physiologically coherent probe: sweating + weak pulse + wind aversion
    # (no contradictory 无汗+汗出 co-presence)
    hard_payload = {"mode": "clinician_assist", "features": ["脉微弱", "汗出", "恶风"]}
    hard_result = run_inference(hard_payload, run_id, output_dir)
    blocked_patterns = {item.get("pattern") for item in hard_result.get("blocked", [])}
    top_patterns = {item.get("pattern") for item in hard_result.get("top_k", [])}
    # consistency = the contraindicated pattern is actually removed from the
    # recommendation list, not just annotated with an alert
    hard_stop_hit = bool(blocked_patterns) and not (blocked_patterns & top_patterns)
    report = {
        "counterfactual_pairs": cases,
        # pass = the engine reacts to the flipped feature (ranking or support changes)
        "counterfactual_pass_rate": changed_count / max(len(PAIRS), 1),
        "ranking_stability": 1 - (changed_count / max(len(PAIRS), 1)),
        "hard_stop_consistency": 1.0 if hard_stop_hit else 0.0,
        "hard_stop_case": {"payload": hard_payload, "blocked_patterns": sorted(blocked_patterns), "alerts_triggered": hard_stop_hit},
    }
    atomic_write_json(run_dir(run_id, output_dir) / "reports" / "counterfactual_report.json", report)
    return report
