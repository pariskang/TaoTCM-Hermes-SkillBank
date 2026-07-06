"""Micro-gold calibration of the genre router.

The protocol assessor lists router calibration against human-adjudicated
micro-gold samples as the first blocking gap before stable grade. This
module measures router output against a gold JSONL file, reporting the
metrics annotation-quality guidelines require for span tasks:

- row-level primary-genre agreement: observed agreement Po AND Cohen's κ
  (both, to expose the kappa paradox under label imbalance);
- span-level exact F1 ((start, end, genre) must match) and relaxed F1
  (same genre, span IoU ≥ 0.5) — boundary-tolerant per PICO-span practice;
- per-genre confusion pairs for error-case analysis.

Gold file format (one JSON object per line):
  {"content": "...", "book": "", "chapter": "", "segments": [{"span": [0, 12], "genre": "canonical_clause"}, ...]}
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from canon_tcm_hermes.router.genre_router import segment_row
from canon_tcm_hermes.utils import atomic_write_json, run_dir, sha1_text

RELAXED_IOU = 0.5


def calibrate_router(gold_path: str | Path, run_id: str | None = None, output_dir: str | Path = "outputs", use_llm: bool | None = None) -> dict[str, Any]:
    gold_rows = [json.loads(line) for line in Path(gold_path).read_text(encoding="utf-8").splitlines() if line.strip()]
    if not gold_rows:
        raise ValueError(f"gold file is empty: {gold_path}")
    pairs: list[tuple[str, str]] = []  # (gold primary genre, predicted primary genre)
    exact_tp = relaxed_tp = pred_total = gold_total = 0
    confusion: Counter[tuple[str, str]] = Counter()
    for index, gold in enumerate(gold_rows, start=1):
        row = {
            "row_id": index,
            "source_id": f"GOLD::ROW{index:06d}",
            "content": gold["content"],
            "book": gold.get("book", ""),
            "volume": gold.get("volume", ""),
            "chapter": gold.get("chapter", ""),
            "version": "",
            "content_hash": sha1_text(gold["content"]),
        }
        predicted = segment_row(row, use_llm=use_llm)["genre_segmentation"]
        pred_spans = [(tuple(seg["span"]), seg["genre"]) for seg in predicted]
        gold_spans = [(tuple(seg["span"]), seg["genre"]) for seg in gold.get("segments", [])]
        pred_total += len(pred_spans)
        gold_total += len(gold_spans)
        exact_tp += len(set(pred_spans) & set(gold_spans))
        relaxed_tp += _relaxed_matches(pred_spans, gold_spans)
        gold_primary = _primary_genre(gold_spans)
        pred_primary = _primary_genre(pred_spans)
        pairs.append((gold_primary, pred_primary))
        if gold_primary != pred_primary:
            confusion[(gold_primary, pred_primary)] += 1
    po, kappa = _cohen_kappa(pairs)
    report = {
        "n_rows": len(gold_rows),
        "primary_genre": {
            "observed_agreement_po": round(po, 6),
            "cohen_kappa": round(kappa, 6) if kappa is not None else None,
            "note": "Po and kappa reported together: under label imbalance kappa alone is distorted (kappa paradox).",
        },
        "spans": {
            "exact_f1": _f1(exact_tp, pred_total, gold_total),
            "relaxed_f1": _f1(relaxed_tp, pred_total, gold_total),
            "relaxed_criterion": f"same genre and span IoU >= {RELAXED_IOU}",
            "predicted_spans": pred_total,
            "gold_spans": gold_total,
        },
        "confusion_pairs": [{"gold": g, "predicted": p, "count": c} for (g, p), c in confusion.most_common()],
        "calibration_gate": {
            "target_kappa": 0.8,
            "passed": kappa is not None and kappa >= 0.8,
            "note": "kappa >= 0.8 is the conventional high-stakes threshold; below it the router needs boundary adjudication before stable-grade claims.",
        },
    }
    if run_id:
        atomic_write_json(run_dir(run_id, output_dir) / "reports" / "router_calibration_report.json", report)
    return report


def _primary_genre(spans: list[tuple[tuple[int, int], str]]) -> str:
    if not spans:
        return "non_medical"
    return max(spans, key=lambda item: item[0][1] - item[0][0])[1]


def _relaxed_matches(pred: list[tuple[tuple[int, int], str]], gold: list[tuple[tuple[int, int], str]]) -> int:
    matched_gold: set[int] = set()
    matches = 0
    for span, genre in pred:
        for gold_index, (gold_span, gold_genre) in enumerate(gold):
            if gold_index in matched_gold or genre != gold_genre:
                continue
            if _iou(span, gold_span) >= RELAXED_IOU:
                matched_gold.add(gold_index)
                matches += 1
                break
    return matches


def _iou(a: tuple[int, int], b: tuple[int, int]) -> float:
    intersection = max(0, min(a[1], b[1]) - max(a[0], b[0]))
    union = max(a[1], b[1]) - min(a[0], b[0])
    return intersection / union if union else 0.0


def _f1(tp: int, pred_total: int, gold_total: int) -> float | None:
    if not pred_total or not gold_total:
        return None
    precision = tp / pred_total
    recall = tp / gold_total
    return round(2 * precision * recall / (precision + recall), 6) if (precision + recall) else 0.0


def _cohen_kappa(pairs: list[tuple[str, str]]) -> tuple[float, float | None]:
    n = len(pairs)
    po = sum(1 for gold, pred in pairs if gold == pred) / n
    labels = {label for pair in pairs for label in pair}
    gold_marginals = Counter(gold for gold, _ in pairs)
    pred_marginals = Counter(pred for _, pred in pairs)
    pe = sum((gold_marginals[label] / n) * (pred_marginals[label] / n) for label in labels)
    if pe >= 1.0:
        return po, None  # degenerate single-label case: kappa undefined
    return po, (po - pe) / (1 - pe)
