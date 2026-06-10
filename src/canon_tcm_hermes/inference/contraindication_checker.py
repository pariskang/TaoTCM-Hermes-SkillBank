def hard_stops(features: set[str], contraindications: list[dict]) -> list[dict]:
    return [c for c in contraindications if set(c.get("condition", [])) <= features and c.get("action") == "hard_stop"]
