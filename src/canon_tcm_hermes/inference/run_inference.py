from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

from canon_tcm_hermes.inference.contraindication_checker import split_alerts
from canon_tcm_hermes.inference.feature_mapper import normalize_features
from canon_tcm_hermes.utils import project_root, read_jsonl, run_dir

PATIENT_QUESTIONS = ["发热持续多久？", "是否出汗？", "是否咳喘？", "是否胸痛或呼吸困难？", "是否正在服用药物？"]
RED_FLAG_TERMS = ["胸痛", "呼吸困难", "神昏", "高热不退", "咯血"]
# Built-in fail-closed floor: the configurable lexicon
# (configs/patient_safety_lexicon.yaml) can only EXTEND these sets, never
# remove from them.
FORBIDDEN_PATIENT_KEYS = {"top_k", "pattern", "formula", "dosage", "treatment_principle", "syndrome"}
# Content-level guard: formula/syndrome/dosage vocabulary must never reach
# the patient_intake response, regardless of which key carries it.
FORBIDDEN_PATIENT_TERMS = ["汤", "湯", "散", "丸", "证", "證", "剂量", "劑量", "两", "兩", "钱", "錢", "治法", "方剂", "方劑"]


def _lexicon_config(config_path: str | Path | None = None) -> dict[str, Any]:
    path = Path(config_path or os.getenv("TAOTCM_PATIENT_LEXICON") or project_root() / "configs" / "patient_safety_lexicon.yaml")
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def patient_forbidden_terms(config_path: str | Path | None = None) -> list[str]:
    extra = _lexicon_config(config_path).get("forbidden_terms") or []
    return sorted(set(FORBIDDEN_PATIENT_TERMS) | {str(t) for t in extra if str(t).strip()})


def patient_forbidden_keys(config_path: str | Path | None = None) -> list[str]:
    extra = _lexicon_config(config_path).get("forbidden_keys") or []
    return sorted(FORBIDDEN_PATIENT_KEYS | {str(k) for k in extra if str(k).strip()})


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
    blocked: list[dict[str, Any]] = []
    for pattern in patterns:
        core = set(normalize_features(pattern.get("core_features", [])))
        common = set(normalize_features(pattern.get("common_features", [])))
        optional = set(normalize_features(pattern.get("optional_features", [])))
        if core and not (core & normalized_features):
            continue
        hard_alerts, soft_alerts = split_alerts(normalized_features, pattern.get("contraindications", []))
        evidence_cards = _evidence_cards_for_pattern(pattern, evidence_by_segment)
        if hard_alerts:
            # T3 hard stop: the pattern is removed from recommendation, not
            # merely down-ranked; it is surfaced separately with its alerts.
            blocked.append({
                "pattern": pattern.get("pattern_name"),
                "pattern_id": pattern.get("pattern_id"),
                "support_level": "blocked",
                "supporting_features": sorted((core | common | optional) & normalized_features),
                "safety_alerts": hard_alerts,
                "evidence_cards": evidence_cards,
            })
            continue
        counter_features = [item for item in pattern.get("exclusion_features", []) if normalize_features([item.get("feature", "")])[0] in normalized_features]
        score = _score_pattern(normalized_features, core, common, optional, counter_features, soft_alerts)
        results.append({
            "pattern": pattern.get("pattern_name"),
            "pattern_id": pattern.get("pattern_id"),
            "score": round(score, 4),
            "support_level": _support_level(score),
            "supporting_features": sorted((core | common | optional) & normalized_features),
            "counter_features": [item.get("feature") for item in counter_features],
            "missing_information": sorted((core | common) - normalized_features)[:5],
            "context_hits": context_hits,
            "evidence_cards": evidence_cards,
            "safety_alerts": soft_alerts,
        })
    results = sorted(results, key=lambda item: item["score"], reverse=True)[: int(payload.get("top_k", 3))]
    for index, item in enumerate(results, start=1):
        item["rank"] = index
    return {"mode": mode, "top_k": results, "blocked": blocked, "physician_override_allowed": True, "normalized_features": sorted(normalized_features)}


def _assert_patient_safe(result: dict[str, Any]) -> None:
    text = str(result)
    leaked = [key for key in patient_forbidden_keys() if key in text]
    leaked += [term for term in patient_forbidden_terms() if term in text]
    if leaked:
        raise ValueError(f"patient_intake output leaked forbidden content: {leaked}")


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


def _score_pattern(features: set[str], core: set[str], common: set[str], optional: set[str], counters: list[dict[str, Any]], soft_alerts: list[dict[str, Any]]) -> float:
    score = len(core & features) * 1.0 + len(common & features) * 0.5 + len(optional & features) * 0.2
    score -= sum(1.0 if item.get("strength") == "hard" else 0.5 for item in counters)
    score -= 1.0 * len(soft_alerts)
    return score


def _support_level(score: float) -> str:
    if score >= 2:
        return "high"
    if score >= 1:
        return "medium"
    return "low"
