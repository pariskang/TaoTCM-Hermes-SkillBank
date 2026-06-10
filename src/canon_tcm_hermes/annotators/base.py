from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from jsonschema import validate

from canon_tcm_hermes.utils import read_jsonl, run_dir, sha1_text, write_jsonl

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

FEATURE_TERMS = ["发热", "發熱", "恶寒", "惡寒", "恶风", "惡風", "无汗", "無汗", "汗出", "身痛", "头痛", "頭痛", "喘", "烦躁", "煩躁", "口渴", "脉浮紧", "脈浮緊", "脉浮缓", "脈浮緩", "脉微弱", "脈微弱"]
FORMULAS = ["桂枝汤", "桂枝湯", "麻黄汤", "麻黃湯", "葛根汤", "葛根湯", "大青龙汤", "大青龍湯", "小青龙汤", "小青龍湯", "麻杏石甘汤", "麻杏石甘湯"]


def evidence_for(row: dict[str, Any], segment: dict[str, Any], quote: str) -> dict[str, Any]:
    return {"source_id": row["source_id"], "segment_id": segment["segment_id"], "evidence_quote": quote, "quote_span": segment["span"], "content_hash": row["content_hash"], "evidence_level": "E1"}


def annotate_segment(row: dict[str, Any], segment: dict[str, Any]) -> dict[str, Any] | None:
    genre = segment["genre"]
    if genre == "non_medical":
        return None
    start, end = segment["span"]
    quote = row["content"][start:end]
    ev = evidence_for(row, segment, quote)
    sid = segment["segment_id"].replace(":", "_")
    if genre == "canonical_clause":
        formula = next((f for f in FORMULAS if f in quote), "")
        feats = [f for f in FEATURE_TERMS if f in quote]
        return {"template_id": f"CLAUSE_{sid}", "source_id": row["source_id"], "segment_id": segment["segment_id"], "states": [], "features_present": feats, "features_absent": ["汗出"] if "无汗" in quote or "無汗" in quote else [], "compound_features": _compound_features(quote), "conclusion": {"formula": formula, "raw": quote}, "assertion_force": "prohibited" if "不可" in quote else "assertive", "negative_clause": "不可" in quote, "risk_tier": "T3" if "不可" in quote else "T1", "evidence": ev, "annotation_flags": ["heuristic_annotation"]}
    if genre == "formula_entry":
        formula = next((f for f in FORMULAS if f in row["content"]), "UNKNOWN_FORMULA")
        herbs = _extract_herbs(quote)
        return {"formula_id": _id(formula), "formula_name": formula, "source_id": row["source_id"], "segment_id": segment["segment_id"], "composition": herbs, "preparation": _find_phrase(quote, ["以水", "煮取", "去滓"]), "administration": _find_phrase(quote, ["温服", "溫服", "覆取", "啜"]), "modification_rules": re.findall(r"若[^。；]*", quote), "expected_response": _find_phrase(quote, ["汗", "愈"]), "dose_conversion_modern": "forbidden", "visibility_policy": {"patient_intake": "hide_formula_dosage_administration"}, "linked_patterns": [], "annotation_flags": ["heuristic_annotation"], "evidence": ev}
    if genre == "materia_medica":
        herb = re.split(r"[，,。\s]", quote)[0]
        return {"herb_id": _id(herb), "herb_name": herb, "source_id": row["source_id"], "segment_id": segment["segment_id"], "properties": {"raw": _find_phrase(quote, ["味", "性", "有毒", "无毒", "無毒"])}, "functions": re.findall(r"主([^。；]*)", quote), "indications_original": re.findall(r"主([^。；]*)", quote), "term_ambiguity": [], "safety_constraints": ["毒性需人工审核"] if "毒" in quote else [], "downstream_use": ["herb_entity", "property", "function", "safety_constraint"], "not_usable_for": ["syndrome_rule", "formula_pattern_rule"], "evidence": ev}
    if genre == "pulse_text":
        pulse = re.split(r"[，,。\s]", quote)[0]
        return {"pulse_id": _id(pulse), "pulse_name": pulse, "source_id": row["source_id"], "segment_id": segment["segment_id"], "definition": quote, "dimension": {"raw": quote}, "polarity": "", "differential_pairs": [], "syndrome_associations": [{"association": "weak_default", "source": "pulse_text"}] if "为" in quote or "為" in quote else [], "not_usable_for": ["single_pulse_to_syndrome_hard_rule"], "evidence": ev}
    if genre == "case_record":
        return {"case_id": f"CASE_{sid}", "source_id": row["source_id"], "segment_id": segment["segment_id"], "patient_context": {"raw": quote[:30]}, "presentation_timeline": re.split(r"[。；]", quote), "physician_reasoning_extracted": "", "interventions": [f for f in FORMULAS if f in quote], "outcome": _find_phrase(quote, ["而愈", "热退", "熱退", "霍然"]), "auto_generated_eval_case": {"input": quote, "gold_answer_scope": "physician_judgment_only"}, "bias_flags": ["case_not_rule"], "school_tag": "", "not_usable_for": ["direct_rule_induction"], "evidence": ev}
    if genre == "commentary":
        return {"comment_id": f"COMMENT_{sid}", "source_id": row["source_id"], "segment_id": segment["segment_id"], "commentator": "", "target_clause": segment.get("dedup_target", ""), "interpretation_summary": quote, "agreement_status": "unknown", "divergence_note": "", "evidence_level": "E3", "downstream_use": ["explanation_enrichment", "aggregation_basis", "disputed_marker"], "not_usable_for": ["independent_rule"], "evidence": ev}
    if genre == "treatise":
        return {"claim_id": f"CLAIM_{sid}", "source_id": row["source_id"], "segment_id": segment["segment_id"], "claim_type": "mechanism_claim", "claims": [quote], "downstream_use": ["context_state_skeleton", "explanation_card"], "not_usable_for": ["formula_pattern_matching_rule"], "school_tag": "", "evidence_level": "E1", "evidence": ev}
    if genre == "mnemonic_misc":
        return {"mnemonic_id": f"MNEMONIC_{sid}", "source_id": row["source_id"], "segment_id": segment["segment_id"], "target_formula": next((f for f in FORMULAS if f in quote), ""), "target_pulse": "脉" if "脉" in quote or "脈" in quote else "", "verse_function": "teaching_memory_aid", "consistency_check": {"status": "needs_cross_validation"}, "evidence_level": "E5", "downstream_use": ["teaching_memory_aid", "retrieval_alias", "cross_validation_signal"], "not_usable_for": ["rule", "evidence_binding"], "evidence": ev}
    return None


