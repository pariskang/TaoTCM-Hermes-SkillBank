from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Iterable


def sha1_text(text: str) -> str:
    return "sha1_" + hashlib.sha1(text.encode("utf-8")).hexdigest()


def now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


def project_root() -> Path:
    """Locate the repository root that carries schemas/ and prompts/.

    Resolution order: TAOTCM_ROOT env var, then walk up from this file,
    then the current working directory.
    """
    env = os.getenv("TAOTCM_ROOT")
    if env:
        return Path(env)
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "schemas").is_dir():
            return parent
    return Path.cwd()


def schemas_dir() -> Path:
    return project_root() / "schemas"


def prompts_dir() -> Path:
    return project_root() / "prompts"


def ensure_dir(path: str | Path) -> Path:
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p


def atomic_write_text(path: str | Path, data: str) -> None:
    path = Path(path)
    ensure_dir(path.parent)
    fd, tmp = tempfile.mkstemp(prefix=path.name, suffix=".tmp", dir=str(path.parent))
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(data)
    os.replace(tmp, path)


def atomic_write_json(path: str | Path, data: Any) -> None:
    atomic_write_text(path, json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def append_jsonl(path: str | Path, rows: Iterable[dict[str, Any]]) -> None:
    path = Path(path)
    ensure_dir(path.parent)
    with path.open("a", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False, sort_keys=False) + "\n")


def write_jsonl(path: str | Path, rows: Iterable[dict[str, Any]]) -> None:
    text = "".join(json.dumps(row, ensure_ascii=False, sort_keys=False) + "\n" for row in rows)
    atomic_write_text(path, text)


def read_jsonl(path: str | Path) -> list[dict[str, Any]]:
    p = Path(path)
    if not p.exists():
        return []
    return [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]


def run_dir(run_id: str, output_dir: str | Path = "outputs") -> Path:
    return ensure_dir(Path(output_dir) / "runs" / run_id)
