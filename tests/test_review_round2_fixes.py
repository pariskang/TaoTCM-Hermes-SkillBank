"""Regression tests for the second external review (P0-1..P0-8 adoption)."""
import json

import pytest

from canon_tcm_hermes.annotators.base import _extract_herbs
from canon_tcm_hermes.inference.run_inference import detect_red_flags, run_inference


def test_formula_parser_handles_classic_mahuang_text():
    text = "麻黄三两桂枝二两杏仁七十枚甘草一两，右四味，以水九升，煮取二升半，去滓，温服八合。"
    herbs = _extract_herbs(text)
    assert [(h["herb"], h["dose_original"]) for h in herbs] == [
        ("麻黄", "三两"), ("桂枝", "二两"), ("杏仁", "七十枚"), ("甘草", "一两"),
    ]
    names = {h["herb"] for h in herbs}
    for pseudo in ["右", "以水", "煮取二升", "温服", "杏仁七"]:
        assert pseudo not in names


def test_formula_parser_stops_at_preparation_without_tally():
    herbs = _extract_herbs("麻黄三两桂枝二两，以水九升，煮取三升。")
    assert [h["herb"] for h in herbs] == ["麻黄", "桂枝"]


def test_red_flags_detected_in_natural_language():
    flags = detect_red_flags(["我现在胸痛而且呼吸困难"])
    assert set(flags) == {"胸痛", "呼吸困难"}
    assert detect_red_flags(["头有点晕"], narrative="偶尔咯血") == ["咯血"]


def test_patient_red_flags_escalate_urgency():
    out = run_inference({"mode": "patient_intake", "features": ["我现在胸痛而且呼吸困难"]})
    assert out["urgency"] == "emergency_referral"
    assert "急诊" in out["visit_summary"] or "急救" in out["visit_summary"]
    routine = run_inference({"mode": "patient_intake", "features": ["无汗"]})
    assert routine["urgency"] == "routine"


@pytest.fixture(scope="module")
def demo_run(tmp_path_factory):
    from canon_tcm_hermes.cli import main
    from canon_tcm_hermes.demo_data import make_demo

    tmp_path = tmp_path_factory.mktemp("review2")
    xlsx = make_demo(tmp_path / "demo.xlsx")
    out = tmp_path / "outputs"
    main(["build", "--input", str(xlsx), "--run-id", "r_rev2", "--output-dir", str(out)])
    return out


def test_transcluded_quotation_not_counted_as_independent_evidence(demo_run):
    patterns = [json.loads(line) for line in (demo_run / "runs" / "r_rev2" / "patterns" / "pattern_aggregations.jsonl").read_text(encoding="utf-8").splitlines()]
    mahuang = next(p for p in patterns if p["pattern_name"] == "麻黄汤证")
    # the commentary row quotes the canonical clause: it must land in
    # transcluded_citations, not in the independent evidence set
    assert mahuang["transcluded_citations"], "commentary-quoted clause must be tracked as transclusion"
    assert not set(mahuang["transcluded_citations"]) & set(mahuang["evidence_segments"])
    # and its evidence entry is downgraded from E1
    evidence = [json.loads(line) for line in (demo_run / "runs" / "r_rev2" / "evidence" / "evidence_index.jsonl").read_text(encoding="utf-8").splitlines()]
    by_segment = {item["segment_id"]: item for item in evidence}
    for segment_id in mahuang["transcluded_citations"]:
        assert by_segment[segment_id]["evidence_level"] == "E3"


def test_core_coverage_gate_blocks_single_trigger_word(demo_run):
    # 麻黄汤证 core has several features; one lone hit must not qualify
    result = run_inference({"mode": "clinician_assist", "features": ["发热"]}, "r_rev2", demo_run)
    assert "麻黄汤证" not in {item["pattern"] for item in result["top_k"]}
    # a real core structure qualifies and reports its coverage
    result = run_inference({"mode": "clinician_assist", "features": ["发热", "无汗", "头痛", "喘"]}, "r_rev2", demo_run)
    top = result["top_k"][0]
    assert top["pattern"] == "麻黄汤证" and top["core_coverage"] >= 0.5


def test_no_zero_score_or_unsupported_candidates(demo_run):
    result = run_inference({"mode": "clinician_assist", "features": ["恶寒"]}, "r_rev2", demo_run)
    for item in result["top_k"]:
        assert item["score"] > 0
        assert item["supporting_features"]


def test_counterfactual_compound_flip_actually_flips(demo_run):
    report = json.loads((demo_run / "runs" / "r_rev2" / "reports" / "counterfactual_report.json").read_text(encoding="utf-8"))
    compound = next(c for c in report["counterfactual_pairs"] if "烦躁" in str(c["a"]))
    assert c_changed(compound), "compound flip must map to real features and change the ranking"
    assert report["hard_stop_consistency"] == 1.0


def c_changed(case):
    return case["changed"] is True


def test_promotion_blocked_when_validation_failed(demo_run):
    from canon_tcm_hermes.governance.promotion import promote_version

    path = demo_run / "runs" / "r_rev2" / "reports" / "validation_summary.json"
    original = path.read_text(encoding="utf-8")
    data = json.loads(original)
    data["passed"] = False
    path.write_text(json.dumps(data), encoding="utf-8")
    try:
        with pytest.raises(ValueError, match="validation did not pass"):
            promote_version("r_rev2", "expert_x", "promote", demo_run, approved_version="1.0.0", skill_id="shanghan_six_formula_cluster", second_expert_id="expert_y")
    finally:
        path.write_text(original, encoding="utf-8")


def test_citation_report_decomposes_semantics(demo_run):
    report = json.loads((demo_run / "runs" / "r_rev2" / "reports" / "citation_validation_report.json").read_text(encoding="utf-8"))
    assert report["source_integrity"] == report["verified_rate"]
    assert 0 < report["source_independence"]["unique_quote_rate"] <= 1
    assert "attribution_report" in report["claim_entailment"]
    assert report["expert_adjudication_status"] == "pending"
