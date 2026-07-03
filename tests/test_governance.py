import pytest
import yaml

from canon_tcm_hermes.builders.hermes_skill_builder import build_skill
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


def _skill_meta(package_dir):
    return yaml.safe_load((package_dir / "skill.yaml").read_text(encoding="utf-8"))


def _stub_audit_package(out, run_id):
    audit = out / "runs" / run_id / "audit"
    audit.mkdir(parents=True, exist_ok=True)
    (audit / "audit_package.json").write_text("{}", encoding="utf-8")


def test_build_skill_refuses_to_overwrite_stable_package(tmp_path):
    out = tmp_path / "outputs"
    build_skill("r1", "skill_a", out)
    _stub_audit_package(out, "r1")
    promote_version("r1", "expert_x", "promote", out, approved_version="1.0.0", skill_id="skill_a")
    with pytest.raises(RuntimeError, match="stable"):
        build_skill("r1", "skill_a", out)
    meta = _skill_meta(out / "runs" / "r1" / "skills" / "skill_a")
    assert meta["status"] == "stable"
    assert meta["version"] == "1.0.0"


def test_rebuild_preserves_evolution_log_and_requires_new_audit(tmp_path):
    out = tmp_path / "outputs"
    build_skill("r1", "skill_a", out)
    _stub_audit_package(out, "r1")
    promote_version("r1", "expert_x", "reject", out, skill_id="skill_a", reason="needs work")
    package = build_skill("r1", "skill_a", out)
    meta = _skill_meta(package)
    assert meta["status"] == "auto_generated_requires_audit"
    assert meta["evolution"]["evolution_log"][-1]["decision"] == "reject"


def test_new_run_lineage_links_latest_promoted_run(tmp_path):
    out = tmp_path / "outputs"
    build_skill("r1", "skill_a", out)
    _stub_audit_package(out, "r1")
    promote_version("r1", "expert_x", "promote", out, approved_version="1.0.0", skill_id="skill_a")
    package = build_skill("r2", "skill_a", out)
    meta = _skill_meta(package)
    assert meta["status"] == "auto_generated_requires_audit"
    assert meta["version"] == "0.1.0"
    assert meta["lineage"]["built_from_run"] == "r2"
    assert meta["lineage"]["parent_run"] == "r1"
    assert meta["lineage"]["parent_stable_version"] == "1.0.0"


def test_promote_requires_audit_package(tmp_path):
    out = tmp_path / "outputs"
    build_skill("r1", "skill_a", out)
    with pytest.raises(FileNotFoundError, match="audit package"):
        promote_version("r1", "expert_x", "promote", out, approved_version="1.0.0", skill_id="skill_a")


def test_promote_requires_version_increase(tmp_path):
    out = tmp_path / "outputs"
    build_skill("r1", "skill_a", out)
    _stub_audit_package(out, "r1")
    with pytest.raises(ValueError, match="greater than current version"):
        promote_version("r1", "expert_x", "promote", out, approved_version="0.1.0", skill_id="skill_a")
    meta = _skill_meta(out / "runs" / "r1" / "skills" / "skill_a")
    assert meta["status"] == "auto_generated_requires_audit"


def test_lineage_has_no_parent_without_promoted_run(tmp_path):
    out = tmp_path / "outputs"
    package = build_skill("r1", "skill_a", out)
    meta = _skill_meta(package)
    assert meta["lineage"]["parent_run"] is None
    assert meta["lineage"]["parent_stable_version"] is None
