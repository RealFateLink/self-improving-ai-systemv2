"""
config.py — Layer 0 Configuration Dataclasses
===============================================
All ~44 mutable configuration dataclasses for the Self-Improving Engineering AI
system. These are pure data-holding structures; no executable logic lives here.

Each class is a regular (mutable) @dataclass with typed fields and sensible
defaults. All dataclasses are ordered so that dependencies come before the
types that reference them.

Sections:
  A. Sandbox configs          (QEMUSandboxConfig, SandboxConfig)
  B. Core subsystem configs   (LLMConfig, BudgetConfig, ScoringConfig,
                               CurriculumConfig, FailureConfig, StrategyConfig,
                               AgentConfig, BenchmarkConfig, ObservabilityConfig)
  C. Graduation / optimization (GraduationSystemConfig, OptimizationConfig,
                                ExplorationConfig, CompressionConfig)
  D. Safety / recovery        (SafetyConfig, RecoveryConfig)
  E. Multi-track subsystem    (TrackSchedulingConfig, TrackGraduationConfig,
                               CrossDomainConfig, TrackDefinitionConfig,
                               TrackReadinessCriteria, TracksConfig)
  F. Task generation          (TaskGenerationConfig)
  G. Top-level                (SystemConfig)

New vs. original: TrackSchedulingConfig, TrackGraduationConfig,
CrossDomainConfig, TrackDefinitionConfig, TrackReadinessCriteria,
TracksConfig, TaskGenerationConfig, and QEMUSandboxConfig are the 8 new
additions from the multi-track expansion (Blueprint §6).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .enums import (
    EngineeringTrack,
    Language,
    RebalanceStrategy,
    SandboxType,
    TaskLevel,
)

__all__ = [
    # A. Sandbox
    "QEMUSandboxConfig",
    "SandboxConfig",
    # B. Core subsystem configs
    "LLMConfig",
    "BudgetConfig",
    "ScoringConfig",
    "CurriculumConfig",
    "FailureConfig",
    "StrategyConfig",
    "AgentConfig",
    "BenchmarkConfig",
    "ObservabilityConfig",
    # C. Graduation / optimization
    "GraduationSystemConfig",
    "OptimizationConfig",
    "ExplorationConfig",
    "CompressionConfig",
    # D. Safety / recovery
    "SafetyConfig",
    "RecoveryConfig",
    # E. Multi-track subsystem
    "TrackSchedulingConfig",
    "TrackGraduationConfig",
    "CrossDomainConfig",
    "TrackDefinitionConfig",
    "TrackReadinessCriteria",
    "TracksConfig",
    # F. Task generation
    "TaskGenerationConfig",
    # G. Top-level
    "SystemConfig",
]

# ---------------------------------------------------------------------------
# A. Sandbox Configs
# ---------------------------------------------------------------------------


@dataclass
class QEMUSandboxConfig:
    """Configuration for QEMU-based VM sandboxes.

    Used when SandboxType.QEMU is selected. Provides full VM isolation for
    untrusted code execution, supporting multiple CPU architectures.
    """

    image_path: str = ""
    """Path to the base QEMU disk image."""

    memory_mb: int = 512
    """RAM allocated to the VM in megabytes."""

    cpu_cores: int = 1
    """Number of virtual CPU cores for the VM."""

    timeout_seconds: int = 120
    """Maximum wall-clock time for a single VM execution."""

    snapshot_before_run: bool = True
    """Whether to snapshot the VM state before each run for clean rollback."""

    network_enabled: bool = False
    """Whether the VM has network access (default disabled for safety)."""

    arch: str = "x86_64"
    """Target CPU architecture (e.g. 'x86_64', 'arm64', 'riscv64')."""


@dataclass
class SandboxConfig:
    """Configuration for the code-execution sandbox layer.

    Controls which isolation mechanism is used and sets resource limits,
    import allowlists/blocklists, and backend-specific parameters.
    """

    default_type: SandboxType = SandboxType.SUBPROCESS
    """Default sandbox isolation mechanism."""

    timeout_seconds: int = 30
    """Maximum execution time for subprocess sandboxes in seconds."""

    memory_limit_mb: int = 256
    """Memory ceiling for subprocess sandboxes in megabytes."""

    allowed_imports: list[str] = field(default_factory=list)
    """Explicit allowlist of top-level Python import names. Empty = no allowlist."""

    blocked_imports: list[str] = field(default_factory=list)
    """Blocklist of top-level Python import names that will be rejected."""

    docker_image: str = "python:3.11-slim"
    """Docker image used when default_type is SandboxType.DOCKER."""

    docker_memory_mb: int = 512
    """Memory limit for Docker containers in megabytes."""

    docker_timeout_seconds: int = 60
    """Execution timeout for Docker containers in seconds."""

    qemu: Optional[QEMUSandboxConfig] = None
    """QEMU-specific settings; required when default_type is SandboxType.QEMU."""


# ---------------------------------------------------------------------------
# B. Core Subsystem Configs
# ---------------------------------------------------------------------------


@dataclass
class LLMConfig:
    """Configuration for all LLM API interactions.

    Controls model selection, retry behaviour, generation parameters, rate
    limits, cost tracking, and economy-mode fallback settings.
    """

    default_model: str = "claude-sonnet-4-6"
    """Primary model used for all generation calls."""

    fallback_model: str = "claude-haiku-4-5-20251001"
    """Model to use when the primary model is unavailable or rate-limited."""

    max_retries: int = 3
    """Maximum number of retry attempts for transient LLM errors."""

    timeout_seconds: int = 60
    """Per-request timeout for LLM API calls in seconds."""

    temperature: float = 0.0
    """Sampling temperature for generation (0.0 = deterministic)."""

    max_tokens: int = 4096
    """Maximum tokens in the completion response."""

    rate_limit_rpm: int = 60
    """Requests-per-minute ceiling enforced by the client-side rate limiter."""

    cost_per_1k_prompt_tokens: float = 0.03
    """Estimated USD cost per 1,000 prompt tokens for the default model."""

    cost_per_1k_completion_tokens: float = 0.06
    """Estimated USD cost per 1,000 completion tokens for the default model."""

    economy_model: str = "claude-haiku-4-5-20251001"
    """Cheaper model substituted automatically when economy mode is active."""

    economy_temperature: float = 0.0
    """Sampling temperature used during economy mode."""

    economy_max_tokens: int = 2048
    """Maximum completion tokens allowed during economy mode."""


@dataclass
class BudgetConfig:
    """Spending limits and alert thresholds for LLM API costs.

    Supports monthly, daily, and per-cycle budget caps, automatic economy-mode
    activation, and configurable alert thresholds.
    """

    monthly_budget_usd: float = 100.0
    """Hard monthly spending ceiling in USD."""

    daily_limit_usd: float = 10.0
    """Soft daily spending cap in USD."""

    cycle_limit_usd: float = 1.0
    """Maximum cost allowed for a single training cycle in USD."""

    economy_mode_threshold: float = 0.30
    """Fraction of budget remaining that triggers economy mode (e.g. 0.30 = 30%)."""

    alert_threshold_percent: float = 0.80
    """Fraction of any budget limit that triggers a budget alert (e.g. 0.80 = 80%)."""

    track_per_model: bool = True
    """Whether to record and report costs broken down per LLM model."""


@dataclass
class ScoringConfig:
    """Weights and thresholds for solution quality scoring.

    The five scoring dimension weights must sum to 1.0 in practice, though this
    is not enforced at the dataclass level.
    """

    correctness_weight: float = 0.4
    """Weight of test-correctness in the composite quality score."""

    efficiency_weight: float = 0.2
    """Weight of runtime/space efficiency in the composite quality score."""

    readability_weight: float = 0.2
    """Weight of code readability in the composite quality score."""

    maintainability_weight: float = 0.1
    """Weight of code maintainability in the composite quality score."""

    test_coverage_weight: float = 0.1
    """Weight of test coverage breadth in the composite quality score."""

    promotion_threshold: float = 0.75
    """Minimum composite score required to promote a solution to the ledger."""

    minimum_test_pass: float = 1.0
    """Fraction of tests that must pass for a solution to be considered at all
    (1.0 = all tests must pass)."""


@dataclass
class CurriculumConfig:
    """Controls the adaptive curriculum difficulty ladder.

    Governs when the system moves up or down the F1–F8 difficulty levels,
    how often promotion is evaluated, and how much exploration is allowed.
    """

    starting_level: TaskLevel = TaskLevel.F1
    """Difficulty level used at first boot."""

    promotion_threshold: float = 0.85
    """Pass rate required to promote to the next difficulty level."""

    demotion_threshold: float = 0.40
    """Pass rate below which the system demotes to the previous difficulty level."""

    cycles_before_promotion_check: int = 50
    """Minimum cycles at the current level before a promotion check is run."""

    exploration_budget_percent: float = 0.10
    """Fraction of cycles reserved for exploratory (non-curriculum) tasks."""

    max_directed_queue: int = 20
    """Maximum number of directed tasks held in the priority queue at once."""


@dataclass
class FailureConfig:
    """Parameters for failure-chain detection and root-cause analysis.

    Controls how many recent cycles the detector inspects, when chains are
    flagged, and how deeply root-cause analysis digs.
    """

    chain_detection_window: int = 10
    """Number of recent cycles inspected for consecutive-failure patterns."""

    min_chain_length: int = 3
    """Minimum consecutive failures needed to open a new failure chain."""

    severity_escalation_threshold: int = 5
    """Chain length at which severity is automatically escalated."""

    max_active_chains: int = 50
    """Maximum number of simultaneously tracked failure chains."""

    narrative_model: str = ""
    """LLM model used for failure narrative generation; empty = use LLMConfig.default_model."""

    root_cause_depth: int = 5
    """Maximum recursive depth for root-cause attribution analysis."""


@dataclass
class StrategyConfig:
    """Governs strategy proposal, probation, confirmation, and rollback.

    A strategy is any system-level behavioural change proposed by the meta-
    learning layer. These settings control its lifecycle.
    """

    max_active_strategies: int = 10
    """Maximum number of strategies that can be in probation or confirmed simultaneously."""

    probation_cycles: int = 100
    """Number of cycles a new strategy must survive before confirmation."""

    confirmation_threshold: float = 0.05
    """Minimum pass-rate improvement over baseline required to confirm a strategy."""

    rollback_threshold: float = -0.05
    """Pass-rate degradation beyond which a strategy is immediately rolled back."""

    pattern_min_applications: int = 5
    """Minimum times a pattern must have been applied before it is evaluated."""

    pattern_validation_threshold: float = 0.60
    """Success rate a pattern must achieve to be promoted from CANDIDATE to VALIDATED."""

    meta_review_interval: int = 100
    """Cycles between full meta-strategy review passes."""

    trigger_cooldown: int = 50
    """Minimum cycles between consecutive triggers of the same strategy type."""


@dataclass
class AgentConfig:
    """Controls the multi-agent sub-system lifecycle and collaboration limits."""

    max_agents: int = 5
    """Maximum number of specialist agents that may be active simultaneously."""

    min_training_cycles: int = 50
    """Minimum training cycles before an agent can leave the TRAINING phase."""

    probation_cycles: int = 50
    """Cycles an agent must survive in PROBATION before becoming fully ACTIVE."""

    probation_margin: float = 0.05
    """Minimum pass-rate improvement over the generalist required during probation."""

    auto_dissolve_below: float = 0.30
    """Pass rate below which an agent is automatically dissolved."""

    merge_similarity_threshold: float = 0.80
    """Embedding similarity above which two agents are candidates for merging."""

    communication_enabled: bool = True
    """Whether the inter-agent message bus is active."""

    max_messages_per_cycle: int = 10
    """Maximum messages any single agent may send on the bus per cycle."""


@dataclass
class BenchmarkConfig:
    """Settings for anonymous benchmark evaluation runs.

    Benchmarks measure the system's generalisation ability on held-out problem
    sets, separate from the main training curriculum.
    """

    enabled: bool = True
    """Master switch for benchmark runs."""

    interval_cycles: int = 1000
    """How often (in training cycles) a benchmark run is triggered."""

    benchmark_dir: str = "benchmarks/"
    """Filesystem directory containing benchmark problem sets."""

    anonymous_feeding: bool = True
    """Whether benchmark problems are injected anonymously into the training cycle."""

    isolation_checks: bool = True
    """Whether integrity checks are run to ensure benchmark problems were never seen."""

    swe_bench_enabled: bool = False
    """Whether the SWE-bench software-engineering benchmark suite is enabled."""


@dataclass
class ObservabilityConfig:
    """Controls the observability and alerting subsystem.

    Governs distributed tracing, analytics digest frequency, alert retention,
    and health-check cadence.
    """

    trace_enabled: bool = True
    """Whether per-cycle execution tracing is active."""

    digest_interval: int = 100
    """Cycles between analytics digest snapshots."""

    alert_retention_cycles: int = 10000
    """Number of cycles for which fired alerts are retained in the store."""

    max_active_alerts: int = 100
    """Maximum number of simultaneously active (unfired/unresolved) alerts."""

    health_check_interval: int = 10
    """Cycles between system health-check runs."""


# ---------------------------------------------------------------------------
# C. Graduation / Optimization Configs
# ---------------------------------------------------------------------------


@dataclass
class GraduationSystemConfig:
    """Global graduation system parameters shared across all tracks.

    These defaults apply to all graduation gates unless overridden by a
    per-track TrackDefinitionConfig.
    """

    exam_allocation: float = 0.25
    """Fraction of cycles allocated to EXAM mode during graduation attempts."""

    consecutive_sessions: int = 15
    """Number of consecutive passing exam sessions required to clear a gate."""

    exam_size: int = 200
    """Number of cycles per exam session."""

    default_gate_pass_rates: dict[str, float] = field(
        default_factory=lambda: {
            "G1": 0.92,
            "G2": 0.94,
            "G3": 0.96,
            "G4": 0.97,
            "G5": 0.98,
        }
    )
    """Required pass rates for each graduation gate G1–G5."""


@dataclass
class OptimizationConfig:
    """Controls the solution-optimisation subsystem.

    After a correct solution is promoted, the optimiser attempts to improve it
    along one or more dimensions (e.g. runtime, readability).
    """

    enabled: bool = True
    """Master switch for post-promotion solution optimisation."""

    max_candidates: int = 3
    """Maximum optimisation candidates generated per solution."""

    auto_apply_threshold: float = 0.90
    """Minimum quality score for an optimised candidate to be auto-applied."""

    dimensions: list[str] = field(
        default_factory=lambda: ["runtime", "readability"]
    )
    """Optimisation dimensions to attempt, in priority order."""


@dataclass
class ExplorationConfig:
    """Controls the exploratory cycle budget and risk appetite.

    Exploration cycles are used to probe novel strategies or patterns outside
    the main curriculum.
    """

    enabled: bool = True
    """Master switch for exploration cycles."""

    budget_percent: float = 0.10
    """Fraction of total cycles reserved for exploration."""

    max_risk_score: float = 0.80
    """Maximum acceptable risk score for an exploration candidate to be run."""

    min_expected_learning: float = 0.30
    """Minimum expected learning gain required to approve an exploration candidate."""


@dataclass
class CompressionConfig:
    """Controls memory compression tiers for the training history store.

    Older records are progressively compacted to reduce storage footprint while
    retaining sufficient signal for meta-learning.
    """

    warm_tier_cycles: int = 10
    """Records younger than this (in cycles) stay in the warm (full-detail) tier."""

    cold_tier_cycles: int = 100
    """Records older than this (in cycles) are moved to the cold (compressed) tier."""

    enabled: bool = True
    """Whether compression is active."""


# ---------------------------------------------------------------------------
# D. Safety / Recovery Configs
# ---------------------------------------------------------------------------


@dataclass
class SafetyConfig:
    """Invariant enforcement and sandbox-violation response settings."""

    max_invariant_violations: int = 3
    """Number of invariant violations permitted before the system halts."""

    halt_on_violation: bool = True
    """Whether to halt the training loop immediately on an invariant violation."""

    monitored_violation_types: list[str] = field(
        default_factory=lambda: [
            "filesystem_access",
            "network_access",
            "env_access",
        ]
    )
    """ViolationType string values that are actively monitored and counted."""


@dataclass
class RecoveryConfig:
    """Retry and back-off parameters for the error-recovery subsystem."""

    max_retries: int = 3
    """Maximum recovery retry attempts before the cycle is marked as failed."""

    backoff_multiplier: float = 2.0
    """Exponential back-off multiplier applied between successive retries."""

    max_backoff_seconds: int = 300
    """Hard ceiling on the computed back-off delay in seconds."""


# ---------------------------------------------------------------------------
# E. Multi-Track Subsystem Configs  (★ NEW — Blueprint §6)
# ---------------------------------------------------------------------------


@dataclass
class TrackSchedulingConfig:
    """Cycle-allocation scheduling parameters for multi-track operation.

    Controls which scheduling algorithm is used, how often tracks are switched,
    and how performance/stagnation/graduation-proximity influence priority.
    """

    algorithm: str = "WEIGHTED_ROUND_ROBIN"
    """Scheduling algorithm: WEIGHTED_ROUND_ROBIN | PRIORITY_QUEUE | ADAPTIVE."""

    rebalance_strategy: RebalanceStrategy = RebalanceStrategy.PROPORTIONAL
    """How cycle allocations are redistributed when tracks activate or deactivate."""

    period_length_cycles: int = 100
    """Length of one scheduling period in training cycles."""

    min_consecutive_same_track: int = 5
    """Minimum consecutive cycles on the same track before a switch is allowed."""

    max_consecutive_same_track: int = 50
    """Maximum consecutive cycles on the same track before a switch is forced."""

    priority_weight_performance: float = 0.3
    """Weight given to recent pass-rate performance when computing track priority."""

    priority_weight_stagnation: float = 0.4
    """Weight given to stagnation duration when computing track priority
    (higher stagnation → higher priority boost)."""

    priority_weight_graduation_proximity: float = 0.3
    """Weight given to proximity to the next graduation gate when computing priority."""


@dataclass
class TrackGraduationConfig:
    """Per-track graduation gate configuration and ceiling-detection settings.

    These defaults apply system-wide; per-track overrides live in
    TrackDefinitionConfig.override_graduation.
    """

    independent_gates: bool = True
    """Whether each track has its own independent graduation gate progression."""

    system_graduation_rule: str = "PRIMARY_TRACK"
    """Rule for computing the system-level graduation tier:
    PRIMARY_TRACK | MIN_ALL_ACTIVE | WEIGHTED_AVERAGE | MAJORITY."""

    exam_allocation_default: float = 0.25
    """Default fraction of cycles allocated to EXAM mode per track."""

    consecutive_sessions_default: int = 15
    """Default number of consecutive passing sessions required to clear a gate."""

    exam_size_default: int = 200
    """Default number of cycles per exam session."""

    pause_on_python_drop: bool = True
    """Pause non-Python tracks automatically if Python pass rate drops below
    python_safety_threshold."""

    python_safety_threshold: float = 0.90
    """Minimum Python pass rate before non-Python tracks are paused."""

    auto_graduation_trigger_threshold: float = 0.05
    """Pass-rate margin above the current gate threshold that triggers an automatic
    exam attempt."""

    auto_graduation_sustained_cycles: int = 200
    """Cycles the pass rate must be sustained above the trigger threshold before
    the exam attempt begins."""

    ceiling_detection_enabled: bool = True
    """Whether to detect tracks that are blocking system graduation (ceiling)."""

    ceiling_stall_cycles: int = 3000
    """Cycles without gate progress before a track is flagged as a ceiling."""

    ceiling_min_pass_rate_for_override: float = 0.65
    """Minimum pass rate a stalled track must achieve before a ceiling override
    is even considered."""


@dataclass
class CrossDomainConfig:
    """Configuration for cross-track pattern-transfer analysis.

    When a pattern proven effective in one engineering track might apply to
    another, this config controls whether and how that transfer is attempted.
    """

    transfer_enabled: bool = True
    """Master switch for cross-track pattern transfer."""

    min_pattern_effectiveness: float = 0.60
    """Minimum effectiveness score in the source track before a pattern is
    considered for transfer."""

    transfer_confidence_threshold: float = 0.75
    """Confidence level required to auto-apply a transferred pattern without
    human review."""

    max_transfers_per_period: int = 10
    """Rate limit on the number of transfer attempts per scheduling period."""

    assessment_interval_cycles: int = 500
    """Cycles between full scans for transferable patterns."""

    min_pattern_applications: int = 5
    """Minimum applications in the source track before a pattern is assessed
    for transfer."""

    min_generalization_quality: float = 0.30
    """Minimum generalisation quality score below which transfer attempts for
    that pattern are suspended."""

    generalization_prompt_template: str = "cross_track_generalize"
    """Name of the prompt template used for generalisation assessment."""

    adaptation_prompt_template: str = "cross_track_adapt"
    """Name of the prompt template used for adaptation during transfer."""


@dataclass
class TrackDefinitionConfig:
    """Per-track configuration overrides.

    One instance per entry in TracksConfig.track_definitions (keyed by track
    ID string). All fields are optional; None means use the system default.
    """

    override_allocation: Optional[float] = None
    """Override the default cycle-allocation percentage for this track."""

    override_graduation: Optional[dict] = None
    """Override graduation gate definitions for this track (serialised dict)."""

    custom_sandbox_config: Optional[dict] = None
    """Full sandbox configuration dict override for this track."""

    docker_image_override: Optional[str] = None
    """Alternative Docker image for this track's sandbox."""

    sandbox_memory_mb_override: Optional[int] = None
    """Memory limit override (MB) for this track's sandbox."""

    sandbox_timeout_override: Optional[int] = None
    """Execution timeout override (seconds) for this track's sandbox."""

    custom_prompt_overrides: Optional[dict[str, str]] = None
    """Mapping of base_template_name → override_template_name (REPLACE semantics)."""

    language_weights: Optional[dict] = None
    """Per-language cycle-allocation weights within this track
    (e.g. {'python': 0.6, 'javascript': 0.4})."""


