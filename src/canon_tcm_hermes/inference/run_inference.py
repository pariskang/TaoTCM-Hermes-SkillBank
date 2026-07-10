from __future__ import annotations

import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import yaml

from canon_tcm_hermes.inference.contraindication_checker import split_alerts
from canon_tcm_hermes.inference.feature_mapper import normalize_features
from canon_tcm_hermes.utils import project_root, read_jsonl, run_dir

DEFAULT_SCORING_WEIGHTS = {
    "core_feature": 1.0,
    "common_feature": 0.5,
    "optional_feature": 0.2,
    "hard_counter": -1.0,
    "soft_counter": -0.5,
    "soft_alert": -1.0,
}
DEFAULT_SUPPORT_LEVELS = {"high": 2.0, "medium": 1.0}

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


@dataclass(frozen=True)
class PatientIntakeResponse:
    """Strongly-typed patient response: the only fields that can exist.

    Patient mode never touches pattern/formula/dosage objects — this type
    is constructed before any pattern data is loaded, so forbidden content
    is excluded structurally, with the lexicon scan kept as defense in
    depth and a response schema validated on top.
    """

    mode: str = "patient_intake"
    red_flags: list[str] = field(default_factory=list)
    urgency: str = "routine"  # routine | emergency_referral
    structured_questions: list[str] = field(default_factory=list)
    visit_summary: str = ""
    forbidden_outputs_checked: bool = True


def detect_red_flags(features: list[Any], narrative: str = "") -> list[str]:
    """Substring red-flag detection over raw feature strings AND free text.

    Exact set-membership missed natural-language input entirely
    (\"我现在胸痛而且呼吸困难\" → no flags); this scans every raw string.
    Still lexical, not semantic — the limitation is stated in the summary
    text, which always instructs the patient to seek care when unsure.
    """
    haystacks = [str(item) for item in features] + [str(narrative)]
    return [term for term in RED_FLAG_TERMS if any(term in haystack for haystack in haystacks)]


def _load_scoring(run_id: str, output_dir: str | Path) -> tuple[dict[str, float], dict[str, float], int, float, float]:
    """Scoring weights, support-level cut points, top_k, minimum core
    coverage and minimum score from the run's inference_config.yaml — the
    config drives the engine (defaults only when the config is absent)."""
    path = run_dir(run_id, output_dir) / "inference" / "inference_config.yaml"
    weights = dict(DEFAULT_SCORING_WEIGHTS)
    levels = dict(DEFAULT_SUPPORT_LEVELS)
    top_k = 3
    min_core_coverage = 0.5
    min_score = 0.0
    if path.exists():
        cfg = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not isinstance(cfg, dict) or not isinstance(cfg.get("scoring", {}), dict):
            raise ValueError(f"malformed inference config: {path}")
        scoring = cfg.get("scoring") or {}
        for key, value in (scoring.get("weights") or {}).items():
            if key in weights and isinstance(value, (int, float)):
                weights[key] = float(value)
        for key, value in (scoring.get("support_levels") or {}).items():
            if key in levels and isinstance(value, (int, float)):
                levels[key] = float(value)
        if isinstance(scoring.get("min_core_coverage"), (int, float)):
            min_core_coverage = float(scoring["min_core_coverage"])
        if isinstance(scoring.get("min_score_exclusive"), (int, float)):
            min_score = float(scoring["min_score_exclusive"])
        ranking = cfg.get("ranking") or {}
        if isinstance(ranking.get("output_top_k"), int) and ranking["output_top_k"] > 0:
            top_k = ranking["output_top_k"]
    return weights, levels, top_k, min_core_coverage, min_score


KNOWN_MODES = {"teaching", "clinician_assist", "patient_intake"}


