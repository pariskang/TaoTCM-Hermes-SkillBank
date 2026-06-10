from canon_tcm_hermes.demo_data import make_demo
from canon_tcm_hermes.cli import main


def test_skill_export_assets(tmp_path):
    xlsx=make_demo(tmp_path/"demo.xlsx"); out=tmp_path/"outputs"
    main(["build", "--input", str(xlsx), "--run-id", "r4", "--skill-id", "skill_a", "--output-dir", str(out)])
    skill=out/"runs"/"r4"/"skills"/"skill_a"
    assert (skill/"SKILL.md").exists()
    assert (skill/"references"/"evidence_index.jsonl").exists()
    assert (out/"runs"/"r4"/"audit"/"audit_package.json").exists()
