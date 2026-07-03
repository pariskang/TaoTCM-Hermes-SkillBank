from __future__ import annotations

import copy
import json
import os
import re
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from pathlib import Path
from typing import Any

from canon_tcm_hermes.io.sqlite_store import SQLiteJobStore
from canon_tcm_hermes.llm.litellm_client import LLMError, complete_json, llm_enabled
from canon_tcm_hermes.utils import (
    atomic_write_json,
    ensure_dir,
    now_iso,
    prompts_dir,
    read_jsonl,
    run_dir,
    sha1_text,
    write_jsonl,
)
from canon_tcm_hermes.validators.schema_validator import schema_errors

GUIDELINE_VERSION = "v1.0"
PROMPT_VERSION = "v2"


@lru_cache(maxsize=None)
def prompt_version(genre: str) -> str:
    """Cache-key component derived from prompt file content.

    Editing a genre prompt (or the shared _annotate_common.md) changes this
    fingerprint and automatically invalidates cached LLM annotations for
    that genre — no manual PROMPT_VERSION bump needed.
    """
    parts = [PROMPT_VERSION]
    for name in (PROMPT_FILES.get(genre, ""), "_annotate_common.md"):
        path = prompts_dir() / name if name else None
        if path and path.exists():
            parts.append(path.read_text(encoding="utf-8"))
    return f"{PROMPT_VERSION}_" + sha1_text("\n".join(parts))[5:13]

ANNOTATION_FILES = {
    "canonical_clause": "clause_templates.jsonl",
    "treatise": "treatise_claims.jsonl",
    "formula_entry": "formula_templates.jsonl",
    "materia_medica": "herb_templates.jsonl",
    "pulse_text": "pulse_templates.jsonl",
    "case_record": "case_templates.jsonl",
    "commentary": "commentary_templates.jsonl",
    "mnemonic_misc": "mnemonic_templates.jsonl",
}
SCHEMA_FILES = {
    "canonical_clause": "clause_template.schema.json",
    "treatise": "treatise_claim.schema.json",
    "formula_entry": "formula_template.schema.json",
    "materia_medica": "herb_template.schema.json",
    "pulse_text": "pulse_template.schema.json",
    "case_record": "case_template.schema.json",
    "commentary": "commentary_template.schema.json",
    "mnemonic_misc": "mnemonic_template.schema.json",
}
PROMPT_FILES = {
    "canonical_clause": "annotate_clause.md",
    "treatise": "annotate_treatise.md",
    "formula_entry": "annotate_formula.md",
    "materia_medica": "annotate_herb.md",
    "pulse_text": "annotate_pulse.md",
    "case_record": "annotate_case.md",
    "commentary": "annotate_commentary.md",
    "mnemonic_misc": "annotate_mnemonic.md",
}
DOWNSTREAM_USE = {
    "canonical_clause": ["clause_template", "pattern_aggregation"],
    "treatise": ["context_state_skeleton", "explanation_card"],
    "formula_entry": ["formula_archive"],
    "materia_medica": ["herb_entity", "safety_constraint_pool"],
    "pulse_text": ["pulse_ontology", "feature_normalization"],
    "case_record": ["eval_cases", "teaching_osce", "pattern_rule_corroboration"],
    "commentary": ["explanation_enrichment", "aggregation_decision_basis", "disputed_marker"],
    "mnemonic_misc": ["teaching_memory_aid", "retrieval_alias", "cross_validation"],
}
NOT_USABLE_FOR = {
    "canonical_clause": [],
    "treatise": ["formula_pattern_matching_rule"],
    "formula_entry": ["indication_rule_without_clause_link"],
    "materia_medica": ["syndrome_rule", "formula_pattern_rule"],
    "pulse_text": ["single_pulse_to_syndrome_hard_rule"],
    "case_record": ["direct_rule_induction"],
    "commentary": ["independent_rule"],
    "mnemonic_misc": ["rule", "evidence_binding"],
}

