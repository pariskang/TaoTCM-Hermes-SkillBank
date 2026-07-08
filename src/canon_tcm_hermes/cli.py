from __future__ import annotations

import argparse
import json

from canon_tcm_hermes.annotators.base import annotate_run
from canon_tcm_hermes.builders.audit_package_builder import build_audit_package
from canon_tcm_hermes.builders.context_state_builder import build_context_state
from canon_tcm_hermes.builders.hermes_skill_builder import build_skill
from canon_tcm_hermes.builders.inference_config_builder import build_inference_config
from canon_tcm_hermes.builders.knowledge_graph_builder import build_knowledge_graph
from canon_tcm_hermes.builders.pattern_aggregator import build_patterns
from canon_tcm_hermes.eval.build_eval_cases import build_eval_cases
from canon_tcm_hermes.eval.run_ablation import run_ablation
from canon_tcm_hermes.eval.run_attribution import run_attribution
from canon_tcm_hermes.eval.run_counterfactual_tests import run_counterfactual
from canon_tcm_hermes.governance.model_card import build_model_card
from canon_tcm_hermes.governance.promotion import promote_version
from canon_tcm_hermes.governance.run_diff import build_run_diff
from canon_tcm_hermes.inference.conformal import run_conformal_report
from canon_tcm_hermes.io.excel_loader import load_excel
from canon_tcm_hermes.router.genre_router import route_rows, route_run
from canon_tcm_hermes.utils import ensure_dir, run_dir
from canon_tcm_hermes.validators.citation_validator import build_and_validate_evidence
from canon_tcm_hermes.validators.pipeline_validator import run_validation
from canon_tcm_hermes.validators.protocol_assessor import assess_protocol

DEFAULT_SKILL_ID = "shanghan_six_formula_cluster"

COMMANDS = [
    "init", "make-demo", "route", "annotate", "validate", "build-graph", "build-patterns",
    "compile-inference", "build-skill", "build-audit", "eval-counterfactual", "build-eval",
    "eval-ablation", "eval-attribution", "conformal", "calibrate-router", "model-card",
    "export", "export-codex", "assess", "promote", "rollback", "log-override", "diff",
    "agent", "agent-status", "all", "build",
]


def _load_dotenv() -> None:
    try:
        from dotenv import find_dotenv, load_dotenv
    except ImportError:
        return
    # Search for .env from the working directory upward (not from the
    # installed package location); override=False (the default) keeps
    # variables already exported in the shell winning over .env values.
    load_dotenv(find_dotenv(usecwd=True))


