"""
task.py — Layer 0 Task-Related Types
======================================
Dataclass types for the task pipeline of the Self-Improving Engineering AI
system.  Covers task specifications, metadata, execution results, directed
tasks, shadow tasks, exploration, and sampler I/O.

Python 3.11+. All mutable types use @dataclass; all frozen types use
@dataclass(frozen=True). No executable logic — pure definitions only.

Sections:
  1.  TaskSpec               — frozen  — full task specification
  2.  TaskMetadata           — frozen  — metadata / stats about a task
  3.  TaskResult             — frozen  — outcome of a single execution
  4.  DirectedTask           — frozen  — externally directed task
  5.  ShadowTask             — frozen  — shadow / mirrored task
  6.  ExplorationCandidate   — frozen  — proposed exploration task
  7.  ExplorationResult      — frozen  — outcome of an exploration attempt
  8.  SamplerRequest         — mutable — query to the task sampler
  9.  SamplerResponse        — frozen  — reply from the task sampler

Field additions from blueprint Section 5.1–5.4 are incorporated inline.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .enums import (
    ApprovalStatus,
    Domain,
    DirectiveSource,
    EngineeringTrack,
    Language,
    SandboxType,
    TaskLevel,
    TaskSource,
)

__all__ = [
    # Core task types
    "TaskSpec",
    "TaskMetadata",
    "TaskResult",
    # Directed / shadow tasks
    "DirectedTask",
    "ShadowTask",
    # Exploration
    "ExplorationCandidate",
    "ExplorationResult",
    # Sampler
    "SamplerRequest",
    "SamplerResponse",
]


# ---------------------------------------------------------------------------
# 1. TaskSpec
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class TaskSpec:
    """
    Immutable specification for a single training task.

    TaskSpec is the canonical representation of a task as it enters the
    training pipeline.  It carries everything needed to generate a solution,
    run it in the sandbox, and evaluate correctness.

    The ``test_code`` field contains the test harness that will be executed
    against the generated solution inside the sandbox.  ``reference_solution``
    is optional and, when present, is used by the task-verification subsystem
    to confirm that the task is solvable.

    Multi-track fields (Section 5.1) allow tasks to belong to one primary
    engineering track and optionally contribute to secondary tracks.  The
    ``sandbox_type_required`` field overrides the default sandbox selection
    when a track needs a specific isolation level (e.g., QEMU for OS tasks).
    """

    task_id: str
    """Unique identifier for this task (UUID or gym-assigned slug)."""

    title: str
    """Short human-readable title of the problem."""

    description: str
    """Full problem statement shown to the generator."""

    level: TaskLevel
    """Difficulty level F1–F8."""

    domain: Domain
    """Algorithmic / problem domain classification."""

    source: TaskSource
    """Origin of this task (GYM, GENERATED, EXPLORATION, etc.)."""

    language: str = "python"
    """
    Primary programming language for code generation and evaluation.

    Most tasks use 'python'; multi-track tasks may use any Language value.
    Stored as a plain str to remain compatible with legacy gym data that
    predates the Language enum, but callers should use Language enum values.
    """

    time_limit_seconds: int = 30
    """Maximum allowed execution time inside the sandbox."""

    memory_limit_mb: int = 256
    """Maximum allowed memory consumption inside the sandbox."""

    test_code: str = ""
    """Test harness source code executed to evaluate a candidate solution."""

    reference_solution: Optional[str] = None
    """
    Optional reference (canonical) solution used by task verification.

    When present, the task-verification subsystem runs this solution against
    ``test_code`` to confirm the task is solvable before admitting it to the
    task pool.
    """

    hints: list[str] = field(default_factory=list)
    """Ordered list of progressive hints that may be injected into the prompt."""

    tags: list[str] = field(default_factory=list)
    """Free-form keyword tags for search and filtering."""

    metadata: Optional[dict] = None
    """Arbitrary key/value metadata (e.g. source URL, original author)."""

    # --- Multi-track expansion fields (blueprint Section 5.1) ---

    domain_track: EngineeringTrack = EngineeringTrack.CORE_ALGORITHMS
    """
    Primary engineering track this task belongs to.

    Used by the scheduler to attribute cycles and pass rates to the correct
    track.  Defaults to CORE_ALGORITHMS for backward compatibility with tasks
    that predate multi-track expansion.
    """

    secondary_tracks: list[EngineeringTrack] = field(default_factory=list)
    """
    Additional tracks this task contributes to.

    When a task exercises concepts from multiple tracks (e.g., a system design
    problem with concurrency and networking), listing secondary tracks allows
    cross-track credit attribution.  The system determines eligibility based
    on each track's current readiness status.
    """

    track_specific_metadata: Optional[dict] = None
    """
    Track-specific context injected alongside the task description.

    Example for OS track: ``{"target_arch": "x86_64", "kernel_version": "6.8"}``.
    The generator prompt template reads this dict and incorporates the values
    as additional context constraints.
    """

    cross_track_links: list[str] = field(default_factory=list)
    """
    Task IDs of equivalent or related problems in other tracks.

    Enables the curriculum to present the same conceptual problem in multiple
    languages/domains and measure cross-track transfer learning.
    """

    sandbox_type_required: Optional[SandboxType] = None
    """
    Override the default sandbox selection for this task.

    None means use the system default (SUBPROCESS for most tasks).  Set to
    DOCKER or QEMU for tasks that require a more isolated execution environment
    (e.g., networking tasks, OS kernel tasks).
    """


# ---------------------------------------------------------------------------
# 2. TaskMetadata
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class TaskMetadata:
    """
    Immutable metadata and aggregate statistics for a task.

    Persisted to the ``task_metadata`` table and updated after each attempt.
    Provides the sampler and curriculum scheduler with the data needed to make
    intelligent task-selection decisions (difficulty rating, observed pass rate,
    attempt counts).

    The ``domain_track`` field (Section 5.2) is stored explicitly rather than
    inferred from the task path, enabling fast per-track queries without a join
    to the task table.
    """

    task_id: str
    """Foreign key to the corresponding TaskSpec."""

    source: TaskSource
    """Origin of the task."""

    level: TaskLevel
    """Difficulty level F1–F8."""

    domain: Domain
    """Algorithmic / problem domain."""

    created_at: str
    """UTC ISO-8601 timestamp when this task was first admitted to the pool."""

    author: str = "system"
    """Author identifier (gym provider name, 'system', or agent_id)."""

    version: int = 1
    """Version number, incremented when the task description or tests change."""

    difficulty_rating: Optional[float] = None
    """
    Empirical difficulty estimate in [0.0, 1.0] derived from observed pass
    rates.  None until sufficient attempt data is available.
    """

    avg_solve_time_ms: Optional[float] = None
    """
    Rolling average of successful solution execution times in milliseconds.
    None until at least one successful attempt is recorded.
    """

    times_attempted: int = 0
    """Total number of times this task has been attempted."""

    times_passed: int = 0
    """Total number of times this task has been passed."""

    pass_rate: float = 0.0
    """
    Lifetime pass rate: times_passed / times_attempted.

    0.0 when times_attempted == 0.
    """

    # --- Multi-track field (blueprint Section 5.2) ---

    domain_track: EngineeringTrack = EngineeringTrack.CORE_ALGORITHMS
    """
    Engineering track this task belongs to, stored explicitly for fast
    per-track ledger queries.
    """


# ---------------------------------------------------------------------------
# 3. TaskResult
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class TaskResult:
    """
    Immutable record of a single task execution outcome.

    Created by the evaluator after each sandbox run and persisted to the
    ``task_results`` table.  The ``test_results`` dict holds per-test
    pass/fail data in the format emitted by the test harness.  The ``score``
    field is a composite quality score computed by the scoring layer (not just
    pass/fail — it may incorporate code quality, runtime efficiency, etc.).
    """

    task_id: str
    """Foreign key to the TaskSpec that was attempted."""

    cycle_number: int
    """Training cycle in which this attempt occurred."""

    passed: bool
    """True if all required tests passed."""

    execution_time_ms: float
    """Wall-clock execution time of the solution code in milliseconds."""

    memory_used_mb: float = 0.0
    """Peak memory consumption during execution in megabytes."""

    test_results: dict = field(default_factory=dict)
    """
    Per-test outcomes dict.

    Example shape: ``{"test_01": True, "test_02": False, "test_03": True}``.
    The exact keys are determined by the test harness format.
    """

    error_output: Optional[str] = None
    """Stderr output or exception traceback when passed=False."""

    generated_code: str = ""
    """The code submitted for evaluation in this attempt."""

    score: float = 0.0
    """
    Composite quality score in [0.0, 1.0] assigned by the scoring layer.

    A passing solution that also scores highly on style, efficiency, and
    edge-case handling will receive a score above the bare-pass threshold.
    """


# ---------------------------------------------------------------------------
# 4. DirectedTask
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class DirectedTask:
    """
    Immutable record of a task that has been explicitly directed to the system
    by an external source.

    DirectedTasks take scheduling priority over normal gym tasks.  They arise
    from benchmark runs, user-directed challenges, and gym task overrides.
    The ``expires_at`` field allows time-bounded directives that expire if not
    completed within a window.
    """

    task_id: str
    """Foreign key to the TaskSpec to be executed."""

    directive_source: DirectiveSource
    """What issued this directive (GYM_TASK, BENCHMARK_ANONYMOUS, etc.)."""

    requester: str
    """Identifier of the entity that issued the directive."""

    priority: int = 0
    """Scheduling priority (higher integer = higher priority)."""

    reason: str = ""
    """Human-readable reason this task was directed."""

    created_at: str = ""
    """UTC ISO-8601 timestamp when the directive was created."""

    expires_at: Optional[str] = None
    """UTC ISO-8601 timestamp after which the directive should be discarded."""


# ---------------------------------------------------------------------------
# 5. ShadowTask
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ShadowTask:
    """
    Immutable record linking a shadow task to its original task.

    Shadow tasks are parallel runs of an existing task under modified
    conditions (different prompt, agent, or strategy) to measure the
    effect of an experimental change without disrupting the primary run.
    """

    task_id: str
    """Foreign key to the TaskSpec being shadow-executed."""

    original_task_id: str
    """Task ID of the primary task this shadows."""

    shadow_purpose: str
    """Short description of why this shadow run was created."""

    created_at: str = ""
    """UTC ISO-8601 timestamp when the shadow task was registered."""


# ---------------------------------------------------------------------------
# 6. ExplorationCandidate
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ExplorationCandidate:
    """
    Immutable record of a task proposed for an exploration cycle.

    Exploration candidates represent tasks outside the current curriculum
    that the system believes could yield valuable learning.  Before running,
    each candidate must be approved (status transitions from PENDING to
    APPROVED or REJECTED).

    The ``risk_score`` quantifies the probability that the exploration cycle
    will be unproductive (wasted compute/budget).
    """

    candidate_id: str
    """Unique identifier for this exploration candidate."""

    task_id: str
    """Foreign key to the TaskSpec proposed for exploration."""

    domain: Domain
    """Domain of the proposed task."""

    level: TaskLevel
    """Difficulty level of the proposed task."""

    rationale: str
    """System's reasoning for proposing this task for exploration."""

    expected_learning: str
    """What the system expects to learn from attempting this task."""

    risk_score: float = 0.5
    """
    Estimated probability that the exploration cycle will be unproductive.

    0.0 = very safe / high expected value; 1.0 = very risky / low expected
    value.
    """

    status: ApprovalStatus = ApprovalStatus.PENDING
    """Current approval status of this candidate."""


