from __future__ import annotations

import re
from collections import Counter
from pathlib import Path
from typing import Any

from canon_tcm_hermes.llm.litellm_client import LLMError, complete_json, llm_enabled
from canon_tcm_hermes.utils import (
    atomic_write_json,
    now_iso,
    prompts_dir,
    read_jsonl,
    run_dir,
    sha1_text,
    write_jsonl,
)
from canon_tcm_hermes.validators.schema_validator import validate_schema

GUIDELINE_VERSION = "v1.0"

GENRE_TO_TEMPLATE = {
    "canonical_clause": "clause",
    "treatise": "treatise_claim",
    "formula_entry": "formula",
    "materia_medica": "herb",
    "pulse_text": "pulse",
    "case_record": "case",
    "commentary": "commentary",
    "mnemonic_misc": "mnemonic",
    "non_medical": "skip",
}
CROSS_LINK_RELATIONS = {"prescribes", "comments_on", "mnemonic_of", "applies", "corroborates", "contradicts", "variant_of", "defines_feature_in"}

FORMULA_START = re.compile(r"(?:[一-鿿]{1,8}[一二三四五六七八九十半两兩斤钱錢分升合枚个箇]+(?:（[^）]*）)?[、，\s]*){2,}|右[一二三四五六七八九十]+味|以水[一二三四五六七八九十]+升|煮取")
COMMENT_MARKER = re.compile(r"(注曰|按曰|按：|愚谓|愚謂|成注|程注|旧注|舊注|喻曰|柯曰)")


def classify_text(text: str, book: str = "", chapter: str = "") -> tuple[str, str]:
    """Heuristic genre classifier following docs/genre_guideline_v1.0.md."""
    if re.search(r"(序|目录|目錄|刊刻|牌记|凡例)", chapter) and not re.search(r"病|脉|藥|药|方|汤|湯", text):
        return "non_medical", "medium"
    if COMMENT_MARKER.search(text):
        return "commentary", "high"
    if re.search(r"(初诊|初診|复诊|復診|翌日|越[一二三四五六七八九十]日|[一二三四五六七八九十]剂后|劑後|余诊|予曰|王姓|某翁|某妇|某婦)", text) and re.search(
        r"(处方|處方|投|服|剂|劑|转归|轉歸|而愈|热退|熱退|不起|霍然)", text
    ):
        return "case_record", "high"
    if re.search(r"^(夫|盖|蓋|凡|故|是以|所谓|所謂|何也|答曰|论曰|論曰)", text) or re.search(r"(皆属于|皆屬於)", text):
        return "treatise", "medium"
    if re.search(r"(汤头|湯頭|歌曰|诀曰|訣曰|赋曰|賦曰|汤中用|湯中用|四般施)", text) or _looks_like_verse(text):
        return "mnemonic_misc", "medium"
    if re.search(r"^[一-鿿]{1,6}[，,]?味[甘苦辛酸咸鹹淡].*(主|有毒|无毒|無毒)", text):
        return "materia_medica", "high"
    if re.search(r"^[一-鿿]{1,4}脉[，,].*(举之|舉之|按之|寻之|尋之|寸|关|關|尺)", text) or (("脉经" in book or "脈經" in book) and re.search(r"(举之|舉之|按之|寻之|尋之)", text)):
        return "pulse_text", "high"
    if re.search(r"(右[一二三四五六七八九十]+味|以水[一二三四五六七八九十]+升|煮取|去滓|温服|溫服|若.{0,12}者，?去.{0,12}加)", text):
        return "formula_entry", "high"
    if re.search(r"(主之|宜|可与|可與|不可与|不可與|与之则|與之則)", text):
        return "canonical_clause", "high"
    if re.search(r"者，.{0,16}也。?$", text):
        # theoretical clause: condition → pathogenesis/name judgement, no disposal verb
        return "canonical_clause", "medium"
    return "canonical_clause", "low"


def _looks_like_verse(text: str) -> bool:
    # disposal assertions mark canonical clauses, never mnemonic verse,
    # even when the clause happens to have evenly-sized phrases.
    if re.search(r"(主之|宜|不可|可与|可與|与之则|與之則)", text):
        return False
    compact = re.sub(r"[，。；、\s]", "", text)
    if len(compact) < 12:
        return False
    parts = re.split(r"[，。；]", text)
    lens = [len(p.strip()) for p in parts if p.strip()]
    return len(lens) >= 3 and max(lens) <= 9 and len(set(lens[:4])) <= 2


