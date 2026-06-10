def normalize_features(features: list[str]) -> list[str]:
    return [f.replace("發", "发").replace("惡", "恶").replace("無", "无").replace("脈", "脉") for f in features]
