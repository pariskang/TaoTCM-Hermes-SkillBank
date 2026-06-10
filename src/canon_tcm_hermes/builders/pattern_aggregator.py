from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from canon_tcm_hermes.inference.feature_mapper import normalize_features
from canon_tcm_hermes.utils import read_jsonl, run_dir, write_jsonl


def build_patterns(run_id: str, output_dir: str | Path = "outputs") -> list[dict[str, Any]]:
    rd = run_dir(run_id, output_dir)
    clauses = read_jsonl(rd / "annotations" / "clause_templates.jsonl")
    commentary = read_jsonl(rd / "annotations" / "commentary_templates.jsonl")
    cases = read_jsonl(rd / "annotations" / "case_templates.jsonl")
    by_formula: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for clause in clauses:
        formula = (clause.get("conclusion") or {}).get("formula")
        if formula:
            by_formula[formula].append(clause)

    patterns: list[dict[str, Any]] = []
    for formula, items in by_formula.items():
        counts = Counter(feature for clause in items for feature in normalize_features(clause.get("features_present", [])))
        core = sorted(feature for feature, count in counts.items() if count == len(items) or feature == "无汗")
        common = sorted(feature for feature in counts if feature not in core)
        evidence_segments = [clause["segment_id"] for clause in items]
        pattern_name = f"{formula}证"
        pattern = {
            "pattern_id": _pattern_id(formula),
            "pattern_name": pattern_name,
            "formula_name": formula,
            "core_features": core,
            "common_features": common,
            "optional_features": [],
            "compound_features": [feature for clause in items for feature in clause.get("compound_features", [])],
            "exclusion_features": _exclusions(core, evidence_segments),
            "contraindications": _contraindications(formula, evidence_segments),
            "evidence_segments": evidence_segments,
            "aggregated_from": [clause["source_id"] for clause in items],
            "commentary_support": _commentary_support(commentary, formula),
            "case_corroboration_count": _case_corroboration_count(cases, formula),
            "aggregation_decisions": [{
                "decision": "从 canonical_clause 聚合核心方证特征",
                "basis": "方证规则只由条文体产生；方书提供档案，医案只作实例佐证，歌诀只作教学校验。",
                "auto_generated": True,
                "needs_audit": True,
            }],
            "status": "auto_generated",
        }
        patterns.append(pattern)
    write_jsonl(rd / "patterns" / "pattern_aggregations.jsonl", patterns)
    return patterns


def _pattern_id(formula: str) -> str:
    return formula.replace("汤", "TANG").replace("湯", "TANG").upper() + "_ZHENG"


def _exclusions(core: list[str], evidence_segments: list[str]) -> list[dict[str, Any]]:
    if "无汗" in core:
        return [{"feature": "汗出", "strength": "hard", "reason": "与无汗核心结构冲突", "evidence_ids": evidence_segments}]
    return []


def _contraindications(formula: str, evidence_segments: list[str]) -> list[dict[str, Any]]:
    if "麻黄" in formula or "麻黃" in formula:
        return [{"condition": ["脉微弱", "汗出", "恶风"], "action": "hard_stop", "risk_tier": "T3", "evidence_ids": evidence_segments}]
    return []


def _commentary_support(commentary: list[dict[str, Any]], formula: str) -> list[str]:
    return [item.get("comment_id", "") for item in commentary if formula in item.get("interpretation_summary", "")]


def _case_corroboration_count(cases: list[dict[str, Any]], formula: str) -> int:
    return sum(1 for case in cases if formula in case.get("interventions", []) or formula in str(case))