FEATURE_TERMS = ["发热", "發熱", "恶寒", "惡寒", "恶风", "惡風", "无汗", "無汗", "汗出", "身痛", "头痛", "頭痛", "喘", "烦躁", "煩躁", "口渴", "脉浮紧", "脈浮緊", "脉浮缓", "脈浮緩", "脉微弱", "脈微弱"]
FORMULAS = ["桂枝汤", "桂枝湯", "麻黄汤", "麻黃湯", "葛根汤", "葛根湯", "大青龙汤", "大青龍湯", "小青龙汤", "小青龍湯", "麻杏石甘汤", "麻杏石甘湯"]

PULSE_DIMENSION_MAP = {"浮": ("深浅", "浮"), "沉": ("深浅", "沉"), "迟": ("速度", "迟"), "遲": ("速度", "迟"), "数": ("速度", "数"), "數": ("速度", "数"), "虚": ("力度", "虚"), "實": ("力度", "实"), "实": ("力度", "实"), "弦": ("紧张度", "弦"), "紧": ("紧张度", "紧"), "緊": ("紧张度", "紧"), "滑": ("流利度", "滑"), "涩": ("流利度", "涩"), "澀": ("流利度", "涩")}


# ---------------------------------------------------------------------------
# Shared building blocks
# ---------------------------------------------------------------------------

def annotation_meta(annotator_type: str, confidence: str = "medium", flags: list[str] | None = None, annotator_id: str = "") -> dict[str, Any]:
    return {
        "annotator_type": annotator_type,
        "annotator_id": annotator_id or ("heuristic_annotator_" + PROMPT_VERSION if annotator_type == "heuristic" else annotator_type),
        "confidence": confidence,
        "annotation_flags": flags or [],
        "guideline_version": GUIDELINE_VERSION,
        "timestamp": now_iso(),
    }


def build_status() -> dict[str, Any]:
    return {
        "auto_build_status": "generated",
        "verification_status": "unverified",
        "review_status": "draft",
        "review_requirement": "terminal_review_before_stable",
        "version": "0.1.0",
    }


def evidence_block(row: dict[str, Any], segment: dict[str, Any], quote: str, level: str = "E1") -> dict[str, Any]:
    start, end = segment["span"]
    return {
        "source": {
            "source_id": row["source_id"],
            "book": row.get("book", ""),
            "volume": row.get("volume", ""),
            "chapter": row.get("chapter", ""),
            "version": row.get("version", ""),
            "row_id": row["row_id"],
            "start_offset": start,
            "end_offset": end,
            "text_hash": sha1_text(quote),
        },
        "quote": quote,
        "quote_hash": sha1_text(quote),
        "evidence_level": level,
        # legacy convenience aliases used by downstream validators/builders
        "source_id": row["source_id"],
        "segment_id": segment["segment_id"],
        "evidence_quote": quote,
        "quote_span": [start, end],
        "content_hash": row["content_hash"],
    }


def evidence_for(row: dict[str, Any], segment: dict[str, Any], quote: str) -> dict[str, Any]:
    """Backwards-compatible alias."""
    return evidence_block(row, segment, quote)


def _id(text: str) -> str:
    return re.sub(r"\W+", "_", text or "UNKNOWN").strip("_").upper() or sha1_text(text)[5:13]


def _sid(segment: dict[str, Any]) -> str:
    return segment["segment_id"].replace(":", "_")


def _find_phrase(text: str, needles: list[str]) -> str:
    for n in needles:
        i = text.find(n)
        if i >= 0:
            return text[i : min(len(text), i + 40)]
    return ""


def _extract_herbs(text: str) -> list[dict[str, str]]:
    names = re.findall(r"([一-鿿]{1,4})([一二三四五六七八九十半]+[两兩斤钱錢分升合枚]*)", text)
    return [{"herb": n, "dose_original": d} for n, d in names]


