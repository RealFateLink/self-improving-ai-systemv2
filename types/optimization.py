"""
optimization.py — Optimization and Refactoring Types
=====================================================
Defines data types for the optimization subsystem: briefs describing what
to optimize, results capturing measured improvements, candidates holding
proposed implementations, and refactor suggestions for code quality work.

All classes are pure data definitions (dataclasses).
Frozen dataclasses are immutable value objects.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .enums import OptimizationDimension, EngineeringTrack

__all__ = [
    "OptimizationBrief",
    "OptimizationResult",
    "OptimizationCandidate",
    "RefactorSuggestion",
]


# ---------------------------------------------------------------------------
# Optimization Brief
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class OptimizationBrief:
    """
    Immutable specification describing an optimization request.

    An ``OptimizationBrief`` is created at the start of an optimization
    pass and used to guide LLM calls and candidate generation.  It records
    the current state of metrics, desired targets, hard constraints, and
    any cross-track opportunities identified by the planner.

    Attributes:
        brief_id: Unique identifier for this brief.
        task_id: The task whose solution is being optimized.
        cycle_number: Training cycle in which this brief was created.
        dimensions: Ordered list of ``OptimizationDimension`` values
            indicating which axes to optimize (highest priority first).
        current_metrics: Snapshot of metric name → value before
            optimization (e.g. ``{"runtime_ms": 450.0}``).
        target_metrics: Desired metric name → value after optimization
            (e.g. ``{"runtime_ms": 200.0}``).
        constraints: Hard constraints that must not be violated during
            optimization (e.g. ``["must pass all unit tests"]``).
        context: Free-text additional context passed to the LLM (e.g.
            language, framework, known bottlenecks).
        model_used: Identifier of the LLM used to generate candidates for
            this brief.
        per_track_priorities: Mapping of ``EngineeringTrack`` string value
            → ordered list of dimension strings, allowing track-specific
            priority overrides.
        cross_track_opportunities: List of dicts describing optimizations
            that may benefit multiple engineering tracks simultaneously.
    """

    brief_id: str
    task_id: str
    cycle_number: int
    dimensions: list[OptimizationDimension] = field(default_factory=list)
    current_metrics: dict[str, float] = field(default_factory=dict)
    target_metrics: dict[str, float] = field(default_factory=dict)
    constraints: list[str] = field(default_factory=list)
    context: str = ""
    model_used: str = ""
    per_track_priorities: dict[str, list] = field(default_factory=dict)
    cross_track_opportunities: list[dict] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Optimization Result
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class OptimizationResult:
    """
    Immutable record of a single optimization outcome along one dimension.

    Created after executing and measuring an ``OptimizationCandidate``.
    One result is produced per dimension per optimization attempt.

    Attributes:
        result_id: Unique identifier for this result record.
        brief_id: The brief that initiated this optimization.
        task_id: The task whose solution was optimized.
        cycle_number: Training cycle in which the result was measured.
        dimension: The optimization dimension this result measures.
        before_value: Metric value before the optimization was applied.
        after_value: Metric value after the optimization was applied.
        improvement_percent: Percentage improvement
            ``((before - after) / before * 100)`` for cost metrics or
            ``((after - before) / before * 100)`` for quality metrics.
            Positive values always indicate improvement.
        approach: Human-readable description of the optimization strategy
            that was applied.
        success: Whether the optimization met the target in ``brief.target_metrics``.
    """

    result_id: str
    brief_id: str
    task_id: str
    cycle_number: int
    dimension: OptimizationDimension
    before_value: float = 0.0
    after_value: float = 0.0
    improvement_percent: float = 0.0
    approach: str = ""
    success: bool = False


# ---------------------------------------------------------------------------
# Optimization Candidate
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class OptimizationCandidate:
    """
    Immutable container for a proposed optimized implementation.

    Generated by an LLM in response to an ``OptimizationBrief``.  Multiple
    candidates may be generated per brief; only the best-performing one
    (measured post-execution) becomes an ``OptimizationResult``.

    Attributes:
        candidate_id: Unique identifier for this candidate.
        brief_id: The brief that prompted this candidate.
        dimension: The optimization dimension this candidate targets.
        proposed_code: Full source code of the proposed optimized
            implementation.
        expected_improvement: LLM-estimated improvement percentage (may
            differ from the measured value in ``OptimizationResult``).
        risk: Natural-language assessment of the risk of applying this
            change (e.g. ``"low"`` / ``"may break edge cases"``).
        model_used: Identifier of the LLM that generated this candidate.
    """

    candidate_id: str
    brief_id: str
    dimension: OptimizationDimension
    proposed_code: str = ""
    expected_improvement: float = 0.0
    risk: str = ""
    model_used: str = ""


# ---------------------------------------------------------------------------
# Refactor Suggestion
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RefactorSuggestion:
    """
    Immutable record of a code-quality refactoring suggestion.

    Distinct from an ``OptimizationCandidate`` in that refactor suggestions
    target structural or readability improvements rather than measurable
    performance metrics.  They are generated during the analysis phase and
    may be queued for a future cycle's optimization pass.

    Attributes:
        suggestion_id: Unique identifier for this suggestion.
        task_id: The task whose code is being refactored.
        cycle_number: Training cycle when this suggestion was produced.
        target_function: Name of the function (or module path) that should
            be refactored.
        current_issues: List of identified code smells or structural
            problems in the target function (e.g. ``["long parameter list",
            "magic numbers"]``).
        proposed_changes: Natural-language description (or diff) of the
            recommended changes.
        expected_benefit: Description of the anticipated improvement in
            quality, maintainability, or readability.
        model_used: Identifier of the LLM that produced this suggestion.
    """

    suggestion_id: str
    task_id: str
    cycle_number: int
    target_function: str
    current_issues: list[str] = field(default_factory=list)
    proposed_changes: str = ""
    expected_benefit: str = ""
    model_used: str = ""
