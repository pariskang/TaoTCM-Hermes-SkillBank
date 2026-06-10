from canon_tcm_hermes.inference.run_inference import run_inference


def test_patient_mode_forbidden_outputs_hidden():
    out = run_inference({"mode":"patient_intake","features":["无汗"]})
    text = str(out)
    assert out["forbidden_outputs_checked"] is True
    assert "麻黄汤" not in text and "证" not in text and "剂量" not in text


def test_hard_contraindication_blocks(tmp_path):
    from canon_tcm_hermes.demo_data import make_demo
    from canon_tcm_hermes.cli import main
    xlsx=make_demo(tmp_path/"demo.xlsx"); out=tmp_path/"outputs"
    main(["build", "--input", str(xlsx), "--run-id", "r3", "--output-dir", str(out)])
    result=run_inference({"mode":"clinician_assist","features":["脉微弱","汗出","恶风","无汗"]}, "r3", out)
    assert any(x["safety_alerts"] for x in result["top_k"])