def _sub_genre(genre: str, text: str) -> str:
    if genre == "canonical_clause":
        return "prescriptive" if re.search(r"(主之|宜|可与|可與|不可|与之则|與之則)", text) else "theoretical"
    if genre == "mnemonic_misc":
        return "verse" if _looks_like_verse(text) or re.search(r"(歌|诀|訣|赋|賦)", text) else "note"
    return ""


def heuristic_segments(row: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return (segments, cross_links) using deterministic rules."""
    text = row["content"]
    book, chapter = row.get("book", ""), row.get("chapter", "")
    segments: list[dict[str, Any]] = []
    links: list[dict[str, Any]] = []

    m_comment = COMMENT_MARKER.search(text)
    if m_comment and m_comment.start() > 6:
        # quoted source text + commentary span (guideline 3.5)
        left = text[: m_comment.start()]
        genre, confidence = classify_text(left, book, chapter)
        if genre == "commentary":
            genre, confidence = "canonical_clause", "medium"
        segments.append({"span": [0, m_comment.start()], "genre": genre, "sub_genre": _sub_genre(genre, left), "confidence": confidence, "quoted": True})
        segments.append({"span": [m_comment.start(), len(text)], "genre": "commentary", "sub_genre": "", "confidence": "high", "quoted": False})
        links.append({"from": 1, "to": 0, "relation": "comments_on"})
        return segments, links

    m_formula = FORMULA_START.search(text)
    m_clause = re.search(r"(主之|宜[一-鿿]{1,8}[汤湯])", text)
    if m_formula and m_clause and m_formula.start() > m_clause.end():
        # clause + formula split (guideline 3.4)
        segments.append({"span": [0, m_formula.start()], "genre": "canonical_clause", "sub_genre": "prescriptive", "confidence": "high", "quoted": False})
        segments.append({"span": [m_formula.start(), len(text)], "genre": "formula_entry", "sub_genre": "", "confidence": "high", "quoted": False})
        links.append({"from": 0, "to": 1, "relation": "prescribes"})
        return segments, links

    genre, confidence = classify_text(text, book, chapter)
    segments.append({"span": [0, len(text)], "genre": genre, "sub_genre": _sub_genre(genre, text), "confidence": confidence, "quoted": False})
    return segments, links


def _llm_segments(row: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], bool, str]:
    system_prompt = (prompts_dir() / "genre_router.md").read_text(encoding="utf-8")
    user_prompt = (
        f"book: {row.get('book', '')}\nvolume: {row.get('volume', '')}\nchapter: {row.get('chapter', '')}\n"
        f"text ({len(row['content'])} chars):\n{row['content']}"
    )
    data = complete_json(system_prompt, user_prompt)
    segments = []
    for seg in data.get("segments", []):
        span = seg.get("span", [])
        genre = seg.get("genre", "")
        if genre not in GENRE_TO_TEMPLATE or len(span) != 2:
            raise LLMError(f"invalid segment from router LLM: {seg}")
        start, end = int(span[0]), int(span[1])
        if not (0 <= start < end <= len(row["content"])):
            raise LLMError(f"span out of bounds: {span}")
        segments.append({
            "span": [start, end],
            "genre": genre,
            "sub_genre": str(seg.get("sub_genre", "")),
            "confidence": seg.get("confidence") if seg.get("confidence") in {"high", "medium", "low"} else "medium",
            "quoted": bool(seg.get("quoted", False)),
        })
    if not segments:
        raise LLMError("router LLM returned no segments")
    segments.sort(key=lambda s: s["span"][0])
    links = []
    for link in data.get("cross_links", []):
        relation = link.get("relation")
        if relation in CROSS_LINK_RELATIONS and isinstance(link.get("from"), int) and isinstance(link.get("to"), int):
            if 0 <= link["from"] < len(segments) and 0 <= link["to"] < len(segments):
                links.append({"from": link["from"], "to": link["to"], "relation": relation})
    return segments, links, bool(data.get("genre_uncertain", False)), str(data.get("uncertainty_note", ""))


def segment_row(row: dict[str, Any], use_llm: bool | None = None) -> dict[str, Any]:
    use_llm = llm_enabled() if use_llm is None else use_llm
    annotator_type, annotator_id, flags = "heuristic", "heuristic_router_v2", []
    uncertain_note = ""
    llm_uncertain = False
    if use_llm:
        try:
            segments, links, llm_uncertain, uncertain_note = _llm_segments(row)
            annotator_type, annotator_id = "llm", __import__("os").getenv("LITELLM_MODEL", "llm")
        except Exception as exc:
            segments, links = heuristic_segments(row)
            flags = [f"llm_router_failed_fallback_heuristic: {str(exc)[:200]}"]
    else:
        segments, links = heuristic_segments(row)

    text = row["content"]
    spans: list[dict[str, Any]] = []
    for idx, seg in enumerate(segments):
        start, end = seg["span"]
        item = {
            "segment_id": f"{row['source_id']}::SEG{idx:02d}",
            "span_index": idx,
            "span": [start, end],
            "genre": seg["genre"],
            "routed_template": GENRE_TO_TEMPLATE[seg["genre"]],
            "genre_confidence": seg["confidence"],
            # legacy aliases kept for downstream readers
            "template": GENRE_TO_TEMPLATE[seg["genre"]],
            "confidence": seg["confidence"],
        }
        if seg.get("sub_genre"):
            item["sub_genre"] = seg["sub_genre"]
        if seg.get("quoted"):
            item["quoted"] = True
            item["dedup_target"] = row["source_id"]
        spans.append(item)

    cross_links = [
        {"from": spans[link["from"]]["segment_id"], "to": spans[link["to"]]["segment_id"], "relation": link["relation"]}
        for link in links
    ]
    uncertain = llm_uncertain or any(s["genre_confidence"] == "low" for s in spans)
    confidence_overall = "low" if uncertain else ("high" if all(s["genre_confidence"] == "high" for s in spans) else "medium")
    route = {
        "segmentation_id": f"GSEG::{row['source_id']}",
        "row_id": row["row_id"],
        "source_id": row["source_id"],
        "row_source": {
            "book": row.get("book", ""),
            "volume": row.get("volume", ""),
            "chapter": row.get("chapter", ""),
            "version": row.get("version", ""),
            "row_id": row["row_id"],
            "row_text_hash": row.get("content_hash") or sha1_text(text),
            "row_char_length": len(text),
        },
        "is_mixed": len(spans) > 1,
        "genre_segmentation": spans,
        "cross_links": cross_links,
        "genre_uncertain": uncertain,
        "uncertainty_note": uncertain_note or ("low heuristic confidence" if uncertain else ""),
        "annotation_meta": {
            "annotator_type": annotator_type,
            "annotator_id": annotator_id,
            "confidence": confidence_overall,
            "guideline_version": GUIDELINE_VERSION,
            "annotation_flags": flags,
            "timestamp": now_iso(),
        },
    }
    return route


def route_rows(rows: list[dict[str, Any]], run_id: str, output_dir: str | Path = "outputs", use_llm: bool | None = None) -> list[dict[str, Any]]:
    routes = [segment_row(row, use_llm=use_llm) for row in rows]
    for route in routes:
        validate_schema(route, "genre_segmentation.schema.json")
    rd = run_dir(run_id, output_dir)
    write_jsonl(rd / "genre_routes.jsonl", routes)
    counts = Counter(seg["genre"] for route in routes for seg in route["genre_segmentation"])
    atomic_write_json(
        rd / "reports" / "genre_report.json",
        {
            "total_rows": len(rows),
            "genre_counts": dict(counts),
            "mixed_rows": sum(1 for r in routes if r["is_mixed"]),
            "genre_uncertain_rate": sum(r["genre_uncertain"] for r in routes) / max(len(routes), 1),
            "router_mode": "llm" if (llm_enabled() if use_llm is None else use_llm) else "heuristic",
        },
    )
    return routes


def route_run(run_id: str, output_dir: str | Path = "outputs", use_llm: bool | None = None) -> list[dict[str, Any]]:
    rows = read_jsonl(run_dir(run_id, output_dir) / "input_rows.jsonl")
    if not rows:
        raise FileNotFoundError(f"input_rows.jsonl missing or empty for run {run_id}; run `canon route --input <xlsx>` first")
    return route_rows(rows, run_id, output_dir, use_llm=use_llm)
