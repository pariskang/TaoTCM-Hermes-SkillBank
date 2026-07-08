# TaoTCM-Hermes-SkillBank

**An agentic SkillBank AutoBuild framework for classical Chinese medicine knowledge engineering** — a genre-aware, evidence-grounded, auditable system that transforms `data.xlsx` into versionable, evolvable Hermes/Codex-compatible Skill packages for teaching and clinician-assist workflows.

Positioning (deliberate): this is a *knowledge-construction and auditable skill-generation agent framework*, *not* an autonomous clinical decision agent. The agent loop plans, acts, observes and reflects over registered pipeline tools with human-in-the-loop checkpoints; it can drive a corpus to an audit-ready skill package, and it can never promote one to stable — that decision is structurally reserved for a human expert.

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

## Agent loop (Plan → Act → Observe → Reflect)

```bash
canon agent --input data/raw/data.xlsx --run-id run001 [--goal skill_package]
canon agent-status --run-id run001
```

The agent plans dynamically over a typed tool registry (each tool declares the artifacts it requires/produces and its risk tier): satisfied steps are skipped, so interrupted runs resume where they stopped; every step is observed (annotation errors, citation failures, empty-core patterns, validation state) and reflected on (continue / retry under budget / abort with reason / pause for human). State and episodic memory persist under `outputs/runs/<run>/agent/`. Goals: `annotate_corpus`, `evidence_ready`, `eval_ready`, `skill_package`. The `promote` tool is registered as `needs_human` — invoking it through the agent always pauses the loop.

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
canon eval-attribution --run-id run001                     # counterfactual citation-faithfulness test
canon conformal --run-id run001 --alpha 0.1                # conformal prediction sets + abstention
canon calibrate-router --gold gold.jsonl --run-id run001   # micro-gold Po/kappa + span F1
canon model-card --run-id run001                           # TRIPOD-LLM-style model card
canon diff --run-id run002 --baseline run001               # delta audit vs. the last audited run
canon export --run-id run001 [--targets claude,codex,openclaw,lobechat]
canon all --input data/raw/data.xlsx --run-id run001 [--llm-baselines]
canon promote --run-id run001 --skill-id shanghan_six_formula_cluster \
      --decision promote --expert-id <id> --approved-version 1.0.0
canon rollback --run-id run002 --expert-id <id> --reason "..."   # restore previous stable package
canon log-override --run-id run001 --physician-id <id> --reason "..." \
      --reason-category safety_concern --payload '{...}'          # tamper-evident override trail
