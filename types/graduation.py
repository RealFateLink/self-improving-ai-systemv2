"""
graduation.py — Graduation and Benchmark Types
================================================
Defines system-level graduation state, gate evaluation/requirements,
and benchmark definition/result/session/version types.

All classes are pure data definitions (dataclasses).
Frozen dataclasses are immutable value objects; non-frozen ones are
mutable state containers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .enums import TaskLevel, EngineeringTrack, GateLevel

__all__ = [
    "GraduationState",
    "GateEvaluation",
    "GateRequirement",
    "BenchmarkDefinition",
    "BenchmarkResult",
    "BenchmarkSession",
    "BenchmarkVersionInfo",
]


# ---------------------------------------------------------------------------
# Graduation State
# ---------------------------------------------------------------------------

@dataclass
class GraduationState:
    """
    System-level graduation state tracking progress through gate checkpoints.

    Tracks the current gate, consecutive passing sessions, exam pass rates,
    and a full history of gate transitions.  This is the single source of
    truth for the graduation subsystem at any given moment.

    Attributes:
        current_gate: The gate the system is currently working toward.
        current_tier: Numeric tier within the current gate (1-indexed).
        consecutive_sessions: Number of consecutive passing sessions so far
            at the current gate level.
        required_sessions: Minimum consecutive passing sessions needed to
            attempt a gate evaluation.
        exam_pass_rate: Aggregate pass rate across exam cycles at the
            current gate.
        last_gate_completed: The most recently completed gate, if any.
        last_gate_completed_at_cycle: Training cycle when the last gate was
            completed.
        total_gate_attempts: Cumulative number of gate evaluation attempts
            across all gates.
        history: Ordered list of gate transition records (dicts).
    """

    current_gate: GateLevel = GateLevel.G1
    current_tier: int = 1
    consecutive_sessions: int = 0
    required_sessions: int = 15
    exam_pass_rate: float = 0.0
    last_gate_completed: Optional[GateLevel] = None
    last_gate_completed_at_cycle: Optional[int] = None
    total_gate_attempts: int = 0
    history: list[dict] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Gate Evaluation
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class GateEvaluation:
    """
    Immutable record of a single gate evaluation attempt.

    Produced at the end of an exam window and stored in the graduation
    history.  The ``passed`` field is the authoritative decision.

    Attributes:
        gate: The gate that was evaluated.
        cycle_number: Training cycle at which the evaluation was performed.
        pass_rate: Observed pass rate during the evaluation window.
        required_pass_rate: Minimum pass rate needed to pass this gate.
        passed: Whether the gate evaluation succeeded.
        sessions_completed: Number of sessions completed in the exam window.
        sessions_required: Number of sessions required for a valid evaluation.
        exam_cycles: Number of training cycles counted as exam cycles.
        detail: Human-readable summary or explanation of the outcome.
    """

    gate: GateLevel
    cycle_number: int
    pass_rate: float
    required_pass_rate: float
    passed: bool
    sessions_completed: int = 0
    sessions_required: int = 15
    exam_cycles: int = 0
    detail: str = ""


# ---------------------------------------------------------------------------
# Gate Requirement
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class GateRequirement:
    """
    Immutable specification of the criteria required to pass a gate.

    Encodes both quantitative thresholds (pass rate, session count) and
    qualitative side-conditions stored in ``additional_criteria``.

    Attributes:
        gate: The gate these requirements apply to.
        min_pass_rate: Minimum fraction of tasks that must pass (0–1).
        min_consecutive_sessions: Minimum consecutive passing sessions
            before an exam window opens.
        exam_size: Number of tasks in a full gate exam.
        min_cycles_at_level: Minimum training cycles the system must spend
            at this gate level before it may graduate.
        additional_criteria: Freeform key→description pairs for any extra
            qualitative requirements (e.g. domain coverage minimums).
    """

    gate: GateLevel
    min_pass_rate: float
    min_consecutive_sessions: int = 15
    exam_size: int = 200
    min_cycles_at_level: int = 1000
    additional_criteria: dict[str, str] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Benchmark Definition
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class BenchmarkDefinition:
    """
    Immutable descriptor for a named benchmark suite.

    A benchmark is a curated set of tasks used to objectively measure
    system capability.  Multiple versions of the same benchmark may exist;
    see ``BenchmarkVersionInfo`` for version management.

    Attributes:
        benchmark_id: Globally unique identifier for this benchmark.
        name: Human-readable benchmark name.
        description: Detailed description of the benchmark's purpose and
            scope.
        task_count: Total number of tasks in this benchmark.
        difficulty_range: Inclusive (min, max) ``TaskLevel`` range covered
            by the benchmark.
        version: Semantic version string (e.g. ``"1.0"``).
        created_at: ISO-8601 timestamp when this benchmark was created.
        tags: Arbitrary classification tags (e.g. ``["regression"]``).
    """

    benchmark_id: str
    name: str
    description: str
    task_count: int
    difficulty_range: tuple[TaskLevel, TaskLevel]
    version: str = "1.0"
    created_at: str = ""
    tags: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Benchmark Result
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class BenchmarkResult:
    """
    Immutable record of a single task's outcome within a benchmark run.

    One ``BenchmarkResult`` is created per task per benchmark session.
    Aggregate statistics are maintained on the parent ``BenchmarkSession``.

    Attributes:
        result_id: Unique identifier for this individual result record.
        benchmark_id: The benchmark this result belongs to.
        session_id: The session during which the result was produced.
        cycle_number: Training cycle when the task was executed.
        task_id: Identifier of the task that was evaluated.
        passed: Whether the task was solved successfully.
        score: Continuous score in [0, 1] representing solution quality.
        execution_time_ms: Wall-clock time taken to execute the task (ms).
        error_detail: Machine-readable error string if the task failed,
            otherwise ``None``.
    """

    result_id: str
    benchmark_id: str
    session_id: str
    cycle_number: int
    task_id: str
    passed: bool
    score: float = 0.0
    execution_time_ms: float = 0.0
    error_detail: Optional[str] = None


# ---------------------------------------------------------------------------
# Benchmark Session
# ---------------------------------------------------------------------------

@dataclass
class BenchmarkSession:
    """
    Mutable state container for an in-progress or completed benchmark run.

    Aggregates per-task ``BenchmarkResult`` records and maintains running
    totals.  ``status`` transitions from ``"running"`` → ``"completed"``
    (or ``"failed"``).

    Attributes:
        session_id: Unique identifier for this benchmark session.
        benchmark_id: The benchmark being executed.
        started_at_cycle: Training cycle when the session began.
        status: Current session status (``"running"``, ``"completed"``,
            ``"failed"``).
        total_tasks: Total tasks scheduled for this session.
        completed_tasks: Tasks that have been attempted (pass or fail).
        passed_tasks: Tasks that passed evaluation.
        pass_rate: Fraction of completed tasks that passed (0–1).
        started_at: ISO-8601 wall-clock timestamp for session start.
        completed_at: ISO-8601 wall-clock timestamp for session end,
            or ``None`` if still running.
        total_cost_usd: Cumulative API cost incurred during this session.
    """

    session_id: str
    benchmark_id: str
    started_at_cycle: int
    status: str = "running"
    total_tasks: int = 0
    completed_tasks: int = 0
    passed_tasks: int = 0
    pass_rate: float = 0.0
    started_at: str = ""
    completed_at: Optional[str] = None
    total_cost_usd: float = 0.0


# ---------------------------------------------------------------------------
# Benchmark Version Info
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class BenchmarkVersionInfo:
    """
    Immutable version metadata for a specific benchmark release.

    Enables the system to track which version of a benchmark was used for
    a given session and to detect staleness or drift over time.

    Attributes:
        benchmark_id: The benchmark this version belongs to.
        version: Semantic version string (e.g. ``"2.1.3"``).
        hash: Content hash of the task list for integrity verification.
        task_count: Number of tasks in this version.
        created_at: ISO-8601 timestamp when this version was released.
        changelog: Human-readable description of changes since the
            previous version.
        applicable_tracks: Engineering tracks this benchmark is designed
            to evaluate; empty list means all tracks.
    """

    benchmark_id: str
    version: str
    hash: str
    task_count: int
    created_at: str
    changelog: str = ""
    applicable_tracks: list[EngineeringTrack] = field(default_factory=list)
