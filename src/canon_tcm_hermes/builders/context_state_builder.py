from __future__ import annotations

from pathlib import Path
from typing import Any

from canon_tcm_hermes.utils import read_jsonl, run_dir, write_jsonl

CONTEXT_TRIGGERS = ["发汗后", "發汗後", "下后", "下後", "吐后", "吐後", "汗出", "无大热", "無大熱"]


def build_context_state(run_id: str, output_dir: str | Path = "outputs") -> list[dict[str, Any]]:
    rd = run_dir(run_id, output_dir)
    rules: list[dict[str, Any]] = []
    for clause in read_jsonl(rd / "annotations" / "clause_templates.jsonl"):
        quote = (clause.get("evidence") or {}).get("evidence_quote", "")
        triggers = _triggers(quote)
        if triggers:
            rules.append({
                "context_rule_id": "CTX_" + clause["template_id"],
                "if": triggers,
                "then": (clause.get("conclusion") or {}).get("raw", ""),
                "evidence_ids": [clause["segment_id"]],
                "source_genre": "canonical_clause",
                "status": "auto_generated",
                "risk_tier": "T2",
            })
    for claim in read_jsonl(rd / "annotations" / "treatise_claims.jsonl"):
        claim_text = " ".join(claim.get("claims", []))
        triggers = _triggers(claim_text)
        if triggers:
            rules.append({
                "context_rule_id": "CTX_" + claim["claim_id"],
                "if": triggers,
                "then": claim_text,
                "evidence_ids": [claim["segment_id"]],
                "source_genre": "treatise",
                "status": "auto_generated",
                "risk_tier": "T1",
            })
    write_jsonl(rd / "inference" / "context_state_rules.jsonl", rules)
    return rules


def _triggers(text: str) -> list[str]:
    normalized = text.replace("發", "发").replace("後", "后").replace("無", "无")
    found = []
    for trigger in CONTEXT_TRIGGERS:
        t = trigger.replace("發", "发").replace("後", "后").replace("無", "无")
        if t in normalized and t not in found:
            found.append(t)
    return found
