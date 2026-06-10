from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pandas as pd

from canon_tcm_hermes.utils import run_dir, sha1_text, write_jsonl

REQUIRED_ALIASES = {
    "book": ["book", "书籍", "書籍", "书名", "書名"],
    "volume": ["volume", "卷", "篇", "卷名", "篇名"],
    "chapter": ["chapter", "章节", "章節", "章", "节", "節"],
    "content": ["content", "内容", "內容", "正文", "原文"],
}
OPTIONAL_COLUMNS = ["version", "page", "source_note", "editor_note"]
BOOK_CODES = {"伤寒论": "SHL", "傷寒論": "SHL", "金匮要略": "JKYL", "金匱要略": "JKYL", "脉经": "MJ", "脈經": "MJ"}


def _slug(value: Any, fallback: str) -> str:
    text = str(value or "").strip()
    if not text:
        return fallback
    if text in BOOK_CODES:
        return BOOK_CODES[text]
    asciiish = re.sub(r"[^0-9A-Za-z]+", "_", text).strip("_").upper()
    if asciiish:
        return asciiish[:40]
    return "U" + sha1_text(text)[5:13].upper()


def _rename_columns(df: pd.DataFrame) -> pd.DataFrame:
    mapping: dict[str, str] = {}
    normalized = {str(c).strip(): c for c in df.columns}
    for canonical, aliases in REQUIRED_ALIASES.items():
        found = next((normalized[a] for a in aliases if a in normalized), None)
        if found is None:
            raise ValueError(f"Missing required column for {canonical}; accepted aliases: {aliases}")
        mapping[found] = canonical
    return df.rename(columns=mapping)


def load_excel(input_path: str | Path, run_id: str, output_dir: str | Path = "outputs") -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    df = _rename_columns(pd.read_excel(input_path, dtype=str).fillna(""))
    rows: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for idx, record in df.iterrows():
        raw_content = str(record.get("content", ""))
        row_id = len(rows) + 1
        if not raw_content.strip():
            skipped.append({"run_id": run_id, "input_index": int(idx), "reason": "empty_content"})
            continue
        book = str(record.get("book", "")).strip()
        volume = str(record.get("volume", "")).strip()
        chapter = str(record.get("chapter", "")).strip()
        book_id = _slug(book, "BOOK")
        volume_id = _slug(volume, "VOL")
        chapter_id = _slug(chapter, "CH")
        source_id = f"{book_id}::{volume_id}::{chapter_id}::ROW{row_id:06d}"
        rows.append({
            "run_id": run_id,
            "row_id": row_id,
            "source_id": source_id,
            "book": book,
            "volume": volume,
            "chapter": chapter,
            "version": str(record.get("version", "")),
            "page": str(record.get("page", "")),
            "source_note": str(record.get("source_note", "")),
            "editor_note": str(record.get("editor_note", "")),
            "content": raw_content,
            "content_hash": sha1_text(raw_content),
            "normalized_book_id": book_id,
            "normalized_volume_id": volume_id,
            "normalized_chapter_id": chapter_id,
        })
    rd = run_dir(run_id, output_dir)
    write_jsonl(rd / "input_rows.jsonl", rows)
    write_jsonl(rd / "skipped_rows.jsonl", skipped)
    return rows, skipped
