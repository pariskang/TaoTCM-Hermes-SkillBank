# TaoTCM-Hermes-SkillBank

TaoTCM-Hermes AutoBuild Protocol implementation: a genre-aware, evidence-grounded, auditable pipeline that transforms `data.xlsx` into versionable, evolvable Hermes/Codex-compatible Skill packages for classical Chinese medicine teaching and clinician-assist workflows.

```text
data.xlsx → genre routing (8 genres + mixed-span segmentation)
          → per-genre LLM/heuristic annotation (authoritative JSON Schemas)
          → evidence back-tracing (quote/span/hash verification)
          → cross-genre knowledge graph → pattern aggregation → context rules
          → inference config + ordinal inference engine
          → counterfactual + ablation evaluation
          → Hermes Skill package + audit package → terminal human audit → stable
```

## Quick start (offline, deterministic)

```bash
pip install -e ".[dev]"
cp .env.example .env
canon make-demo
canon all --input data/demo/shanghan_six_formula_demo.xlsx --run-id demo001
canon validate --run-id demo001
pytest -q
```

Without `LITELLM_MODEL`, every stage runs on deterministic heuristic annotators, so CI and offline runs always complete. All outputs land in `outputs/runs/<run-id>/`.

## LLM annotation via LiteLLM (Azure example)

Put these in `.env` (or the shell):

```bash
LITELLM_MODEL=azure/gpt-4o          # azure/<your-deployment-name>
AZURE_API_KEY=...
AZURE_API_BASE=https://your-resource.openai.azure.com
AZURE_API_VERSION=2024-08-01-preview
TAOTCM_USE_LLM=1                    # set 0 to force heuristic mode
MAX_CONCURRENCY=5
MAX_RETRIES=4
```

Then run with LLM routing + annotation:

```bash
canon all --input data/raw/data.xlsx --run-id run001 --llm
```

How LLM mode works:

- The genre router sends each row with `prompts/genre_router.md` (which embeds the v1.0 文体分类标注规范 decision rules) and gets back character-span segmentation.
- Each routed span goes to its genre prompt (`prompts/annotate_*.md`); the LLM fills semantic fields, the pipeline injects provenance (source_id, offsets, hashes), build_status, and annotation_meta, then validates against the authoritative schemas in `schemas/`.
- Retry policy: JSON parse errors retry with the parser message; schema failures retry with the validation diff; exhausted budgets fall back to the heuristic annotator with an `llm_*_failed_fallback_heuristic` flag — never silently dropped (failures land in `errors/annotation_errors.jsonl`).
- LLM annotation jobs are resumable: results are cached per segment in SQLite (`outputs/progress.sqlite`) + `annotations/cache/`, keyed by input hash, prompt version, and guideline version.
- `--llm` / `--no-llm` flags override the environment per command.

## Main commands

```bash
canon make-demo                                   # generate the demo workbook
canon route --input data/raw/data.xlsx --run-id run001 [--llm|--no-llm]
canon annotate --run-id run001 [--llm|--no-llm]
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
canon promote --run-id run001 --skill-id shanghan_six_formula_cluster \
      --decision promote --expert-id <id> --approved-version 1.0.0
```

## Evolvable skill lifecycle

Every exported skill package (`outputs/runs/<run>/skills/<skill_id>/`) carries `skill.yaml` with `version`, `lineage`, and an `evolution_log`. Skills are born `auto_generated_requires_audit` at version `0.1.0` and only become `stable` through a recorded terminal human-audit decision:

```text
1. add/revise rows in data.xlsx
2. canon all --input data.xlsx --run-id <new-run>
3. review outputs/runs/<new-run>/audit/audit_package.json
4. canon promote --run-id <new-run> --skill-id <skill> --decision promote --expert-id <id>
```

`promote` bumps the skill version, records lineage, and appends to the evolution log; `revise`/`reject`/`disputed` are recorded without granting stable status. No automated path can mark a skill stable.

Promoted packages are protected: rebuilding a run whose skill package is already `stable` is refused (use a new run id), rebuilding an unpromoted package preserves its evolution log, and every fresh package links `lineage.parent_run` / `lineage.parent_stable_version` to the most recently promoted run of the same skill.

## Authoritative schemas and annotation guideline

- `schemas/*.schema.json` — the authoritative draft-07 genre schemas (with cross-file `$ref` into `common.schema.json`): clause/treatise/formula/herb/pulse/case/commentary/mnemonic templates plus genre segmentation. Every annotation and every route is validated against them.
- `docs/genre_guideline_v1.0.md` — 中医古籍文体分类标注规范 v1.0 (operational definitions, boundary adjudication, segmentation rules); embedded in the router prompt and shipped inside every skill package under `references/genre_guideline.md`.

## Evaluation honesty notes

- Counterfactual pairs compare ranking signatures (pattern + support level), not raw payloads, so the pass rate reflects real sensitivity to flipped features.
- Ablation baselines B0/B1/B2 are deterministic local proxies with **no gold-label leakage** (majority guess / lexical retrieval / structure-aware retrieval). Replace them with real bare-LLM / naive-RAG / GraphRAG adapters for publication-grade studies; metrics that a baseline cannot produce (e.g. citation rates for systems that emit no citations) are reported as `null`, not invented.
- `canon assess --run-id <run>` writes `protocol_assessment_report.json` listing remaining gaps (micro-gold calibration, expert audit, etc.). The system is not claimed stable-grade by default.

## Safety

This project does not provide patient-facing diagnosis, syndrome suggestions, formula recommendations, dosage advice, self-medication advice, or medication stop/change advice. Patient intake mode is limited to red-flag triage, structured questions, and visit summaries, and is guarded by a content-level forbidden-output check (formula/syndrome/dosage vocabulary can never appear in patient responses). Dose conversion to modern units is structurally forbidden (`dose_conversion_modern.status = not_attempted`). Contraindication rules are T3 and hard-stop in the inference engine.
