import json

import pytest

from canon_tcm_hermes.eval.statistics import bootstrap_ci, holm_bonferroni, paired_permutation_test, risk_coverage_curve


def test_bootstrap_ci_is_deterministic_and_bounded():
    values = [1.0, 0.0, 1.0, 1.0, 0.0, 1.0, 1.0, 1.0]
    ci_a = bootstrap_ci(values)
    ci_b = bootstrap_ci(values)
    assert ci_a == ci_b
    assert 0.0 <= ci_a["lo"] <= ci_a["mean"] <= ci_a["hi"] <= 1.0


def test_permutation_test_detects_clear_difference_and_ties():
    better = [1.0] * 12
    worse = [0.0] * 12
    result = paired_permutation_test(better, worse)
    assert result["delta"] == 1.0
    assert result["p_value"] < 0.05
    tie = paired_permutation_test(better, better)
    assert tie["p_value"] == 1.0


def test_holm_bonferroni_is_monotone_and_conservative():
    corrected = holm_bonferroni({"a": 0.001, "b": 0.04, "c": 0.9})
    assert corrected["a"]["significant"] is True
    assert corrected["c"]["significant"] is False
    assert corrected["a"]["p_adjusted"] <= corrected["b"]["p_adjusted"] <= corrected["c"]["p_adjusted"]


def test_risk_coverage_curve_orders_by_confidence():
    # confident cases correct, unconfident wrong -> selective risk rises with coverage
    curve = risk_coverage_curve([1.0, 1.0, 0.0, 0.0], [0.9, 0.8, 0.2, 0.1])
    assert curve["points"][0]["selective_risk"] == 0.0
    assert curve["points"][-1]["selective_risk"] == 0.5
    assert curve["aurc"] is not None and 0.0 <= curve["aurc"] <= 0.5


@pytest.fixture(scope="module")
def demo_run(tmp_path_factory):
    from canon_tcm_hermes.cli import main
    from canon_tcm_hermes.demo_data import make_demo

    tmp_path = tmp_path_factory.mktemp("pubgrade")
    xlsx = make_demo(tmp_path / "demo.xlsx")
    out = tmp_path / "outputs"
    main(["build", "--input", str(xlsx), "--run-id", "r_pub", "--output-dir", str(out)])
    return out


def test_ablation_report_carries_statistics_block(demo_run):
    report = json.loads((demo_run / "runs" / "r_pub" / "reports" / "ablation_report.json").read_text(encoding="utf-8"))
    stats = report["statistics"]
    assert stats["n_cases"] >= 1
    assert "S3" in stats["top1_ci95"]
    assert set(stats["s3_vs_others_top1"]) == {"B0", "B1", "B2", "S1", "S2"}
    for comparison in stats["s3_vs_others_top1"].values():
        assert "p_adjusted" in comparison and "significant" in comparison
    assert report["selective_prediction_s3"]["aurc"] is not None


def test_conformal_report_honest_about_small_n(demo_run):
    report = json.loads((demo_run / "runs" / "r_pub" / "reports" / "conformal_report.json").read_text(encoding="utf-8"))
    calibration = report["calibration"]
    # demo has ~1 eval case: the guarantee must be reported vacuous, not faked
    if calibration["n_calibration"] < calibration["min_n_for_nonvacuous"]:
        assert calibration["vacuous"] is True
        assert all(case["abstained"] for case in report["cases"])
    assert (demo_run / "runs" / "r_pub" / "inference" / "conformal_calibration.json").exists()


def test_attribution_report_measures_faithfulness(demo_run):
    report = json.loads((demo_run / "runs" / "r_pub" / "reports" / "attribution_report.json").read_text(encoding="utf-8"))
    assert report["n_cases"] >= 1
    assert report["feature_necessity_rate"] is not None
    assert 0.0 <= report["feature_necessity_rate"] <= 1.0
    assert report["evidence_grounding_rate"] is not None


def test_model_card_generated_with_key_sections(demo_run):
    card = (demo_run / "runs" / "r_pub" / "reports" / "model_card.md").read_text(encoding="utf-8")
    for heading in ["Intended use", "Uncertainty & abstention", "Attribution faithfulness", "Error-case analysis", "Limitations", "Reproducibility"]:
        assert heading in card
    assert (demo_run / "runs" / "r_pub" / "skills" / "shanghan_six_formula_cluster" / "references" / "MODEL_CARD.md").exists()


def test_router_micro_gold_calibration(tmp_path):
    from canon_tcm_hermes.validators.router_calibration import calibrate_router

    gold = tmp_path / "gold.jsonl"
    rows = [
        {"content": "太阳病，头痛发热，无汗而喘者，麻黄汤主之。", "book": "伤寒论", "chapter": "太阳病", "segments": [{"span": [0, 20], "genre": "canonical_clause"}]},
        {"content": "麻黄，味苦温，主中风伤寒头痛，无毒。", "book": "本经", "chapter": "", "segments": [{"span": [0, 18], "genre": "materia_medica"}]},
        {"content": "浮脉，举之有余，按之不足。", "book": "脉经", "chapter": "", "segments": [{"span": [0, 13], "genre": "pulse_text"}]},
    ]
    gold.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    report = calibrate_router(gold, use_llm=False)
    assert report["n_rows"] == 3
    assert report["primary_genre"]["observed_agreement_po"] == 1.0
    assert report["primary_genre"]["cohen_kappa"] == 1.0
    assert report["spans"]["relaxed_f1"] is not None
    assert report["calibration_gate"]["passed"] is True
