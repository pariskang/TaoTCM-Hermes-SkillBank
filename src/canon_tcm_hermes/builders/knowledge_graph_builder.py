from __future__ import annotations

from pathlib import Path
from typing import Any

from canon_tcm_hermes.utils import atomic_write_json, read_jsonl, run_dir, write_jsonl
from canon_tcm_hermes.validators.cross_genre_validator import validate_cross_genre

ANNOTATION_NODE_TYPES = {
    "clause_templates.jsonl": ("template_id", "ClauseTemplate"),
    "formula_templates.jsonl": ("formula_id", "Formula"),
    "herb_templates.jsonl": ("herb_id", "Herb"),
    "pulse_templates.jsonl": ("pulse_id", "Pulse"),
    "treatise_claims.jsonl": ("claim_id", "TreatiseClaim"),
    "case_templates.jsonl": ("case_id", "CaseRecord"),
    "commentary_templates.jsonl": ("comment_id", "Commentary"),
    "mnemonic_templates.jsonl": ("item_id", "Mnemonic"),
}


def build_knowledge_graph(run_id: str, output_dir: str | Path = "outputs") -> dict[str, Any]:
    rd = run_dir(run_id, output_dir)
    nodes: dict[str, dict[str, Any]] = {}
    edges: list[dict[str, Any]] = []
    links: list[dict[str, Any]] = []

    for row in read_jsonl(rd / "input_rows.jsonl"):
        _add_node(nodes, row["normalized_book_id"], "Book", label=row["book"])
        _add_node(nodes, row["normalized_volume_id"], "Volume", label=row["volume"])
        _add_node(nodes, row["normalized_chapter_id"], "Chapter", label=row["chapter"])
        _add_node(nodes, row["source_id"], "SourceSegment", label=row["chapter"], source_id=row["source_id"])
        edges.extend([
            {"source": row["normalized_book_id"], "target": row["normalized_volume_id"], "relation": "has_volume"},
            {"source": row["normalized_volume_id"], "target": row["normalized_chapter_id"], "relation": "has_chapter"},
            {"source": row["normalized_chapter_id"], "target": row["source_id"], "relation": "has_source_row"},
        ])

    for route in read_jsonl(rd / "genre_routes.jsonl"):
        for segment in route["genre_segmentation"]:
            _add_node(nodes, segment["segment_id"], "SourceSegment", genre=segment["genre"], span=segment["span"])
            edges.append({"source": route["source_id"], "target": segment["segment_id"], "relation": "has_segment"})
        for link in route.get("cross_links", []):
            edge = {"source": _segid(route, link["from"]), "target": _segid(route, link["to"]), "relation": link["relation"]}
            edges.append(edge)
            links.append(edge)

    annotations = {filename: read_jsonl(rd / "annotations" / filename) for filename in ANNOTATION_NODE_TYPES}
    for filename, (id_key, node_type) in ANNOTATION_NODE_TYPES.items():
        for item in annotations[filename]:
            node_id = item.get(id_key)
            if not node_id:
                continue
            _add_node(nodes, node_id, node_type, label=item.get("formula_name") or item.get("herb_name") or item.get("pulse_name") or node_id)
            if item.get("segment_id"):
                edges.append({"source": item["segment_id"], "target": node_id, "relation": "annotates"})

    _add_domain_edges(edges, annotations, nodes)
    graph = {"nodes": list(nodes.values()), "edges": _dedupe_edges(edges)}
    atomic_write_json(rd / "graphs" / "knowledge_graph.json", graph)
    write_jsonl(rd / "graphs" / "cross_genre_links.jsonl", links)
    validate_cross_genre(run_id, output_dir)
    return graph


def _add_domain_edges(edges: list[dict[str, Any]], annotations: dict[str, list[dict[str, Any]]], nodes: dict[str, dict[str, Any]]) -> None:
    from canon_tcm_hermes.builders.entity_resolver import canonical_name, formula_node_id, fold_variants, herb_node_id, pulse_node_id

    formulas = annotations["formula_templates.jsonl"]
    # canonical surface form -> annotated template id, so aliases and
    # variant characters resolve to ONE node id
    formula_ids = {canonical_name(item.get("formula_name", ""), "formulas"): item.get("formula_id") for item in formulas if item.get("formula_id")}
    herb_ids = {canonical_name(item.get("herb_name", ""), "herbs"): item.get("herb_id") for item in annotations["herb_templates.jsonl"] if item.get("herb_id")}
    pulse_ids = {canonical_name(item.get("pulse_name", ""), "pulses"): item.get("pulse_id") for item in annotations["pulse_templates.jsonl"] if item.get("pulse_id")}

    def formula_ref(name: str) -> str:
        node_id = formula_node_id(name, formula_ids)
        _add_node(nodes, node_id, "Formula", label=canonical_name(name, "formulas"))
        return node_id

    def herb_ref(name: str) -> str:
        node_id = herb_node_id(name, herb_ids)
        _add_node(nodes, node_id, "Herb", label=canonical_name(name, "herbs"))
        return node_id

    for clause in annotations["clause_templates.jsonl"]:
        formula_name = (clause.get("conclusion") or {}).get("formula")
        if formula_name:
            edges.append({"source": clause["template_id"], "target": formula_ref(formula_name), "relation": "prescribes"})
    for formula in formulas:
        for herb in formula.get("composition", []):
            herb_name = herb.get("herb")
            if herb_name:
                edges.append({"source": formula["formula_id"], "target": herb_ref(herb_name), "relation": "contains_herb"})
    for comment in annotations["commentary_templates.jsonl"]:
        target = comment.get("target_clause")
        if target:
            edges.append({"source": comment["comment_id"], "target": target, "relation": "comments_on"})
    for mnemonic in annotations["mnemonic_templates.jsonl"]:
        target = mnemonic.get("target_formula") or (mnemonic.get("verse_fields") or {}).get("target_id") or mnemonic.get("target_pulse")
        if target:
            folded = fold_variants(target)
            formula_canonical = canonical_name(target, "formulas")
            if formula_canonical in formula_ids or any(suffix in formula_canonical for suffix in ("汤", "散", "丸", "饮")):
                resolved = formula_ref(target)
            elif "脉" in folded:
                resolved = pulse_node_id(target, pulse_ids)
                _add_node(nodes, resolved, "Pulse", label=canonical_name(target, "pulses"))
            else:
                resolved = folded
                _add_node(nodes, resolved, "Concept", label=folded)
            edges.append({"source": mnemonic["item_id"], "target": resolved, "relation": "mnemonic_of"})
    for case in annotations["case_templates.jsonl"]:
        for intervention in case.get("interventions", []):
            formula = intervention.get("formula") if isinstance(intervention, dict) else intervention
            if formula:
                edges.append({"source": case["case_id"], "target": formula_ref(formula), "relation": "corroborates"})


def _add_node(nodes: dict[str, dict[str, Any]], node_id: str, node_type: str, **attrs: Any) -> None:
    if not node_id:
        return
    nodes.setdefault(node_id, {"id": node_id, "type": node_type}).update(attrs)


def _dedupe_edges(edges: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen = set()
    out = []
    for edge in edges:
        key = (edge.get("source"), edge.get("target"), edge.get("relation"))
        if key not in seen:
            seen.add(key)
            out.append(edge)
    return out


def _segid(route: dict[str, Any], short: str) -> str:
    if short.startswith(route["source_id"]):
        return short
    return f"{route['source_id']}::{short}"