def _assertion_force(quote: str) -> str:
    for marker in ["主之", "不可与", "不可與", "不可", "可与", "可與", "与之则", "與之則", "宜", "当", "當", "禁"]:
        if marker in quote:
            return marker.replace("與", "与").replace("當", "当")
    return "未明示"


def _compound_features(text: str) -> list[dict[str, Any]]:
    out = []
    for surface, components in [("无汗而喘", ["无汗", "喘"]), ("無汗而喘", ["无汗", "喘"]), ("汗出而喘", ["汗出", "喘"])]:
        if surface in text:
            out.append({"surface": surface, "components": components, "scoring_policy": "compound_as_unit"})
    return out


# ---------------------------------------------------------------------------
# Heuristic content extraction (deterministic fallback / offline mode)
# ---------------------------------------------------------------------------

def heuristic_content(genre: str, row: dict[str, Any], segment: dict[str, Any], quote: str) -> dict[str, Any]:
    if genre == "canonical_clause":
        formula = next((f for f in FORMULAS if f in quote), "")
        negative = "不可" in quote or "禁" in quote
        subtype = "contraindication" if negative else ("prescriptive" if re.search(r"(主之|宜|可与|可與|与之则|與之則)", quote) else "theoretical")
        conclusion_type = "prohibition" if negative else ("formula" if formula else ("pattern_naming" if subtype == "theoretical" else "treatment_method"))
        return {
            "clause_subtype": subtype,
            "states": [s for s in ["太阳病", "太阳中风", "伤寒", "阳明病", "少阳病"] if s in quote],
            "features_present": [f for f in FEATURE_TERMS if f in quote],
            "features_absent": ["汗出"] if ("无汗" in quote or "無汗" in quote) else [],
            "compound_features": _compound_features(quote),
            "pulse_features": re.findall(r"脉[一-鿿]{1,3}|脈[一-鿿]{1,3}", quote),
            "conclusion": {"type": conclusion_type, "formula": formula, "assertion_force": _assertion_force(quote), "raw": quote},
            "risk_tier": "T3" if negative else "T2",
        }
    if genre == "formula_entry":
        formula = next((f for f in FORMULAS if f in row["content"]), "")
        return {
            "formula_name": formula or "未署名方",
            "composition": _extract_herbs(quote),
            "preparation": {"method": _find_phrase(quote, ["煮取", "去滓"]), "water": _find_phrase(quote, ["以水"])},
            "administration": {
                "dose_per_serving": _find_phrase(quote, ["温服", "溫服"]),
                "expected_response": _find_phrase(quote, ["微似汗", "覆取", "汗", "愈"]),
                "regimen_note": _find_phrase(quote, ["啜", "禁生冷"]),
            },
            "modification_rules": [{"condition": m} for m in re.findall(r"若[^。；]*", quote)],
        }
    if genre == "materia_medica":
        herb = re.split(r"[，,。\s]", quote)[0]
        toxicity = next((t for t in ["大毒", "有毒", "微毒", "无毒", "無毒"] if t in quote), "未明示")
        safety = []
        if toxicity in {"有毒", "大毒", "微毒"}:
            safety.append({"constraint": f"{herb}原文标记{toxicity}", "constraint_type": "dose_warning", "source_type": "原文明示", "evidence_level": "E1", "enforcement": "soft_alert" if toxicity == "微毒" else "hard_stop"})
        return {
            "herb_name": herb,
            "properties": {"taste_original": _find_phrase(quote, ["味"])[:6], "toxicity_original": toxicity.replace("無毒", "无毒")},
            "functions": re.findall(r"主([^。；]*)", quote),
            "indications_original": re.findall(r"主([^。；]*)", quote),
            "safety_constraints": safety,
        }
    if genre == "pulse_text":
        pulse = re.split(r"[，,。\s]", quote)[0]
        head = pulse[0] if pulse else ""
        dimension, polarity = PULSE_DIMENSION_MAP.get(head, ("形态", head or "未明示"))
        return {
            "pulse_name": pulse,
            "definition": {
                "light_touch": _find_phrase(quote, ["举之", "舉之"]),
                "heavy_press": _find_phrase(quote, ["按之"]),
                "original_definition_quote": quote,
            },
            "dimensions": [{"dimension": dimension, "polarity": polarity}],
            "differential_pairs": [],
            "syndrome_associations": ([{"association": _find_phrase(quote, ["为", "為"]), "strength": "weak_default"}] if ("为" in quote or "為" in quote) else []),
            "feature_decomposition_rules": [],
        }
    if genre == "case_record":
        feats = [f for f in FEATURE_TERMS if f in quote]
        interventions = [{"stage": 1, "formula": f} for f in FORMULAS if f in quote]
        cured = any(k in quote for k in ["而愈", "热退", "熱退", "霍然", "愈"])
        return {
            "patient_context": {"raw": quote[:30]},
            "presentation_timeline": [{"stage": 1, "stage_label": "初诊", "features": feats}],
            "physician_reasoning_extracted": [],
            "interventions": interventions,
            "outcome": {"result": _find_phrase(quote, ["而愈", "热退", "熱退", "霍然", "不起"]), "result_category": "痊愈" if cured else "失访/未载", "outcome_reliability": "author_reported"},
            "school_tag": "",
        }
    if genre == "commentary":
        name_match = re.match(r"([一-鿿]{1,3})(?:注曰|曰|按)", quote)
        return {
            "commentator": {"name": name_match.group(1) if name_match else "未署名"},
            "interpretation_type": "病机阐释",
            "interpretation_summary": quote,
            "agreement_status": "unassessed",
            "divergence_note": "",
        }
    if genre == "treatise":
        m = re.search(r"(.+?)(皆属于|皆屬於)(.+?)[。；]?$", quote)
        if m:
            claims = [{"subject": m.group(1).strip("，。 "), "predicate": "皆属于", "object": m.group(3).strip("，。 "), "quantifier": "universal"}]
        else:
            parts = re.split(r"[，。；]", quote)
            claims = [{"subject": parts[0] if parts else quote, "predicate": "论述", "object": "，".join(p for p in parts[1:] if p) or "未明示", "quantifier": "unspecified"}]
        return {"claim_type": "pathogenesis_principle", "claims": claims, "transmission_states": [], "school_tag": ""}
    if genre == "mnemonic_misc":
        formula = next((f for f in FORMULAS if f in quote), "")
        is_verse = segment.get("sub_genre") == "verse" or bool(re.search(r"(歌|诀|訣|赋|賦)", row.get("book", "") + row.get("chapter", ""))) or formula != ""
        content: dict[str, Any] = {"sub_genre": "verse" if is_verse else "note"}
        if is_verse:
            content["verse_fields"] = {
                "verse_function": "方剂组成记忆" if formula else ("脉象记忆" if ("脉" in quote or "脈" in quote) else "其他"),
                "target_type": "formula" if formula else ("pulse" if ("脉" in quote or "脈" in quote) else "other"),
                "target_id": _id(formula) if formula else "",
                "consistency_check": {"against": f"{_id(formula)}.composition" if formula else "", "status": "not_checked"},
            }
            content["target_formula"] = formula
        else:
            content["note_fields"] = {"note_type": "临证心得", "summary": quote[:60]}
        return content
    raise ValueError(f"unknown genre: {genre}")


