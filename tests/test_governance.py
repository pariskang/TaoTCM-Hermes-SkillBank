import yaml

from canon_tcm_hermes.cli import main
from canon_tcm_hermes.demo_data import make_demo
from canon_tcm_hermes.governance.promotion import promote_version


def test_promote_evolves_skill_package(tmp_path):
    xlsx = make_demo(tmp_path / "demo.xlsx")
    out = tmp_path / "outputs"
    main(["build", "--input", str(xlsx), "--run-id", "r_gov", "--output-dir", str(out)])

    skill_yaml = out / "runs" / "r_gov" / "skills" / "shanghan_six_formula_cluster" / "skill.yaml"
    before = yaml.safe_load(skill_yaml.read_text(encoding="utf-8"))
    assert before["status"] == "auto_generated_requires_audit"
    assert before["version"] == "0.1.0"

    record = promote_version("r_gov", "expert_x", "promote", out, approved_version="1.2.0", skill_id="shanghan_six_formula_cluster", reason="ok")
    assert record["stable"] is True
    after = yaml.safe_load(skill_yaml.read_text(encoding="utf-8"))
    assert after["status"] == "stable"
    assert after["version"] == "1.2.0"
    assert after["lineage"]["parent_version"] == "0.1.0"
    assert after["evolution"]["evolution_log"][-1]["to_version"] == "1.2.0"


def test_reject_never_marks_stable(tmp_path):
    xlsx = make_demo(tmp_path / "demo.xlsx")
    out = tmp_path / "outputs"
    main(["build", "--input", str(xlsx), "--run-id", "r_gov2", "--output-dir", str(out)])
    record = promote_version("r_gov2", "expert_x", "reject", out, skill_id="shanghan_six_formula_cluster", reason="insufficient evidence")
    assert record["stable"] is False
    skill_yaml = out / "runs" / "r_gov2" / "skills" / "shanghan_six_formula_cluster" / "skill.yaml"
    meta = yaml.safe_load(skill_yaml.read_text(encoding="utf-8"))
    assert meta["status"] == "rejected"
    assert meta["version"] == "0.1.0"
