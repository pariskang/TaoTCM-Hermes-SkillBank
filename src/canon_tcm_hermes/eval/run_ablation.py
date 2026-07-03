from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from canon_tcm_hermes.eval.baseline_adapters import llm_baselines_enabled, predict_baseline
from canon_tcm_hermes.eval.build_eval_cases import build_eval_cases
from canon_tcm_hermes.inference.run_inference import patient_forbidden_terms, run_inference
from canon_tcm_hermes.llm.litellm_client import LLMError
from canon_tcm_hermes.utils import atomic_write_json, read_jsonl, run_dir

SYSTEMS = ["B0", "B1", "B2", "S1", "S2", "S3"]
BASELINE_SYSTEMS = {"B0", "B1", "B2"}
HARD_PROBE = ["脉微弱", "汗出", "恶风", "无汗"]

PROXY_NOTE = (
    "B0/B1/B2 are deterministic local proxies (no gold-label leakage): "
    "B0 = context-free majority guess, B1 = lexical retrieval, B2 = lexical + structure-aware retrieval. "
    "S1 removes symbolic gating/contraindication, S2 removes citation validation, S3 is the full system. "
    "Enable real LLM/RAG baselines with --llm-baselines (or TAOTCM_LLM_BASELINES=1) and a configured LITELLM_MODEL."
)
LLM_NOTE = (
    "B0/B1/B2 ran as real LLM baselines over a shared closed candidate set: "
    "B0 = bare LLM (features only), B1 = naive RAG (lexically retrieved quotes), B2 = graph RAG (pattern subgraphs + linked evidence). "
    "B1/B2 must return the evidence ids they relied on, so their citation rates are measured, not imputed. "
    "Cases where the LLM call exhausted its retry budget fell back to the deterministic proxy (see llm_fallback_cases)."
)


