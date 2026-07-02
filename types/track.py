"""
track.py — Multi-Track Domain Types (Layer 0)
==============================================
All type definitions for multi-track domain expansion, task self-generation,
and graduation ceiling detection.

Sections:
  4.1  Core Track Types          (TrackDefinition, TrackConfig, TrackPerformance)
  4.2  Track Lifecycle Types     (TrackReadinessAssessment, TrackPreparationState,
                                  TrackDeactivationRecord)
  4.2.1 Track State Machine      (TrackTransitionRule, TRACK_TRANSITION_RULES)
  4.3  Track Scheduling & Balance (TrackSchedule, TrackSchedulerState, TrackBalance)
  4.4  Track Graduation          (TrackGraduationState)
  4.4.1 Graduation Ceiling       (GraduationCeilingFlag, GraduationOverride)
  4.5  Cross-Track Learning      (CrossTrackInsight, DomainTaskPool,
                                  TrackBenchmarkMapping)
  4.6  Task Self-Generation      (GeneratedTaskCandidate, TaskVerificationResult,
                                  TaskGenerationCapability)
  4.7  Overnight Session         (OvernightSession)

All types are frozen dataclasses unless explicitly noted as mutable.
No executable logic — pure definitions only.

Blueprint reference: Section 4, layer0_blueprint.txt (March 27, 2026)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .enums import (
    EngineeringTrack,
    Language,
    TaskLevel,
    TrackPriority,
    TrackStatus,
    SandboxType,
    Trend,
)

__all__ = [
    # 4.1 Core Track Types
    "TrackDefinition",
    "TrackConfig",
    "TrackPerformance",
    # 4.2 Track Lifecycle Types
    "TrackReadinessAssessment",
    "TrackPreparationState",
    "TrackDeactivationRecord",
    # 4.2.1 Track State Machine
    "TrackTransitionRule",
    "TRACK_TRANSITION_RULES",
    # 4.3 Track Scheduling & Balance
    "TrackSchedule",
    "TrackSchedulerState",
    "TrackBalance",
    # 4.4 Track Graduation
    "TrackGraduationState",
    # 4.4.1 Graduation Ceiling Detection
    "GraduationCeilingFlag",
    "GraduationOverride",
    # 4.5 Cross-Track Learning
    "CrossTrackInsight",
    "DomainTaskPool",
    "TrackBenchmarkMapping",
    # 4.6 Task Self-Generation
    "GeneratedTaskCandidate",
    "TaskVerificationResult",
    "TaskGenerationCapability",
    # 4.7 Overnight Session
    "OvernightSession",
]


# ---------------------------------------------------------------------------
# 4.1  Core Track Types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TrackDefinition:
    """Static definition of a single engineering domain track.

    Frozen — structural identity of a track.  Runtime state lives in
    TrackConfig (allocation settings) and TrackPerformance (live metrics).

    Fields (19 total):
        track_id               — Which domain this track covers.
        display_name           — Human-readable name.
        description            — What this track teaches.
        priority               — Scheduling priority.
        status                 — Current lifecycle state.
        min_activation_tier    — Minimum graduation tier to even consider
                                 activation.
        required_languages     — Languages needed.
        prerequisite_tracks    — Tracks that must be ACTIVE first.
        primary_language       — Most tasks use this language initially.
        task_pool_size         — Number of tasks in pool.
        task_sources           — Where tasks originate (exercism, leetcode,
                                 generated, etc.).
        f_level_range          — Min/max F-levels available.
        f_level_sandbox_overrides — Maps F-level ranges to SandboxType.
        sandbox_requirements   — Which sandbox types needed.
        context_preamble       — Static context injected into Generator for
                                 this track.
        estimated_avg_cost_per_cycle — Budget forecast before real data exists.
        estimated_months_to_g1 — Rough time estimate.
        readiness_overrides    — Per-track overrides for readiness criteria.
    """

    track_id: EngineeringTrack
    display_name: str
    description: str
    priority: TrackPriority
    status: TrackStatus
    min_activation_tier: int
    required_languages: tuple[Language, ...]
    prerequisite_tracks: tuple[EngineeringTrack, ...]
    primary_language: Language
    task_pool_size: int
    task_sources: tuple[str, ...]
    f_level_range: tuple[TaskLevel, TaskLevel]
    f_level_sandbox_overrides: Optional[dict]
    sandbox_requirements: tuple[SandboxType, ...]
    context_preamble: str
    estimated_avg_cost_per_cycle: float
    estimated_months_to_g1: float
    readiness_overrides: Optional[dict]


@dataclass
class TrackConfig:
    """Mutable allocation and scheduling configuration for a single track.

    Lives alongside TrackDefinition but is updated by the scheduler as
    allocations are rebalanced across active tracks.

    Fields (11 total):
        track_id               — Which track.
        cycle_allocation_percent — % of cycles allocated.
        min_allocation_percent — Floor (never below this).
        max_allocation_percent — Ceiling.
        max_budget_percent     — Max fraction of monthly budget this track
                                 can consume.
        exam_allocation_percent — % of track cycles that are EXAM during
                                  graduation.
        graduation_gates       — Per-gate graduation requirements.
        difficulty_ramp_rate   — How fast F-level increases.
        tier_progression_rate  — Multiplier on tier advancement speed.
        exploration_budget_percent — Track-specific exploration allocation.
        overnight_priority_boost — Priority multiplier during overnight.
    """

    track_id: EngineeringTrack
    cycle_allocation_percent: float
    min_allocation_percent: float
    max_allocation_percent: float
    max_budget_percent: float
    exam_allocation_percent: float
    graduation_gates: dict = field(default_factory=dict)
    difficulty_ramp_rate: float = 1.0
    tier_progression_rate: float = 1.0
    exploration_budget_percent: float = 0.1
    overnight_priority_boost: float = 1.0


@dataclass
class TrackPerformance:
    """Live runtime performance metrics for a single track.

    Mutable — updated after every cycle that runs on this track.

    Fields (22 total):
        track_id               — Which track.
        total_cycles           — Cycles spent on this track.
        pass_rate_overall      — Lifetime pass rate.
        pass_rate_rolling_100  — Last 100 TRACK cycles (not system cycles).
        pass_rate_rolling_500  — Last 500 TRACK cycles.
        current_f_level_mode   — Most common F-level being attempted.
        highest_f_level_passed — Highest F-level with >50% pass rate.
        current_tier           — Track's independent tier progression.
        patterns_discovered    — Track-specific patterns found.
        prevention_artifacts   — Track-specific artifacts.
        active_agents          — Domain specialists currently active.
        cost_spent_usd         — Total API cost.
        avg_cost_per_cycle     — Running average cost per cycle.
        cross_domain_knowledge_generated — Patterns that transferred to other
                                           tracks.
        last_cycle_timestamp   — When last ran (ISO-8601 string).
        trend                  — Performance direction.
        stagnation_cycles      — Cycles since last meaningful improvement.
        consecutive_crashes    — Reset on success; auto-pause if exceeds
                                 threshold.
        warmup_remaining       — Immunity cycles for new tracks.
        health_score           — Composite 0.0–1.0 (trend + stagnation +
                                 cost efficiency + agents).
        paused_at_cycle        — When paused (None if active).
        pause_reason           — Why paused (None if active).
    """

    track_id: EngineeringTrack
    total_cycles: int = 0
    pass_rate_overall: float = 0.0
    pass_rate_rolling_100: float = 0.0
    pass_rate_rolling_500: float = 0.0
    current_f_level_mode: TaskLevel = TaskLevel.F1
    highest_f_level_passed: TaskLevel = TaskLevel.F1
    current_tier: int = 0
    patterns_discovered: int = 0
    prevention_artifacts: int = 0
    active_agents: int = 0
    cost_spent_usd: float = 0.0
    avg_cost_per_cycle: float = 0.0
    cross_domain_knowledge_generated: int = 0
    last_cycle_timestamp: str = ""
    trend: Trend = Trend.STABLE
    stagnation_cycles: int = 0
    consecutive_crashes: int = 0
    warmup_remaining: int = 0
    health_score: float = 0.0
    paused_at_cycle: Optional[int] = None
    pause_reason: Optional[str] = None


# ---------------------------------------------------------------------------
# 4.2  Track Lifecycle Types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TrackReadinessAssessment:
    """Snapshot of whether an INACTIVE track is ready to become PREPARING.

    Frozen — produced by the readiness-check protocol, stored for audit.

    Fields (10 total):
        track_id               — Track being assessed.
        assessed_at_cycle      — When assessment ran.
        prerequisite_status    — Each prereq → {pass_rate, meets_threshold,
                                 cycles}.
        language_proficiency   — Each language → {pass_rate, cycles,
                                 meets_threshold}.
        pattern_depth_score    — 0.0–1.0, relevant pattern coverage.
        current_track_load     — How many tracks currently active.
        resource_availability  — Available budget headroom.
        overall_ready          — All criteria met.
        blocking_reasons       — Empty if ready.
        confidence             — Assessment confidence.
    """

    track_id: EngineeringTrack
    assessed_at_cycle: int
    prerequisite_status: dict[str, dict]
    language_proficiency: dict[str, dict]
    pattern_depth_score: float
    current_track_load: int
    resource_availability: float
    overall_ready: bool
    blocking_reasons: tuple[str, ...]
    confidence: float


@dataclass
class TrackPreparationState:
    """Mutable state while a track is in the PREPARING lifecycle phase.

    Tracks progress toward meeting the conditions required to become ACTIVE.

    Fields (10 total):
        track_id               — Track being prepared.
        started_at_cycle       — When PREPARING began.
        tasks_loaded           — Tasks loaded so far.
        tasks_required         — Minimum before ACTIVE.
        task_loading_complete  — Enough tasks loaded.
        sandbox_verified       — Required sandbox tested.
        agent_proposed         — Domain specialist proposed.
        agent_proposal_id      — Approval queue ID (None if not yet proposed).
        estimated_ready_at_cycle — ETA for ACTIVE (None if unknown).
        blockers               — What prevents ACTIVE transition.
    """

    track_id: EngineeringTrack
    started_at_cycle: int
    tasks_loaded: int = 0
    tasks_required: int = 0
    task_loading_complete: bool = False
    sandbox_verified: bool = False
    agent_proposed: bool = False
    agent_proposal_id: Optional[str] = None
    estimated_ready_at_cycle: Optional[int] = None
    blockers: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class TrackDeactivationRecord:
    """Permanent audit record created when a track is deactivated.

    Frozen — append-only once written.  Preserved even if track is later
    reactivated (a new record is created on the next deactivation).

    Fields (11 total):
        track_id               — Which track.
        deactivated_at_cycle   — When deactivated.
        reason                 — Why.
        final_performance      — Snapshot of TrackPerformance at deactivation.
        agents_dissolved       — Agent IDs dissolved.
        graduation_progress_archived — Gate progress at deactivation.
        patterns_retained      — Patterns kept in shared library.
        patterns_retired       — Patterns retired.
        total_cycles_spent     — Lifetime cycles on this track.
        total_cost_spent       — Lifetime cost.
        reactivation_eligible  — Can this track be reactivated.
    """

    track_id: EngineeringTrack
    deactivated_at_cycle: int
    reason: str
    final_performance: dict
    agents_dissolved: tuple[str, ...]
    graduation_progress_archived: dict
    patterns_retained: int
    patterns_retired: int
    total_cycles_spent: int
    total_cost_spent: float
    reactivation_eligible: bool


# ---------------------------------------------------------------------------
# 4.2.1  Track State Machine
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TrackTransitionRule:
    """Single valid edge in the track lifecycle state machine.

    Frozen — these are constants, not runtime state.  The full set of valid
    transitions is encoded in TRACK_TRANSITION_RULES below.

    Fields (5 total):
        from_status        — Source state.
        to_status          — Target state.
        requires_approval  — Needs human approval (ApprovalItemType).
        auto_trigger       — Condition string for automatic transition
                             (None if human-only).
        can_system_initiate — System can trigger without human intervention.
    """

    from_status: TrackStatus
    to_status: TrackStatus
    requires_approval: bool
    auto_trigger: Optional[str]
    can_system_initiate: bool


# Reference table — enforced by Layer 1 validators, not evaluated here.
# 10 valid transitions matching the blueprint table (Section 4.2.1).
TRACK_TRANSITION_RULES: tuple[TrackTransitionRule, ...] = (
    # INACTIVE → PREPARING  (readiness check passes; human approval required)
    TrackTransitionRule(
        from_status=TrackStatus.INACTIVE,
        to_status=TrackStatus.PREPARING,
        requires_approval=True,
        auto_trigger="readiness_check_passes",
        can_system_initiate=False,
    ),
    # PREPARING → ACTIVE  (all preparation complete; automatic)
    TrackTransitionRule(
        from_status=TrackStatus.PREPARING,
        to_status=TrackStatus.ACTIVE,
        requires_approval=False,
        auto_trigger="preparation_complete",
        can_system_initiate=True,
    ),
    # ACTIVE → PAUSED  (crashes, stagnation, budget, or human)
    TrackTransitionRule(
        from_status=TrackStatus.ACTIVE,
        to_status=TrackStatus.PAUSED,
        requires_approval=False,
        auto_trigger="crash_threshold_or_stagnation_or_budget",
        can_system_initiate=True,
    ),
    # ACTIVE → GRADUATING  (auto-trigger on sustained high pass rate)
    TrackTransitionRule(
        from_status=TrackStatus.ACTIVE,
        to_status=TrackStatus.GRADUATING,
        requires_approval=False,
        auto_trigger="sustained_high_pass_rate",
        can_system_initiate=True,
    ),
    # GRADUATING → ACTIVE  (exam failed or streak broken)
    TrackTransitionRule(
        from_status=TrackStatus.GRADUATING,
        to_status=TrackStatus.ACTIVE,
        requires_approval=False,
        auto_trigger="exam_failed_or_streak_broken",
        can_system_initiate=True,
    ),
    # GRADUATING → GRADUATED  (exam passed — all sessions)
    TrackTransitionRule(
        from_status=TrackStatus.GRADUATING,
        to_status=TrackStatus.GRADUATED,
        requires_approval=False,
        auto_trigger="exam_passed_all_sessions",
        can_system_initiate=True,
    ),
    # PAUSED → ACTIVE  (conditions resolved or human resumes)
    TrackTransitionRule(
        from_status=TrackStatus.PAUSED,
        to_status=TrackStatus.ACTIVE,
        requires_approval=False,
        auto_trigger="conditions_resolved",
        can_system_initiate=True,
    ),
    # PAUSED → DEACTIVATING  (track permanently removed; human approval required)
    TrackTransitionRule(
        from_status=TrackStatus.PAUSED,
        to_status=TrackStatus.DEACTIVATING,
        requires_approval=True,
        auto_trigger=None,
        can_system_initiate=False,
    ),
    # DEACTIVATING → INACTIVE  (cleanup complete — agents dissolved, archived)
    TrackTransitionRule(
        from_status=TrackStatus.DEACTIVATING,
        to_status=TrackStatus.INACTIVE,
        requires_approval=False,
        auto_trigger="cleanup_complete",
        can_system_initiate=True,
    ),
    # Any → PAUSED  (safety trigger: crash threshold or budget; system can always
    #               pause regardless of current state)
    TrackTransitionRule(
        from_status=TrackStatus.ACTIVE,   # sentinel: "Any" state
        to_status=TrackStatus.PAUSED,
        requires_approval=False,
        auto_trigger="safety_trigger_crash_or_budget",
        can_system_initiate=True,
    ),
)


# ---------------------------------------------------------------------------
# 4.3  Track Scheduling & Balance
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TrackSchedule:
    """Per-track scheduling state for the current scheduling period.

    Frozen — produced by the scheduler each period; prior snapshots retained
    for audit.

    Fields (6 total):
        track_id                  — Which track.
        allocated_cycles_this_period — Cycles allocated in current period.
        used_cycles_this_period   — Cycles consumed so far.
        next_eligible_cycle       — Earliest cycle this track can run.
        priority_score            — Computed scheduling priority.
        consecutive_skips         — Scheduling rounds skipped (used to prevent
                                    starvation).
    """

    track_id: EngineeringTrack
    allocated_cycles_this_period: int
    used_cycles_this_period: int
    next_eligible_cycle: int
    priority_score: float
    consecutive_skips: int


@dataclass
class TrackSchedulerState:
    """Mutable live state of the multi-track scheduler.

    Updated each time the scheduler selects a track or rebalances allocations.

    Fields (5 total):
        current_track       — What's running now.
        cycles_on_current   — Consecutive cycles on this track.
        next_switch_at      — When to consider switching.
        queue               — Ordered by priority: [(track, score), ...].
        last_rebalance_cycle — When allocations were last adjusted.
    """

    current_track: EngineeringTrack
    cycles_on_current: int = 0
    next_switch_at: int = 0
    queue: list[tuple] = field(default_factory=list)
    last_rebalance_cycle: int = 0


@dataclass(frozen=True)
class TrackBalance:
    """Point-in-time snapshot of allocation vs. actual usage across tracks.

    Produced by TrackSchedulerProtocol.get_balance().  Frozen for audit.

    Fields (6 total):
        total_active_tracks  — Active track count.
        allocations          — Target % per track (track_id → float).
        actual_usage         — Actual % per track (track_id → float).
        imbalance_score      — sum(|actual - target|) / 2; 0.0 = perfect.
        rebalance_needed     — Exceeds imbalance threshold.
        last_rebalance_cycle — When last adjusted.
    """

    total_active_tracks: int
    allocations: dict[str, float]
    actual_usage: dict[str, float]
    imbalance_score: float
    rebalance_needed: bool
    last_rebalance_cycle: int


# ---------------------------------------------------------------------------
# 4.4  Track Graduation
# ---------------------------------------------------------------------------


@dataclass
class TrackGraduationState:
    """Mutable graduation progress state for a single track.

    Tracks the current gate attempt, exam pass rate, and historical gate
    completions.  Updated during GRADUATING phase cycles.

    Fields (10 total):
        track_id              — Which track.
        current_gate          — G1–G5 (string label).
        consecutive_sessions  — Current passing streak.
        required_sessions     — Sessions needed to complete the gate.
        exam_cycles_completed — EXAM cycles in current attempt.
        exam_pass_rate        — Pass rate on EXAMs in current attempt.
        attempt_start_cycle   — When current attempt started (None if no
                                active attempt).
        previous_attempts     — Failed attempts at current gate.
        best_streak           — Longest passing streak ever recorded.
        gate_history          — Previous gate completions (list of dicts
                                with gate, completed_at_cycle, attempts,
                                final_pass_rate).
    """

    track_id: EngineeringTrack
    current_gate: str = "G1"
    consecutive_sessions: int = 0
    required_sessions: int = 15
    exam_cycles_completed: int = 0
    exam_pass_rate: float = 0.0
    attempt_start_cycle: Optional[int] = None
    previous_attempts: int = 0
    best_streak: int = 0
    gate_history: list[dict] = field(default_factory=list)


# ---------------------------------------------------------------------------
# 4.4.1  Graduation Ceiling Detection
# ---------------------------------------------------------------------------


@dataclass
class GraduationCeilingFlag:
    """Evidence record built when a track blocks system graduation.

    The system must demonstrate it has tried every intervention and articulate
    clearly why it is stuck before requesting human override.  Mutable so
    evidence fields can be appended as new strategies are attempted.

    Fields (21 total):
        flag_id                        — Unique identifier.
        system_gate                    — G1–G5 being attempted system-wide.
        blocking_track                 — Which track is blocking graduation.
        blocking_track_pass_rate       — Current pass rate of the blocking
                                         track.
        blocking_track_target          — What the gate requires.
        system_avg_pass_rate           — Average pass rate across all tracks.
        non_blocking_tracks_pass_rate  — Average of tracks that DO meet the
                                         threshold.
        cycles_at_current_level        — How long the system has been stuck.
        improvement_trend              — Still improving or flatlined.
        estimated_cycles_to_threshold  — Extrapolated ETA (None if flatlined).
        strategies_attempted           — Every intervention tried + outcomes.
        total_track_cycles             — Total cycles invested in blocking
                                         track.
        cycles_since_last_improvement  — Cycles since meaningful improvement.
        detailed_reasoning             — System's full explanation.
        alternative_approaches_considered — What else could be tried + why
                                            system thinks it won't work.
        self_assessment_confidence     — How sure the system is this is
                                         ceiling vs. plateau (0.0–1.0).
        recommendation                 — HUMAN_OVERRIDE_SUGGESTED |
                                         KEEP_TRAINING | PAUSE_TRACK.
        evidence                       — All supporting data dict.
        created_at_cycle               — When flagged.
        reviewed                       — Has human reviewed.
        review_outcome                 — APPROVED_GRADUATION | KEEP_TRAINING |
                                         THRESHOLD_ADJUSTED | TRACK_PAUSED
                                         (None until reviewed).
    """

    flag_id: str
    system_gate: str
    blocking_track: EngineeringTrack
    blocking_track_pass_rate: float
    blocking_track_target: float
    system_avg_pass_rate: float
    non_blocking_tracks_pass_rate: float
    cycles_at_current_level: int
    improvement_trend: Trend
    estimated_cycles_to_threshold: Optional[int]
    strategies_attempted: list[dict] = field(default_factory=list)
    total_track_cycles: int = 0
    cycles_since_last_improvement: int = 0
    detailed_reasoning: str = ""
    alternative_approaches_considered: list[str] = field(default_factory=list)
    self_assessment_confidence: float = 0.0
    recommendation: str = "KEEP_TRAINING"
    evidence: dict = field(default_factory=dict)
    created_at_cycle: int = 0
    reviewed: bool = False
    review_outcome: Optional[str] = None


@dataclass(frozen=True)
class GraduationOverride:
    """Human-approved record allowing a track to graduate below its threshold.

    Frozen — append-only.  Each override is a permanent audit entry; reverts
    require a new override record (conditions field may encode revert logic).

    Fields (9 total):
        override_id         — Unique identifier.
        system_gate         — G1–G5 being overridden.
        track_id            — Which track received the override.
        original_threshold  — What the gate required.
        actual_pass_rate    — What the track actually achieved.
        approved_by         — Approver identifier (HUMAN or user ID).
        justification       — Human's reasoning.
        conditions          — Optional revert conditions (e.g. "must reach
                               85% within 2000 cycles or revert").
        created_at          — ISO-8601 timestamp.
        cycle_number        — System cycle when approved.
    """

    override_id: str
    system_gate: str
    track_id: EngineeringTrack
    original_threshold: float
    actual_pass_rate: float
    approved_by: str
    justification: str
    conditions: Optional[str]
    created_at: str
    cycle_number: int


# ---------------------------------------------------------------------------
# 4.5  Cross-Track Learning
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CrossTrackInsight:
    """A single transferable pattern from one domain to another.

    Frozen — each insight is an immutable observation; outcomes are recorded
    by creating updated frozen copies or new sibling records.

    Fields (12 total):
        source_track             — Where the pattern originated.
        target_track             — Where it could apply.
        pattern_id               — The transferable pattern's identifier.
        transfer_type            — DIRECT_APPLY | ADAPT_REQUIRED |
                                   PRINCIPLE_ONLY.
        confidence               — Likelihood of successful transfer (0.0–1.0).
        generalization_quality   — Success rate of this pattern's transfers
                                   (None until measured).
        attempted                — Has transfer been tried.
        outcome                  — SUCCESS | PARTIAL | FAILED (None if not
                                   yet attempted).
        test_cycles              — Cycle IDs where transferred pattern applied.
        effectiveness_in_target  — Measured effectiveness after application
                                   (None if not yet measured).
        discovery_cycle          — When insight was found.
        notes                    — Free-form additional context.
    """

    source_track: EngineeringTrack
    target_track: EngineeringTrack
    pattern_id: str
    transfer_type: str
    confidence: float
    generalization_quality: Optional[float]
    attempted: bool
    outcome: Optional[str]
    test_cycles: tuple[int, ...]
    effectiveness_in_target: Optional[float]
    discovery_cycle: int
    notes: str = ""


@dataclass(frozen=True)
class DomainTaskPool:
    """Inventory snapshot of available tasks for a (track, language) pair.

    Frozen — produced periodically by the pool-refresh process; prior
    snapshots kept for trend analysis.

    Fields (9 total):
        track_id               — Which domain.
        language               — Language for this pool.
        total_tasks            — Tasks available.
        task_source_breakdown  — Source → count
                                 (e.g. {"exercism": 500, "generated": 200}).
        tasks_by_level         — Count per F-level string label.
        tasks_attempted        — How many have been tried.
        tasks_mastered         — Tasks with >90% best pass rate.
        last_refresh_date      — ISO-8601 date when pool last expanded.
        generation_ready       — Can auto-generate new tasks for this pool.
    """

    track_id: EngineeringTrack
    language: Language
    total_tasks: int
    task_source_breakdown: dict[str, int]
    tasks_by_level: dict[str, int]
    tasks_attempted: int
    tasks_mastered: int
    last_refresh_date: str
    generation_ready: bool


@dataclass(frozen=True)
class TrackBenchmarkMapping:
    """Maps a track to the benchmark IDs used for its EXAM scoring.

    Frozen — structural mapping that changes only via human configuration.

    Fields (5 total):
        track_id                  — Which track.
        benchmark_ids             — Applicable benchmark IDs.
        primary_benchmark         — Main benchmark for this track.
        graduation_benchmark      — Which benchmark is used for EXAM scoring.
        benchmark_interval_cycles — Per-track override for benchmark
                                    frequency (None = use system default).
    """

    track_id: EngineeringTrack
    benchmark_ids: tuple[str, ...]
    primary_benchmark: str
    graduation_benchmark: str
    benchmark_interval_cycles: Optional[int]


# ---------------------------------------------------------------------------
# 4.6  Task Self-Generation Subsystem
# ---------------------------------------------------------------------------


@dataclass
class GeneratedTaskCandidate:
    """A single task candidate produced by the self-generation subsystem.

    Mutable — quality assessment and acceptance status are populated after
    generation during the verification pipeline.

    Flow: generated → verified (TaskVerificationResult) → accepted/rejected
          → if accepted, enters DomainTaskPool.

    Fields (14 total):
        candidate_id          — Unique identifier.
        track_id              — Target track.
        target_f_level        — Target difficulty.
        language              — Target language.
        generated_description — Problem statement.
        generated_tests       — Test code.
        generated_solution    — Reference solution (proves task is solvable).
        generated_metadata    — Task metadata fields dict.
        quality_assessment    — Verification results dict (None until
                                verified).
        quality_score         — Overall quality 0.0–1.0 (None until
                                verified).
        accepted              — Entered the task pool.
        rejection_reasons     — Why rejected (empty if accepted).
        generated_at_cycle    — When generated.
        generated_by          — MAIN or agent_id string.
    """

    candidate_id: str
    track_id: EngineeringTrack
    target_f_level: TaskLevel
    language: Language
    generated_description: str
    generated_tests: str
    generated_solution: str
    generated_metadata: dict = field(default_factory=dict)
    quality_assessment: Optional[dict] = None
    quality_score: Optional[float] = None
    accepted: bool = False
    rejection_reasons: list[str] = field(default_factory=list)
    generated_at_cycle: int = 0
    generated_by: str = "MAIN"


@dataclass(frozen=True)
class TaskVerificationResult:
    """Result of running the quality-verification pipeline on a candidate task.

    Frozen — verification is a one-time assessment; re-verification produces
    a new record.

    ⚠  novelty_score prevents gaming: the system cannot generate near-
    duplicates of tasks it already solves.  Minimum threshold is read from
    TaskGenerationConfig.min_novelty_score at verification time.

    Fields (11 total):
        candidate_id           — Which candidate was verified.
        is_solvable            — Reference solution passes generated tests.
        tests_valid            — Tests actually test what description asks.
        difficulty_appropriate — Actually at claimed F-level.
        difficulty_verified    — Confirmed not trivially easy.
        description_clear      — Problem statement is unambiguous.
        tests_comprehensive    — Tests cover edge cases.
        novelty_score          — 0.0–1.0 difference from existing tasks via
                                 embedding comparison.
        overall_pass           — All checks passed.
        failure_details        — What failed (empty if overall_pass=True).
        verified_at_cycle      — When verification ran.
    """

    candidate_id: str
    is_solvable: bool
    tests_valid: bool
    difficulty_appropriate: bool
    difficulty_verified: bool
    description_clear: bool
    tests_comprehensive: bool
    novelty_score: float
    overall_pass: bool
    failure_details: tuple[str, ...]
    verified_at_cycle: int


@dataclass
class TaskGenerationCapability:
    """Mutable privilege and statistics record for self-generation per track.

    When the acceptance_rate drops below TaskGenerationConfig.min_acceptance_rate
    the privilege is revoked (enabled=False) and privilege_revoked_at_cycle is
    set.  The system may later request reinstatement with evidence.

    ⚠  acceptance_rate = accepted / generated (recomputable from
    total_accepted / total_generated).

    Fields (12 total):
        track_id                    — Per-track capability tracking.
        enabled                     — Currently allowed to generate.
        total_generated             — Lifetime generated count.
        total_accepted              — Lifetime accepted count.
        total_rejected              — Lifetime rejected count.
        acceptance_rate             — accepted / generated.
        last_generation_cycle       — Most recent generation cycle.
        privilege_revoked_at_cycle  — When privilege was lost (None if still
                                      held).
        revocation_reason           — Why revoked (None if not revoked).
        reinstatement_requested     — Has system asked for privilege back.
        reinstatement_request_cycle — When reinstatement was requested (None
                                      if not requested).
        reinstatement_evidence      — System's argument for reinstatement
                                      (None if not requested).
    """

    track_id: EngineeringTrack
    enabled: bool = True
    total_generated: int = 0
    total_accepted: int = 0
    total_rejected: int = 0
    acceptance_rate: float = 0.0
    last_generation_cycle: int = 0
    privilege_revoked_at_cycle: Optional[int] = None
    revocation_reason: Optional[str] = None
    reinstatement_requested: bool = False
    reinstatement_request_cycle: Optional[int] = None
    reinstatement_evidence: Optional[str] = None


# ---------------------------------------------------------------------------
# 4.7  Overnight Session
# ---------------------------------------------------------------------------


@dataclass
class OvernightSession:
    """Mutable record of a single unattended overnight training session.

    Created at session start; updated in-place as cycles complete; finalised
    when the session ends (ended_at populated).

    Fields (13 total):
        session_id      — Unique identifier.
        start_cycle     — First cycle in this session.
        end_cycle       — Last cycle in this session (0 while running).
        planned_cycles  — Target cycle count for the session.
        actual_cycles   — Completed cycles so far.
        tracks_run      — Which track IDs ran during this session.
        per_track_cycles — Cycles per track ID.
        cost_spent      — Total USD cost accumulated.
        pass_rate       — Overall pass rate across all cycles.
        notable_events  — Alerts, graduations, track transitions, etc.
        started_at      — ISO-8601 timestamp when session started.
        ended_at        — ISO-8601 timestamp when session ended (None if
                          still running).
        summary         — Optional free-form summary written at session end.
    """

    session_id: str
    start_cycle: int
    end_cycle: int
    planned_cycles: int
    actual_cycles: int = 0
    tracks_run: list[str] = field(default_factory=list)
    per_track_cycles: dict[str, int] = field(default_factory=dict)
    cost_spent: float = 0.0
    pass_rate: float = 0.0
    notable_events: list[str] = field(default_factory=list)
    started_at: str = ""
    ended_at: Optional[str] = None
    summary: Optional[str] = None