@dataclass
class TrackReadinessCriteria:
    """Criteria that must be met before an inactive track can be activated.

    These thresholds guard against activating a new engineering track before
    the system has sufficient capability and budget headroom.
    """

    min_prerequisite_pass_rate: float = 0.85
    """All prerequisite tracks must be above this pass rate."""

    min_prerequisite_cycles: int = 1000
    """Each prerequisite track must have accumulated at least this many cycles."""

    min_language_pass_rate: float = 0.70
    """Required programming languages must be above this pass rate."""

    min_language_cycles: int = 500
    """Required programming languages must have at least this many cycles."""

    require_all_languages: bool = False
    """If False, meeting the criteria for any required language is sufficient for
    activation; if True, all required languages must qualify."""

    min_pattern_depth: float = 0.40
    """Minimum pattern-coverage score (breadth × depth) before activation."""

    min_budget_headroom_percent: float = 0.15
    """Fraction of budget that must remain available before a new track activates."""

    cooldown_after_last_activation_cycles: int = 2000
    """Minimum cycles to wait after the most recent track activation before another
    track can be activated."""


@dataclass
class TracksConfig:
    """Top-level configuration for the multi-track domain expansion subsystem.

    This is the single entry-point for all multi-track settings. It is embedded
    as SystemConfig.tracks.
    """

    enabled: bool = False
    """Master switch for multi-track operation. False = CORE_ALGORITHMS only."""

    initial_active_tracks: list[EngineeringTrack] = field(
        default_factory=lambda: [EngineeringTrack.CORE_ALGORITHMS]
    )
    """Tracks that start in the ACTIVE state on first boot."""

    max_active_tracks: int = 3
    """Maximum number of tracks that may be simultaneously active."""

    rebalance_interval_cycles: int = 500
    """Cycles between automatic allocation rebalancing passes."""

    stagnation_threshold_cycles: int = 2000
    """Cycles without meaningful improvement before a track is considered stagnant."""

    stagnation_improvement_threshold: float = 0.02
    """Minimum pass-rate improvement (absolute) required to reset the stagnation
    counter for a track."""

    warmup_cycles_per_track: int = 200
    """Immunity cycles for a newly activated track (not penalised during warmup)."""

    activation_cooldown_cycles: int = 2000
    """Minimum cycles between consecutive track activations."""

    max_consecutive_crashes_before_pause: int = 5
    """Number of consecutive sandbox crashes that trigger automatic track pause."""

    overnight_focus_mode: bool = False
    """Whether overnight sessions concentrate on the weakest active track."""

    overnight_focus_threshold: float = 0.15
    """Pass-rate gap between the weakest and average track that enables focus mode."""

    readiness_check_interval_cycles: int = 500
    """Cycles between readiness evaluations for inactive tracks."""

    scheduling: TrackSchedulingConfig = field(
        default_factory=TrackSchedulingConfig
    )
    """Cycle-allocation scheduling configuration."""

    graduation: TrackGraduationConfig = field(
        default_factory=TrackGraduationConfig
    )
    """Per-track graduation and ceiling-detection configuration."""

    cross_domain: CrossDomainConfig = field(
        default_factory=CrossDomainConfig
    )
    """Cross-track pattern-transfer configuration."""

    track_definitions: dict[str, TrackDefinitionConfig] = field(
        default_factory=dict
    )
    """Per-track override configs, keyed by EngineeringTrack string value."""

    readiness_criteria: TrackReadinessCriteria = field(
        default_factory=TrackReadinessCriteria
    )
    """Criteria used to evaluate whether an inactive track is ready for activation."""


