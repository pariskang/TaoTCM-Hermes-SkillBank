from __future__ import annotations

from pathlib import Path
from typing import Any

from canon_tcm_hermes.utils import atomic_write_json, read_jsonl, run_dir

# executable_status answers: "does the repository contain a runnable implementation?"
# maturity_status answers: "is this publication/stable-grade without further expert work?"
PROTOCOL_CAPABILITIES = [
    {
        "capability": "L0_excel_import",
        "executable_status": "implemented",
        "maturity_status": "mvp_complete",
        "note": "Loads xlsx, normalizes aliases, creates row_id/source_id/content_hash.",
        "remaining_work": [],
    },
    {
        "capability": "L0_5_genre_router",
        "executable_status": "implemented",
        "maturity_status": "needs_micro_gold_calibration",
        "note": "Router covers eight genres and common mixed-span cases with schema validation.",
        "remaining_work": ["Calibrate boundaries and labels against 100-150 human-adjudicated micro-gold samples."],
    },
    {
        "capability": "L1_annotation",
        "executable_status": "implemented",
        "maturity_status": "needs_llm_production_mode",
        "note": "Genre-specific deterministic annotators plus schema-validating LiteLLM JSON wrapper are available.",
        "remaining_work": ["Wire default async LiteLLM annotation orchestration, retries, validation-diff prompts, and raw output persistence for production runs."],
    },
    {
        "capability": "L2_evidence_backtrace",
        "executable_status": "implemented",
        "maturity_status": "mvp_complete",
        "note": "Validates source_id, quote substring, quote_span, and content_hash.",
        "remaining_work": [],
    },
    {
        "capability": "L3_cross_genre_graph",
        "executable_status": "implemented",
        "maturity_status": "needs_entity_resolution",
        "note": "Builds multi-node knowledge graph and cross-genre inconsistency/warning report.",
        "remaining_work": ["Add robust formula/herb/pulse alias resolution and variant-text deduplication beyond simple name matching."],
    },
    {
        "capability": "L4_pattern_aggregation",
        "executable_status": "implemented",
        "maturity_status": "needs_expert_calibration",
        "note": "Aggregates formula patterns from canonical clauses with commentary/case support metadata.",
        "remaining_work": ["Calibrate core/common/optional feature thresholds and contraindication strength with terminal expert review."],
    },
    {
        "capability": "L5_context_state",
        "executable_status": "implemented",
        "maturity_status": "needs_richer_temporal_model",
        "note": "Extracts context rules from canonical clauses and treatise claims.",
        "remaining_work": ["Expand course-day, prior-intervention, transmission, and mistreatment state modeling."],
    },
    {
        "capability": "L6_inference_config",
        "executable_status": "implemented",
        "maturity_status": "mvp_complete",
        "note": "Compiles default ordinal inference configuration.",
        "remaining_work": [],
    },
    {
        "capability": "L7_inference_engine",
        "executable_status": "implemented",
        "maturity_status": "needs_gold_evaluation",
        "note": "Runs safety-gated ranking with feature normalization, context hits, missing information, and evidence cards.",
        "remaining_work": ["Validate ranking behavior on expert-adjudicated clinical teaching/eval cases before any stable use."],
    },
    {
        "capability": "L8_cds_profiles",
        "executable_status": "implemented",
        "maturity_status": "mvp_complete",
        "note": "Configures teaching, clinician_assist, and patient_intake visibility rules.",
        "remaining_work": [],
    },
    {
        "capability": "L9_skill_export",
        "executable_status": "implemented",
        "maturity_status": "mvp_complete",
        "note": "Exports Codex/Hermes-compatible skill folder with references and executable helper scripts.",
        "remaining_work": [],
    },
    {
        "capability": "L10_audit_package",
        "executable_status": "implemented",
        "maturity_status": "requires_terminal_human_audit",
        "note": "Builds terminal human-audit package and audit queue.",
        "remaining_work": ["Stable promotion remains blocked until expert audit decisions are recorded."],
    },
    {
        "capability": "counterfactual_eval",
        "executable_status": "implemented",
        "maturity_status": "needs_gold_thresholds",
        "note": "Runs deterministic counterfactual inference comparisons and hard-stop checks.",
        "remaining_work": ["Define pass/fail thresholds from adjudicated counterfactual suites rather than demo-only expectations."],
    },
    {
        "capability": "ablation_eval",
        "executable_status": "implemented",
        "maturity_status": "local_proxy_not_publication_grade",
        "note": "Runs deterministic local B0/B1/B2/S1/S2/S3 ablation metrics over generated eval cases.",
        "remaining_work": ["Replace local proxy baselines with real bare-LLM, naive-RAG, and GraphRAG adapters for publication-grade studies."],
    },
    {
        "capability": "governance",
        "executable_status": "implemented",
        "maturity_status": "requires_operational_policy",
        "note": "Provides risk tiering, audit queue, promotion, rollback, and override logging utilities.",
        "remaining_work": ["Bind promotion/rollback/override records to organizational identity, review, and deployment policy."],
    },
]


def assess_protocol(run_id: str | None = None, output_dir: str | Path = "outputs") -> dict[str, Any]:
    executable_counts = {"implemented": 0, "partial": 0, "missing": 0}
    maturity_counts: dict[str, int] = {}
    items = []
    blocking_gaps = []
    for item in PROTOCOL_CAPABILITIES:
        executable_counts[item["executable_status"]] += 1
        maturity_counts[item["maturity_status"]] = maturity_counts.get(item["maturity_status"], 0) + 1
        items.append(item)
        for gap in item["remaining_work"]:
            blocking_gaps.append({"capability": item["capability"], "gap": gap})
    report: dict[str, Any] = {
        "claim": "not_perfect_all_features_research_grade",
        "summary": "All protocol stages have executable local implementations, but the system is not perfect or stable-grade until micro-gold calibration, production LLM orchestration, publication-grade baselines, and terminal expert audit are completed.",
        "executable_counts": executable_counts,
        "maturity_counts": maturity_counts,
        "items": items,
        "blocking_gaps_before_stable": blocking_gaps,
        "stable_promotion_allowed": False,
    }
    if run_id:
        rd = run_dir(run_id, output_dir)
        report["run_artifacts"] = {
            "input_rows": len(read_jsonl(rd / "input_rows.jsonl")),
            "genre_routes": len(read_jsonl(rd / "genre_routes.jsonl")),
            "patterns": len(read_jsonl(rd / "patterns" / "pattern_aggregations.jsonl")),
            "eval_cases": len(read_jsonl(rd / "eval" / "eval_cases.jsonl")),
            "audit_package_exists": (rd / "audit" / "audit_package.json").exists(),
        }
        atomic_write_json(rd / "reports" / "protocol_assessment_report.json", report)
    return report