def main(argv: list[str] | None = None) -> None:
    _load_dotenv()
    parser = argparse.ArgumentParser(prog="canon")
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name in COMMANDS:
        p = sub.add_parser(name)
        p.add_argument("--input")
        p.add_argument("--run-id", default="demo001")
        p.add_argument("--skill-id", default=DEFAULT_SKILL_ID)
        p.add_argument("--output-dir", default="outputs")
        llm = p.add_mutually_exclusive_group()
        llm.add_argument("--llm", dest="use_llm", action="store_true", default=None, help="force LiteLLM annotation (requires LITELLM_MODEL env)")
        llm.add_argument("--no-llm", dest="use_llm", action="store_false", help="force deterministic heuristic annotation")
        if name == "promote":
            p.add_argument("--decision", required=True, choices=["promote", "revise", "reject", "disputed"])
            p.add_argument("--expert-id", required=True)
            p.add_argument("--approved-version", default="1.0.0")
            p.add_argument("--reason", default="")
        if name == "diff":
            p.add_argument("--baseline", required=True, help="baseline run id to diff against (e.g. the last promoted run)")
        if name == "export":
            p.add_argument("--targets", default="", help="comma-separated export targets (claude,codex,openclaw,lobechat); default: configs/export_targets.yaml")
        if name in {"eval-ablation", "all", "build"}:
            p.add_argument("--llm-baselines", dest="llm_baselines", action="store_true", default=None, help="run B0-B2 as real LLM/RAG baselines (requires LITELLM_MODEL; default: TAOTCM_LLM_BASELINES env)")
        if name in {"conformal", "all", "build"}:
            p.add_argument("--alpha", type=float, default=0.1, help="conformal miscoverage level (coverage target = 1 - alpha)")
        if name == "calibrate-router":
            p.add_argument("--gold", required=True, help="micro-gold JSONL: {content, book, chapter, segments:[{span,genre}]} per line")
        if name == "agent":
            p.add_argument("--goal", default="skill_package", choices=["annotate_corpus", "evidence_ready", "eval_ready", "skill_package"], help="target state the agent plans toward")
        if name == "rollback":
            p.add_argument("--expert-id", required=True)
            p.add_argument("--reason", default="")
        if name == "log-override":
            p.add_argument("--physician-id", required=True)
            p.add_argument("--reason", required=True)
            p.add_argument("--reason-category", default="clinical_judgment", choices=["clinical_judgment", "missing_information", "patient_preference", "safety_concern", "other"])
            p.add_argument("--payload", default="{}", help="JSON payload of the overridden inference input/output")
    args = parser.parse_args(argv)

    if args.cmd == "init":
        for p in ["data/raw", "outputs/runs", "configs", "schemas"]:
            ensure_dir(p)
        return
    if args.cmd == "make-demo":
        from canon_tcm_hermes.demo_data import make_demo

        print(make_demo(args.input or "data/demo/shanghan_six_formula_demo.xlsx"))
        return
    if args.cmd == "route":
        if args.input:
            rows, _ = load_excel(args.input, args.run_id, args.output_dir)
            route_rows(rows, args.run_id, args.output_dir, use_llm=args.use_llm)
        else:
            route_run(args.run_id, args.output_dir, use_llm=args.use_llm)
        return
    if args.cmd == "annotate":
        annotate_run(args.run_id, args.output_dir, use_llm=args.use_llm)
        return
    if args.cmd == "validate":
        report = run_validation(args.run_id, args.output_dir, args.skill_id)
        print("validation passed" if report["passed"] else "validation FAILED — see reports/validation_summary.json")
        return
    if args.cmd == "build-graph":
        build_knowledge_graph(args.run_id, args.output_dir)
        return
    if args.cmd == "build-patterns":
        build_patterns(args.run_id, args.output_dir)
        return
    if args.cmd == "compile-inference":
        build_context_state(args.run_id, args.output_dir)
        build_inference_config(args.run_id, args.skill_id, args.output_dir)
        return
    if args.cmd == "build-skill":
        build_skill(args.run_id, args.skill_id, args.output_dir)
        return
    if args.cmd in {"export", "export-codex"}:
        from canon_tcm_hermes.exporters import export_skill_targets

        package = run_dir(args.run_id, args.output_dir) / "skills" / args.skill_id / "skill.yaml"
        if not package.exists():
            build_skill(args.run_id, args.skill_id, args.output_dir)
        targets = ["codex"] if args.cmd == "export-codex" else [t.strip() for t in args.targets.split(",") if t.strip()] or None
        results = export_skill_targets(args.run_id, args.skill_id, targets, args.output_dir)
        print(json.dumps(results, ensure_ascii=False, indent=2))
        return
    if args.cmd == "build-audit":
        build_audit_package(args.run_id, args.skill_id, args.output_dir)
        return
    if args.cmd == "eval-counterfactual":
        run_counterfactual(args.run_id, args.output_dir)
        return
    if args.cmd == "build-eval":
        build_eval_cases(args.run_id, args.output_dir)
        return
    if args.cmd == "eval-ablation":
        run_ablation(args.run_id, args.output_dir, llm_baselines=args.llm_baselines)
        return
    if args.cmd == "eval-attribution":
        report = run_attribution(args.run_id, args.output_dir)
        print(json.dumps({"feature_necessity_rate": report["feature_necessity_rate"], "evidence_grounding_rate": report["evidence_grounding_rate"]}, ensure_ascii=False))
        return
    if args.cmd == "conformal":
        report = run_conformal_report(args.run_id, args.output_dir, alpha=args.alpha)
        print(json.dumps({k: report[k] for k in ["empirical_coverage_in_sample", "average_set_size", "abstention_rate"]}, ensure_ascii=False))
        return
    if args.cmd == "calibrate-router":
        from canon_tcm_hermes.validators.router_calibration import calibrate_router

        report = calibrate_router(args.gold, run_id=args.run_id, output_dir=args.output_dir, use_llm=args.use_llm)
        print(json.dumps({"primary_genre": report["primary_genre"], "spans": report["spans"], "calibration_gate": report["calibration_gate"]}, ensure_ascii=False, indent=2))
        return
    if args.cmd == "model-card":
        print(build_model_card(args.run_id, args.skill_id, args.output_dir))
        return
    if args.cmd == "agent":
        from canon_tcm_hermes.agent import run_agent

        state = run_agent(args.run_id, goal=args.goal, input_path=args.input or "", skill_id=args.skill_id, output_dir=args.output_dir)
        print(json.dumps({"status": state.status, "completed_steps": state.completed_steps, "warnings": state.warnings, "human_checkpoint": state.human_checkpoint, "failure_reason": state.failure_reason}, ensure_ascii=False, indent=2))
        return
    if args.cmd == "agent-status":
        from canon_tcm_hermes.agent import agent_status

        print(json.dumps(agent_status(args.run_id, args.output_dir), ensure_ascii=False, indent=2))
        return
    if args.cmd == "rollback":
        from canon_tcm_hermes.governance.rollback import rollback_version

        print(json.dumps(rollback_version(args.run_id, args.expert_id, args.reason, args.skill_id, args.output_dir), ensure_ascii=False, indent=2))
        return
    if args.cmd == "log-override":
        from canon_tcm_hermes.governance.override_logger import log_override

        print(json.dumps(log_override(args.run_id, args.physician_id, args.reason, json.loads(args.payload), reason_category=args.reason_category, output_dir=args.output_dir), ensure_ascii=False, indent=2))
        return
    if args.cmd == "assess":
        assess_protocol(args.run_id, args.output_dir)
        return
    if args.cmd == "diff":
        report = build_run_diff(args.run_id, args.baseline, args.output_dir, skill_id=args.skill_id)
        print(json.dumps({"summary": report["summary"], "audit_focus": report["audit_focus"]}, ensure_ascii=False, indent=2))
        return
    if args.cmd == "promote":
        record = promote_version(
            args.run_id, args.expert_id, args.decision, args.output_dir,
            approved_version=args.approved_version, skill_id=args.skill_id, reason=args.reason,
        )
        print(record)
        return
    if args.cmd in {"all", "build"}:
        if not args.input:
            raise SystemExit("canon all/build requires --input")
        rows, _ = load_excel(args.input, args.run_id, args.output_dir)
        route_rows(rows, args.run_id, args.output_dir, use_llm=args.use_llm)
        annotate_run(args.run_id, args.output_dir, use_llm=args.use_llm)
        build_and_validate_evidence(args.run_id, args.output_dir)
        build_knowledge_graph(args.run_id, args.output_dir)
        build_patterns(args.run_id, args.output_dir)
        build_context_state(args.run_id, args.output_dir)
        build_inference_config(args.run_id, args.skill_id, args.output_dir)
        build_eval_cases(args.run_id, args.output_dir)
        run_counterfactual(args.run_id, args.output_dir)
        run_ablation(args.run_id, args.output_dir, llm_baselines=args.llm_baselines)
        run_attribution(args.run_id, args.output_dir)
        run_conformal_report(args.run_id, args.output_dir, alpha=args.alpha)
        build_skill(args.run_id, args.skill_id, args.output_dir)
        build_audit_package(args.run_id, args.skill_id, args.output_dir)
        run_validation(args.run_id, args.output_dir, args.skill_id)
        assess_protocol(args.run_id, args.output_dir)
        build_model_card(args.run_id, args.skill_id, args.output_dir)
        print(run_dir(args.run_id, args.output_dir))


if __name__ == "__main__":
    main()
