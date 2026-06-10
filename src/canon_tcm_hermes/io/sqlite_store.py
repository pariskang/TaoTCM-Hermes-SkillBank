from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from canon_tcm_hermes.utils import ensure_dir

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
  job_id TEXT PRIMARY KEY,
  run_id TEXT,
  stage TEXT,
  source_id TEXT,
  segment_id TEXT,
  genre TEXT,
  input_hash TEXT,
  prompt_version TEXT,
  schema_version TEXT,
  status TEXT,
  attempts INTEGER,
  output_path TEXT,
  error TEXT,
  updated_at TEXT
);
"""

class SQLiteJobStore:
    def __init__(self, path: str | Path = "outputs/progress.sqlite") -> None:
        self.path = Path(path)
        ensure_dir(self.path.parent)
        self.conn = sqlite3.connect(self.path)
        self.conn.execute(SCHEMA)
        self.conn.commit()

    def upsert_job(self, **fields: Any) -> None:
        fields.setdefault("updated_at", datetime.now(timezone.utc).isoformat())
        cols = list(fields)
        placeholders = ",".join("?" for _ in cols)
        updates = ",".join(f"{c}=excluded.{c}" for c in cols if c != "job_id")
        sql = f"INSERT INTO jobs ({','.join(cols)}) VALUES ({placeholders}) ON CONFLICT(job_id) DO UPDATE SET {updates}"
        self.conn.execute(sql, [fields[c] for c in cols])
        self.conn.commit()

    def should_skip(self, job_id: str, input_hash: str, prompt_version: str = "v1", schema_version: str = "v1") -> bool:
        cur = self.conn.execute("SELECT status,input_hash,prompt_version,schema_version FROM jobs WHERE job_id=?", (job_id,))
        row = cur.fetchone()
        return bool(row and row == ("done", input_hash, prompt_version, schema_version))
