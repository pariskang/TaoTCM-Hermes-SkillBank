"""Real LLM/RAG baseline adapters for the ablation study (B0/B1/B2).

The deterministic local proxies keep CI and offline runs green. For
publication-grade experiments, enable the adapters (TAOTCM_LLM_BASELINES=1
or `--llm-baselines`, plus a configured LITELLM_MODEL) and the baselines
become real systems sharing one closed candidate set with the proxies:

- B0 bare LLM: candidates + case features only — no corpus context.
- B1 naive RAG: candidates + top-k lexically retrieved evidence quotes.
- B2 graph RAG: candidates + structured pattern subgraphs (features,
  exclusions, contraindications) with their linked evidence.

B1/B2 must return the evidence ids they relied on, which makes
hallucinated/verified citation rates measurable for baselines instead of
null. A failed LLM call raises LLMError; run_ablation falls back to the
deterministic proxy for that case and reports the fallback count.
"""
from __future__ import annotations

import os
from typing import Any

from canon_tcm_hermes.llm.litellm_client import complete_json, llm_enabled

RETRIEVAL_TOP_K = 5

_SYSTEM_PROMPT = (
    "你是中医方证判读评测中的基线系统。根据输入特征，从候选方证列表中选出最可能的前三个，"
    "输出严格 JSON：{\"patterns\": [按可能性降序的候选名], \"citations\": [你实际依据的证据 id 列表，无则为空列表]}。"
    "patterns 只能从候选列表中选择，不得编造名称。除 JSON 外不要输出任何内容。"
)


def llm_baselines_enabled(flag: bool | None = None) -> bool:
    enabled = flag if flag is not None else os.getenv("TAOTCM_LLM_BASELINES", "0") == "1"
    return bool(enabled) and llm_enabled()


def predict_baseline(system: str, case: dict[str, Any], patterns: list[dict[str, Any]], evidence: list[dict[str, Any]]) -> dict[str, Any]:
    """Return {"patterns": [top3 names], "citations": [evidence ids] | None}."""
    features = [str(f) for f in case.get("input_features", [])]
    candidates = [p.get("pattern_name", "") for p in patterns if p.get("pattern_name")]
    if system == "B0":
        context = ""
    elif system == "B1":
        context = "## 检索到的证据（按词面相关性）\n" + _lexical_context(features, evidence)
    elif system == "B2":
        context = "## 知识图谱子图（方证结构 + 关联证据）\n" + _graph_context(patterns, evidence)
    else:
        raise ValueError(f"no LLM baseline adapter for system {system}")
    user_prompt = (
        f"候选方证：{candidates}\n"
        f"病例特征：{features}\n"
        + (context + "\n" if context else "")
        + "给出 JSON。"
    )
    data = complete_json(_SYSTEM_PROMPT, user_prompt, validate=lambda d: _validate(d, candidates))
    citations = None
    if system in {"B1", "B2"}:
        citations = [str(c) for c in (data.get("citations") or [])]
    return {"patterns": [str(p) for p in data.get("patterns", [])][:3], "citations": citations}


def _validate(data: Any, candidates: list[str]) -> list[str]:
    if not isinstance(data, dict):
        return ["response must be a JSON object"]
    patterns = data.get("patterns")
    if not isinstance(patterns, list) or not patterns:
        return ["patterns must be a non-empty list"]
    unknown = [p for p in patterns if p not in candidates]
    if unknown:
        return [f"patterns must be chosen from the candidate list; unknown: {unknown[:3]}"]
    if not isinstance(data.get("citations", []), list):
        return ["citations must be a list of evidence ids"]
    return []


def _lexical_context(features: list[str], evidence: list[dict[str, Any]]) -> str:
    scored = []
    for item in evidence:
        quote = str(item.get("quote", ""))
        score = sum(1 for f in features if f and f in quote)
        if score > 0:
            scored.append((score, item))
    scored.sort(key=lambda pair: pair[0], reverse=True)
    lines = [
        f"- [{item.get('evidence_id')}] {item.get('quote')}（来源 {item.get('source_id')}）"
        for _, item in scored[:RETRIEVAL_TOP_K]
    ]
    return "\n".join(lines) if lines else "（无相关证据命中）"


def _graph_context(patterns: list[dict[str, Any]], evidence: list[dict[str, Any]]) -> str:
    by_segment: dict[str, list[dict[str, Any]]] = {}
    for item in evidence:
        by_segment.setdefault(str(item.get("segment_id", "")), []).append(item)
    blocks = []
    for pattern in patterns:
        quotes = [
            f"[{e.get('evidence_id')}] {e.get('quote')}"
            for segment in pattern.get("evidence_segments", [])
            for e in by_segment.get(str(segment), [])
        ]
        blocks.append(
            f"- {pattern.get('pattern_name')}：核心特征 {pattern.get('core_features')}；"
            f"常见特征 {pattern.get('common_features')}；排除特征 {pattern.get('exclusion_features')}；"
            f"禁忌 {pattern.get('contraindications')}；证据 {quotes[:RETRIEVAL_TOP_K]}"
        )
    return "\n".join(blocks) if blocks else "（图谱为空）"
