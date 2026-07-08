"""Typed tool registry: every pipeline capability as a declared tool.

Each tool declares what artifacts it requires and produces (paths relative
to the run directory, `{skill_id}` interpolated), a risk tier, and whether
it may run without human approval. The planner reasons over these
declarations instead of a hardcoded stage order — dynamic tool selection
per the agent review.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from canon_tcm_hermes.agent.state import AgentState


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    requires: tuple[str, ...]
    produces: tuple[str, ...]
    run: Callable[[AgentState], Any]
    risk_tier: str = "T1"
    needs_human: bool = False
    params: dict[str, str] = field(default_factory=dict)


def _rd(state: AgentState) -> Path:
    from canon_tcm_hermes.utils import run_dir

    return run_dir(state.run_id, state.output_dir)


class HumanApprovalRequired(RuntimeError):
    """Raised by tools whose execution is reserved for a human decision."""


def artifact_exists(state: AgentState, relative: str) -> bool:
    return (_rd(state) / relative.format(skill_id=state.skill_id)).exists()


def artifact_satisfied(state: AgentState, relative: str) -> bool:
    """Existence plus validity: a failed validation summary does NOT satisfy
    the validate_run target — the gate must be re-run, not skipped."""
    path = _rd(state) / relative.format(skill_id=state.skill_id)
    if not path.exists():
        return False
    if relative == "reports/validation_summary.json":
        import json

        try:
            return bool(json.loads(path.read_text(encoding="utf-8")).get("passed"))
        except (ValueError, OSError):
            return False
    return True


def _load_excel(state: AgentState) -> Any:
    from canon_tcm_hermes.io.excel_loader import load_excel

    if not state.input_path:
        raise ValueError("goal requires input rows but no --input was provided")
    return load_excel(state.input_path, state.run_id, state.output_dir)


def _route(state: AgentState) -> Any:
    from canon_tcm_hermes.router.genre_router import route_run

    return route_run(state.run_id, state.output_dir)


def _annotate(state: AgentState) -> Any:
    from canon_tcm_hermes.annotators.base import annotate_run

    return annotate_run(state.run_id, state.output_dir)


def _evidence(state: AgentState) -> Any:
    from canon_tcm_hermes.validators.citation_validator import build_and_validate_evidence

    return build_and_validate_evidence(state.run_id, state.output_dir)


def _graph(state: AgentState) -> Any:
    from canon_tcm_hermes.builders.knowledge_graph_builder import build_knowledge_graph

    return build_knowledge_graph(state.run_id, state.output_dir)


def _patterns(state: AgentState) -> Any:
    from canon_tcm_hermes.builders.pattern_aggregator import build_patterns

    return build_patterns(state.run_id, state.output_dir)


def _context(state: AgentState) -> Any:
    from canon_tcm_hermes.builders.context_state_builder import build_context_state

    return build_context_state(state.run_id, state.output_dir)


def _inference_config(state: AgentState) -> Any:
    from canon_tcm_hermes.builders.inference_config_builder import build_inference_config

    return build_inference_config(state.run_id, state.skill_id, state.output_dir)


def _eval_cases(state: AgentState) -> Any:
    from canon_tcm_hermes.eval.build_eval_cases import build_eval_cases

    return build_eval_cases(state.run_id, state.output_dir)


def _counterfactual(state: AgentState) -> Any:
    from canon_tcm_hermes.eval.run_counterfactual_tests import run_counterfactual

    return run_counterfactual(state.run_id, state.output_dir)


def _ablation(state: AgentState) -> Any:
    from canon_tcm_hermes.eval.run_ablation import run_ablation

    return run_ablation(state.run_id, state.output_dir)


def _attribution(state: AgentState) -> Any:
    from canon_tcm_hermes.eval.run_attribution import run_attribution

    return run_attribution(state.run_id, state.output_dir)


def _conformal(state: AgentState) -> Any:
    from canon_tcm_hermes.inference.conformal import run_conformal_report

    return run_conformal_report(state.run_id, state.output_dir)


def _skill(state: AgentState) -> Any:
    from canon_tcm_hermes.builders.hermes_skill_builder import build_skill

    return build_skill(state.run_id, state.skill_id, state.output_dir)


def _audit(state: AgentState) -> Any:
    from canon_tcm_hermes.builders.audit_package_builder import build_audit_package

    return build_audit_package(state.run_id, state.skill_id, state.output_dir)


def _validate(state: AgentState) -> Any:
    from canon_tcm_hermes.validators.pipeline_validator import run_validation

    return run_validation(state.run_id, state.output_dir, state.skill_id)


def _assess(state: AgentState) -> Any:
    from canon_tcm_hermes.validators.protocol_assessor import assess_protocol

    return assess_protocol(state.run_id, state.output_dir)


def _model_card(state: AgentState) -> Any:
    from canon_tcm_hermes.governance.model_card import build_model_card

    return build_model_card(state.run_id, state.skill_id, state.output_dir)


TOOLS: dict[str, ToolSpec] = {tool.name: tool for tool in [
    ToolSpec("load_excel", "Load and normalize the source workbook", (), ("input_rows.jsonl",), _load_excel),
    ToolSpec("route_genre", "Genre-route every row with span segmentation", ("input_rows.jsonl",), ("genre_routes.jsonl", "reports/genre_report.json"), _route),
    ToolSpec("annotate", "Per-genre schema-validated annotation", ("genre_routes.jsonl",), (
        "annotations/clause_templates.jsonl", "annotations/treatise_claims.jsonl", "annotations/formula_templates.jsonl",
        "annotations/herb_templates.jsonl", "annotations/pulse_templates.jsonl", "annotations/case_templates.jsonl",
        "annotations/commentary_templates.jsonl", "annotations/mnemonic_templates.jsonl",
    ), _annotate),
    ToolSpec("validate_evidence", "Build and verify the evidence index (quote/span/hash)", ("annotations/clause_templates.jsonl",), ("evidence/evidence_index.jsonl", "reports/citation_validation_report.json"), _evidence, risk_tier="T2"),
    ToolSpec("build_graph", "Cross-genre knowledge graph", ("annotations/clause_templates.jsonl",), ("graphs/knowledge_graph.json",), _graph),
    ToolSpec("aggregate_patterns", "Aggregate formula-pattern rules from clauses", ("annotations/clause_templates.jsonl", "evidence/evidence_index.jsonl"), ("patterns/pattern_aggregations.jsonl",), _patterns, risk_tier="T2"),
    ToolSpec("compile_context", "Compile context-state rules", ("annotations/clause_templates.jsonl",), ("inference/context_state_rules.jsonl",), _context),
    ToolSpec("compile_inference", "Emit the inference configuration that drives scoring", ("patterns/pattern_aggregations.jsonl",), ("inference/inference_config.yaml",), _inference_config),
    ToolSpec("build_eval_cases", "Derive eval cases from case records", ("annotations/case_templates.jsonl",), ("eval/eval_cases.jsonl",), _eval_cases),
    ToolSpec("eval_counterfactual", "Counterfactual sensitivity + hard-stop consistency", ("patterns/pattern_aggregations.jsonl", "inference/inference_config.yaml"), ("reports/counterfactual_report.json",), _counterfactual),
    ToolSpec("eval_ablation", "Ablation with CIs, permutation tests, selective prediction", ("eval/eval_cases.jsonl", "reports/counterfactual_report.json"), ("reports/ablation_report.json",), _ablation),
    ToolSpec("eval_attribution", "Counterfactual citation-faithfulness test", ("eval/eval_cases.jsonl", "patterns/pattern_aggregations.jsonl", "inference/inference_config.yaml", "inference/context_state_rules.jsonl"), ("reports/attribution_report.json",), _attribution),
    ToolSpec("conformal", "Conformal prediction sets with abstention", ("eval/eval_cases.jsonl", "patterns/pattern_aggregations.jsonl", "inference/inference_config.yaml", "inference/context_state_rules.jsonl"), ("reports/conformal_report.json",), _conformal),
    ToolSpec("build_skill", "Export the governed skill package", (
        "patterns/pattern_aggregations.jsonl", "inference/inference_config.yaml", "evidence/evidence_index.jsonl",
        "inference/context_state_rules.jsonl", "eval/eval_cases.jsonl",
    ), ("skills/{skill_id}/skill.yaml",), _skill, risk_tier="T2"),
    ToolSpec("build_audit", "Assemble the human-audit package", (
        "skills/{skill_id}/skill.yaml", "input_rows.jsonl", "genre_routes.jsonl",
        "patterns/pattern_aggregations.jsonl", "annotations/case_templates.jsonl",
    ), ("audit/audit_package.json",), _audit, risk_tier="T2"),
    ToolSpec("validate_run", "Full pipeline validation gate", (
        "audit/audit_package.json", "graphs/knowledge_graph.json", "inference/context_state_rules.jsonl",
        "eval/eval_cases.jsonl", "reports/counterfactual_report.json", "reports/ablation_report.json",
    ), ("reports/validation_summary.json",), _validate, risk_tier="T2"),
    ToolSpec("assess", "Protocol self-assessment (remaining gaps)", ("reports/validation_summary.json",), ("reports/protocol_assessment_report.json",), _assess),
    ToolSpec("model_card", "TRIPOD-LLM-style model card", ("reports/protocol_assessment_report.json",), ("reports/model_card.md",), _model_card),
    ToolSpec("promote", "Terminal human-audit decision (never autonomous)", ("audit/audit_package.json",), (), lambda state: (_ for _ in ()).throw(HumanApprovalRequired("promote requires a human expert decision via `canon promote`")), risk_tier="T3", needs_human=True),
]}
