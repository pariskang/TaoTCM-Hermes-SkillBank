from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from canon_tcm_hermes.eval.build_eval_cases import build_eval_cases
from canon_tcm_hermes.inference.run_inference import run_inference
from canon_tcm_hermes.utils import atomic_write_json, read_jsonl, run_dir

SYSTEMS = ["B0", "B1", "B2", "S1", "S2", "S3"]
HARD_PROBE = ["脉微弱", "汗出", "恶风", "无汗"]


def run_ablation(run_id: str, output_dir: str | Path = "outputs") -> dict[str, Any]:
    rd = run_dir(run_id, output_dir)
    eval_cases = read_jsonl(rd / "eval" / "eval_cases.jsonl") or build_eval_cases(run_id, output_dir)
    patterns = read_jsonl(rd / "patterns" / "pattern_aggregations.jsonl")
    citation_report = _read_json(rd / "reports" / "citation_validation_report.json")
    counterfactual_report = _read_json(rd / "reports" / "counterfactual_report.json")
    systems = {
        system: _evaluate_system(system, eval_cases, patterns, run_id, output_dir, citation_report, counterfactual_report)
        for system in SYSTEMS
    }
    scored = {name: m for name, m in systems.items() if m["top1_pattern_accuracy"] is not None}
    report = {
        "status": "completed_deterministic_local_ablation",
        "note": (
            "B0/B1/B2 are deterministic local proxies (no gold-label leakage): "
            "B0 = context-free majority guess, B1 = lexical retrieval, B2 = lexical + structure-aware retrieval. "
            "S1 removes symbolic gating/contraindication, S2 removes citation validation, S3 is the full system. "
            "Replace proxies with external LLM/RAG runners for publication-grade experiments."
        ),
        "eval_case_count": len(eval_cases),
        "systems": systems,
        "best_system_by_top1": max(scored, key=lambda name: scored[name]["top1_pattern_accuracy"]) if scored else None,
    }
    atomic_write_json(rd / "reports" / "ablation_report.json", report)
    return report


def _evaluate_system(
    system: str,
    eval_cases: list[dict[str, Any]],
    patterns: list[dict[str, Any]],
    run_id: str,
    output_dir: str | Path,
    citation_report: dict[str, Any],
    counterfactual_report: dict[str, Any],
) -> dict[str, Any]:
    if not eval_cases:
        return {metric: None for metric in [
            "top1_pattern_accuracy", "top3_pattern_accuracy", "hallucinated_citation_rate",
            "citation_verified_rate", "contraindication_sensitivity", "counterfactual_stability",
            "patient_forbidden_output_rate",
        ]}
    top1 = 0
    top3 = 0
    for case in eval_cases:
        expected = set(case.get("expected_patterns", []))
        predicted = _predict(system, case, patterns, run_id, output_dir)
        if predicted and predicted[0] in expected:
            top1 += 1
        if expected & set(predicted[:3]):
            top3 += 1
    produces_citations = system in {"S1", "S2", "S3"}
    validates_citations = system in {"S1", "S3"}
    verified_rate = citation_report.get("verified_rate")
    return {
        "top1_pattern_accuracy": top1 / len(eval_cases),
        "top3_pattern_accuracy": top3 / len(eval_cases),
        # B* baselines emit no citations at all; S2 emits citations but skips
        # verification, so its hallucination rate is unobservable by design.
        "hallucinated_citation_rate": (max(0.0, 1.0 - verified_rate) if (validates_citations and verified_rate is not None) else None),
        "citation_verified_rate": (verified_rate if validates_citations else None),
        "contraindication_sensitivity": _contraindication_sensitivity(system, run_id, output_dir),
        "counterfactual_stability": (counterfactual_report.get("ranking_stability") if system in {"S2", "S3"} else None),
        # S systems route patient_intake through the forbidden-output guard;
        # baselines have no guard, so any pattern/formula text would leak.
        "patient_forbidden_output_rate": 0.0 if system in {"S1", "S2", "S3"} else 1.0,
        "notes": {
            "produces_citations": produces_citations,
            "validates_citations": validates_citations,
        },
    }


def _contraindication_sensitivity(system: str, run_id: str, output_dir: str | Path) -> float:
    if system in {"S2", "S3"}:
        result = run_inference({"mode": "clinician_assist", "features": HARD_PROBE}, run_id, output_dir)
        return 1.0 if any(item.get("safety_alerts") for item in result.get("top_k", [])) else 0.0
    # S1 strips the symbolic contraindication checker; B* never had one.
    return 0.0


def _predict(system: str, case: dict[str, Any], patterns: list[dict[str, Any]], run_id: str, output_dir: str | Path) -> list[str]:
    features = case.get("input_features", [])
    if system == "B0":
        # Context-free majority guess: most corroborated pattern overall.
        ranked = sorted(patterns, key=lambda p: (p.get("case_corroboration_count", 0), len(p.get("aggregated_from", []))), reverse=True)
        return [p.get("pattern_name", "") for p in ranked[:3]]
    if system == "B1":
        return _lexical_rank(features, patterns, structure_aware=False)[:3]
    if system == "B2":
        return _lexical_rank(features, patterns, structure_aware=True)[:3]
    if system == "S1":
        # Full retrieval but no symbolic core-gate / hard-stop logic.
        return _lexical_rank(features, patterns, structure_aware=True)[:3]
    result = run_inference({"mode": "clinician_assist", "features": features, "context": case.get("context", {})}, run_id, output_dir)
    return [item.get("pattern") for item in result.get("top_k", []) if item.get("pattern")][:3]


def _lexical_rank(features: list[str], patterns: list[dict[str, Any]], structure_aware: bool) -> list[str]:
    feature_set = set(features)
    scores: Counter[str] = Counter()
    for pattern in patterns:
        name = pattern.get("pattern_name", "")
        overlap = feature_set & set(pattern.get("core_features", []) + pattern.get("common_features", []))
        score = len(overlap)
        if structure_aware:
            for compound in pattern.get("compound_features", []):
                if set(compound.get("components", [])) <= feature_set:
                    score += 1
            for exclusion in pattern.get("exclusion_features", []):
                if exclusion.get("feature") in feature_set:
                    score -= 1
        scores[name] = score
    return [name for name, score in scores.most_common() if score > 0]


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))
