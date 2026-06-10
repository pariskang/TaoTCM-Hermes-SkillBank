from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from jsonschema import Draft7Validator
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT7

from canon_tcm_hermes.utils import schemas_dir


@lru_cache(maxsize=1)
def _schema_store() -> dict[str, dict[str, Any]]:
    store: dict[str, dict[str, Any]] = {}
    for path in sorted(schemas_dir().glob("*.schema.json")):
        schema = json.loads(path.read_text(encoding="utf-8"))
        store[schema.get("$id", path.name)] = schema
        store[path.name] = schema
    return store


@lru_cache(maxsize=1)
def _registry() -> Registry:
    resources = []
    seen: set[int] = set()
    for key, schema in _schema_store().items():
        if id(schema) in seen:
            continue
        seen.add(id(schema))
        resources.append((schema.get("$id", key), Resource(contents=schema, specification=DRAFT7)))
    return Registry().with_resources(resources)


def load_schema(schema_name: str) -> dict[str, Any]:
    name = Path(str(schema_name)).name
    store = _schema_store()
    if name in store:
        return store[name]
    raise FileNotFoundError(f"Schema not found: {schema_name} (looked in {schemas_dir()})")


def get_validator(schema_name: str) -> Draft7Validator:
    return Draft7Validator(load_schema(schema_name), registry=_registry())


def schema_errors(data: Any, schema_name: str) -> list[str]:
    """Return human-readable validation errors; empty list means valid."""
    errors = []
    for err in get_validator(schema_name).iter_errors(data):
        location = "/".join(str(p) for p in err.absolute_path) or "<root>"
        errors.append(f"{location}: {err.message}")
    return errors


def validate_schema(data: Any, schema_name: str) -> None:
    errors = schema_errors(data, schema_name)
    if errors:
        raise ValueError(f"Schema validation failed for {schema_name}: " + "; ".join(errors[:5]))


# Backwards-compatible alias used by the LLM client.
def validate_schema_file(data: Any, schema_name: str | Path) -> None:
    validate_schema(data, str(schema_name))