def run_inference(payload: dict[str, Any], run_id: str = "demo001", output_dir: str | Path = "outputs") -> dict[str, Any]:
    mode = payload.get("mode", "teaching")
    if mode not in KNOWN_MODES:
        # fail closed: an unknown/misspelled mode must never fall through to
        # the clinician branch and expose formula/pattern content
        raise ValueError(f"unknown inference mode {mode!r}; expected one of {sorted(KNOWN_MODES)}")
    normalized_features = set(normalize_features(payload.get("features", [])))
    if mode == "patient_intake":
        # Structural isolation: the typed response is built and returned
        # before any pattern/formula/dosage data is loaded.
        red_flags = detect_red_flags(payload.get("features", []), str(payload.get("narrative", "")))
        if red_flags:
            summary = (
                "您描述的症状（" + "、".join(red_flags) + "）属于需要立即就医的警示症状："
                "请立即前往急诊或拨打当地急救电话，不要等待，也不要自行处理。"
            )
        else:
            summary = "请记录症状起止时间、伴随症状、既往处理和正在使用的药物，并交由医生判断。若症状加重或出现胸痛、呼吸困难、神志改变，请立即就医。"
        response = PatientIntakeResponse(
            red_flags=red_flags,
            urgency="emergency_referral" if red_flags else "routine",
            structured_questions=list(PATIENT_QUESTIONS),
            visit_summary=summary,
        )
        result = asdict(response)
        _assert_patient_schema(result)
        _assert_patient_safe(result)
        return result

    rd = run_dir(run_id, output_dir)
    patterns = read_jsonl(rd / "patterns" / "pattern_aggregations.jsonl")
    evidence_by_segment = _load_evidence_by_segment(rd)
    context_rules = read_jsonl(rd / "inference" / "context_state_rules.jsonl")
    context_hits = _match_context(payload.get("context", {}), normalized_features, context_rules)
    weights, support_levels, config_top_k, min_core_coverage, min_score = _load_scoring(run_id, output_dir)

    results: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []
    excluded_needs_review: list[str] = []
    for pattern in patterns:
        core = set(normalize_features(pattern.get("core_features", [])))
        common = set(normalize_features(pattern.get("common_features", [])))
        optional = set(normalize_features(pattern.get("optional_features", [])))
        # Safety FIRST: a hard-stop contraindication matching the presented
        # signs blocks the formula regardless of how well it would rank.
        hard_alerts, soft_alerts = split_alerts(normalized_features, pattern.get("contraindications", []))
        if hard_alerts:
            blocked.append({
                "pattern": pattern.get("pattern_name"),
                "pattern_id": pattern.get("pattern_id"),
                "support_level": "blocked",
                "supporting_features": sorted((core | common | optional) & normalized_features),
                "safety_alerts": hard_alerts,
                "evidence_cards": _evidence_cards_for_pattern(pattern, evidence_by_segment),
            })
            continue
        if not core:
            # Empty-core patterns are aggregation artifacts awaiting expert
            # review (audit queue) — they must not be recommendable.
            excluded_needs_review.append(str(pattern.get("pattern_name")))
            continue
        # minimal-satisfaction gate: a core STRUCTURE must be present, not
        # just any single trigger word
        coverage = len(core & normalized_features) / len(core)
        if coverage < min_core_coverage:
            continue
        evidence_cards = _evidence_cards_for_pattern(pattern, evidence_by_segment)
        counter_features = [item for item in pattern.get("exclusion_features", []) if normalize_features([item.get("feature", "")])[0] in normalized_features]
        score = _score_pattern(normalized_features, core, common, optional, counter_features, soft_alerts, weights)
        supporting = sorted((core | common | optional) & normalized_features)
        if score <= min_score or not supporting:
            # a candidate with no positive score or no supporting evidence
            # must never be presented as a recommendation
            continue
        results.append({
            "pattern": pattern.get("pattern_name"),
            "pattern_id": pattern.get("pattern_id"),
            "score": round(score, 4),
            "core_coverage": round(coverage, 4),
            "support_level": _support_level(score, support_levels),
            "supporting_features": supporting,
            "counter_features": [item.get("feature") for item in counter_features],
            "missing_information": sorted((core | common) - normalized_features)[:5],
            "context_hits": context_hits,
            "evidence_cards": evidence_cards,
            "safety_alerts": soft_alerts,
        })
    results = sorted(results, key=lambda item: item["score"], reverse=True)[: max(1, int(payload.get("top_k", config_top_k)))]
    for index, item in enumerate(results, start=1):
        item["rank"] = index
    return {
        "mode": mode,
        "top_k": results,
        "blocked": blocked,
        "excluded_needs_review": excluded_needs_review,
        "physician_override_allowed": True,
        "normalized_features": sorted(normalized_features),
    }


def _assert_patient_schema(result: dict[str, Any]) -> None:
    from canon_tcm_hermes.validators.schema_validator import schema_errors

    errors = schema_errors(result, "patient_intake_response.schema.json")
    if errors:
        raise ValueError("patient_intake response failed schema validation: " + "; ".join(errors[:5]))


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


def _score_pattern(features: set[str], core: set[str], common: set[str], optional: set[str], counters: list[dict[str, Any]], soft_alerts: list[dict[str, Any]], weights: dict[str, float]) -> float:
    score = (
        len(core & features) * weights["core_feature"]
        + len(common & features) * weights["common_feature"]
        + len(optional & features) * weights["optional_feature"]
    )
    score += sum(weights["hard_counter"] if item.get("strength") == "hard" else weights["soft_counter"] for item in counters)
    score += weights["soft_alert"] * len(soft_alerts)
    return score


def _support_level(score: float, levels: dict[str, float]) -> str:
    if score >= levels["high"]:
        return "high"
    if score >= levels["medium"]:
        return "medium"
    return "low"
