# AGENTS.md

## Project overview

This repository implements CanonTCM-Hermes AutoBuild Protocol, a genre-aware pipeline that transforms classical Chinese medical texts from data.xlsx into evidence-grounded Hermes Skill packages.

The pipeline is AutoBuild-first and Human-Audit-last:
1. Load data.xlsx.
2. Route text by genre.
3. Annotate each genre with dedicated JSON Schema.
4. Validate evidence and citations.
5. Build cross-genre knowledge assets.
6. Compile inference configs.
7. Generate Hermes/Codex-compatible Skill packages.
8. Produce audit_package for terminal expert review.

## Core principles

- Never treat all texts as canonical clauses.
- Always run genre routing before annotation.
- Never generate clinical advice for patients.
- Patient mode can only produce red-flag triage, structured intake, and visit summaries.
- Formula, dosage, syndrome, treatment principle, and herb recommendation must be hidden in patient_intake mode.
- Every rule must bind to source_id, quote_span, and content_hash.
- Every LLM output must pass JSON Schema validation.
- Never promote auto-generated rules to stable without audit_package.

## Setup

Use Python 3.11+.

Install dependencies:

```bash
pip install -e ".[dev]"
```

Create environment file:

```bash
cp .env.example .env
```

## Main commands

Run full demo:

```bash
python -m canon_tcm_hermes.demo_data
canon build --input data/demo/shanghan_six_formula_demo.xlsx --run-id demo001
```

Run only genre routing:

```bash
canon route --input data/raw/data.xlsx --run-id route001
```

Run annotation:

```bash
canon annotate --run-id route001
```

Run validation:

```bash
canon validate --run-id route001
```

Build skill package:

```bash
canon build-skill --run-id route001 --skill-id shanghan_six_formula_cluster
```

Run tests:

```bash
pytest -q
```

Run ablation:

```bash
canon eval-ablation --run-id route001
```

## Code style

* Use typed Python.
* Use pydantic or jsonschema for output validation.
* Store all intermediate outputs as jsonl.
* Use SQLite for job status and resume.
* Never overwrite a previous run; every run has run_id.
* Use atomic file writes.

## Safety constraints

* No patient-facing syndrome suggestions.
* No patient-facing formula suggestions.
* No dosage conversion.
* No instruction to self-medicate.
* No drug stopping or switching advice.
* All safety-critical rules are T3 and require terminal expert audit.

## Testing requirements

Before completing a change, run:

```bash
pytest -q
canon validate --run-id demo001
```

## Protocol-completeness transparency

Use `canon assess --run-id <run_id>` to generate a protocol assessment report. Do not claim the system is perfect or stable-grade merely because all stages have executable local implementations; stable release promotion requires micro-gold calibration where applicable, production LLM/run validation where applicable, and terminal human audit.
