"""F8 Addendum — A-7: Concurrent Evaluation Types.

is_concurrent_safe class attribute for L4 modules. ContextModifier
callback type for deferred state modifications.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional, Protocol, runtime_checkable


@runtime_checkable
class ConcurrentSafeModule(Protocol):
    """Protocol for L4 modules that declare concurrent safety.

    Default: is_concurrent_safe = False (conservative).
    Only True modules run in Phase 1 (concurrent read-only).
    """

    is_concurrent_safe: bool


ContextModifier = Callable[[dict[str, Any]], dict[str, Any]]
"""Callback type for deferred context modifications.

If a concurrent evaluator needs to signal a context change,
it returns a ContextModifier. Callbacks are queued per-evaluator-ID
and applied in deterministic order after Phase 1. No evaluator sees
another's modifications.
"""


@dataclass(frozen=True)
class EvaluationPhaseResult:
    """Result from a single evaluation module in Phase 1."""

    module_name: str
    result: Any
    context_modifier: Optional[ContextModifier] = None
    error: Optional[str] = None
    succeeded: bool = True


@dataclass(frozen=True)
class ConcurrentEvaluationResult:
    """Aggregated result of Phase 1 concurrent evaluation."""

    phase1_results: tuple[EvaluationPhaseResult, ...]
    context_modifiers: tuple[ContextModifier, ...]
    all_succeeded: bool
    partial_results_available: bool = True
    """If one evaluator crashes but others succeed, partial results
    are available. Decision: proceed with partial or abort."""
