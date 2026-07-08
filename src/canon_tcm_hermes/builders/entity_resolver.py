"""Entity resolution for the knowledge graph.

The graph previously linked edges to raw surface strings (herb names,
formula names), so 麻黃湯 and 麻黄汤 became different nodes and herb
targets were not stable ids. The resolver canonicalizes surface forms via
configs/entity_aliases.yaml plus generic traditional→simplified variant
folding, and mints deterministic ids (F_/H_/P_ prefixes) for entities that
have no annotated template of their own.
"""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

import yaml

from canon_tcm_hermes.utils import project_root, sha1_text

# generic traditional -> simplified folds that matter for TCM entity names
_VARIANT_FOLDS = str.maketrans({
    "湯": "汤", "黃": "黄", "藥": "药", "薑": "姜", "棗": "枣", "脈": "脉",
    "證": "证", "龍": "龙", "當": "当", "歸": "归", "膠": "胶", "參": "参",
})


def fold_variants(name: str) -> str:
    return str(name or "").translate(_VARIANT_FOLDS).strip()


@lru_cache(maxsize=None)
def _alias_index(config_path: str | None = None) -> dict[str, dict[str, str]]:
    path = Path(config_path) if config_path else project_root() / "configs" / "entity_aliases.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else {}
    data = data if isinstance(data, dict) else {}
    index: dict[str, dict[str, str]] = {}
    for kind in ("formulas", "herbs", "pulses"):
        table: dict[str, str] = {}
        for canonical, aliases in (data.get(kind) or {}).items():
            canonical_folded = fold_variants(canonical)
            table[canonical_folded] = canonical_folded
            for alias in aliases or []:
                table[fold_variants(alias)] = canonical_folded
        index[kind] = table
    return index


def canonical_name(name: str, kind: str) -> str:
    folded = fold_variants(name)
    return _alias_index()[kind].get(folded, folded)


def _mint(prefix: str, canonical: str) -> str:
    ascii_id = re.sub(r"\W+", "", canonical)
    if re.fullmatch(r"[A-Za-z0-9_]+", ascii_id or ""):
        return f"{prefix}_{ascii_id.upper()}"
    return f"{prefix}_{sha1_text(canonical)[5:13].upper()}"


def formula_node_id(name: str, known_ids: dict[str, str] | None = None) -> str:
    canonical = canonical_name(name, "formulas")
    if known_ids and canonical in known_ids:
        return known_ids[canonical]
    return _mint("F", canonical)


def herb_node_id(name: str, known_ids: dict[str, str] | None = None) -> str:
    canonical = canonical_name(name, "herbs")
    if known_ids and canonical in known_ids:
        return known_ids[canonical]
    return _mint("H", canonical)


def pulse_node_id(name: str, known_ids: dict[str, str] | None = None) -> str:
    canonical = canonical_name(name, "pulses")
    if known_ids and canonical in known_ids:
        return known_ids[canonical]
    return _mint("P", canonical)
