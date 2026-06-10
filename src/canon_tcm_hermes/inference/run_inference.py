from __future__ import annotations

from pathlib import Path
from typing import Any

from canon_tcm_hermes.inference.feature_mapper import normalize_features
from canon_tcm_hermes.utils import read_jsonl, run_dir

PATIENT_QUESTIONS = ["发热持续多久？", "是否出汗？", "是否咳喘？", "是否胸痛或呼吸困难？", "是否正在服用药物？"]
RED_FLAG_TERMS = ["胸痛", "呼吸困难", "神昏", "高热不退", "咯血"]
FORBIDDEN_PATIENT_KEYS = {"top_k", "pattern", "formula", "dosage", "treatment_principle", "syndrome"}


def run_inference(payload: dict[str, Any], run_id: str = "demo001", output_dir: str | Path = "outputs") -> dict[str, Any]:
    mode = payload.get("mode", "teaching")
    normalized_features = set(normalize_features(payload.get("features", [])))
    if mode == "patient_intake":
        red_flags = [term for term in RED_FLAG_TERMS if term in normalized_features]
        result = {
            "mode": "patient_intake",
            "red_flags": red_flags,
            "structured_questions": PATIENT_QUESTIONS,
            "visit_summary": "请记录症状起止时间、伴随症状、既往处理和正在使用的药物，并交由医生判断。",
            "forbidden_outputs_checked": True,
        }
        _assert_patient_safe(result)
        return result

    rd = run_dir(run_id, output_dir)
    patterns = read_jsonl(rd / "patterns" / "pattern_aggregations.jsonl")
    evidence_by_segment = _load_evidence_by_segment(rd)
    context_rules = read_jsonl(rd / "inference" / "context_state_rules.jsonl")
    context_hits = _match_context(payload.get("context", {}), normalized_features, context_rules)

    results: list[dict[str, Any]] = []
    for pattern in patterns:
        core = set(normalize_features(pattern.get("core_features", [])))
        common = set(normalize_features(pattern.get("common_features", [])))
        optional = set(normalize_features(pattern.get("optional_features", [])))
        if core and not (core & normalized_features):
            continue
        safety_alerts = [contra for contra in pattern.get("contraindications", []) if set(normalize_features(contra.get("condition", []))) <= normalized_features]
        counter_features = [item for item in pattern.get("exclusion_features", []) if normalize_features([item.get("feature", "")])[0] in normalized_features]
        score = _score_pattern(normalized_features, core, common, optional, counter_features, safety_alerts)
        evidence_cards = _evidence_cards_for_pattern(pattern, evidence_by_segment)
        results.append({
            "pattern": pattern.get("pattern_name"),
            "pattern_id": pattern.get("pattern_id"),
            "score": round(score, 4),
            "support_level": "blocked" if safety_alerts else _support_level(score),
            "supporting_features": sorted((core | common | optional) & normalized_features),
            "counter_features": [item.get("feature") for item in counter_features],
            "missing_information": sorted((core | common) - normalized_features)[:5],
            "context_hits": context_hits,
            "evidence_cards": evidence_cards,
            "safety_alerts": safety_alerts,
        })
    results = sorted(results, key=lambda item: item["score"], reverse=True)[: int(payload.get("top_k", 3))]
    for index, item in enumerate(results, start=1):
        item["rank"] = index
    return {"mode": mode, "top_k": results, "physician_override_allowed": True, "normalized_features": sorted(normalized_features)}


def _assert_patient_safe(result: dict[str, Any]) -> None:
    text = str(result)
    leaked = [key for key in FORBIDDEN_PATIENT_KEYS if key in text]
    if leaked:
        raise ValueError(f"patient_intake output leaked forbidden keys: {leaked}")


def _load_evidence_by_segment(rd: Path) -> dict[str, list[dict[str, Any]]]:
    evidence: dict[str, list[dict[str, Any]]] = {}
    for item in read_jsonl(rd / "evidence" / "evidence_index.jsonl"):
        evidence.setdefault(item.get("segment_id", ""), []).append(item)
    return evidence


def _evidence_cards_for_pattern(pattern: dict[str, Any], evidence_by_segment: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    cards: list[dict[str, Any]] = []
    segment_ids = set()
    for source in pattern.get("evidence_segments", []):
        segment_ids.add(source)
    for item in pattern.get("exclusion_features", []):
        segment_ids.update(item.get("evidence_ids", []))
    for item in pattern.get("contraindications", []):
        segment_ids.update(item.get("evidence_ids", []))
    for segment_id in segment_ids:
        for evidence in evidence_by_segment.get(segment_id, []):
            cards.append({
                "evidence_id": evidence.get("evidence_id"),
                "quote": evidence.get("quote"),
                "source_id": evidence.get("source_id"),
                "evidence_level": evidence.get("evidence_level"),
                "verification_status": evidence.get("verification_status"),
            })
    return cards[:5]


def _match_context(context: dict[str, Any], features: set[str], rules: list[dict[str, Any]]) -> list[dict[str, Any]]:
    tokens = set(normalize_features(context.get("prior_interventions", []))) | set(normalize_features(context.get("current_state", []))) | features
    return [rule for rule in rules if set(normalize_features(rule.get("if", []))) <= tokens]


def _score_pattern(features: set[str], core: set[str], common: set[str], optional: set[str], counters: list[dict[str, Any]], safety_alerts: list[dict[str, Any]]) -> float:
    score = len(core & features) * 1.0 + len(common & features) * 0.5 + len(optional & features) * 0.2
    score -= sum(1.0 if item.get("strength") == "hard" else 0.5 for item in counters)
    if safety_alerts:
        score -= 100.0
    return score


def _support_level(score: float) -> str:
    if score >= 2:
        return "high"
    if score >= 1:
        return "medium"
    return "low"
