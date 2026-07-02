from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


@pytest.fixture(autouse=True)
def _force_heuristic_mode(monkeypatch):
    """Keep the suite deterministic even when the developer's shell or .env
    (loaded by the CLI entry point) configures a real LLM provider."""
    monkeypatch.setenv("TAOTCM_USE_LLM", "0")
