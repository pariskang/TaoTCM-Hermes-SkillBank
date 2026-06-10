from canon_tcm_hermes.eval.run_counterfactual_tests import run_counterfactual
from canon_tcm_hermes.demo_data import make_demo
from canon_tcm_hermes.cli import main


def test_counterfactual_report(tmp_path):
    xlsx = make_demo(tmp_path / "demo.xlsx")
    out = tmp_path / "outputs"
    main(["build", "--input", str(xlsx), "--run-id", "r_cf", "--output-dir", str(out)])
    report = run_counterfactual("r_cf", out)
    assert len(report["counterfactual_pairs"]) == 5
    assert 0 <= report["counterfactual_pass_rate"] <= 1
    assert report["hard_stop_consistency"] == 1
