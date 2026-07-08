from __future__ import annotations
from pathlib import Path
import yaml
from canon_tcm_hermes.utils import atomic_write_text, run_dir

def build_inference_config(run_id: str, skill_id: str = "shanghan_six_formula_cluster", output_dir: str | Path = "outputs") -> dict:
    cfg = {
        "skill_id": skill_id,
        "scoring": {
            "method": "ordinal_interval",
            # weights actually consumed by run_inference (config-driven, not hardcoded)
            "weights": {
                "core_feature": 1.0,
                "common_feature": 0.5,
                "optional_feature": 0.2,
                "hard_counter": -1.0,
                "soft_counter": -0.5,
                "soft_alert": -1.0,
            },
            # ordinal support-level cut points on the weighted score
            "support_levels": {"high": 2.0, "medium": 1.0},
            # documentation intervals for expert review of the weight bands
            "core_feature": [0.75, 1.0],
            "common_feature": [0.40, 0.75],
            "optional_feature": [0.10, 0.40],
            "soft_counter": [-0.70, -0.40],
            "hard_counter": "hard_block",
            "contraindication": "hard_stop",
        },
        "ranking": {"output_top_k": 3, "require_missing_info_report": True, "sensitivity_analysis": True},
        "compound_feature_policy": {"default": "compound_as_unit", "split_only_if_marked": True},
        "context": {"use_course_day": True, "use_prior_interventions": True, "use_state_transition_rules": True},
        "patient_visibility": {"show_syndrome": False, "show_formula": False, "show_dosage": False, "show_treatment_principle": False},
    }
    atomic_write_text(run_dir(run_id, output_dir)/"inference"/"inference_config.yaml", yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False))
    return cfg
