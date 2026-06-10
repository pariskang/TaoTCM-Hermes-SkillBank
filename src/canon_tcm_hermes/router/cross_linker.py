def infer_cross_links(route: dict) -> list[dict]:
    return route.get("cross_links", [])
