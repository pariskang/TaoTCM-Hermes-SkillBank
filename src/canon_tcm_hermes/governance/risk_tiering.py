from __future__ import annotations

from typing import Any

_TIER_ORDER = ["T0", "T1", "T2", "T3"]


def assign_risk_tier(item: dict[str, Any]) -> str:
    """Assign the audit risk tier from the item's structure.

    Tiers follow configs/risk_tiers.yaml: T3 hard-stop material, T2 content
    that needs audit or carries soft safety semantics, T1 teaching-only
    notes, T0 passive info. An explicit `risk_tier` on the item is honored
    but never below what its structure demands (max of both).
    """
    own = item.get("risk_tier")
    own_tier = own if own in _TIER_ORDER else "T0"
    structural = _structural_tier(item)
    return max(own_tier, structural, key=_TIER_ORDER.index)


def _structural_tier(item: dict[str, Any]) -> str:
    contraindications = [c for c in (item.get("contraindications") or []) if isinstance(c, dict)]
    if any(c.get("action") == "hard_stop" or c.get("risk_tier") == "T3" for c in contraindications):
        return "T3"
    exclusions = [e for e in (item.get("exclusion_features") or []) if isinstance(e, dict)]
    if contraindications or any(e.get("strength") == "hard" for e in exclusions):
        return "T2"
    decisions = [d for d in (item.get("aggregation_decisions") or []) if isinstance(d, dict)]
    if any(d.get("needs_audit") for d in decisions):
        return "T2"
    if item.get("usage") == "teaching" or item.get("genre") == "mnemonic_misc":
        return "T1"
    return "T0"