# ---------------------------------------------------------------------------
# LLM content extraction
# ---------------------------------------------------------------------------

def llm_content(genre: str, row: dict[str, Any], segment: dict[str, Any], quote: str) -> dict[str, Any]:
    common = (prompts_dir() / "_annotate_common.md").read_text(encoding="utf-8")
    system_prompt = (prompts_dir() / PROMPT_FILES[genre]).read_text(encoding="utf-8") + "\n\n" + common
    user_prompt = (
        f"book: {row.get('book', '')} | volume: {row.get('volume', '')} | chapter: {row.get('chapter', '')}\n"
        f"segment_genre: {genre}" + (f" | sub_genre: {segment.get('sub_genre')}" if segment.get("sub_genre") else "") + "\n"
        f"span text:\n{quote}"
    )

    def _validate(data: Any) -> list[str]:
        # The raw LLM payload only becomes schema-valid after assemble()
        # injects provenance, so validate the assembled probe — its schema
        # diff is fed back to the model on retry.
        if not isinstance(data, dict):
            return [f"response must be a JSON object, got {type(data).__name__}"]
        try:
            probe = assemble(genre, row, segment, quote, copy.deepcopy(data), annotation_meta("llm"))
        except Exception as exc:  # noqa: BLE001 — any assembly crash is retry feedback
            return [f"content could not be assembled: {exc}"]
        return schema_errors(probe, SCHEMA_FILES[genre])

    data = complete_json(system_prompt, user_prompt, validate=_validate)
    if not isinstance(data, dict):
        raise LLMError(f"annotator LLM returned non-object: {type(data).__name__}")
    return data


