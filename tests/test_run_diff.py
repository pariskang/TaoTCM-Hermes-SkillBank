import json

import pytest

from canon_tcm_hermes.governance.run_diff import build_run_diff


def _write_jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")


def _write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def _make_run(out, run_id, patterns, evidence, counterfactual):
    rd = out / "runs" / run_id
    _write_jsonl(rd / "patterns" / "pattern_aggregations.jsonl", patterns)
    _write_jsonl(rd / "evidence" / "evidence_index.jsonl", evidence)
    _write_json(rd / "reports" / "counterfactual_report.json", counterfactual)


BASE_PATTERN = {
    "pattern_id": "MHT_ZHENG",
    "pattern_name": "麻黄汤证",
    "core_features": ["无汗", "发热"],
    "contraindications": [{"condition": ["脉微弱"], "action": "hard_stop", "risk_tier": "T3"}],
}
BASE_EVIDENCE = {"source_id": "S1", "quote": "无汗而喘", "verification_status": "verified"}


def test_diff_detects_safety_changes_and_regressions(tmp_path):
    out = tmp_path / "outputs"
    changed_pattern = dict(BASE_PATTERN, contraindications=[])
    new_pattern = {"pattern_id": "GZT_ZHENG", "pattern_name": "桂枝汤证", "core_features": ["汗出"]}
    _make_run(out, "base", [BASE_PATTERN], [BASE_EVIDENCE], {"counterfactual_pass_rate": 0.4, "hard_stop_consistency": 1.0})
    _make_run(out, "new", [changed_pattern, new_pattern], [], {"counterfactual_pass_rate": 0.4, "hard_stop_consistency": 0.0})

    report = build_run_diff("new", "base", out)

    assert report["summary"]["patterns_added"] == 1
    assert report["summary"]["patterns_changed"] == 1
    assert report["patterns"]["changed"][0]["safety_relevant"] is True
    assert report["metric_deltas"]["hard_stop_consistency"]["regression"] is True
    assert report["summary"]["evidence_removed"] == 1
    high = [f["item"] for f in report["audit_focus"] if f["priority"] == "high"]
    assert any("safety fields changed" in item for item in high)
    assert any("hard_stop_consistency" in item for item in high)
    assert (out / "runs" / "new" / "reports" / "run_diff_report.json").exists()


def test_diff_identical_runs_reports_no_changes(tmp_path):
    out = tmp_path / "outputs"
    _make_run(out, "base", [BASE_PATTERN], [BASE_EVIDENCE], {"counterfactual_pass_rate": 0.4, "hard_stop_consistency": 1.0})
    _make_run(out, "new", [BASE_PATTERN], [BASE_EVIDENCE], {"counterfactual_pass_rate": 0.4, "hard_stop_consistency": 1.0})
    report = build_run_diff("new", "base", out)
    summary = report["summary"]
    assert summary["patterns_added"] == summary["patterns_removed"] == summary["patterns_changed"] == 0
    assert summary["metric_regressions"] == 0
    assert report["audit_focus"] == []


def test_diff_requires_existing_baseline(tmp_path):
    out = tmp_path / "outputs"
    _make_run(out, "new", [BASE_PATTERN], [BASE_EVIDENCE], {})
    with pytest.raises(FileNotFoundError, match="baseline run"):
        build_run_diff("new", "missing", out)
    with pytest.raises(ValueError, match="distinct"):
        build_run_diff("new", "new", out)


def test_cli_diff_and_audit_package_integration(tmp_path, capsys):
    from canon_tcm_hermes.cli import main
    from canon_tcm_hermes.demo_data import make_demo

    xlsx = make_demo(tmp_path / "demo.xlsx")
    out = tmp_path / "outputs"
    main(["build", "--input", str(xlsx), "--run-id", "r_base", "--output-dir", str(out)])
    main(["build", "--input", str(xlsx), "--run-id", "r_new", "--output-dir", str(out)])
    capsys.readouterr()  # drop the build stage's stdout
    main(["diff", "--run-id", "r_new", "--baseline", "r_base", "--output-dir", str(out)])
    printed = json.loads(capsys.readouterr().out)
    assert printed["summary"]["patterns_changed"] == 0
    assert printed["summary"]["metric_regressions"] == 0

    # rebuilding the audit package after a diff embeds the delta for the expert
    main(["build-audit", "--run-id", "r_new", "--output-dir", str(out)])
    package = json.loads((out / "runs" / "r_new" / "audit" / "audit_package.json").read_text(encoding="utf-8"))
    assert package["delta_since_baseline"]["baseline_run"] == "r_base"
