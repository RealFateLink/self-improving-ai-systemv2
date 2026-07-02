"""intent_interpreter.py — Transforms TaskSpec into Directive.

Stage 1 of the 13-stage pipeline.

Benchmark-anonymous handling: field suppression when CycleContext.is_benchmark=True.
All modules return Result[ModuleResult[T], ModuleError].
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

__all__ = ["IntentInterpreter", "Directive"]

# ── Benchmark field suppression list ─────────────────────────────────────────
_BENCHMARK_SUPPRESS_FIELDS = frozenset({
    "source_repo", "author", "origin_url", "benchmark_id_hint",
    "known_solution_path",
})


@dataclass(frozen=True)
class Directive:
    """Interpreted task intent for downstream modules."""
    task_id: str
    objective: str
    constraints: list[str]
    language: str
    domain: str
    track_id: str
    difficulty: str
    context_hints: dict[str, Any] = field(default_factory=dict)
    is_benchmark: bool = False
    suppressed_fields: frozenset[str] = frozenset()

    @property
    def effective_constraints(self) -> list[str]:
        """Constraints excluding benchmark-suppressed items."""
        return [c for c in self.constraints if c not in self.suppressed_fields]


@dataclass(frozen=True)
class ModuleResult:
    """Standard result envelope for Layer 4 modules."""
    primary: Any
    proposals: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[dict[str, Any]] = field(default_factory=list)
    lifecycle_signals: list[dict[str, Any]] = field(default_factory=list)
    recoverability: str = "RECOVERABLE"  # RECOVERABLE | FATAL | INFRASTRUCTURE


@dataclass(frozen=True)
class ModuleError:
    """Standard error envelope for Layer 4 modules."""
    error_type: str  # RECOVERABLE | FATAL | INFRASTRUCTURE
    message: str
    partial_envelope: ModuleResult | None = None
    is_retryable: bool = False


@dataclass
class IntentInterpreter:
    """Transforms a TaskSpec into a Directive consumed by downstream modules.

    In benchmark mode (CycleContext.is_benchmark=True), suppresses fields
    that could leak benchmark identity into the learning pipeline.
    """

    config: dict[str, Any] = field(default_factory=dict)

    def interpret(
        self,
        task_spec: dict[str, Any],
        cycle_context: dict[str, Any],
    ) -> tuple[bool, ModuleResult | ModuleError]:
        """Main entry point.

        Args:
            task_spec: Raw task specification dict.
            cycle_context: CycleContext fields.

        Returns:
            (True, ModuleResult) on success, (False, ModuleError) on failure.
        """
        try:
            is_benchmark = cycle_context.get("is_benchmark", False)
            suppressed = frozenset()

            if is_benchmark:
                suppressed = _BENCHMARK_SUPPRESS_FIELDS
                task_spec = self._sanitize_for_benchmark(task_spec)

            directive = Directive(
                task_id=task_spec.get("task_id", ""),
                objective=task_spec.get("objective", task_spec.get("description", "")),
                constraints=self._extract_constraints(task_spec),
                language=task_spec.get("language", cycle_context.get("language", "python")),
                domain=task_spec.get("domain", ""),
                track_id=cycle_context.get("domain_track", ""),
                difficulty=task_spec.get("difficulty", "F1"),
                context_hints=self._extract_hints(task_spec, cycle_context),
                is_benchmark=is_benchmark,
                suppressed_fields=suppressed,
            )

            proposals: list[dict[str, Any]] = []
            warnings: list[dict[str, Any]] = []

            # Warn if task has no clear objective.
            if not directive.objective:
                warnings.append({
                    "type": "MISSING_OBJECTIVE",
                    "severity": "CAUTION",
                    "message": f"Task {directive.task_id} has no objective.",
                })

            return True, ModuleResult(
                primary=directive,
                proposals=proposals,
                warnings=warnings,
            )

        except Exception as exc:
            return False, ModuleError(
                error_type="RECOVERABLE",
                message=f"Intent interpretation failed: {exc}",
                is_retryable=True,
            )

    def _sanitize_for_benchmark(self, task_spec: dict[str, Any]) -> dict[str, Any]:
        """Remove benchmark-identifying fields."""
        sanitized = dict(task_spec)
        for field_name in _BENCHMARK_SUPPRESS_FIELDS:
            sanitized.pop(field_name, None)
        return sanitized

    def _extract_constraints(self, task_spec: dict[str, Any]) -> list[str]:
        """Extract constraints from task spec."""
        constraints = task_spec.get("constraints", [])
        if isinstance(constraints, str):
            constraints = [c.strip() for c in constraints.split(";") if c.strip()]
        return constraints

    def _extract_hints(
        self,
        task_spec: dict[str, Any],
        cycle_context: dict[str, Any],
    ) -> dict[str, Any]:
        """Build context hints for downstream modules."""
        return {
            "readiness_mode": cycle_context.get("readiness_mode", "FULL"),
            "generation_intensity": cycle_context.get("generation_intensity", "NORMAL"),
            "economy_mode": cycle_context.get("economy_mode", False),
            "overnight": cycle_context.get("overnight", False),
            "collaboration_mode": cycle_context.get("collaboration_mode", "SOLO"),
            "existing_code": task_spec.get("existing_code"),
            "test_suite": task_spec.get("tests"),
        }