# ---------------------------------------------------------------------------
# Assembly: content fields + provenance/governance fields
# ---------------------------------------------------------------------------

def assemble(genre: str, row: dict[str, Any], segment: dict[str, Any], quote: str, content: dict[str, Any], meta: dict[str, Any]) -> dict[str, Any]:
    sid = _sid(segment)
    ann: dict[str, Any] = dict(content)
    if not ann.get("school_tag"):
        ann.pop("school_tag", None)  # schema requires non-empty when present
    ann["source_id"] = row["source_id"]
    ann["segment_id"] = segment["segment_id"]
    ann["downstream_use"] = DOWNSTREAM_USE[genre]
    ann["not_usable_for"] = NOT_USABLE_FOR[genre]
    ann["build_status"] = build_status()
    ann["annotation_meta"] = meta
    level = "E3" if genre == "commentary" else ("E5" if genre == "mnemonic_misc" else "E1")
    ann["evidence"] = evidence_block(row, segment, quote, level=level)

    if genre == "canonical_clause":
        ann.setdefault("template_id", f"CLAUSE_{sid}")
        ann.setdefault("clause_subtype", "prescriptive")
        conclusion = ann.get("conclusion") or {}
        conclusion.setdefault("type", "formula" if conclusion.get("formula") else "pattern_naming")
        conclusion.setdefault("assertion_force", _assertion_force(quote))
        ann["conclusion"] = conclusion
        if ann.get("clause_subtype") in {"contraindication", "mistreatment_consequence"}:
            ann["risk_tier"] = "T3"
        ann.setdefault("risk_tier", "T2")
    elif genre == "formula_entry":
        name = ann.get("formula_name") or "未署名方"
        ann["formula_name"] = name
        ann.setdefault("formula_id", "F_" + _id(name))
        composition = [c for c in ann.get("composition", []) if isinstance(c, dict) and c.get("herb")]
        for c in composition:
            c.setdefault("dose_original", "未明示")
        ann["composition"] = composition
        ann["dose_conversion_modern"] = {"status": "not_attempted"}
        ann["visibility_policy"] = {"teaching": "full", "clinician_assist": "full", "patient_intake": "hidden"}
        ann.setdefault("linked_patterns", [])
        if isinstance(ann.get("preparation"), str):
            ann["preparation"] = {"method": ann["preparation"]}
        if isinstance(ann.get("administration"), str):
            ann["administration"] = {"dose_per_serving": ann["administration"]}
        if isinstance(ann.get("expected_response"), str):
            admin = ann.setdefault("administration", {})
            if isinstance(admin, dict):
                admin.setdefault("expected_response", ann.pop("expected_response"))
        rules = []
        for ruleitem in ann.get("modification_rules", []):
            if isinstance(ruleitem, str):
                rules.append({"condition": ruleitem})
            elif isinstance(ruleitem, dict) and ruleitem.get("condition"):
                rules.append(ruleitem)
        ann["modification_rules"] = rules
    elif genre == "materia_medica":
        name = ann.get("herb_name") or re.split(r"[，,。\s]", quote)[0]
        ann["herb_name"] = name
        ann.setdefault("herb_id", "H_" + _id(name))
        constraints = []
        for c in ann.get("safety_constraints", []):
            if not isinstance(c, dict) or not c.get("constraint"):
                continue
            c.setdefault("constraint_type", "condition")
            c.setdefault("source_type", "原文明示")
            c.setdefault("evidence_level", "E1")
            c.setdefault("enforcement", "soft_alert")
            constraints.append(c)
        ann["safety_constraints"] = constraints
    elif genre == "pulse_text":
        name = ann.get("pulse_name") or re.split(r"[，,。\s]", quote)[0]
        ann["pulse_name"] = name
        ann.setdefault("pulse_id", "P_" + _id(name))
        if isinstance(ann.get("definition"), str):
            ann["definition"] = {"original_definition_quote": ann["definition"]}
        ann.setdefault("definition", {"original_definition_quote": quote})
        pairs = []
        for pair in ann.get("differential_pairs", []):
            if isinstance(pair, dict) and pair.get("vs_pulse"):
                pair.setdefault("distinction", "未明示")
                pairs.append(pair)
        ann["differential_pairs"] = pairs
        dims = [d for d in ann.get("dimensions", []) if isinstance(d, dict) and d.get("dimension") and d.get("polarity")]
        if not dims:
            head = name[0] if name else ""
            dimension, polarity = PULSE_DIMENSION_MAP.get(head, ("形态", head or "未明示"))
            dims = [{"dimension": dimension, "polarity": polarity}]
        ann["dimensions"] = dims
        assoc = []
        for a in ann.get("syndrome_associations", []):
            if isinstance(a, dict) and a.get("association"):
                a.setdefault("strength", "weak_default")
                assoc.append(a)
        ann["syndrome_associations"] = assoc
    elif genre == "case_record":
        ann.setdefault("case_id", f"CASE_{sid}")
        timeline = [t for t in ann.get("presentation_timeline", []) if isinstance(t, dict)]
        for index, stage in enumerate(timeline, start=1):
            stage.setdefault("stage", index)
            stage.setdefault("features", [])
        if not timeline:
            timeline = [{"stage": 1, "stage_label": "初诊", "features": [f for f in FEATURE_TERMS if f in quote]}]
        ann["presentation_timeline"] = timeline
        interventions = []
        for index, item in enumerate(ann.get("interventions", []), start=1):
            if isinstance(item, str):
                interventions.append({"stage": 1, "formula": item})
            elif isinstance(item, dict):
                item.setdefault("stage", index)
                interventions.append(item)
        ann["interventions"] = interventions
        outcome = ann.get("outcome") if isinstance(ann.get("outcome"), dict) else {}
        if outcome.get("result_category") not in {"痊愈", "好转", "无效", "恶化", "死亡", "失访/未载"}:
            outcome["result_category"] = "失访/未载"
        outcome["outcome_reliability"] = "author_reported"
        ann["outcome"] = outcome
        gold = next((i.get("formula") for i in interventions if i.get("formula")), "")
        ann["auto_generated_eval_case"] = {
            "eval_case_id": f"EVAL_{sid}",
            "gold_answer": f"{gold}证" if gold else "未明示",
            "gold_answer_scope": "physician_judgment_only_not_objective_truth",
            "tests": ["formula_pattern_recognition"],
        }
        ann["bias_flags"] = list(dict.fromkeys(list(ann.get("bias_flags", [])) + ["case_not_rule"]))
    elif genre == "commentary":
        ann.setdefault("comment_id", f"COMMENT_{sid}")
        commentator = ann.get("commentator")
        if not isinstance(commentator, dict) or not commentator.get("name"):
            commentator = {"name": "未署名"}
        ann["commentator"] = commentator
        ann.setdefault("target_clause", segment.get("dedup_target") or row["source_id"])
        if ann.get("agreement_status") not in {"consensus", "divergent", "unique", "unassessed"}:
            ann["agreement_status"] = "unassessed"
        ann.setdefault("interpretation_summary", quote)
    elif genre == "treatise":
        ann.setdefault("claim_id", f"CLAIM_{sid}")
        valid_types = {"pathogenesis_principle", "transmission_framework", "treatment_principle", "physiology_doctrine", "diagnostic_principle", "ethics_or_practice_norm"}
        if ann.get("claim_type") not in valid_types:
            ann["claim_type"] = "pathogenesis_principle"
        claims = [c for c in ann.get("claims", []) if isinstance(c, dict) and c.get("subject") and c.get("predicate") and c.get("object")]
        if not claims:
            claims = heuristic_content("treatise", row, segment, quote)["claims"]
        ann["claims"] = claims
    elif genre == "mnemonic_misc":
        ann.setdefault("item_id", f"MNEMONIC_{sid}")
        if ann.get("sub_genre") not in {"verse", "note"}:
            ann["sub_genre"] = "verse" if segment.get("sub_genre") == "verse" else "note"
        if ann["sub_genre"] == "verse":
            fields = ann.get("verse_fields") if isinstance(ann.get("verse_fields"), dict) else {}
            if fields.get("verse_function") not in {"方剂组成记忆", "药性记忆", "脉象记忆", "治法记忆", "穴位记忆", "其他"}:
                fields["verse_function"] = "其他"
            if fields.get("target_type") not in {"formula", "herb", "pulse", "other"}:
                fields["target_type"] = "other"
            ann["verse_fields"] = fields
            target_name = fields.get("target_name") or ann.get("target_formula") or next((f for f in FORMULAS if f in quote), "")
            if target_name and fields["target_type"] in {"formula", "other"}:
                ann["target_formula"] = target_name
        else:
            fields = ann.get("note_fields") if isinstance(ann.get("note_fields"), dict) else {}
            if fields.get("note_type") not in {"临证心得", "读书札记", "医林掌故", "见闻杂记", "warning_anecdote"}:
                fields["note_type"] = "临证心得"
            ann["note_fields"] = fields
    return ann


