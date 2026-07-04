"""Split conformal prediction for the ordinal inference engine.

Distribution-free, finite-sample marginal coverage (Vovk et al.;
Angelopoulos & Bates 2023): calibrate a nonconformity threshold q̂ on
labeled eval cases so that the prediction set contains a correct pattern
with probability ≥ 1 − α on exchangeable future cases. The nonconformity
score is the score margin between the top-ranked pattern and the true
pattern; abstention is explicit — an empty or uninformative set (all
candidates) is surfaced as `abstained`, never silently truncated.

Honesty notes baked into the report: the finite-sample guarantee is
vacuous when the calibration set is smaller than ceil(1/α) − 1 (q̂ becomes
infinite and every set is the full candidate list), and coverage measured
on the calibration cases themselves is in-sample, not a test-set claim.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from canon_tcm_hermes.inference.run_inference import run_inference
from canon_tcm_hermes.utils import atomic_write_json, read_jsonl, run_dir

FULL_RANKING_TOP_K = 1000


def _ranked_scores(features: list[str], context: dict[str, Any], run_id: str, output_dir: str | Path) -> list[dict[str, Any]]:
    payload = {"mode": "clinician_assist", "features": features, "context": context or {}, "top_k": FULL_RANKING_TOP_K}
    return run_inference(payload, run_id, output_dir).get("top_k", [])


def _nonconformity(ranked: list[dict[str, Any]], expected_patterns: list[str]) -> float | None:
    """Margin between the top score and the best correct pattern's score.

    None = no correct pattern was scored at all (infinite nonconformity).
    """
    if not ranked:
        return None
    by_name = {item.get("pattern"): float(item.get("score", 0.0)) for item in ranked}
    true_scores = [by_name[p] for p in expected_patterns if p in by_name]
    if not true_scores:
        return None
    return float(ranked[0].get("score", 0.0)) - max(true_scores)


def calibrate_conformal(run_id: str, output_dir: str | Path = "outputs", alpha: float = 0.1) -> dict[str, Any]:
    rd = run_dir(run_id, output_dir)
    eval_cases = read_jsonl(rd / "eval" / "eval_cases.jsonl")
    scores: list[float | None] = []
    for case in eval_cases:
        ranked = _ranked_scores(case.get("input_features", []), case.get("context", {}), run_id, output_dir)
        scores.append(_nonconformity(ranked, case.get("expected_patterns", [])))
    n = len(scores)
    rank_needed = math.ceil((n + 1) * (1 - alpha))
    if n == 0 or rank_needed > n or any(s is None for s in scores):
        qhat: float | None = None  # infinite threshold: guarantee is vacuous at this n/alpha
    else:
        qhat = sorted(float(s) for s in scores if s is not None)[rank_needed - 1]
    calibration = {
        "alpha": alpha,
        "coverage_target": 1 - alpha,
        "n_calibration": n,
        "nonconformity": "score_margin_top_minus_true",
        "qhat": qhat,
        "vacuous": qhat is None,
        "min_n_for_nonvacuous": math.ceil(1 / alpha) - 1 if alpha > 0 else None,
        "note": "Marginal coverage holds under exchangeability of calibration and future cases. qhat=null means the threshold is infinite: every prediction set is the full candidate list and the engine abstains.",
    }
    atomic_write_json(rd / "inference" / "conformal_calibration.json", calibration)
    return calibration


def conformal_predict(payload: dict[str, Any], run_id: str, output_dir: str | Path = "outputs", calibration: dict[str, Any] | None = None) -> dict[str, Any]:
    rd = run_dir(run_id, output_dir)
    if calibration is None:
        path = rd / "inference" / "conformal_calibration.json"
        if not path.exists():
            raise FileNotFoundError(f"conformal calibration not found: {path}; run `canon conformal` first")
        calibration = json.loads(path.read_text(encoding="utf-8"))
    ranked = _ranked_scores(payload.get("features", []), payload.get("context", {}), run_id, output_dir)
    qhat = calibration.get("qhat")
    if not ranked:
        selected: list[dict[str, Any]] = []
    elif qhat is None:
        selected = ranked
    else:
        top_score = float(ranked[0].get("score", 0.0))
        selected = [item for item in ranked if top_score - float(item.get("score", 0.0)) <= qhat + 1e-12]
    uninformative = bool(ranked) and len(selected) == len(ranked) and len(ranked) > 1
    abstained = (not selected) or uninformative or qhat is None
    return {
        "prediction_set": [{"pattern": item.get("pattern"), "score": item.get("score"), "support_level": item.get("support_level")} for item in selected],
        "set_size": len(selected),
        "coverage_target": calibration.get("coverage_target"),
        "abstained": abstained,
        "abstain_reason": ("no_scored_candidates" if not selected else "uninformative_full_set" if uninformative else "vacuous_calibration" if qhat is None else None) if abstained else None,
        "recommendation": "defer_to_human_expert" if abstained else "present_set_with_evidence",
    }


def run_conformal_report(run_id: str, output_dir: str | Path = "outputs", alpha: float = 0.1) -> dict[str, Any]:
    rd = run_dir(run_id, output_dir)
    calibration = calibrate_conformal(run_id, output_dir, alpha)
    eval_cases = read_jsonl(rd / "eval" / "eval_cases.jsonl")
    covered = 0
    set_sizes = []
    abstentions = 0
    cases = []
    for case in eval_cases:
        prediction = conformal_predict({"features": case.get("input_features", []), "context": case.get("context", {})}, run_id, output_dir, calibration)
        expected = set(case.get("expected_patterns", []))
        hit = bool(expected & {item["pattern"] for item in prediction["prediction_set"]})
        covered += int(hit)
        set_sizes.append(prediction["set_size"])
        abstentions += int(prediction["abstained"])
        cases.append({"eval_case_id": case.get("eval_case_id"), "set": [item["pattern"] for item in prediction["prediction_set"]], "covered": hit, "abstained": prediction["abstained"]})
    n = len(eval_cases)
    report = {
        "calibration": calibration,
        "empirical_coverage_in_sample": (covered / n) if n else None,
        "average_set_size": (sum(set_sizes) / n) if n else None,
        "abstention_rate": (abstentions / n) if n else None,
        "cases": cases,
        "caveat": "Coverage here is measured on the calibration cases (in-sample). For a test-set claim, calibrate and evaluate on disjoint case splits.",
    }
    atomic_write_json(rd / "reports" / "conformal_report.json", report)
    return report
