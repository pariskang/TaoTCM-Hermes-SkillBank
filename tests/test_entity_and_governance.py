import json

import pytest
import yaml

from canon_tcm_hermes.builders.entity_resolver import canonical_name, fold_variants, formula_node_id, herb_node_id
from canon_tcm_hermes.builders.hermes_skill_builder import build_skill
from canon_tcm_hermes.governance.override_logger import log_override, verify_override_chain
from canon_tcm_hermes.governance.promotion import promote_version
from canon_tcm_hermes.governance.rollback import rollback_version


def test_entity_resolver_folds_variants_and_aliases():
    assert fold_variants("麻黃湯") == "麻黄汤"
    assert canonical_name("麻黃湯", "formulas") == "麻黄汤"
    assert canonical_name("桂枝湯", "formulas") == "桂枝汤"
    assert canonical_name("生薑", "herbs") == "生姜"
    # unknown names still fold generically and mint deterministic ids
    assert formula_node_id("葛根湯") == formula_node_id("葛根汤")
    assert herb_node_id("石膏").startswith("H_")


def test_graph_uses_resolved_entity_ids(tmp_path):
    from canon_tcm_hermes.cli import main
    from canon_tcm_hermes.demo_data import make_demo

    xlsx = make_demo(tmp_path / "demo.xlsx")
    out = tmp_path / "outputs"
    main(["build", "--input", str(xlsx), "--run-id", "r_kg", "--output-dir", str(out)])
    graph = json.loads((out / "runs" / "r_kg" / "graphs" / "knowledge_graph.json").read_text(encoding="utf-8"))
    node_ids = {node["id"] for node in graph["nodes"]}
    herb_edges = [e for e in graph["edges"] if e["relation"] == "contains_herb"]
    assert herb_edges
    for edge in herb_edges:
        assert edge["target"] in node_ids, "herb targets must be graph nodes, not raw strings"
    corroborates = [e for e in graph["edges"] if e["relation"] == "corroborates"]
    for edge in corroborates:
        assert edge["target"] in node_ids


def _stub_audit(out, run_id):
    audit = out / "runs" / run_id / "audit"
    audit.mkdir(parents=True, exist_ok=True)
    (audit / "audit_package.json").write_text("{}", encoding="utf-8")
    reports = out / "runs" / run_id / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    (reports / "validation_summary.json").write_text('{"passed": true}', encoding="utf-8")


def test_rollback_restores_previous_stable_package(tmp_path):
    out = tmp_path / "outputs"
    build_skill("r1", "skill_a", out)
    _stub_audit(out, "r1")
    promote_version("r1", "expert_x", "promote", out, approved_version="1.0.0", skill_id="skill_a")
    package = build_skill("r2", "skill_a", out)
    meta = yaml.safe_load((package / "skill.yaml").read_text(encoding="utf-8"))
    assert meta["lineage"]["parent_run"] == "r1"

    record = rollback_version("r2", "expert_x", "regression found", "skill_a", out)
    assert record["restored_run"] == "r1" and record["restored_version"] == "1.0.0"
    restored = yaml.safe_load((package / "skill.yaml").read_text(encoding="utf-8"))
    assert restored["version"] == "1.0.0"
    assert restored["status"] == "stable_rolled_back"
    assert restored["evolution"]["evolution_log"][-1]["decision"] == "rollback"


def test_rollback_refuses_without_stable_parent(tmp_path):
    out = tmp_path / "outputs"
    build_skill("r1", "skill_a", out)
    with pytest.raises(ValueError, match="nothing stable"):
        rollback_version("r1", "expert_x", "", "skill_a", out)


def test_override_log_hash_chain(tmp_path):
    out = tmp_path / "outputs"
    log_override("r1", "dr_wang", "patient allergy history", {"features": ["发热"]}, reason_category="safety_concern", output_dir=out)
    log_override("r1", "dr_wang", "second opinion", {"features": ["无汗"]}, output_dir=out)
    assert verify_override_chain("r1", out) is True
    # tampering breaks the chain
    path = out / "runs" / "r1" / "audit" / "override_log.jsonl"
    lines = path.read_text(encoding="utf-8").splitlines()
    first = json.loads(lines[0])
    first["reason"] = "edited later"
    path.write_text(json.dumps(first, ensure_ascii=False) + "\n" + lines[1] + "\n", encoding="utf-8")
    assert verify_override_chain("r1", out) is False


def test_override_requires_reason_and_valid_category(tmp_path):
    with pytest.raises(ValueError):
        log_override("r1", "", "reason", {}, output_dir=tmp_path / "outputs")
    with pytest.raises(ValueError):
        log_override("r1", "dr", "reason", {}, reason_category="whatever", output_dir=tmp_path / "outputs")
