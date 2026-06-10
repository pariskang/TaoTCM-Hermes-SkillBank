# TaoTCM-Hermes-SkillBank

TaoTCM-Hermes AutoBuild Protocol implementation: a genre-aware, evidence-grounded, auditable pipeline that transforms `data.xlsx` into Hermes/Codex-compatible Skill packages for classical Chinese medicine teaching and clinician-assist workflows.

## Quick start

```bash
pip install -e ".[dev]"
cp .env.example .env
python -m canon_tcm_hermes.demo_data
canon build --input data/demo/shanghan_six_formula_demo.xlsx --run-id demo001
pytest -q
canon assess --run-id demo001
```

## LiteLLM / Azure example

```bash
LITELLM_MODEL=azure/gpt-4o
AZURE_API_KEY=...
AZURE_API_BASE=https://your-resource.openai.azure.com
AZURE_API_VERSION=2024-08-01-preview
```

The pipeline ships with executable local implementations for every protocol stage, plus `src/canon_tcm_hermes/llm/litellm_client.py` as a schema-validating `call_llm_json` wrapper for production LLM annotation through LiteLLM. It is **not claimed to be perfect or stable-grade by default**: run `canon assess --run-id <run_id>` to generate `protocol_assessment_report.json`, which lists blocking gaps such as micro-gold calibration, production LLM orchestration, publication-grade baselines, and terminal human audit.

## Main commands

```bash
canon route --input data/raw/data.xlsx --run-id run001
canon annotate --run-id run001
canon validate --run-id run001
canon build-graph --run-id run001
canon build-patterns --run-id run001
canon compile-inference --run-id run001
canon build-skill --run-id run001 --skill-id shanghan_six_formula_cluster
canon build-audit --run-id run001
canon eval-counterfactual --run-id run001
canon build-eval --run-id run001
canon eval-ablation --run-id run001
canon assess --run-id run001
canon all --input data/raw/data.xlsx --run-id run001
```

## Safety

This project does not provide patient-facing diagnosis, syndrome suggestions, formula recommendations, dosage advice, self-medication advice, or medication stop/change advice. Patient intake mode is limited to red-flag triage, structured questions, and visit summaries.
