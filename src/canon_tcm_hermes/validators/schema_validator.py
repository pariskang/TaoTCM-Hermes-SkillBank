from __future__ import annotations
import json
from pathlib import Path
from typing import Any
from jsonschema import validate

def validate_schema_file(data: Any, schema_name: str | Path) -> None:
    path = Path(schema_name)
    if not path.exists():
        path = Path("schemas") / str(schema_name)
    schema = json.loads(path.read_text(encoding="utf-8"))
    validate(data, schema)
