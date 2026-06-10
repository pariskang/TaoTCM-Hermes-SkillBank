from __future__ import annotations

from typing import Any


def assign_risk_tier(item: dict[str, Any]) -> str:
    text = str(item)
    if "hard_stop" in text or "不可" in text or "contraindication" in text:
        return "T3"
    if "warning" in text or "needs_audit" in text:
        return "T2"
    if "teaching" in text:
        return "T1"
    return "T0"