```

Engineering notes: annotation and routing are validated against strict schemas (`additionalProperties: false` — unknown fields are rejected, not tolerated); scoring weights, support-level cut points and top-k are read from the run's `inference/inference_config.yaml` (the config drives the engine); contraindication rules are extracted from `contraindication`/`mistreatment_consequence` clauses with evidence ids — never hardcoded per formula; patterns with no core features are excluded from ranking and queued for audit; the patient response is a strongly-typed structure validated against its own response schema before the lexicon scan; knowledge-graph entities are canonicalized through `configs/entity_aliases.yaml` (traditional/simplified folding + alias resolution); the LLM job store is thread-safe under concurrent annotation.

## Evolvable skill lifecycle

Every exported skill package (`outputs/runs/<run>/skills/<skill_id>/`) carries `skill.yaml` with `version`, `lineage`, and an `evolution_log`. Skills are born `auto_generated_requires_audit` at version `0.1.0` and only become `stable` through a recorded terminal human-audit decision:

```text
1. add/revise rows in data.xlsx
2. canon all --input data.xlsx --run-id <new-run>
3. canon diff --run-id <new-run> --baseline <last-promoted-run>   # optional but recommended
4. review outputs/runs/<new-run>/audit/audit_package.json
5. canon promote --run-id <new-run> --skill-id <skill> --decision promote --expert-id <id>
```

`canon diff` writes `reports/run_diff_report.json` — a delta audit against the baseline run: patterns added/removed/changed (safety-field changes flagged high priority), evidence added/removed/re-verified, and eval-metric regressions (hard-stop consistency, patient forbidden-output rate, citation rate). Rebuilding the audit package after a diff embeds the delta as `delta_since_baseline`, so the terminal human audit reviews what changed instead of re-reading the whole package. Promotion itself requires the audit package to exist and the approved version to be strictly greater than the current one.

`promote` bumps the skill version, records lineage, and appends to the evolution log; `revise`/`reject`/`disputed` are recorded without granting stable status. No automated path can mark a skill stable.

Promoted packages are protected: rebuilding a run whose skill package is already `stable` is refused (use a new run id), rebuilding an unpromoted package preserves its evolution log, and every fresh package links `lineage.parent_run` / `lineage.parent_stable_version` to the most recently promoted run of the same skill.

## Multi-platform export

`canon export` renders the built (never mutated) skill package into the targets configured in `configs/export_targets.yaml`, under `outputs/runs/<run>/exports/<target>/`:

- **claude** — Claude (Agent) Skill directory: `SKILL.md` with the frontmatter contract (hyphenated `name` ≤64 chars, `description` ≤1024), references and scripts copied verbatim.
- **codex** — Codex-style bundle mirroring this repo's `.agents/skills` convention, with an `AGENTS.md` entry file describing when/how to engage the skill.
- **openclaw** — machine-readable `openclaw.skill.json` manifest (script entrypoints, resource inventory, safety block with the effective forbidden-term lexicon) plus `prompt.md`.
- **lobechat** — `lobechat-agent.json` (identifier/meta/systemRole). LobeChat cannot run scripts, so the behavioral contract and safety rules are inlined into the system role and references ship as `knowledge/` files for RAG upload.

Every export carries a manifest recording the source skill version and status; exporting never touches `skill.yaml` or its governance state.

## Authoritative schemas and annotation guideline

- `schemas/*.schema.json` — the authoritative draft-07 genre schemas (with cross-file `$ref` into `common.schema.json`): clause/treatise/formula/herb/pulse/case/commentary/mnemonic templates plus genre segmentation. Every annotation and every route is validated against them.
- `docs/genre_guideline_v1.0.md` — 中医古籍文体分类标注规范 v1.0 (operational definitions, boundary adjudication, segmentation rules); embedded in the router prompt and shipped inside every skill package under `references/genre_guideline.md`.

## Evaluation honesty notes

- Counterfactual pairs compare ranking signatures (pattern + support level), not raw payloads, so the pass rate reflects real sensitivity to flipped features.
- Ablation baselines B0/B1/B2 are deterministic local proxies by default with **no gold-label leakage** (majority guess / lexical retrieval / structure-aware retrieval). For publication-grade studies, run `canon eval-ablation --llm-baselines` (or set `TAOTCM_LLM_BASELINES=1`) with a configured `LITELLM_MODEL`: B0 becomes a bare closed-set LLM classifier, B1 a naive-RAG prompt over lexically retrieved quotes, and B2 a graph-RAG prompt over pattern subgraphs with linked evidence. LLM-mode B1/B2 must return the evidence ids they relied on, so their hallucinated/verified citation rates are measured against the run's evidence index; metrics a system cannot produce (e.g. citation rates for the proxies, which emit no citations) are reported as `null`, not invented. Failed LLM calls fall back per-case to the deterministic proxy and are counted in `llm_fallback_cases`.
- `canon assess --run-id <run>` writes `protocol_assessment_report.json` listing remaining gaps (micro-gold calibration, expert audit, etc.). The system is not claimed stable-grade by default.
- Publication-grade reporting (see `docs/METHODS.md` for the research grounding): the ablation report carries bootstrap 95% CIs, paired permutation tests with Holm–Bonferroni correction, and a risk–coverage/AURC selective-prediction block; `canon conformal` produces distribution-free prediction sets with explicit abstention (vacuous small-n calibrations are reported as vacuous); `canon eval-attribution` tests citation *faithfulness* by intervention (feature necessity + evidence grounding), not just citation correctness; `canon calibrate-router` measures router quality against human micro-gold (Po + Cohen's κ, exact/relaxed span F1, κ≥0.8 gate); `canon model-card` renders a TRIPOD-LLM-style model card from run artifacts.

## Safety

This project does not provide patient-facing diagnosis, syndrome suggestions, formula recommendations, dosage advice, self-medication advice, or medication stop/change advice. Patient intake mode is limited to red-flag triage, structured questions, and visit summaries, and is guarded by a content-level forbidden-output check (formula/syndrome/dosage vocabulary can never appear in patient responses). The forbidden vocabulary is configurable via `configs/patient_safety_lexicon.yaml` (path overridable with `TAOTCM_PATIENT_LEXICON`), which can only **extend** the built-in floor — never remove from it; the effective lexicon ships inside every skill package as `references/safety_policy.yaml`. Dose conversion to modern units is structurally forbidden (`dose_conversion_modern.status = not_attempted`). Contraindication rules are T3 and hard-stop in the inference engine: a pattern whose hard-stop condition matches is removed from the ranked recommendations entirely and surfaced in a separate `blocked` list with its safety alerts; softer matched rules stay as alerts on the ranked results. The ablation report's patient forbidden-output rate is measured by probing each eval case through the patient path, not assumed.
