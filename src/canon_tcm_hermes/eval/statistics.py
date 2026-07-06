"""Publication-grade statistics for evaluation reports.

Top-venue reporting standards (e.g. TRIPOD-LLM, HELM) require uncertainty
around point metrics and significance for system comparisons. Everything
here is deterministic (fixed seeds) so CI runs are reproducible:

- percentile bootstrap confidence intervals over per-case scores;
- paired sign-flip permutation tests for system-vs-system deltas.

Small evaluation sets yield wide intervals and inconclusive p-values —
that is reported honestly, never hidden.
"""
from __future__ import annotations

import random
from typing import Any, Sequence

DEFAULT_SEED = 13
DEFAULT_BOOTSTRAP = 2000
DEFAULT_PERMUTATIONS = 5000


def mean(values: Sequence[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def bootstrap_ci(values: Sequence[float], n_boot: int = DEFAULT_BOOTSTRAP, alpha: float = 0.05, seed: int = DEFAULT_SEED) -> dict[str, float]:
    """Percentile bootstrap CI for the mean of per-case scores."""
    if not values:
        return {"mean": 0.0, "lo": 0.0, "hi": 0.0}
    rng = random.Random(seed)
    n = len(values)
    means = sorted(mean([values[rng.randrange(n)] for _ in range(n)]) for _ in range(n_boot))
    lo_index = int((alpha / 2) * n_boot)
    hi_index = min(n_boot - 1, int((1 - alpha / 2) * n_boot))
    return {"mean": round(mean(values), 6), "lo": round(means[lo_index], 6), "hi": round(means[hi_index], 6)}


def paired_permutation_test(a: Sequence[float], b: Sequence[float], n_perm: int = DEFAULT_PERMUTATIONS, seed: int = DEFAULT_SEED) -> dict[str, Any]:
    """Two-sided paired sign-flip permutation test on per-case differences."""
    if len(a) != len(b):
        raise ValueError("paired test requires equal-length per-case score vectors")
    diffs = [x - y for x, y in zip(a, b)]
    observed = abs(mean(diffs))
    if not diffs or all(d == 0 for d in diffs):
        return {"delta": round(mean(diffs), 6) if diffs else 0.0, "p_value": 1.0, "n": len(diffs)}
    rng = random.Random(seed)
    extreme = 0
    for _ in range(n_perm):
        flipped = mean([d if rng.random() < 0.5 else -d for d in diffs])
        if abs(flipped) >= observed - 1e-12:
            extreme += 1
    # add-one smoothing keeps p > 0 (Phipson & Smyth correction)
    p_value = (extreme + 1) / (n_perm + 1)
    return {"delta": round(mean(diffs), 6), "p_value": round(p_value, 6), "n": len(diffs)}


def holm_bonferroni(p_values: dict[str, float], alpha: float = 0.05) -> dict[str, dict[str, Any]]:
    """Holm–Bonferroni step-down correction for multiple comparisons.

    Guards against over-claiming when one system is compared against many
    (the paired-bootstrap protocol standard for multi-system benchmarks).
    """
    ordered = sorted(p_values.items(), key=lambda kv: kv[1])
    m = len(ordered)
    results: dict[str, dict[str, Any]] = {}
    rejected_so_far = True
    for rank, (name, p) in enumerate(ordered):
        threshold = alpha / (m - rank)
        adjusted = min(1.0, max(p * (m - rank), max((r["p_adjusted"] for r in results.values()), default=0.0)))
        rejected = rejected_so_far and p <= threshold
        rejected_so_far = rejected_so_far and rejected
        results[name] = {"p_raw": p, "p_adjusted": round(adjusted, 6), "significant": rejected}
    return results


def risk_coverage_curve(correct: Sequence[float], confidence: Sequence[float]) -> dict[str, Any]:
    """Selective-prediction analysis: accuracy when answering only the
    top-confidence fraction of cases, plus AURC (area under the
    risk-coverage curve; lower is better)."""
    if len(correct) != len(confidence):
        raise ValueError("correct and confidence vectors must align")
    if not correct:
        return {"points": [], "aurc": None}
    order = sorted(range(len(correct)), key=lambda i: confidence[i], reverse=True)
    points = []
    running_errors = 0.0
    risks = []
    for rank, index in enumerate(order, start=1):
        running_errors += 1.0 - correct[index]
        risk = running_errors / rank
        risks.append(risk)
        points.append({"coverage": round(rank / len(order), 6), "selective_risk": round(risk, 6)})
    return {"points": points, "aurc": round(mean(risks), 6)}
