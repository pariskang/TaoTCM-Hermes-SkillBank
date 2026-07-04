# Evaluation & Reliability Methods

This document maps each publication-grade mechanism in the pipeline to the
research it is grounded in, and states the honesty caveats that apply.
Everything below runs deterministically offline; nothing requires an LLM.

## 1. Statistical reporting protocol

**Implementation**: `eval/statistics.py`, embedded in `reports/ablation_report.json` (`statistics` block).

- Percentile bootstrap 95% CIs (B=2000, seed=13) over per-case scores for every system.
- Paired sign-flip permutation tests (R=5000, add-one smoothed per Phipson & Smyth) for S3-vs-each-system top-1 deltas.
- Holm–Bonferroni step-down correction across the multi-system comparisons, so "S3 is better" claims survive a multiple-comparison guard.

Grounding: MedHELM's bootstrap-CI reporting standard (arXiv 2505.23802); paired-bootstrap + sign-flip + Holm–Bonferroni anti-overclaiming protocol ("When +1% Is Not Enough", arXiv 2511.19794); NLP significance-testing guidance (Dror et al., ACL 2018).

Caveat (reported in the artifact itself): with few eval cases the intervals are wide and tests inconclusive by design; expand the case corpus before making claims.

## 2. Conformal prediction with explicit abstention

**Implementation**: `inference/conformal.py`; `canon conformal --alpha 0.1`; `reports/conformal_report.json`.

Split conformal calibration over labeled eval cases; nonconformity = score margin between the top-ranked and the true pattern. Prediction sets carry a distribution-free marginal coverage target (1 − α) under exchangeability. Abstention is explicit and first-class: empty sets, uninformative full sets, and vacuous calibrations (n < ⌈1/α⌉ − 1) all surface `abstained: true` with a reason and a `defer_to_human_expert` recommendation.

Grounding: split conformal for black-box predictors (Vovk et al.; Angelopoulos & Bates 2023); conformal uncertainty for LLM outputs (ConU, arXiv 2407.00499); clinical-abstention benchmarking showing explicit abstention options are required to elicit safe behavior (MedAbstain, arXiv 2601.12471).

Caveats reported: demo-scale calibration sets are vacuous and say so; in-sample coverage is labeled in-sample, not a test-set claim; coverage ≠ downstream clinical utility (arXiv 2503.11709).

## 3. Selective prediction (risk–coverage)

**Implementation**: `risk_coverage_curve` in `eval/statistics.py`; `selective_prediction_s3` block of the ablation report.

Cases are ordered by the engine's confidence signal (top-1 minus top-2 score margin); we report the full risk–coverage curve and AURC. This measures whether the engine's confidence is informative — i.e. whether answering only the most confident X% actually lowers error.

Grounding: selective risk / RC-curve / AURC lineage (Geifman & El-Yaniv); specialty-stratified clinical calibration benchmarks (arXiv 2506.10769).

## 4. Attribution faithfulness by intervention

**Implementation**: `eval/run_attribution.py`; `canon eval-attribution`; `reports/attribution_report.json`.

Citation *correctness* (quote exists, span and hash verify — `citation_validator`) is necessary but not sufficient: a system can answer from prior knowledge and decorate with citations. Because the inference engine is symbolic, faithfulness is directly testable by intervention:

- **Feature necessity**: remove each supporting feature and check whether the top pattern or its score changes. Decorative features fail.
- **Evidence grounding**: each cited quote must contain at least one supporting feature of the pattern it allegedly supports.

Grounding: correctness-vs-faithfulness distinction in RAG attribution (SIGIR ICTIR 2025); counterfactual attribution by evidence removal (RAGonite, arXiv 2412.10571); AIS attribution framework (Rashkin et al., TACL); ALCE citation precision/recall (Gao et al., EMNLP 2023).

## 5. Router micro-gold calibration

**Implementation**: `validators/router_calibration.py`; `canon calibrate-router --gold <jsonl>`; `reports/router_calibration_report.json`.

Row-level primary-genre agreement is reported as observed agreement Po **and** Cohen's κ together (κ alone is distorted under label imbalance — the kappa paradox). Span agreement is reported as exact F1 and boundary-tolerant relaxed F1 (same genre, IoU ≥ 0.5). A κ ≥ 0.8 high-stakes gate (Krippendorff's threshold convention) is evaluated explicitly; the protocol assessor lists this calibration as the first blocking gap before stable grade.

Grounding: inter-coder agreement canon (Artstein & Poesio, CL 2008); exact/relaxed span agreement practice (PICO spans, arXiv 1904.09557); boundary-tolerant segmentation metrics (Fournier & Inkpen, ACL 2013).

## 6. TRIPOD-LLM-style model card

**Implementation**: `governance/model_card.py`; `canon model-card`; `reports/model_card.md` + shipped into the skill package as `references/MODEL_CARD.md`.

Auto-generated from run artifacts only (absent artifacts are reported absent, never invented): intended use, data provenance, LLM/prompt configuration with content-hashed prompt fingerprints, metrics with CIs, uncertainty/abstention behavior, attribution faithfulness, annotation-quality calibration, error-case analysis, governance state, limitations from the protocol self-assessment, and reproducibility notes.

Grounding: TRIPOD-LLM reporting statement (Nature Medicine 2025); Model Cards (Mitchell et al., FAccT 2019); Datasheets for Datasets (Gebru et al., CACM 2021); CONSORT-AI's error-case-analysis requirement (Nature Medicine 2020).

## Known gaps this document does not paper over

- The demo corpus is tiny; every statistical artifact says so in its own caveat field.
- Conformal calibration and evaluation currently use the same cases (in-sample); split them for test-set claims.
- Micro-gold router calibration needs 100–150 human-adjudicated rows (protocol requirement) — the harness is ready, the gold data is not.
- LLM-annotation debiasing for corpus-level statistics (PPI / design-based semi-supervised inference, Science 2023) is a recommended next step once a human micro-gold subset exists.
