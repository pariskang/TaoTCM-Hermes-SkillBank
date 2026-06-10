from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

from jsonschema import validate

from canon_tcm_hermes.utils import atomic_write_json, read_jsonl, run_dir, write_jsonl

GENRE_TO_TEMPLATE = {
    "canonical_clause": "clause_template",
    "treatise": "treatise_claim",
    "formula_entry": "formula_template",
    "materia_medica": "herb_template",
    "pulse_text": "pulse_template",
    "case_record": "case_template",
    "commentary": "commentary_template",
    "mnemonic_misc": "mnemonic_template",
    "non_medical": "non_medical",
}
FORMULA_START = re.compile(r"(?:[\u4e00-\u9fff]{1,8}[一二三四五六七八九十半两兩斤钱錢分升合枚个箇]+(?:（[^）]*）)?[、，\s]*){2,}|右[一二三四五六七八九十]+味|以水[一二三四五六七八九十]+升|煮取")


def classify_text(text: str, book: str = "", chapter: str = "") -> tuple[str, str]:
    if re.search(r"(序|目录|目錄|刊刻|牌记|凡例)", chapter) and not re.search(r"病|脉|藥|药|方|汤|湯", text):
        return "non_medical", "medium"
    if re.search(r"(注曰|按曰|愚谓|愚謂|成注|程注|旧注|舊注|者，.*也|者.*也)", text) and re.search(r"(曰|云|主之|不可|宜)", text):
        return "commentary", "high"
    if re.search(r"(初诊|初診|复诊|復診|翌日|越[一二三四五六七八九十]日|[一二三四五六七八九十]剂后|劑後|而愈|霍然|余诊|予曰|某|王姓|年[一二三四五六七八九十0-9])", text):
        if re.search(r"(处方|處方|投|服|剂|劑|转归|轉歸|而愈|热退|熱退)", text):
            return "case_record", "high"
    if re.search(r"^(夫|盖|蓋|凡|故|是以|所谓|所謂|何也|答曰|论曰|論曰)", text) or re.search(r"(所以|由是|致|皆属于|皆屬於)", text):
        return "treatise", "medium"
    if re.search(r"(汤头|湯頭|歌曰|诀曰|訣曰|赋曰|賦曰|汤中用|湯中用|四般施)", text) or _looks_like_verse(text):
        return "mnemonic_misc", "medium"
    if re.search(r"^[\u4e00-\u9fff]{1,6}[，,]?味[甘苦辛酸咸鹹淡].*(主|有毒|无毒|無毒)", text):
        return "materia_medica", "high"
    if re.search(r"^[\u4e00-\u9fff]{1,4}脉[，,].*(举之|舉之|按之|寻之|尋之|寸|关|關|尺)", text) or ("脉经" in book or "脈經" in book) and re.search(r"(举之|舉之|按之|寻之|尋之)", text):
        return "pulse_text", "high"
    if re.search(r"(右[一二三四五六七八九十]+味|以水[一二三四五六七八九十]+升|煮取|去滓|温服|溫服|若.*者，?去.*加)", text):
        return "formula_entry", "high"
    if re.search(r"(主之|宜|可与|可與|不可与|不可與|与之则|與之則|当|當).{0,12}$", text) or re.search(r"(主之|宜|可与|可與|不可与|不可與|与之则|與之則)", text):
        return "canonical_clause", "high"
    return "canonical_clause", "low"


def _looks_like_verse(text: str) -> bool:
    compact = re.sub(r"[，。；、\s]", "", text)
    if len(compact) < 12:
        return False
    parts = re.split(r"[，。；]", text)
    lens = [len(p.strip()) for p in parts if p.strip()]
    return len(lens) >= 3 and max(lens) <= 9 and len(set(lens[:4])) <= 2


def segment_row(row: dict[str, Any]) -> dict[str, Any]:
    text = row["content"]
    spans: list[dict[str, Any]] = []
    links: list[dict[str, str]] = []

    # commentary with an explicit quoted clause before 注曰/按曰.
    m_comment = re.search(r"(注曰|按曰|愚谓|愚謂)", text)
    if m_comment and m_comment.start() > 6:
        left = text[:m_comment.start()]
        g, c = classify_text(left, row.get("book", ""), row.get("chapter", ""))
        spans.append(_span(row, 0, 0, m_comment.start(), g, c, quoted=True))
        spans.append(_span(row, 1, m_comment.start(), len(text), "commentary", "high"))
        links.append({"from": "SEG01", "to": "SEG00", "relation": "comments_on"})
    else:
        # clause + formula entry split: keep 主之 in clause and start formula at herb list / 右X味.
        m_formula = FORMULA_START.search(text)
        m_clause = re.search(r"(主之|宜[\u4e00-\u9fff]{1,8}汤|宜[\u4e00-\u9fff]{1,8}湯)", text)
        if m_formula and m_clause and m_formula.start() > m_clause.end():
            spans.append(_span(row, 0, 0, m_formula.start(), "canonical_clause", "high"))
            spans.append(_span(row, 1, m_formula.start(), len(text), "formula_entry", "high"))
            links.append({"from": "SEG00", "to": "SEG01", "relation": "prescribes"})
        else:
            genre, confidence = classify_text(text, row.get("book", ""), row.get("chapter", ""))
            spans.append(_span(row, 0, 0, len(text), genre, confidence))
    uncertain = any(s["confidence"] == "low" for s in spans)
    route = {"row_id": row["row_id"], "source_id": row["source_id"], "is_mixed": len(spans) > 1, "genre_segmentation": spans, "cross_links": links, "genre_uncertain": uncertain, "uncertainty_note": "low heuristic confidence" if uncertain else ""}
    return route


def _span(row: dict[str, Any], idx: int, start: int, end: int, genre: str, confidence: str, quoted: bool = False) -> dict[str, Any]:
    item = {"segment_id": f"{row['source_id']}::SEG{idx:02d}", "span": [start, end], "genre": genre, "template": GENRE_TO_TEMPLATE[genre], "confidence": confidence}
    if quoted:
        item["quoted"] = True
        item["dedup_target"] = row["source_id"]
    return item


def route_rows(rows: list[dict[str, Any]], run_id: str, output_dir: str | Path = "outputs") -> list[dict[str, Any]]:
    routes = [segment_row(row) for row in rows]
    schema = json.loads(Path("schemas/genre_segmentation.schema.json").read_text(encoding="utf-8"))
    for route in routes:
        validate(route, schema)
    rd = run_dir(run_id, output_dir)
    write_jsonl(rd / "genre_routes.jsonl", routes)
    counts = Counter(seg["genre"] for route in routes for seg in route["genre_segmentation"])
    atomic_write_json(rd / "reports" / "genre_report.json", {"total_rows": len(rows), "genre_counts": dict(counts), "genre_uncertain_rate": sum(r["genre_uncertain"] for r in routes) / max(len(routes), 1)})
    return routes


def route_run(run_id: str, output_dir: str | Path = "outputs") -> list[dict[str, Any]]:
    rows = read_jsonl(run_dir(run_id, output_dir) / "input_rows.jsonl")
    return route_rows(rows, run_id, output_dir)
