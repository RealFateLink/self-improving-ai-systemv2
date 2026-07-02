"""
scoring.py — Layer 0 Scoring Types
=====================================
Frozen dataclasses representing how candidate solutions are scored,
ranked, and tracked across training cycles.

Covers:
    - ScoreBreakdown       — per-dimension score components
    - ScoringResult        — full scoring output for a single candidate
    - ConfidenceScore      — confidence-adjusted score for one dimension
    - PerformanceSnapshot  — point-in-time system-wide performance metrics
    - CycleScoreSummary    — condensed per-cycle outcome for analytics

All types are pure definitions (frozen dataclasses). No executable logic.
Imported by Layers 1–8; never imports from them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .enums import TaskLevel, Trend

__all__ = [
    "ScoreBreakdown",
    "ScoringResult",
    "ConfidenceScore",
    "PerformanceSnapshot",
    "CycleScoreSummary",
]


# ---------------------------------------------------------------------------
# ScoreBreakdown
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ScoreBreakdown:
    """
    Decomposed quality score across six independent dimensions.

    Each field holds a normalised score in [0.0, 1.0]. The breakdown
    lets the learning system diagnose which dimensions are improving or
    regressing independently of the rolled-up total score.

    Attributes
    ----------
    correctness : float
        How well the solution produces the expected outputs for all
        test cases.  0.0 = all tests fail, 1.0 = all tests pass.
    efficiency : float
        Algorithmic and runtime efficiency relative to the optimal
        solution for the given task level.
    readability : float
        Clarity of naming, structure, and documentation.
    maintainability : float
        Ease of future modification (low coupling, clear abstractions,
        no code smells).
    test_coverage : float
        Proportion of code paths exercised by the test suite submitted
        with the solution.
    style : float
        Adherence to the target language's idiomatic style guide.
    """

    correctness: float = 0.0
    efficiency: float = 0.0
    readability: float = 0.0
    maintainability: float = 0.0
    test_coverage: float = 0.0
    style: float = 0.0


# ---------------------------------------------------------------------------
# ScoringResult
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ScoringResult:
    """
    Complete scoring output for a single GenerationCandidate.

    Produced after test execution, static review, and semantic critique
    are all complete. The selection subsystem uses this record as the
    primary input when ranking candidates within a cycle.

    Attributes
    ----------
    result_id : str
        Globally unique identifier for this scoring result.
    task_id : str
        Identifier of the task whose candidate is being scored.
    cycle_number : int
        Training cycle in which scoring was performed.
    candidate_id : str
        candidate_id of the GenerationCandidate being scored.
    total_score : float
        Weighted aggregate score across all dimensions, in [0.0, 1.0].
    breakdown : Optional[ScoreBreakdown]
        Detailed per-dimension scores. None if scoring was aborted.
    passed_all_tests : bool
        True if every required test case passed.
    tests_passed : int
        Count of individual test cases that passed.
    tests_total : int
        Total number of test cases in the test suite.
    execution_time_ms : float
        Observed execution time of the candidate's solution in
        milliseconds (summed across all test cases).
    memory_used_mb : float
        Peak memory consumption observed during test execution,
        in megabytes.
    normalized_score : float
        total_score normalised relative to the current task level's
        expected baseline, in [0.0, 1.0]. Used for cross-level
        comparisons and promotion thresholds.
    """

    result_id: str
    task_id: str
    cycle_number: int
    candidate_id: str
    total_score: float = 0.0
    breakdown: Optional[ScoreBreakdown] = None
    passed_all_tests: bool = False
    tests_passed: int = 0
    tests_total: int = 0
    execution_time_ms: float = 0.0
    memory_used_mb: float = 0.0
    normalized_score: float = 0.0


# ---------------------------------------------------------------------------
# ConfidenceScore
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ConfidenceScore:
    """
    A confidence-adjusted score for a single performance dimension.

    Confidence scores are maintained per dimension (e.g., "correctness",
    "efficiency") and updated each cycle. The Trend field allows the
    learning system to detect regressions before they affect graduation.

    Attributes
    ----------
    dimension : str
        Name of the performance dimension being tracked (e.g.,
        "correctness", "readability").
    score : float
        Current point estimate for this dimension, in [0.0, 1.0].
    confidence : float
        Statistical confidence in the score estimate, in [0.0, 1.0].
        Low values indicate the score is based on few samples or high
        variance.
    sample_size : int
        Number of cycles included in the current score estimate.
    trend : Trend
        Recent direction of movement: IMPROVING, STABLE, or DECLINING.
    last_updated_cycle : int
        Cycle number when this record was last updated.
    """

    dimension: str
    score: float
    confidence: float = 0.0
    sample_size: int = 0
    trend: Trend = Trend.STABLE
    last_updated_cycle: int = 0


# ---------------------------------------------------------------------------
# PerformanceSnapshot
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PerformanceSnapshot:
    """
    A point-in-time snapshot of system-wide performance metrics.

    Snapshots are written periodically (e.g., every 10 cycles) so that
    long-term trends can be reconstructed and graduation gates can be
    evaluated against rolling pass rates.

    Attributes
    ----------
    snapshot_id : str
        Globally unique identifier for this snapshot.
    cycle_number : int
        Cycle number at which this snapshot was taken.
    timestamp : str
        ISO-8601 UTC timestamp when the snapshot was recorded.
    pass_rate_overall : float
        Fraction of all completed cycles that passed (lifetime),
        in [0.0, 1.0].
    pass_rate_rolling_10 : float
        Pass rate over the 10 most recent cycles, in [0.0, 1.0].
    pass_rate_rolling_100 : float
        Pass rate over the 100 most recent cycles, in [0.0, 1.0].
    current_level : TaskLevel
        The task difficulty level active at snapshot time.
    current_tier : int
        Numeric graduation tier active at snapshot time (1-indexed).
    total_cycles : int
        Total number of cycles completed (including failed cycles).
    total_tasks_attempted : int
        Total number of distinct tasks attempted across all cycles.
    """

    snapshot_id: str
    cycle_number: int
    timestamp: str
    pass_rate_overall: float = 0.0
    pass_rate_rolling_10: float = 0.0
    pass_rate_rolling_100: float = 0.0
    current_level: TaskLevel = TaskLevel.F1
    current_tier: int = 1
    total_cycles: int = 0
    total_tasks_attempted: int = 0


# ---------------------------------------------------------------------------
# CycleScoreSummary
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CycleScoreSummary:
    """
    Condensed per-cycle outcome record used for analytics and dashboards.

    Written at the end of every cycle. Provides a lightweight view of
    cycle outcomes without requiring a full join across ScoringResult,
    GenerationCandidate, and PlanOutcomeRecord tables.

    Attributes
    ----------
    cycle_number : int
        Training cycle this summary covers.
    task_id : str
        Identifier of the task attempted during this cycle.
    passed : bool
        True if the cycle resolved with a promoted solution.
    total_score : float
        Best total_score achieved by any candidate in the cycle.
        Zero if no candidates were produced.
    candidates_generated : int
        Number of GenerationCandidates created during this cycle.
    best_candidate_id : Optional[str]
        candidate_id of the highest-scoring GenerationCandidate, or
        None if no candidates were generated.
    time_spent_ms : float
        Total elapsed wall-clock time for the cycle in milliseconds.
    """

    cycle_number: int
    task_id: str
    passed: bool
    total_score: float = 0.0
    candidates_generated: int = 0
    best_candidate_id: Optional[str] = None
    time_spent_ms: float = 0.0
