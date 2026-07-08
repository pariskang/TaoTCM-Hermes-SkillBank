"""Agent policies: the non-negotiable operating rules of the loop."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Policies:
    max_attempts_per_step: int = 2
    max_loop_iterations: int = 60
    # T3 / needs_human tools always stop the loop for a human decision
    never_autonomous: frozenset[str] = frozenset({"promote"})
    # observations that abort the run outright
    hard_stop_on_validation_failure: bool = True
    # observations that only warn (recorded, loop continues)
    annotation_error_warn_threshold: int = 1
    citation_failure_warn_threshold: int = 1
    empty_core_warn: bool = True
    warn_signals: tuple[str, ...] = field(default=("annotation_errors", "citation_failures", "empty_core_patterns"))