# ---------------------------------------------------------------------------
# F. Task Generation Config  (★ NEW — Blueprint §6.8)
# ---------------------------------------------------------------------------


@dataclass
class TaskGenerationConfig:
    """Configuration for the task self-generation subsystem.

    The system generates its own training tasks, verifies quality, and self-
    manages generation privileges on a per-track basis.
    """

    enabled: bool = True
    """Master switch for task self-generation."""

    min_acceptance_rate: float = 0.70
    """Minimum acceptance rate for generated tasks; dropping below this threshold
    triggers privilege revocation for the offending track."""

    min_novelty_score: float = 0.30
    """Minimum embedding-distance novelty score required for a generated task to
    be accepted (prevents near-duplicate generation)."""

    verification_attempts_per_task: int = 3
    """Number of independent solve attempts used to verify a generated task is
    actually solvable."""

    revocation_cooldown_cycles: int = 2000
    """Cycles a track must wait after privilege revocation before it may request
    reinstatement."""

    max_generated_per_batch: int = 10
    """Maximum number of task candidates produced in a single generation batch."""

    human_review_on_revocation: bool = True
    """Whether a human-review flag is raised when generation privilege is revoked."""


# ---------------------------------------------------------------------------
# G. Top-Level System Config
# ---------------------------------------------------------------------------