def run_ablation(run_id: str, output_dir: str | Path = "outputs", llm_baselines: bool | None = None) -> dict[str, Any]:
    rd = run_dir(run_id, output_dir)
    eval_cases = read_jsonl(rd / "eval" / "eval_cases.jsonl") or build_eval_cases(run_id, output_dir)
    patterns = read_jsonl(rd / "patterns" / "pattern_aggregations.jsonl")
    evidence = read_jsonl(rd / "evidence" / "evidence_index.jsonl")
    citation_report = _read_json(rd / "reports" / "citation_validation_report.json")
    counterfactual_report = _read_json(rd / "reports" / "counterfactual_report.json")
    use_llm_baselines = llm_baselines_enabled(llm_baselines)
    systems = {
        system: _evaluate_system(system, eval_cases, patterns, evidence, run_id, output_dir, citation_report, counterfactual_report, use_llm_baselines)
        for system in SYSTEMS
    }
    scored = {name: m for name, m in systems.items() if m["top1_pattern_accuracy"] is not None}
    report = {
        "status": "completed_llm_baseline_ablation" if use_llm_baselines else "completed_deterministic_local_ablation",
        "baseline_mode": "llm_adapter" if use_llm_baselines else "deterministic_proxy",
        "note": LLM_NOTE if use_llm_baselines else PROXY_NOTE,
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
    evidence: list[dict[str, Any]],
    run_id: str,
    output_dir: str | Path,
    citation_report: dict[str, Any],
    counterfactual_report: dict[str, Any],
    use_llm_baselines: bool,
) -> dict[str, Any]:
    if not eval_cases:
        return {metric: None for metric in [
            "top1_pattern_accuracy", "top3_pattern_accuracy", "hallucinated_citation_rate",
            "citation_verified_rate", "contraindication_sensitivity", "counterfactual_stability",
            "patient_forbidden_output_rate",
        ]}
    llm_mode = use_llm_baselines and system in BASELINE_SYSTEMS
    evidence_by_id = {str(item.get("evidence_id")): item for item in evidence}
    top1 = 0
    top3 = 0
    fallbacks = 0
    cited_total = cited_known = cited_verified = 0
    for case in eval_cases:
        expected = set(case.get("expected_patterns", []))
        citations: list[str] | None = None
        if llm_mode:
            try:
                result = predict_baseline(system, case, patterns, evidence)
                predicted = result["patterns"]
                citations = result["citations"]
            except LLMError:
                fallbacks += 1
                predicted = _predict(system, case, patterns, run_id, output_dir)
        else:
            predicted = _predict(system, case, patterns, run_id, output_dir)
        if predicted and predicted[0] in expected:
            top1 += 1
        if expected & set(predicted[:3]):
            top3 += 1
        for cited in citations or []:
            cited_total += 1
            item = evidence_by_id.get(cited)
            if item is not None:
                cited_known += 1
                if item.get("verification_status") == "verified":
                    cited_verified += 1
    produces_citations = system in {"S1", "S2", "S3"} or (llm_mode and system in {"B1", "B2"})
    validates_citations = system in {"S1", "S3"}
    verified_rate = citation_report.get("verified_rate")
    if validates_citations and verified_rate is not None:
        hallucinated = max(0.0, 1.0 - verified_rate)
        cited_rate: float | None = verified_rate
    elif cited_total:
        # LLM baseline citations measured against the run's evidence index
        hallucinated = (cited_total - cited_known) / cited_total
        cited_rate = cited_verified / cited_total
    else:
        # B* proxies emit no citations at all; S2 emits citations but skips
        # verification, so its hallucination rate is unobservable by design.
        hallucinated = None
        cited_rate = None
    notes: dict[str, Any] = {
        "mode": ("llm_adapter" if llm_mode else ("deterministic_proxy" if system in BASELINE_SYSTEMS else "local_system")),
        "produces_citations": produces_citations,
        "validates_citations": validates_citations,
    }
    if llm_mode:
        notes["llm_fallback_cases"] = fallbacks
    return {
        "top1_pattern_accuracy": top1 / len(eval_cases),
        "top3_pattern_accuracy": top3 / len(eval_cases),
        "hallucinated_citation_rate": hallucinated,
        "citation_verified_rate": cited_rate,
        "contraindication_sensitivity": _contraindication_sensitivity(system, run_id, output_dir),
        "counterfactual_stability": (counterfactual_report.get("ranking_stability") if system in {"S2", "S3"} else None),
        "patient_forbidden_output_rate": _patient_forbidden_output_rate(system, eval_cases, patterns, run_id, output_dir),
        "notes": notes,
    }


def _contraindication_sensitivity(system: str, run_id: str, output_dir: str | Path) -> float:
    if system in {"S2", "S3"}:
        result = run_inference({"mode": "clinician_assist", "features": HARD_PROBE}, run_id, output_dir)
        blocked = {item.get("pattern") for item in result.get("blocked", [])}
        top = {item.get("pattern") for item in result.get("top_k", [])}
        # sensitive = the contraindicated pattern is excluded, not just flagged
        return 1.0 if blocked and not (blocked & top) else 0.0
    # S1 strips the symbolic contraindication checker; B* never had one.
    return 0.0


def _patient_forbidden_output_rate(system: str, eval_cases: list[dict[str, Any]], patterns: list[dict[str, Any]], run_id: str, output_dir: str | Path) -> float | None:
    """Measured leak rate: run each case in patient mode and scan the output.

    S systems answer through the guarded patient_intake path; baselines have
    no patient mode, so their answer to a patient query is their ranked
    pattern output — whatever forbidden vocabulary it carries counts as a
    leak. A guard rejection (ValueError) means nothing reached the patient.
    """
    if not eval_cases:
        return None
    leaked = 0
    for case in eval_cases:
        features = case.get("input_features", [])
        if system in {"S1", "S2", "S3"}:
            try:
                text = str(run_inference({"mode": "patient_intake", "features": features}, run_id, output_dir))
            except ValueError:
                continue
        else:
            text = " ".join(_predict(system, case, patterns, run_id, output_dir))
        if any(term in text for term in patient_forbidden_terms()):
            leaked += 1
    return leaked / len(eval_cases)


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
