from __future__ import annotations
from pathlib import Path
from typing import Any
from canon_tcm_hermes.annotators.base import ANNOTATION_FILES
from canon_tcm_hermes.utils import atomic_write_json, read_jsonl, run_dir, sha1_text, write_jsonl

def build_and_validate_evidence(run_id: str, output_dir: str | Path = "outputs") -> dict[str, Any]:
    rd = run_dir(run_id, output_dir)
    rows = {r["source_id"]: r for r in read_jsonl(rd / "input_rows.jsonl")}
    evidence = []
    failures = []
    n = 0
    for fname in ANNOTATION_FILES.values():
        for ann in read_jsonl(rd / "annotations" / fname):
            ev = ann.get("evidence") or {}
            if not ev:
                continue
            n += 1
            source = rows.get(ev.get("source_id"))
            quote = ev.get("evidence_quote", "")
            span = ev.get("quote_span", [None, None])
            status = "verified"
            reason = ""
            if not source:
                status, reason = "failed", "source_id_not_found"
            elif source.get("content_hash") != ev.get("content_hash"):
                status, reason = "failed", "content_hash_mismatch"
            elif quote not in source.get("content", ""):
                status, reason = "failed", "quote_not_found"
            elif span[0] is None or source["content"][span[0]:span[1]] != quote:
                status, reason = "failed", "quote_span_mismatch"
            eid = f"EV_{n:06d}"
            item = {"evidence_id": eid, "source_id": ev.get("source_id"), "segment_id": ev.get("segment_id"), "quote": quote, "quote_span": span, "quote_hash": sha1_text(quote), "content_hash": ev.get("content_hash"), "evidence_level": ev.get("evidence_level", "E1"), "verification_status": status}
            evidence.append(item)
            if status != "verified": failures.append({"evidence_id": eid, "reason": reason})
    write_jsonl(rd / "evidence" / "evidence_index.jsonl", evidence)
    report = {"total_evidence": len(evidence), "verified": len(evidence) - len(failures), "failed": len(failures), "verified_rate": (len(evidence) - len(failures)) / max(len(evidence), 1), "failures": failures}
    atomic_write_json(rd / "reports" / "citation_validation_report.json", report)
    return report
