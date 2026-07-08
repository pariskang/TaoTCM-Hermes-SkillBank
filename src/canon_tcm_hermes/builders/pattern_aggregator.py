from __future__ import annotations

import re
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
    # Contraindication / mistreatment clauses are safety knowledge, not
    # positive pattern evidence — mixing them in would corrupt core features.
    SAFETY_SUBTYPES = {"contraindication", "mistreatment_consequence"}
    positive_clauses = [c for c in clauses if c.get("clause_subtype") not in SAFETY_SUBTYPES]
    safety_clauses = [c for c in clauses if c.get("clause_subtype") in SAFETY_SUBTYPES]
    by_formula: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for clause in positive_clauses:
        formula = (clause.get("conclusion") or {}).get("formula")
        if formula:
            by_formula[formula].append(clause)

    patterns: list[dict[str, Any]] = []
    for formula, items in by_formula.items():
        counts = Counter(feature for clause in items for feature in normalize_features(clause.get("features_present", [])))
        # core = features attested by every aggregated clause; absence-marked
        # features (features_absent counterpart) stay core-eligible too.
        core = sorted(feature for feature, count in counts.items() if count == len(items))
        common = sorted(feature for feature in counts if feature not in core)
        if not core and common:
            most_common = counts.most_common(1)[0][0]
            core, common = [most_common], [f for f in common if f != most_common]
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
            "contraindications": _contraindications_from_clauses(formula, safety_clauses),
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
        if not pattern["core_features"]:
            # An aggregation artifact without a core is not recommendable:
            # the inference engine skips it and it goes to the audit queue.
            pattern["status"] = "auto_generated_needs_review"
            pattern["aggregation_decisions"].append({
                "decision": "core_features 为空，暂不可用于推理",
                "basis": "无任何全条文共现特征；需专家裁定核心症群后方可参与排序。",
                "auto_generated": True,
                "needs_audit": True,
            })
        patterns.append(pattern)
    write_jsonl(rd / "patterns" / "pattern_aggregations.jsonl", patterns)
    return patterns


def _pattern_id(formula: str) -> str:
    return formula.replace("汤", "TANG").replace("湯", "TANG").upper() + "_ZHENG"


def _exclusions(core: list[str], evidence_segments: list[str]) -> list[dict[str, Any]]:
    if "无汗" in core:
        return [{"feature": "汗出", "strength": "hard", "reason": "与无汗核心结构冲突", "evidence_ids": evidence_segments}]
    return []


_PROHIBITION_TARGET = re.compile(r"(?:不可(?:与|與|服|发汗以|發汗以)?服?|禁用?|勿(?:与|與|服))\s*([一-鿿]{2,8}[汤湯散丸饮飲])")


def _prohibition_targets(quote: str) -> list[str]:
    """Formulas that the clause actually prohibits (canonicalized).

    Substring matching alone would also hit the RECOMMENDED alternative in
    contrast clauses (不可与桂枝汤，宜麻黄汤), so the prohibition target is
    parsed from the prohibition marker itself.
    """
    from canon_tcm_hermes.builders.entity_resolver import canonical_name

    return [canonical_name(match, "formulas") for match in _PROHIBITION_TARGET.findall(quote)]


def _contraindications_from_clauses(formula: str, safety_clauses: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Contraindications are extracted from contraindication/mistreatment
    clauses that prohibit this formula — evidence-grounded, never hardcoded.
    Matching is canonicalized (traditional/simplified folding, aliases) and
    targeted at the prohibited formula, not any formula mentioned in the
    quote. Each rule carries the segment ids of its source clauses, so
    citation validation covers safety rules too."""
    from canon_tcm_hermes.builders.entity_resolver import canonical_name

    canonical_formula = canonical_name(formula, "formulas")
    rules: list[dict[str, Any]] = []
    for clause in safety_clauses:
        conclusion = clause.get("conclusion") or {}
        quote = str((clause.get("evidence") or {}).get("quote", "")) or str(conclusion.get("raw", ""))
        targets = _prohibition_targets(quote)
        if targets:
            prohibited = canonical_formula in targets
        else:
            # no parsable prohibition target: fall back to the clause's own
            # conclusion formula (canonicalized), never to raw substring
            prohibited = canonical_name(str(conclusion.get("formula") or ""), "formulas") == canonical_formula
        if not prohibited:
            continue
        condition = list(dict.fromkeys(list(clause.get("features_present", [])) + list(clause.get("pulse_features", []))))
        if not condition:
            continue
        rules.append({
            "condition": condition,
            "action": "hard_stop",
            "risk_tier": clause.get("risk_tier", "T3"),
            "evidence_ids": [clause.get("segment_id")],
            "source_clause_subtype": clause.get("clause_subtype"),
        })
    return rules


def _commentary_support(commentary: list[dict[str, Any]], formula: str) -> list[str]:
    return [item.get("comment_id", "") for item in commentary if formula in item.get("interpretation_summary", "")]


def _case_corroboration_count(cases: list[dict[str, Any]], formula: str) -> int:
    count = 0
    for case in cases:
        formulas = {item.get("formula") for item in case.get("interventions", []) if isinstance(item, dict)}
        if formula in formulas:
            count += 1
    return count
