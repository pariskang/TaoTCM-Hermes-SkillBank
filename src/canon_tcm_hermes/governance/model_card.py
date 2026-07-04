"""TRIPOD-LLM-style model card generator.

Renders a reproducibility-first model card for a run's skill package from
the artifacts the pipeline already produced: data provenance, LLM
configuration and prompt fingerprints, metrics with confidence intervals,
uncertainty/abstention behavior, attribution faithfulness, error-case
analysis (a CONSORT-AI requirement), governance state, and limitations
from the protocol assessment. Missing artifacts are reported as absent —
never invented.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import yaml

from canon_tcm_hermes.annotators.base import GUIDELINE_VERSION, PROMPT_FILES, prompt_version
from canon_tcm_hermes.utils import atomic_write_text, now_iso, read_jsonl, run_dir


def build_model_card(run_id: str, skill_id: str, output_dir: str | Path = "outputs") -> Path:
    rd = run_dir(run_id, output_dir)
    rows = read_jsonl(rd / "input_rows.jsonl")
    routes = read_jsonl(rd / "genre_routes.jsonl")
    errors = read_jsonl(rd / "errors" / "annotation_errors.jsonl")
    ablation = _read_json(rd / "reports" / "ablation_report.json")
    counterfactual = _read_json(rd / "reports" / "counterfactual_report.json")
    citation = _read_json(rd / "reports" / "citation_validation_report.json")
    conformal = _read_json(rd / "reports" / "conformal_report.json")
    attribution = _read_json(rd / "reports" / "attribution_report.json")
    router_calibration = _read_json(rd / "reports" / "router_calibration_report.json")
    assessment = _read_json(rd / "reports" / "protocol_assessment_report.json")
    diff = _read_json(rd / "reports" / "run_diff_report.json")
    skill_meta = _read_yaml(rd / "skills" / skill_id / "skill.yaml")

    books = sorted({row.get("book", "") for row in rows if row.get("book")})
    statistics = ablation.get("statistics") or {}
    s3 = (ablation.get("systems") or {}).get("S3") or {}
    uncertain_routes = [r for r in routes if r.get("genre_uncertain")]

    lines = [
        f"# Model Card — {skill_id}",
        "",
        f"Generated {now_iso()} from run `{run_id}` (TRIPOD-LLM-style reporting skeleton).",
        "",
        "## 1. Intended use",
        "- Evidence-grounded teaching and clinician-assist reasoning over classical Chinese medicine formula-pattern clusters.",
        "- Patient-facing use is limited to red-flag triage, structured intake questions and visit summaries; syndrome/formula/dosage output to patients is structurally forbidden.",
        "- Not a medical device; terminal human audit is required before any stable-grade claim.",
        "",
        "## 2. Data provenance",
        f"- Source rows: {len(rows)}; books: {', '.join(books) if books else 'n/a'}.",
        f"- Genre routing: {len(routes)} rows routed; {len(uncertain_routes)} flagged genre-uncertain for human adjudication.",
        f"- Annotation guideline version: {GUIDELINE_VERSION}.",
        "",
        "## 3. Model & pipeline configuration",
        f"- LLM annotation model: `{os.getenv('LITELLM_MODEL') or 'none (deterministic heuristic mode)'}` via LiteLLM; retries={os.getenv('MAX_RETRIES', '4')}, concurrency={os.getenv('MAX_CONCURRENCY', '5')}.",
        "- Prompt fingerprints (content-hashed; editing a prompt invalidates the annotation cache):",
    ]
    for genre in sorted(PROMPT_FILES):
        lines.append(f"  - {genre}: `{prompt_version(genre)}`")
    lines += [
        "",
        "## 4. Performance (full system S3)",
        _metric_line("Top-1 pattern accuracy", s3.get("top1_pattern_accuracy"), (statistics.get("top1_ci95") or {}).get("S3")),
        f"- Contraindication sensitivity (hard-stop must exclude, not just flag): {_fmt(s3.get('contraindication_sensitivity'))}",
        f"- Patient forbidden-output rate (measured by probe): {_fmt(s3.get('patient_forbidden_output_rate'))}",
        f"- Citation verified rate: {_fmt(citation.get('verified_rate'))} ({citation.get('verified', 0)}/{citation.get('total_evidence', 0)} evidence entries).",
        f"- Counterfactual pass rate: {_fmt(counterfactual.get('counterfactual_pass_rate'))}; hard-stop consistency: {_fmt(counterfactual.get('hard_stop_consistency'))}.",
        f"- Statistical protocol: {((statistics.get('config') or {}).get('method')) or 'not computed'}; n_cases={statistics.get('n_cases', 0)}.",
        f"- Baseline mode: {ablation.get('baseline_mode', 'n/a')}.",
        "",
        "## 5. Uncertainty & abstention",
    ]
    if conformal:
        calibration = conformal.get("calibration") or {}
        lines += [
            f"- Split conformal prediction sets at coverage target {_fmt(calibration.get('coverage_target'))} (alpha={calibration.get('alpha')}), nonconformity = top-minus-true score margin.",
            f"- Calibration n={calibration.get('n_calibration')}; vacuous={calibration.get('vacuous')} (guarantee requires n ≥ {calibration.get('min_n_for_nonvacuous')}).",
            f"- In-sample coverage: {_fmt(conformal.get('empirical_coverage_in_sample'))}; average set size: {_fmt(conformal.get('average_set_size'))}; abstention rate: {_fmt(conformal.get('abstention_rate'))}.",
        ]
    else:
        lines.append("- Conformal report absent — run `canon conformal`.")
    selective = ablation.get("selective_prediction_s3") or {}
    lines.append(f"- Selective prediction (risk-coverage): AURC = {_fmt(selective.get('aurc'))} (confidence signal: {selective.get('confidence_signal', 'n/a')}).")
    lines += [
        "",
        "## 6. Attribution faithfulness",
    ]
    if attribution:
        lines += [
            f"- Feature necessity rate (counterfactual intervention): {_fmt(attribution.get('feature_necessity_rate'))}.",
            f"- Evidence grounding rate (cited quote contains a supporting feature): {_fmt(attribution.get('evidence_grounding_rate'))}.",
        ]
    else:
        lines.append("- Attribution report absent — run `canon eval-attribution`.")
    lines += [
        "",
        "## 7. Annotation quality calibration",
    ]
    if router_calibration:
        primary = router_calibration.get("primary_genre") or {}
        spans = router_calibration.get("spans") or {}
        gate = router_calibration.get("calibration_gate") or {}
        lines += [
            f"- Router vs micro-gold: Po={_fmt(primary.get('observed_agreement_po'))}, Cohen κ={_fmt(primary.get('cohen_kappa'))} over {router_calibration.get('n_rows')} rows.",
            f"- Span agreement: exact F1={_fmt(spans.get('exact_f1'))}, relaxed F1={_fmt(spans.get('relaxed_f1'))} ({spans.get('relaxed_criterion')}).",
            f"- High-stakes gate (κ ≥ 0.8): {'PASSED' if gate.get('passed') else 'NOT PASSED'}.",
        ]
    else:
        lines.append("- No micro-gold calibration recorded — run `canon calibrate-router --gold <file>` (protocol blocking gap).")
    lines += [
        "",
        "## 8. Error-case analysis",
        f"- Annotation errors recorded: {len(errors)} (see errors/annotation_errors.jsonl; LLM failures fall back to heuristics with flags, never silently dropped).",
        f"- Citation verification failures: {len(citation.get('failures', []))}.",
        f"- Genre-uncertain rows requiring adjudication: {len(uncertain_routes)}.",
        "",
        "## 9. Governance & human oversight",
        f"- Skill status: `{skill_meta.get('status', 'unknown')}`, version `{skill_meta.get('version', 'unknown')}`; lineage: {json.dumps(skill_meta.get('lineage') or {}, ensure_ascii=False)}.",
        "- A skill only becomes stable through a recorded terminal human-audit decision (`canon promote`); promotion requires the audit package and a strictly increasing version.",
        f"- Delta audit vs baseline: {('baseline ' + str(diff.get('baseline_run')) + ', ' + str((diff.get('summary') or {}).get('high_priority_focus')) + ' high-priority focus items') if diff else 'not run (canon diff)'}.",
        "",
        "## 10. Limitations (from protocol self-assessment)",
    ]
    gaps = assessment.get("blocking_gaps_before_stable") or []
    if gaps:
        lines += [f"- {gap}" for gap in gaps[:12]]
    else:
        summary = assessment.get("summary")
        lines.append(f"- {summary}" if summary else "- Protocol assessment absent — run `canon assess`.")
    lines += [
        "",
        "## 11. Reproducibility",
        "- Deterministic offline mode (heuristic annotators) reproduces bit-identical annotations; statistics use fixed seeds (bootstrap/permutation seed 13).",
        "- LLM annotations cached by (input hash, prompt content fingerprint, guideline version); resumable via outputs/progress.sqlite.",
        f"- Report generated from: ablation, counterfactual, citation, conformal, attribution, router-calibration, protocol-assessment artifacts under outputs/runs/{run_id}/reports/.",
        "",
    ]
    text = "\n".join(lines)
    card_path = rd / "reports" / "model_card.md"
    atomic_write_text(card_path, text)
    package_refs = rd / "skills" / skill_id / "references"
    if package_refs.is_dir():
        atomic_write_text(package_refs / "MODEL_CARD.md", text)
    return card_path


def _metric_line(label: str, value: Any, ci: dict[str, Any] | None) -> str:
    if ci:
        return f"- {label}: {_fmt(value)} (95% CI [{_fmt(ci.get('lo'))}, {_fmt(ci.get('hi'))}], percentile bootstrap)."
    return f"- {label}: {_fmt(value)}."


def _fmt(value: Any) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:.4g}"
    return str(value)


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}
