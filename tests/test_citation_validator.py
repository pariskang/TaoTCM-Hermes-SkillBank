from pathlib import Path
from canon_tcm_hermes.demo_data import make_demo
from canon_tcm_hermes.cli import main


def test_citation_back_to_source(tmp_path):
    xlsx = make_demo(tmp_path / "demo.xlsx")
    out = tmp_path / "outputs"
    main(["build", "--input", str(xlsx), "--run-id", "r1", "--output-dir", str(out)])
    report = (out / "runs" / "r1" / "reports" / "citation_validation_report.json").read_text(encoding="utf-8")
    assert '"failed": 0' in report