def annotate_run(run_id: str, output_dir: str | Path = "outputs") -> dict[str, int]:
    rd = run_dir(run_id, output_dir)
    rows = {r["source_id"]: r for r in read_jsonl(rd / "input_rows.jsonl")}
    routes = read_jsonl(rd / "genre_routes.jsonl")
    buckets: dict[str, list[dict[str, Any]]] = {g: [] for g in ANNOTATION_FILES}
    errors: list[dict[str, Any]] = []
    schemas = {g: __import__("json").loads((Path("schemas") / SCHEMA_FILES[g]).read_text(encoding="utf-8")) for g in SCHEMA_FILES}
    for route in routes:
        row = rows[route["source_id"]]
        for segment in route["genre_segmentation"]:
            try:
                ann = annotate_segment(row, segment)
                if ann is None:
                    continue
                validate(ann, schemas[segment["genre"]])
                buckets[segment["genre"]].append(ann)
            except Exception as exc:
                errors.append({"source_id": route["source_id"], "segment_id": segment.get("segment_id"), "genre": segment.get("genre"), "error": str(exc)})
    for genre, fname in ANNOTATION_FILES.items():
        write_jsonl(rd / "annotations" / fname, buckets[genre])
    write_jsonl(rd / "errors" / "annotation_errors.jsonl", errors)
    return {g: len(v) for g, v in buckets.items()}


def _id(text: str) -> str:
    return re.sub(r"\W+", "_", text or "UNKNOWN").strip("_").upper() or sha1_text(text)[5:13]


def _extract_herbs(text: str) -> list[dict[str, str]]:
    names = re.findall(r"([\u4e00-\u9fff]{1,4})([一二三四五六七八九十半]+[两兩斤钱錢分升合枚]*)", text)
    return [{"herb": n, "original_dose": d} for n, d in names]


def _find_phrase(text: str, needles: list[str]) -> str:
    for n in needles:
        i = text.find(n)
        if i >= 0:
            return text[i:min(len(text), i + 40)]
    return ""


def _compound_features(text: str) -> list[dict[str, Any]]:
    out=[]
    if "无汗而喘" in text or "無汗而喘" in text:
        out.append({"surface":"无汗而喘","components":["无汗","喘"],"scoring_policy":"compound_as_unit"})
    return out
