import json
import threading

import pytest
import yaml

from canon_tcm_hermes.inference.run_inference import run_inference
from canon_tcm_hermes.io.sqlite_store import SQLiteJobStore
from canon_tcm_hermes.validators.schema_validator import schema_errors


@pytest.fixture(scope="module")
def demo_run(tmp_path_factory):
    from canon_tcm_hermes.cli import main
    from canon_tcm_hermes.demo_data import make_demo

    tmp_path = tmp_path_factory.mktemp("p0")
    xlsx = make_demo(tmp_path / "demo.xlsx")
    out = tmp_path / "outputs"
    main(["build", "--input", str(xlsx), "--run-id", "r_p0", "--output-dir", str(out)])
    return out


def test_sqlite_store_is_thread_safe(tmp_path):
    store = SQLiteJobStore(tmp_path / "progress.sqlite")
    errors = []

    def worker(index):
        try:
            for j in range(20):
                store.upsert_job(job_id=f"job{index}_{j}", run_id="r", stage="annotate", status="done", input_hash="h", prompt_version="v", schema_version="v", attempts=1, output_path="", error="", source_id="s", segment_id="g", genre="x")
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert not errors
    assert store.should_skip("job0_0", "h", "v", "v") is True


def test_inference_config_drives_scoring(demo_run):
    config_path = demo_run / "runs" / "r_p0" / "inference" / "inference_config.yaml"
    payload = {"mode": "clinician_assist", "features": ["发热", "无汗", "头痛", "喘"]}
    baseline = run_inference(payload, "r_p0", demo_run)["top_k"][0]["score"]
    cfg = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    cfg["scoring"]["weights"]["core_feature"] = 2.0
    config_path.write_text(yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False), encoding="utf-8")
    try:
        doubled = run_inference(payload, "r_p0", demo_run)["top_k"][0]["score"]
        assert doubled > baseline  # config change actually changed the engine
    finally:
        cfg["scoring"]["weights"]["core_feature"] = 1.0
        config_path.write_text(yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False), encoding="utf-8")


def test_patient_response_is_strongly_typed():
    out = run_inference({"mode": "patient_intake", "features": ["无汗", "胸痛"]})
    assert set(out) == {"mode", "red_flags", "structured_questions", "visit_summary", "forbidden_outputs_checked"}
    assert schema_errors(out, "patient_intake_response.schema.json") == []


def test_schemas_reject_additional_properties(demo_run):
    clause = json.loads((demo_run / "runs" / "r_p0" / "annotations" / "clause_templates.jsonl").read_text(encoding="utf-8").splitlines()[0])
    assert schema_errors(clause, "clause_template.schema.json") == []
    clause["smuggled_field"] = "x"
    errors = schema_errors(clause, "clause_template.schema.json")
    assert any("Additional properties" in e for e in errors)


def test_contraindications_extracted_from_clauses(demo_run):
    patterns = [json.loads(line) for line in (demo_run / "runs" / "r_p0" / "patterns" / "pattern_aggregations.jsonl").read_text(encoding="utf-8").splitlines()]
    mahuang = next(p for p in patterns if p["pattern_name"] == "麻黄汤证")
    assert mahuang["contraindications"], "contraindication must be extracted from the demo clause"
    rule = mahuang["contraindications"][0]
    assert rule["source_clause_subtype"] == "contraindication"
    assert rule["evidence_ids"] and all(eid for eid in rule["evidence_ids"])
    assert set(rule["condition"]) >= {"脉微弱", "汗出", "恶风"}
    # the contraindication clause must NOT pollute positive core features
    assert "脉微弱" not in mahuang["core_features"]


def test_empty_core_pattern_gated_from_inference(demo_run):
    patterns = [json.loads(line) for line in (demo_run / "runs" / "r_p0" / "patterns" / "pattern_aggregations.jsonl").read_text(encoding="utf-8").splitlines()]
    guizhi = next(p for p in patterns if p["pattern_name"] == "桂枝汤证")
    assert guizhi["core_features"] == []
    assert guizhi["status"] == "auto_generated_needs_review"
    result = run_inference({"mode": "clinician_assist", "features": ["发热", "无汗"]}, "r_p0", demo_run)
    assert "桂枝汤证" not in {item["pattern"] for item in result["top_k"]}
    assert "桂枝汤证" in result["excluded_needs_review"]
    # and it must be in the audit queue
    queue = [json.loads(line) for line in (demo_run / "runs" / "r_p0" / "audit" / "audit_queue.jsonl").read_text(encoding="utf-8").splitlines()]
    assert any(item["item_id"] == guizhi["pattern_id"] for item in queue)
