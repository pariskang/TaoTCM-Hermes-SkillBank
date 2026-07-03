import json

from canon_tcm_hermes.eval import baseline_adapters
from canon_tcm_hermes.eval.run_ablation import run_ablation
from canon_tcm_hermes.llm import litellm_client


def _build_demo(tmp_path):
    from canon_tcm_hermes.cli import main
    from canon_tcm_hermes.demo_data import make_demo

    xlsx = make_demo(tmp_path / "demo.xlsx")
    out = tmp_path / "outputs"
    main(["build", "--input", str(xlsx), "--run-id", "r_abl", "--output-dir", str(out)])
    return out


def test_llm_baselines_require_explicit_optin_and_llm(monkeypatch):
    monkeypatch.setenv("LITELLM_MODEL", "azure/test")
    monkeypatch.setenv("TAOTCM_USE_LLM", "1")
    assert baseline_adapters.llm_baselines_enabled() is False
    assert baseline_adapters.llm_baselines_enabled(True) is True
    monkeypatch.setenv("TAOTCM_LLM_BASELINES", "1")
    assert baseline_adapters.llm_baselines_enabled() is True
    monkeypatch.setenv("TAOTCM_USE_LLM", "0")
    assert baseline_adapters.llm_baselines_enabled(True) is False


def test_ablation_with_llm_adapters_measures_baseline_citations(tmp_path, monkeypatch):
    out = _build_demo(tmp_path)
    evidence_path = out / "runs" / "r_abl" / "evidence" / "evidence_index.jsonl"
    first_evidence = json.loads(evidence_path.read_text(encoding="utf-8").splitlines()[0])

    def fake_completion(settings, messages):
        return json.dumps({"patterns": ["麻黄汤证"], "citations": [first_evidence["evidence_id"], "EV_FAKE999"]}, ensure_ascii=False)

    monkeypatch.setattr(litellm_client, "_completion_text", fake_completion)
    monkeypatch.setenv("LITELLM_MODEL", "azure/test")
    monkeypatch.setenv("TAOTCM_USE_LLM", "1")
    report = run_ablation("r_abl", out, llm_baselines=True)

    assert report["baseline_mode"] == "llm_adapter"
    assert report["status"] == "completed_llm_baseline_ablation"
    b1 = report["systems"]["B1"]
    assert b1["notes"]["mode"] == "llm_adapter"
    assert b1["notes"]["llm_fallback_cases"] == 0
    # one real citation + one fabricated per case -> measured, not imputed
    assert b1["hallucinated_citation_rate"] == 0.5
    assert b1["citation_verified_rate"] == 0.5
    # bare LLM emits no citations by design
    assert report["systems"]["B0"]["hallucinated_citation_rate"] is None
    assert report["systems"]["S3"]["notes"]["mode"] == "local_system"


def test_ablation_falls_back_to_proxy_when_llm_fails(tmp_path, monkeypatch):
    out = _build_demo(tmp_path)

    def boom(settings, messages):
        raise RuntimeError("provider down")

    monkeypatch.setattr(litellm_client, "_completion_text", boom)
    monkeypatch.setenv("LITELLM_MODEL", "azure/test")
    monkeypatch.setenv("TAOTCM_USE_LLM", "1")
    monkeypatch.setenv("MAX_RETRIES", "2")
    report = run_ablation("r_abl", out, llm_baselines=True)
    b0 = report["systems"]["B0"]
    assert b0["notes"]["mode"] == "llm_adapter"
    assert b0["notes"]["llm_fallback_cases"] >= 1
    assert b0["top1_pattern_accuracy"] is not None


def test_offline_default_remains_deterministic_proxy(tmp_path):
    out = _build_demo(tmp_path)
    report = run_ablation("r_abl", out)
    assert report["baseline_mode"] == "deterministic_proxy"
    assert report["systems"]["B1"]["notes"]["mode"] == "deterministic_proxy"
    assert report["systems"]["B1"]["hallucinated_citation_rate"] is None
