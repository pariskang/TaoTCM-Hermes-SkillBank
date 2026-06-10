from __future__ import annotations

from pathlib import Path
from typing import Any

from canon_tcm_hermes.utils import atomic_write_json, read_jsonl, run_dir


def validate_cross_genre(run_id: str, output_dir: str | Path = "outputs") -> dict[str, Any]:
    rd = run_dir(run_id, output_dir)
    formulas = read_jsonl(rd / "annotations" / "formula_templates.jsonl")
    clauses = read_jsonl(rd / "annotations" / "clause_templates.jsonl")
    cases = read_jsonl(rd / "annotations" / "case_templates.jsonl")
    commentary = read_jsonl(rd / "annotations" / "commentary_templates.jsonl")
    herbs = read_jsonl(rd / "annotations" / "herb_templates.jsonl")
    mnemonics = read_jsonl(rd / "annotations" / "mnemonic_templates.jsonl")

    formula_names = {item.get("formula_name") for item in formulas if item.get("formula_name")}
    formula_ids = {item.get("formula_id") for item in formulas if item.get("formula_id")}
    clause_segments = {item.get("segment_id") for item in clauses}
    herb_names = {item.get("herb_name") for item in herbs if item.get("herb_name")}
    formula_herbs = {herb.get("herb") for formula in formulas for herb in formula.get("composition", []) if herb.get("herb")}

    inconsistencies: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []

    for mnemonic in mnemonics:
        target = mnemonic.get("target_formula")
        if target and target not in formula_names and target.upper() not in formula_ids:
            warnings.append({"type": "mnemonic_target_without_formula_archive", "target": target, "mnemonic_id": mnemonic.get("mnemonic_id")})
    for formula in formulas:
        linked = any((clause.get("conclusion") or {}).get("formula") == formula.get("formula_name") for clause in clauses)
        if not linked:
            warnings.append({"type": "formula_without_clause_link", "formula": formula.get("formula_name")})
    for case in cases:
        for intervention in case.get("interventions", []):
            if intervention not in formula_names:
                warnings.append({"type": "case_intervention_without_formula_archive", "case_id": case.get("case_id"), "intervention": intervention})
    for comment in commentary:
        target = comment.get("target_clause")
        if target and target not in clause_segments and "::ROW" not in target:
            inconsistencies.append({"type": "commentary_target_clause_missing", "comment_id": comment.get("comment_id"), "target": target})
    for herb_name in herb_names:
        if formula_herbs and herb_name not in formula_herbs:
            warnings.append({"type": "herb_not_used_by_formula_archive", "herb": herb_name})

    report = {
        "checked": True,
        "inconsistencies": inconsistencies,
        "warnings": warnings,
        "passed": not inconsistencies,
        "counts": {"formulas": len(formulas), "clauses": len(clauses), "cases": len(cases), "commentary": len(commentary), "herbs": len(herbs), "mnemonics": len(mnemonics)},
    }
    atomic_write_json(rd / "reports" / "cross_genre_validation_report.json", report)
    return report
