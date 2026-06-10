from pathlib import Path
import yaml

def load_cds_profiles(path: str | Path = "configs/cds_profiles.yaml") -> dict:
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))
