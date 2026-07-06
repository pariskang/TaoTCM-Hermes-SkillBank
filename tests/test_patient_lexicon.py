import pytest

from canon_tcm_hermes.inference.run_inference import (
    FORBIDDEN_PATIENT_KEYS,
    FORBIDDEN_PATIENT_TERMS,
    _assert_patient_safe,
    patient_forbidden_keys,
    patient_forbidden_terms,
    run_inference,
)


def test_config_extends_builtin_floor(tmp_path):
    cfg = tmp_path / "lex.yaml"
    cfg.write_text("forbidden_terms: [特制药膏X]\nforbidden_keys: [secret_key]\n", encoding="utf-8")
    terms = patient_forbidden_terms(cfg)
    assert set(FORBIDDEN_PATIENT_TERMS) <= set(terms)
    assert "特制药膏X" in terms
    keys = patient_forbidden_keys(cfg)
    assert FORBIDDEN_PATIENT_KEYS <= set(keys)
    assert "secret_key" in keys


def test_config_cannot_remove_builtin_terms(tmp_path):
    cfg = tmp_path / "lex.yaml"
    cfg.write_text("forbidden_terms: []\nforbidden_keys: []\n", encoding="utf-8")
    assert set(FORBIDDEN_PATIENT_TERMS) <= set(patient_forbidden_terms(cfg))
    assert FORBIDDEN_PATIENT_KEYS <= set(patient_forbidden_keys(cfg))


def test_repo_lexicon_extends_guard():
    # 宜服 comes from configs/patient_safety_lexicon.yaml, not the built-ins
    assert "宜服" not in FORBIDDEN_PATIENT_TERMS
    assert "宜服" in patient_forbidden_terms()
    with pytest.raises(ValueError, match="leaked"):
        _assert_patient_safe({"visit_summary": "宜服某物"})


def test_env_var_overrides_lexicon_path(monkeypatch, tmp_path):
    cfg = tmp_path / "custom.yaml"
    cfg.write_text("forbidden_terms: [自定义禁词]\n", encoding="utf-8")
    monkeypatch.setenv("TAOTCM_PATIENT_LEXICON", str(cfg))
    assert "自定义禁词" in patient_forbidden_terms()


def test_patient_mode_output_stays_clean_with_extended_lexicon():
    out = run_inference({"mode": "patient_intake", "features": ["无汗"]})
    assert out["forbidden_outputs_checked"] is True
