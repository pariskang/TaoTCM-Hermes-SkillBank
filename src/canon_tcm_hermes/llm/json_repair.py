from __future__ import annotations
import json, re
from typing import Any

def repair_json(raw: str) -> Any:
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.S)
    candidates = [text]
    m = re.search(r"(\{.*\}|\[.*\])", text, flags=re.S)
    if m:
        candidates.append(m.group(1))
    last_exc: Exception | None = None
    for candidate in candidates:
        for attempt in (candidate, re.sub(r",\s*([}\]])", r"\1", candidate)):
            try:
                return json.loads(attempt)
            except json.JSONDecodeError as exc:
                last_exc = exc
    assert last_exc is not None
    raise last_exc
