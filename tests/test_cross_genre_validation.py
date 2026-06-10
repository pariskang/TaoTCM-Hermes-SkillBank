from canon_tcm_hermes.validators.cross_genre_validator import validate_cross_genre
from canon_tcm_hermes.demo_data import make_demo
from canon_tcm_hermes.cli import main


def test_cross_genre_report_exists(tmp_path):
    xlsx=make_demo(tmp_path/"demo.xlsx"); out=tmp_path/"outputs"
    main(["build", "--input", str(xlsx), "--run-id", "r2", "--output-dir", str(out)])
    report=validate_cross_genre("r2", out)
    assert report["checked"] is True
