import json

import pytest
import yaml

from canon_tcm_hermes.builders.hermes_skill_builder import build_skill
from canon_tcm_hermes.exporters import EXPORTERS, configured_targets, export_skill_targets


def test_configured_targets_come_from_config():
    assert set(configured_targets()) == set(EXPORTERS)


def test_export_all_targets_produces_platform_layouts(tmp_path):
    out = tmp_path / "outputs"
    build_skill("r1", "skill_a", out)
    results = export_skill_targets("r1", "skill_a", None, out)
    assert set(results) == set(EXPORTERS)
    base = out / "runs" / "r1" / "exports"

    # claude: SKILL.md frontmatter contract (hyphenated name + description)
    text = (base / "claude" / "skill-a" / "SKILL.md").read_text(encoding="utf-8")
    frontmatter = yaml.safe_load(text.split("---")[1])
    assert frontmatter["name"] == "skill-a"
    assert frontmatter["description"]
    assert (base / "claude" / "skill-a" / "references" / "safety_policy.yaml").exists()

    # codex: AGENTS.md entry + SKILL.md + scripts
    assert (base / "codex" / "skill-a" / "AGENTS.md").exists()
    assert (base / "codex" / "skill-a" / "scripts" / "run_inference.py").exists()

    # openclaw: machine-readable manifest with the effective safety lexicon
    manifest = json.loads((base / "openclaw" / "skill-a" / "openclaw.skill.json").read_text(encoding="utf-8"))
    assert manifest["schema"] == "openclaw.skill/v1"
    assert "汤" in manifest["safety"]["forbidden_patient_terms"]
    assert manifest["entrypoints"]["inference"] == "scripts/run_inference.py"
    assert (base / "openclaw" / "skill-a" / "scripts" / "run_inference.py").exists()

    # lobechat: agent json with inlined safety contract + knowledge files
    agent = json.loads((base / "lobechat" / "skill-a" / "lobechat-agent.json").read_text(encoding="utf-8"))
    assert agent["identifier"] == "skill-a"
    assert "红旗分诊" in agent["config"]["systemRole"]
    assert "dose_conversion_modern" in agent["config"]["systemRole"]
    assert (base / "lobechat" / "skill-a" / "knowledge" / "safety_policy.yaml").exists()


def test_export_never_mutates_source_package(tmp_path):
    out = tmp_path / "outputs"
    build_skill("r1", "skill_a", out)
    skill_yaml = out / "runs" / "r1" / "skills" / "skill_a" / "skill.yaml"
    before = skill_yaml.read_text(encoding="utf-8")
    export_skill_targets("r1", "skill_a", None, out)
    assert skill_yaml.read_text(encoding="utf-8") == before


def test_export_rejects_unknown_target(tmp_path):
    out = tmp_path / "outputs"
    build_skill("r1", "skill_a", out)
    with pytest.raises(ValueError, match="unknown export targets"):
        export_skill_targets("r1", "skill_a", ["slack"], out)


def test_export_requires_built_package(tmp_path):
    with pytest.raises(FileNotFoundError, match="skill package"):
        export_skill_targets("r_missing", "skill_a", ["claude"], tmp_path / "outputs")


def test_cli_export_builds_package_when_missing(tmp_path, capsys):
    from canon_tcm_hermes.cli import main

    main(["export", "--run-id", "r2", "--skill-id", "skill_b", "--output-dir", str(tmp_path / "outputs"), "--targets", "claude,lobechat"])
    printed = json.loads(capsys.readouterr().out)
    assert set(printed) == {"claude", "lobechat"}
