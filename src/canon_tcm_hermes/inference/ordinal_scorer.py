def score(core_matches: int, common_matches: int, counters: int = 0) -> float:
    return core_matches * 1.0 + common_matches * 0.5 - counters
