"""Counterfactual attribution faithfulness for the symbolic engine.

Citation correctness (the quote exists and hashes match) is not the same
as citation faithfulness (the cited material actually drives the
conclusion). Because the inference engine is symbolic, faithfulness is
directly testable by intervention:

- feature necessity: for the top-ranked pattern of each eval case, remove
  each supporting feature in turn and check whether the ranking signature
  (top pattern or its score) actually changes — a supporting feature that
  changes nothing is decorative, not load-bearing;
- evidence grounding: every evidence card attached to the top pattern
  must contain at least one of its supporting features in the quoted
  passage, otherwise the citation decorates rather than grounds.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from canon_tcm_hermes.inference.run_inference import run_inference
from canon_tcm_hermes.utils import atomic_write_json, read_jsonl, run_dir


def run_attribution(run_id: str, output_dir: str | Path = "outputs") -> dict[str, Any]:
    rd = run_dir(run_id, output_dir)
    eval_cases = read_jsonl(rd / "eval" / "eval_cases.jsonl")
    case_reports = []
    necessity_rates = []
    grounding_rates = []
    for case in eval_cases:
        features = [str(f) for f in case.get("input_features", [])]
        base = run_inference({"mode": "clinician_assist", "features": features, "context": case.get("context", {})}, run_id, output_dir)
        ranked = base.get("top_k", [])
        if not ranked:
            case_reports.append({"eval_case_id": case.get("eval_case_id"), "skipped": "no ranked pattern"})
            continue
        top = ranked[0]
        supporting = [str(f) for f in top.get("supporting_features", [])]
        necessary = []
        for feature in supporting:
            ablated_features = [f for f in features if f != feature]
            ablated = run_inference({"mode": "clinician_assist", "features": ablated_features, "context": case.get("context", {})}, run_id, output_dir)
            ablated_ranked = ablated.get("top_k", [])
            ablated_top = ablated_ranked[0] if ablated_ranked else None
            score_by_name = {item.get("pattern"): item.get("score") for item in ablated_ranked}
            changed = (
                ablated_top is None
                or ablated_top.get("pattern") != top.get("pattern")
                or score_by_name.get(top.get("pattern")) != top.get("score")
            )
            necessary.append({"feature": feature, "necessary": changed})
        cards = top.get("evidence_cards", [])
        grounded_cards = [card for card in cards if any(f in str(card.get("quote", "")) for f in supporting)]
        necessity_rate = (sum(1 for item in necessary if item["necessary"]) / len(necessary)) if necessary else None
        grounding_rate = (len(grounded_cards) / len(cards)) if cards else None
        if necessity_rate is not None:
            necessity_rates.append(necessity_rate)
        if grounding_rate is not None:
            grounding_rates.append(grounding_rate)
        case_reports.append({
            "eval_case_id": case.get("eval_case_id"),
            "top_pattern": top.get("pattern"),
            "feature_necessity": necessary,
            "feature_necessity_rate": necessity_rate,
            "evidence_cards": len(cards),
            "evidence_grounding_rate": grounding_rate,
        })
    report = {
        "n_cases": len(eval_cases),
        "feature_necessity_rate": (sum(necessity_rates) / len(necessity_rates)) if necessity_rates else None,
        "evidence_grounding_rate": (sum(grounding_rates) / len(grounding_rates)) if grounding_rates else None,
        "cases": case_reports,
        "note": "Faithfulness by intervention: supporting features must be causally load-bearing (removal changes the ranking signature) and cited quotes must contain at least one supporting feature. Correct-but-decorative citations fail here even when hash/span verification passes.",
    }
    atomic_write_json(rd / "reports" / "attribution_report.json", report)
    return report