# ---------------------------------------------------------------------------
# 7. ExplorationResult
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ExplorationResult:
    """
    Immutable record of the outcome of an approved exploration cycle.

    Written by the analysis layer after an ExplorationCandidate has been
    attempted.  The ``was_valuable`` flag drives the exploration budget
    controller: persistent false outcomes reduce the exploration budget
    allocation.
    """

    candidate_id: str
    """Foreign key to the originating ExplorationCandidate."""

    task_id: str
    """Task that was actually executed."""

    cycle_number: int
    """Cycle in which the exploration was run."""

    passed: bool
    """Whether the exploration task was solved."""

    actual_learning: str = ""
    """
    Description of what was actually learned (may differ from
    ExplorationCandidate.expected_learning).
    """

    outcome: str = "neutral"
    """
    Qualitative outcome label: 'valuable', 'neutral', or 'wasteful'.

    Should be one of the ExplorationOutcome enum values, stored as str to
    avoid a circular import with the broader type system.
    """

    was_valuable: bool = False
    """
    True if the exploration yielded a new pattern, artifact, or insight.

    The analysis layer sets this after evaluating the outcome against the
    system's learning state.
    """


# ---------------------------------------------------------------------------
# 8. SamplerRequest
# ---------------------------------------------------------------------------

@dataclass
class SamplerRequest:
    """
    Mutable query object passed to the task sampler.

    The sampler uses these fields to filter and rank tasks from the task pool.
    All fields are optional; an empty SamplerRequest returns any single task.

    Multi-track fields (blueprint Section 5.4) extend the original sampler
    without introducing a separate TrackSamplerRequest type.  Setting
    ``track_id`` restricts sampling to tasks belonging to that track.
    Setting ``is_exam=True`` further restricts to exam-eligible tasks for
    graduation gate evaluation.
    """

    level: Optional[TaskLevel] = None
    """Restrict to tasks at this F-level (None = any level)."""

    domain: Optional[Domain] = None
    """Restrict to tasks in this domain (None = any domain)."""

    source: Optional[TaskSource] = None
    """Restrict to tasks from this source (None = any source)."""

    exclude_task_ids: list[str] = field(default_factory=list)
    """Task IDs that must not appear in results (e.g. recently attempted)."""

    max_results: int = 1
    """Maximum number of TaskSpec objects to return."""

    difficulty_range: Optional[tuple[float, float]] = None
    """
    Optional (min, max) difficulty rating filter applied to TaskMetadata.

    None means no difficulty filter.  Values are in [0.0, 1.0].
    """

    # --- Multi-track extension fields (blueprint Section 5.4) ---

    track_id: Optional[EngineeringTrack] = None
    """
    Restrict sampling to tasks belonging to this engineering track.

    None means multi-track filtering is disabled (use with single-track
    sessions or when aggregating across all tracks).
    """

    is_exam: bool = False
    """
    When True, restrict to tasks eligible for graduation EXAM cycles.

    Exam-eligible tasks must meet additional quality criteria (difficulty
    verified, novelty score above threshold, not recently attempted).
    """

    preferred_language: Optional[Language] = None
    """
    Language preference for multi-language task pools.

    The sampler will prioritise tasks in this language but may return tasks
    in other languages if the preferred language has insufficient candidates
    after other filters are applied.
    """


# ---------------------------------------------------------------------------
# 9. SamplerResponse
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SamplerResponse:
    """
    Immutable response from the task sampler.

    Contains the sampled TaskSpec objects along with counts that allow
    callers to detect when filters are too restrictive (e.g., filtered_count
    close to total_available suggests the pool needs expansion).
    """

    tasks: list[TaskSpec]
    """Sampled tasks, up to SamplerRequest.max_results in length."""

    total_available: int = 0
    """Total tasks in the pool before any filters were applied."""

    filtered_count: int = 0
    """
    Number of tasks remaining after applying all request filters.

    If filtered_count < max_results, the sampler returned everything that
    matched — the pool may need to be replenished.
    """
