from __future__ import annotations

import argparse
from pathlib import Path

from canon_tcm_hermes.annotators.base import annotate_run
from canon_tcm_hermes.builders.audit_package_builder import build_audit_package
from canon_tcm_hermes.builders.context_state_builder import build_context_state
from canon_tcm_hermes.builders.hermes_skill_builder import build_skill
from canon_tcm_hermes.builders.inference_config_builder import build_inference_config
from canon_tcm_hermes.builders.knowledge_graph_builder import build_knowledge_graph
from canon_tcm_hermes.builders.pattern_aggregator import build_patterns
from canon_tcm_hermes.eval.build_eval_cases import build_eval_cases
from canon_tcm_hermes.eval.run_ablation import run_ablation
from canon_tcm_hermes.eval.run_counterfactual_tests import run_counterfactual
from canon_tcm_hermes.io.excel_loader import load_excel
from canon_tcm_hermes.router.genre_router import route_rows, route_run
from canon_tcm_hermes.utils import ensure_dir, run_dir
from canon_tcm_hermes.validators.citation_validator import build_and_validate_evidence
from canon_tcm_hermes.validators.pipeline_validator import run_validation
from canon_tcm_hermes.validators.protocol_assessor import assess_protocol

DEFAULT_SKILL_ID = "shanghan_six_formula_cluster"

def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="canon")
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name in ["init", "route", "annotate", "validate", "build-graph", "build-patterns", "compile-inference", "build-skill", "build-audit", "eval-counterfactual", "build-eval", "eval-ablation", "export-codex", "assess", "all", "build"]:
        p = sub.add_parser(name)
        p.add_argument("--input")
        p.add_argument("--run-id", default="demo001")
        p.add_argument("--skill-id", default=DEFAULT_SKILL_ID)
        p.add_argument("--output-dir", default="outputs")
    args = parser.parse_args(argv)
    if args.cmd == "init":
        for p in ["data/raw","outputs/runs","configs","schemas"]: ensure_dir(p)
        return
    if args.cmd == "route":
        if args.input:
            rows, _ = load_excel(args.input, args.run_id, args.output_dir); route_rows(rows, args.run_id, args.output_dir)
        else:
            route_run(args.run_id, args.output_dir)
        return
    if args.cmd == "annotate": annotate_run(args.run_id, args.output_dir); return
    if args.cmd == "validate": run_validation(args.run_id, args.output_dir, args.skill_id); return
    if args.cmd == "build-graph": build_knowledge_graph(args.run_id, args.output_dir); return
    if args.cmd == "build-patterns": build_patterns(args.run_id, args.output_dir); return
    if args.cmd == "compile-inference": build_context_state(args.run_id, args.output_dir); build_inference_config(args.run_id, args.skill_id, args.output_dir); return
    if args.cmd in {"build-skill", "export-codex"}: build_skill(args.run_id, args.skill_id, args.output_dir); return
    if args.cmd == "build-audit": build_audit_package(args.run_id, args.skill_id, args.output_dir); return
    if args.cmd == "eval-counterfactual": run_counterfactual(args.run_id, args.output_dir); return
    if args.cmd == "build-eval": build_eval_cases(args.run_id, args.output_dir); return
    if args.cmd == "eval-ablation": run_ablation(args.run_id, args.output_dir); return
    if args.cmd == "assess": assess_protocol(args.run_id, args.output_dir); return
    if args.cmd in {"all", "build"}:
        if not args.input:
            raise SystemExit("canon all/build requires --input")
        rows, _ = load_excel(args.input, args.run_id, args.output_dir)
        route_rows(rows, args.run_id, args.output_dir)
        annotate_run(args.run_id, args.output_dir)
        build_and_validate_evidence(args.run_id, args.output_dir)
        build_knowledge_graph(args.run_id, args.output_dir)
        build_patterns(args.run_id, args.output_dir)
        build_context_state(args.run_id, args.output_dir)
        build_inference_config(args.run_id, args.skill_id, args.output_dir)
        build_eval_cases(args.run_id, args.output_dir)
        run_counterfactual(args.run_id, args.output_dir)
        run_ablation(args.run_id, args.output_dir)
        build_skill(args.run_id, args.skill_id, args.output_dir)
        build_audit_package(args.run_id, args.skill_id, args.output_dir)
        run_validation(args.run_id, args.output_dir, args.skill_id)
        assess_protocol(args.run_id, args.output_dir)
        print(run_dir(args.run_id, args.output_dir))

if __name__ == "__main__":
    main()
