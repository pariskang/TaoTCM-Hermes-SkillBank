from __future__ import annotations

from typing import Any

from canon_tcm_hermes.inference.feature_mapper import normalize_features


def split_alerts(features: set[str], contraindications: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Partition matched contraindications into hard stops and soft alerts.

    A contraindication matches when every feature of its condition set is
    present in the normalized feature set. `action == "hard_stop"` (risk
    tier T3) removes the pattern from recommendation entirely; any other
    matched rule stays a soft safety alert on the ranked result.
    """
    hard: list[dict[str, Any]] = []
    soft: list[dict[str, Any]] = []
    for contra in contraindications:
        if not isinstance(contra, dict):
            continue
        condition = set(normalize_features(contra.get("condition", [])))
        if not condition or not condition <= features:
            continue
        (hard if contra.get("action") == "hard_stop" else soft).append(contra)
    return hard, soft


def hard_stops(features: set[str], contraindications: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return split_alerts(features, contraindications)[0]
