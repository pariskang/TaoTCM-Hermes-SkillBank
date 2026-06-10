---
name: canon-tcm-hermes-autobuild
description: Use this skill when implementing or modifying the CanonTCM-Hermes AutoBuild pipeline for genre-aware classical Chinese medicine text annotation, evidence validation, inference compilation, and Hermes/Codex Skill export. Do not use for direct medical advice.
---

# CanonTCM-Hermes AutoBuild Skill

## Scope

This skill guides the implementation of a reproducible AutoBuild pipeline that transforms `data.xlsx` into validated, evidence-grounded Hermes Skill packages.

## Required workflow

1. Load and normalize `data.xlsx`.
2. Generate row_id, source_id, and content_hash.
3. Run Genre Router before any annotation.
4. If mixed genre is detected, perform character-span segmentation.
5. Route each span to a dedicated annotator.
6. Validate every output against schema.
7. Build evidence_index.
8. Validate quote_span and content_hash.
9. Build cross-genre links.
10. Build pattern aggregations.
11. Compile inference_config.
12. Generate eval_cases from case_record.
13. Generate safety_policy.
14. Generate audit_package.
15. Export Codex-compatible Skill package.

## Never do

- Never bypass genre routing.
- Never infer a formula-pattern rule from materia medica or mnemonic text.
- Never use case records as direct rules.
- Never show formulas or dosage in patient_intake mode.
- Never promote a rule directly to stable.
- Never accept an LLM JSON output without schema validation.
- Never silently discard failed annotations; write them to errors.jsonl.

## Output quality gates

A run is successful only when genre routes, annotations/errors, evidence index, citation report, cross-genre report, inference config, audit package, and exported Skill assets exist.