@dataclass
class SystemConfig:
    """Root configuration object for the entire Self-Improving Engineering AI
    system.

    One instance of SystemConfig is the single source of truth for all tunable
    parameters at runtime. It is typically loaded from defaults.yaml and then
    optionally patched by environment-specific overrides.
    """

    project_name: str = "self_improving_ai"
    """Human-readable project identifier embedded in logs and reports."""

    version: str = "0.1.0"
    """Semantic version of the system configuration schema."""

    max_cycles: int = 100_000
    """Hard upper bound on total training cycles before the system halts."""

    log_level: str = "INFO"
    """Python logging level string: DEBUG | INFO | WARNING | ERROR | CRITICAL."""

    data_dir: str = "data/"
    """Root directory for all persistent data (database, artefacts, logs)."""

    llm: LLMConfig = field(default_factory=LLMConfig)
    """LLM API and generation settings."""

    sandbox: SandboxConfig = field(default_factory=SandboxConfig)
    """Code-execution sandbox settings."""

    budget: BudgetConfig = field(default_factory=BudgetConfig)
    """Spending limits and alert thresholds."""

    scoring: ScoringConfig = field(default_factory=ScoringConfig)
    """Solution quality scoring weights and thresholds."""

    curriculum: CurriculumConfig = field(default_factory=CurriculumConfig)
    """Adaptive curriculum difficulty settings."""

    failure: FailureConfig = field(default_factory=FailureConfig)
    """Failure-chain detection and root-cause analysis settings."""

    strategy: StrategyConfig = field(default_factory=StrategyConfig)
    """Strategy proposal, probation, and rollback settings."""

    agents: AgentConfig = field(default_factory=AgentConfig)
    """Multi-agent subsystem lifecycle settings."""

    benchmarks: BenchmarkConfig = field(default_factory=BenchmarkConfig)
    """Anonymous benchmark evaluation settings."""

    observability: ObservabilityConfig = field(
        default_factory=ObservabilityConfig
    )
    """Tracing, alerting, and health-check settings."""

    graduation: GraduationSystemConfig = field(
        default_factory=GraduationSystemConfig
    )
    """Global graduation gate defaults."""

    optimization: OptimizationConfig = field(
        default_factory=OptimizationConfig
    )
    """Post-promotion solution optimisation settings."""

    exploration: ExplorationConfig = field(default_factory=ExplorationConfig)
    """Exploratory cycle budget and risk settings."""

    compression: CompressionConfig = field(default_factory=CompressionConfig)
    """Memory compression tier settings."""

    safety: SafetyConfig = field(default_factory=SafetyConfig)
    """Invariant enforcement and violation-response settings."""

    recovery: RecoveryConfig = field(default_factory=RecoveryConfig)
    """Error-recovery retry and back-off settings."""

    tracks: TracksConfig = field(default_factory=TracksConfig)
    """Multi-track domain expansion settings (disabled by default)."""

    task_generation: TaskGenerationConfig = field(
        default_factory=TaskGenerationConfig
    )
    """Task self-generation settings."""
