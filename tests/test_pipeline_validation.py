from canon_tcm_hermes.demo_data import make_demo
from canon_tcm_hermes.cli import main
from canon_tcm_hermes.validators.pipeline_validator import run_validation


def test_full_validation_summary(tmp_path):
    xlsx = make_demo(tmp_path / "demo.xlsx")
    out = tmp_path / "outputs"
    main(["build", "--input", str(xlsx), "--run-id", "r_val", "--output-dir", str(out)])
    report = run_validation("r_val", out)
    assert report["passed"] is True
    assert report["citation_validation"]["failed"] == 0
