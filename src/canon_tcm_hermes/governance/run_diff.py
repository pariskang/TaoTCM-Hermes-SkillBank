"""Delta audit between two pipeline runs.

The evolution loop revises data.xlsx and rebuilds under a new run id; the
terminal human audit then only needs to review what actually changed since
the last audited baseline instead of re-reading the whole package.
`build_run_diff` computes that delta — patterns, evidence, safety/eval
metrics, genre routing — and writes reports/run_diff_report.json into the
current run, flagging safety-relevant changes as high-priority audit focus.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from canon_tcm_hermes.utils import atomic_write_json, now_iso, read_jsonl, run_dir

# Pattern fields the expert must re-review when they change.
PATTERN_FIELDS = [
    "core_features",
    "common_features",
    "optional_features",
    "compound_features",
    "exclusion_features",
    "contraindications",
    "case_corroboration_count",
    "commentary_support",
]
SAFETY_PATTERN_FIELDS = {"exclusion_features", "contraindications"}

# metric -> which direction is an improvement
METRIC_DIRECTION = {
    "counterfactual_pass_rate": "higher",
    "hard_stop_consistency": "higher",
    "citation_verified_rate": "higher",
    "s3_top1_pattern_accuracy": "higher",
    "s3_contraindication_sensitivity": "higher",
    "s3_patient_forbidden_output_rate": "lower",
}
SAFETY_METRICS = {"hard_stop_consistency", "s3_contraindication_sensitivity", "s3_patient_forbidden_output_rate"}


def build_run_diff(run_id: str, baseline_run_id: str, output_dir: str | Path = "outputs", skill_id: str | None = None) -> dict[str, Any]:
    baseline_dir = Path(output_dir) / "runs" / baseline_run_id
    if not baseline_dir.is_dir():
        raise FileNotFoundError(f"baseline run not found: {baseline_dir}")
    if run_id == baseline_run_id:
        raise ValueError("diff requires two distinct runs")
    rd = run_dir(run_id, output_dir)

    patterns = _diff_patterns(
        read_jsonl(baseline_dir / "patterns" / "pattern_aggregations.jsonl"),
        read_jsonl(rd / "patterns" / "pattern_aggregations.jsonl"),
    )
    evidence = _diff_evidence(
        read_jsonl(baseline_dir / "evidence" / "evidence_index.jsonl"),
        read_jsonl(rd / "evidence" / "evidence_index.jsonl"),
    )
    metrics = _diff_metrics(_metrics(baseline_dir), _metrics(rd))
    genres = _diff_genre_counts(baseline_dir, rd)
    audit_focus = _audit_focus(patterns, evidence, metrics)

    report = {
        "baseline_run": baseline_run_id,
        "current_run": run_id,
        "generated_at": now_iso(),
        "summary": {
            "patterns_added": len(patterns["added"]),
            "patterns_removed": len(patterns["removed"]),
            "patterns_changed": len(patterns["changed"]),
            "patterns_unchanged": patterns["unchanged_count"],
            "evidence_added": len(evidence["added"]),
            "evidence_removed": len(evidence["removed"]),
            "evidence_status_changed": len(evidence["status_changed"]),
            "metric_regressions": sum(1 for m in metrics.values() if m.get("regression")),
            "high_priority_focus": sum(1 for f in audit_focus if f["priority"] == "high"),
        },
        "patterns": patterns,
        "evidence": evidence,
        "metric_deltas": metrics,
        "genre_count_changes": genres,
        "audit_focus": audit_focus,
        "note": "Review scope for the terminal human audit: entries here changed since the audited baseline; everything else is byte-identical at the compared level.",
    }
    if skill_id:
        report["skill_context"] = {
            "skill_id": skill_id,
            "baseline_skill": _skill_summary(baseline_dir, skill_id),
            "current_skill": _skill_summary(rd, skill_id),
        }
    atomic_write_json(rd / "reports" / "run_diff_report.json", report)
    return report


def _diff_patterns(baseline: list[dict[str, Any]], current: list[dict[str, Any]]) -> dict[str, Any]:
    base_by = {p.get("pattern_id"): p for p in baseline}
    cur_by = {p.get("pattern_id"): p for p in current}
    added = [{"pattern_id": pid, "pattern_name": cur_by[pid].get("pattern_name")} for pid in sorted(set(cur_by) - set(base_by))]
    removed = [{"pattern_id": pid, "pattern_name": base_by[pid].get("pattern_name")} for pid in sorted(set(base_by) - set(cur_by))]
    changed = []
    unchanged = 0
    for pid in sorted(set(base_by) & set(cur_by)):
        field_changes = {}
        for field in PATTERN_FIELDS:
            if base_by[pid].get(field) != cur_by[pid].get(field):
                field_changes[field] = {"baseline": base_by[pid].get(field), "current": cur_by[pid].get(field)}
        if field_changes:
            changed.append({
                "pattern_id": pid,
                "pattern_name": cur_by[pid].get("pattern_name"),
                "safety_relevant": bool(SAFETY_PATTERN_FIELDS & set(field_changes)),
                "changes": field_changes,
            })
        else:
            unchanged += 1
    return {"added": added, "removed": removed, "changed": changed, "unchanged_count": unchanged}


def _evidence_key(item: dict[str, Any]) -> tuple[str, str]:
    return (str(item.get("source_id", "")), str(item.get("quote", item.get("evidence_quote", ""))))


def _diff_evidence(baseline: list[dict[str, Any]], current: list[dict[str, Any]]) -> dict[str, Any]:
    base_by = {_evidence_key(e): e for e in baseline}
    cur_by = {_evidence_key(e): e for e in current}
    added = [cur_by[k] for k in sorted(set(cur_by) - set(base_by))]
    removed = [base_by[k] for k in sorted(set(base_by) - set(cur_by))]
    status_changed = []
    for key in sorted(set(base_by) & set(cur_by)):
        before = base_by[key].get("verification_status")
        after = cur_by[key].get("verification_status")
        if before != after:
            status_changed.append({"source_id": key[0], "quote": key[1], "baseline": before, "current": after})
    slim = lambda e: {"source_id": e.get("source_id"), "quote": e.get("quote", e.get("evidence_quote")), "verification_status": e.get("verification_status")}  # noqa: E731
    return {"added": [slim(e) for e in added], "removed": [slim(e) for e in removed], "status_changed": status_changed}


def _metrics(rd: Path) -> dict[str, Any]:
    counterfactual = _read_json(rd / "reports" / "counterfactual_report.json")
    citation = _read_json(rd / "reports" / "citation_validation_report.json")
    ablation_s3 = ((_read_json(rd / "reports" / "ablation_report.json").get("systems") or {}).get("S3") or {})
    return {
        "counterfactual_pass_rate": counterfactual.get("counterfactual_pass_rate"),
        "hard_stop_consistency": counterfactual.get("hard_stop_consistency"),
        "citation_verified_rate": citation.get("verified_rate"),
        "s3_top1_pattern_accuracy": ablation_s3.get("top1_pattern_accuracy"),
        "s3_contraindication_sensitivity": ablation_s3.get("contraindication_sensitivity"),
        "s3_patient_forbidden_output_rate": ablation_s3.get("patient_forbidden_output_rate"),
    }


def _diff_metrics(baseline: dict[str, Any], current: dict[str, Any]) -> dict[str, Any]:
    deltas: dict[str, Any] = {}
    for name, direction in METRIC_DIRECTION.items():
        before, after = baseline.get(name), current.get(name)
        entry: dict[str, Any] = {"baseline": before, "current": after, "delta": None, "regression": False}
        if isinstance(before, (int, float)) and isinstance(after, (int, float)):
            delta = round(after - before, 6)
            entry["delta"] = delta
            entry["regression"] = (delta < 0) if direction == "higher" else (delta > 0)
        deltas[name] = entry
    return deltas


def _diff_genre_counts(baseline_dir: Path, rd: Path) -> dict[str, Any]:
    before = _read_json(baseline_dir / "reports" / "genre_report.json").get("genre_counts") or {}
    after = _read_json(rd / "reports" / "genre_report.json").get("genre_counts") or {}
    return {
        genre: {"baseline": before.get(genre, 0), "current": after.get(genre, 0)}
        for genre in sorted(set(before) | set(after))
        if before.get(genre, 0) != after.get(genre, 0)
    }


def _audit_focus(patterns: dict[str, Any], evidence: dict[str, Any], metrics: dict[str, Any]) -> list[dict[str, str]]:
    focus: list[dict[str, str]] = []
    for item in patterns["changed"]:
        if item["safety_relevant"]:
            focus.append({"priority": "high", "item": f"pattern {item['pattern_name']}: safety fields changed ({', '.join(sorted(SAFETY_PATTERN_FIELDS & set(item['changes'])))})"})
        else:
            focus.append({"priority": "medium", "item": f"pattern {item['pattern_name']}: fields changed ({', '.join(sorted(item['changes']))})"})
    for item in patterns["added"]:
        focus.append({"priority": "medium", "item": f"new pattern requires first-time review: {item['pattern_name']}"})
    for item in patterns["removed"]:
        focus.append({"priority": "high", "item": f"pattern removed since baseline: {item['pattern_name']}"})
    for name, entry in metrics.items():
        if entry.get("regression"):
            priority = "high" if name in SAFETY_METRICS else "medium"
            focus.append({"priority": priority, "item": f"metric regression: {name} {entry['baseline']} -> {entry['current']}"})
    if evidence["removed"]:
        focus.append({"priority": "medium", "item": f"{len(evidence['removed'])} evidence entries removed since baseline"})
    for item in evidence["status_changed"]:
        focus.append({"priority": "high", "item": f"evidence verification status changed for {item['source_id']}: {item['baseline']} -> {item['current']}"})
    return sorted(focus, key=lambda f: 0 if f["priority"] == "high" else 1)


def _skill_summary(rdir: Path, skill_id: str) -> dict[str, Any] | None:
    skill_yaml = rdir / "skills" / skill_id / "skill.yaml"
    if not skill_yaml.exists():
        return None
    import yaml

    meta = yaml.safe_load(skill_yaml.read_text(encoding="utf-8")) or {}
    return {"version": meta.get("version"), "status": meta.get("status"), "lineage": meta.get("lineage")}


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))
