def detect_context(context: dict, rules: list[dict]) -> list[dict]:
    tokens = set(context.get("prior_interventions", [])) | set(context.get("current_state", []))
    return [r for r in rules if set(r.get("if", [])) <= tokens]