def annotate_segment(row: dict[str, Any], segment: dict[str, Any], use_llm: bool = False) -> dict[str, Any] | None:
    """Annotate a single routed segment. Returns None for non-medical spans."""
    genre = segment["genre"]
    if genre == "non_medical" or segment.get("routed_template") == "skip":
        return None
    start, end = segment["span"]
    quote = row["content"][start:end]
    flags: list[str] = []
    content: dict[str, Any] | None = None
    annotator_type = "heuristic"
    if use_llm:
        try:
            content = llm_content(genre, row, segment, quote)
            annotator_type = "llm"
        except Exception as exc:
            flags.append(f"llm_annotation_failed_fallback_heuristic: {str(exc)[:200]}")
    if content is None:
        content = heuristic_content(genre, row, segment, quote)
        flags.append("heuristic_annotation") if "heuristic_annotation" not in flags else None
    meta = annotation_meta(
        annotator_type,
        confidence="medium" if annotator_type == "llm" else "low",
        flags=flags,
        annotator_id=os.getenv("LITELLM_MODEL", "") if annotator_type == "llm" else "",
    )
    ann = assemble(genre, row, segment, quote, content, meta)
    errors = schema_errors(ann, SCHEMA_FILES[genre])
    if errors and annotator_type == "llm":
        # LLM produced unsalvageable content: rebuild from heuristics, keep trace.
        content = heuristic_content(genre, row, segment, quote)
        meta = annotation_meta("heuristic", confidence="low", flags=flags + ["llm_output_failed_schema:" + "; ".join(errors[:3])])
        ann = assemble(genre, row, segment, quote, content, meta)
        errors = schema_errors(ann, SCHEMA_FILES[genre])
    if errors:
        raise ValueError("annotation schema validation failed: " + "; ".join(errors[:5]))
    return ann


def annotate_run(run_id: str, output_dir: str | Path = "outputs", use_llm: bool | None = None) -> dict[str, int]:
    use_llm = llm_enabled() if use_llm is None else use_llm
    rd = run_dir(run_id, output_dir)
    rows = {r["source_id"]: r for r in read_jsonl(rd / "input_rows.jsonl")}
    routes = read_jsonl(rd / "genre_routes.jsonl")
    if not routes:
        raise FileNotFoundError(f"genre_routes.jsonl missing or empty for run {run_id}; run `canon route` first")

    jobs: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for route in routes:
        row = rows.get(route["source_id"])
        if row is None:
            continue
        for segment in route["genre_segmentation"]:
            jobs.append((row, segment))

    store = SQLiteJobStore(Path(output_dir) / "progress.sqlite") if use_llm else None
    cache_dir = ensure_dir(rd / "annotations" / "cache") if use_llm else None
    buckets: dict[str, list[dict[str, Any]]] = {g: [] for g in ANNOTATION_FILES}
    errors: list[dict[str, Any]] = []

    def run_job(row: dict[str, Any], segment: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any] | None, str | None]:
        genre = segment["genre"]
        if genre == "non_medical" or segment.get("routed_template") == "skip":
            return segment, None, None
        start, end = segment["span"]
        input_hash = sha1_text(row["content"][start:end])
        job_id = f"{run_id}:annotate:{segment['segment_id']}"
        cache_path = cache_dir / (sha1_text(job_id)[5:25] + ".json") if cache_dir else None
        if store and cache_path and cache_path.exists() and store.should_skip(job_id, input_hash, prompt_version(genre), GUIDELINE_VERSION):
            return segment, json.loads(cache_path.read_text(encoding="utf-8")), None
        try:
            ann = annotate_segment(row, segment, use_llm=use_llm)
            if store and cache_path and ann is not None:
                atomic_write_json(cache_path, ann)
                store.upsert_job(job_id=job_id, run_id=run_id, stage="annotate", source_id=row["source_id"], segment_id=segment["segment_id"], genre=genre, input_hash=input_hash, prompt_version=prompt_version(genre), schema_version=GUIDELINE_VERSION, status="done", attempts=1, output_path=str(cache_path), error="")
            return segment, ann, None
        except Exception as exc:
            if store:
                store.upsert_job(job_id=job_id, run_id=run_id, stage="annotate", source_id=row["source_id"], segment_id=segment["segment_id"], genre=genre, input_hash=input_hash, prompt_version=prompt_version(genre), schema_version=GUIDELINE_VERSION, status="failed", attempts=1, output_path="", error=str(exc)[:500])
            return segment, None, str(exc)

    if use_llm and len(jobs) > 1:
        max_workers = max(int(os.getenv("MAX_CONCURRENCY", "5")), 1)
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            results = list(pool.map(lambda pair: run_job(*pair), jobs))
    else:
        results = [run_job(row, segment) for row, segment in jobs]

    for segment, ann, error in results:
        if error is not None:
            errors.append({"source_id": segment["segment_id"].split("::SEG")[0], "segment_id": segment.get("segment_id"), "genre": segment.get("genre"), "error": error})
        elif ann is not None:
            buckets[segment["genre"]].append(ann)

    for genre, fname in ANNOTATION_FILES.items():
        write_jsonl(rd / "annotations" / fname, buckets[genre])
    write_jsonl(rd / "errors" / "annotation_errors.jsonl", errors)
    return {g: len(v) for g, v in buckets.items()}
