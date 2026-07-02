"""
common.py — Layer 0 Shared Types
==================================
Shared dataclass types used across the Self-Improving Engineering AI system.
These types are referenced by multiple modules in Layers 1–8.

Python 3.11+. All mutable types use @dataclass; all frozen types use
@dataclass(frozen=True). No executable logic — pure definitions only.

Sections:
  1.  MemoryContext           — mutable  — conversation/session context
  2.  RecoveryState           — mutable  — system recovery tracking
  3.  SystemEvent             — frozen   — structured event log entry
  4.  Alert                   — frozen   — operational alert
  5.  ConfigSnapshot          — frozen   — point-in-time config capture
  6.  ApprovalRequest         — mutable  — pending approval item
  7.  ApprovalHistoryEntry    — frozen   — resolved approval record
  8.  BudgetSnapshot          — frozen   — budget state at a point in time
  9.  LLMCallRecord           — frozen   — single LLM API call record
  10. SandboxExecution        — frozen   — sandbox run record
  11. ProtectedParam          — frozen   — protected DB parameter descriptor
  12. InvariantCheck          — frozen   — invariant definition + last result
  13. CompressionRecord       — frozen   — memory compression event
  14. GateSet                 — frozen   — graduation gate specification
  15. SelfModel               — mutable  — system's model of its own capabilities
  16. SelfModelHistory        — frozen   — historical snapshot of SelfModel
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .enums import (
    AlertSeverity,
    ApprovalItemType,
    ApprovalStatus,
    CheckFrequency,
    CompressionTier,
    EngineeringTrack,
    FailureCategory,
    FinishReason,
    ProtectionLevel,
    RecoveryAction,
    SandboxType,
    SystemEventType,
    TaskLevel,
)

__all__ = [
    # 1. Session / context
    "MemoryContext",
    # 2. Recovery
    "RecoveryState",
    # 3. Observability
    "SystemEvent",
    "Alert",
    # 4. Config
    "ConfigSnapshot",
    # 5. Approval
    "ApprovalRequest",
    "ApprovalHistoryEntry",
    # 6. Budget & cost tracking
    "BudgetSnapshot",
    "LLMCallRecord",
    "SandboxExecution",
    # 7. Safety / invariants
    "ProtectedParam",
    "InvariantCheck",
    # 8. Compression
    "CompressionRecord",
    # 9. Graduation
    "GateSet",
    # 10. Self-model
    "SelfModel",
    "SelfModelHistory",
]


# ---------------------------------------------------------------------------
# 1. MemoryContext
# ---------------------------------------------------------------------------

@dataclass
class MemoryContext:
    """
    Mutable, per-session context carried through the system's working memory.

    Tracks the active session identity, progress through cycles, recently
    observed patterns/failures, active meta-learning strategies, and the
    system's current resource posture.

    ``active_track`` is set to the EngineeringTrack currently being scheduled
    (None when multi-track is disabled or during cross-track operations).
    """

    session_id: str
    """Unique identifier for the current training session."""

    cycle_number: int
    """Monotonically increasing cycle counter within the session."""

    current_task_id: Optional[str] = None
    """Task being attempted in the current cycle (None between cycles)."""

    recent_cycles: list[str] = field(default_factory=list)
    """Ordered list of recent cycle IDs (newest last)."""

    recent_patterns: list[str] = field(default_factory=list)
    """Pattern IDs observed in recent cycles, used for prompt injection."""

    recent_failures: list[str] = field(default_factory=list)
    """Failure category strings observed in recent cycles."""

    active_strategies: list[str] = field(default_factory=list)
    """Strategy IDs currently in CONFIRMED or IN_PROBATION state."""

    self_model_summary: str = ""
    """Human-readable one-paragraph summary from the most recent SelfModel."""

    budget_remaining_percent: float = 1.0
    """Fraction of monthly budget remaining (1.0 = full, 0.0 = exhausted)."""

    economy_mode: bool = False
    """When True, the system restricts LLM calls to reduce spend."""

    active_track: Optional[EngineeringTrack] = None
    """Engineering track currently being executed (None = not set)."""


# ---------------------------------------------------------------------------
# 2. RecoveryState
# ---------------------------------------------------------------------------

@dataclass
class RecoveryState:
    """
    Mutable state for a single recovery episode triggered after a system
    failure.

    A new RecoveryState is created whenever the cycle runner detects an
    unrecoverable error and transitions to CycleStatus.RECOVERING.  The
    record tracks retry attempts, resolution, and — if multi-track is active —
    which track was running when the failure occurred.
    """

    recovery_id: str
    """Unique identifier for this recovery episode."""

    triggered_at_cycle: int
    """Cycle number when recovery was triggered."""

    triggered_by: str
    """Module name or component that initiated recovery."""

    recovery_action: RecoveryAction
    """The action being taken (COMPLETE, ABORT, or RETRY)."""

    original_error: str
    """String representation of the error that caused this recovery."""

    retry_count: int = 0
    """Number of retry attempts made so far."""

    max_retries: int = 3
    """Maximum allowed retries before escalating to ABORT."""

    resolved: bool = False
    """True once recovery concludes (successfully or via abort)."""

    resolved_at_cycle: Optional[int] = None
    """Cycle number when recovery concluded (None if still in progress)."""

    detail: str = ""
    """Free-text explanation for operators/log consumers."""

    active_track: Optional[EngineeringTrack] = None
    """Track that was running when the failure occurred."""


# ---------------------------------------------------------------------------
# 3. SystemEvent
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SystemEvent:
    """
    Immutable structured event emitted by any system component and stored in
    the event bus / event log table.

    SystemEvents are the audit trail of significant lifecycle changes:
    startups, shutdowns, circuit-breaker trips, invariant violations, manual
    pauses, graduation milestones, and track lifecycle transitions.
    """

    event_id: str
    """UUID-format unique identifier for this event."""

    event_type: SystemEventType
    """Category of the event (see SystemEventType enum)."""

    cycle_number: int
    """Cycle number when the event was emitted."""

    timestamp: str
    """UTC ISO-8601 timestamp string."""

    detail: str
    """Human-readable description of the event."""

    severity: AlertSeverity = AlertSeverity.INFO
    """Severity level — INFO, WARN, or CRITICAL."""

    metadata: Optional[dict[str, str]] = None
    """Optional key/value bag of additional structured metadata."""


# ---------------------------------------------------------------------------
# 4. Alert
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Alert:
    """
    Immutable operational alert emitted by the observability layer.

    Alerts represent conditions that may require human attention, ranging from
    informational notices (economy mode activated) through critical failures
    (invariant violation, budget exhausted).  They are stored in the alerts
    table and surfaced in the operator dashboard.
    """

    alert_id: str
    """UUID-format unique identifier."""

    severity: AlertSeverity
    """INFO, WARN, or CRITICAL."""

    message: str
    """Short human-readable summary of the alert condition."""

    cycle_number: int
    """Cycle number when the alert was raised."""

    timestamp: str
    """UTC ISO-8601 timestamp string."""

    source_module: str
    """Dotted module path that emitted the alert (e.g. 'layer2.evaluator')."""

    acknowledged: bool = False
    """True once an operator has acknowledged the alert."""

    detail: Optional[str] = None
    """Optional verbose description with diagnostic information."""


# ---------------------------------------------------------------------------
# 5. ConfigSnapshot
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ConfigSnapshot:
    """
    Immutable point-in-time snapshot of the system configuration.

    A ConfigSnapshot is written whenever the effective configuration changes
    (e.g., a parameter is updated via an approved ApprovalRequest).  The
    ``config_hash`` is a SHA-256 hex digest of the serialised config_data,
    allowing change detection without full diff comparison.
    """

    snapshot_id: str
    """Unique identifier for this snapshot."""

    cycle_number: int
    """Cycle during which the snapshot was taken."""

    timestamp: str
    """UTC ISO-8601 timestamp string."""

    config_hash: str
    """SHA-256 hex digest of the serialised configuration."""

    config_data: dict
    """Full configuration dictionary at the time of snapshot."""

    change_description: str = ""
    """Human-readable summary of what changed vs. the previous snapshot."""


# ---------------------------------------------------------------------------
# 6. ApprovalRequest
# ---------------------------------------------------------------------------

@dataclass
class ApprovalRequest:
    """
    Mutable record representing an item awaiting human or system approval.

    Approval requests are created by the system when it wants to perform an
    action that requires external sign-off (e.g., activating a new engineering
    track, reinstating task-generation privileges, proposing an agent).

    The status field progresses: PENDING → APPROVED | REJECTED | DEFERRED.
    """

    request_id: str
    """UUID-format unique identifier."""

    item_type: ApprovalItemType
    """Category of the item requiring approval."""

    title: str
    """Short title shown in the approval queue UI."""

    description: str
    """Full description of what is being requested and why."""

    evidence: dict = field(default_factory=dict)
    """Supporting data assembled by the system (metrics, reasoning, etc.)."""

    status: ApprovalStatus = ApprovalStatus.PENDING
    """Current disposition of the request."""

    requested_at: str = ""
    """UTC ISO-8601 timestamp when the request was created."""

    resolved_at: Optional[str] = None
    """UTC ISO-8601 timestamp when the request was resolved (None if pending)."""

    resolved_by: Optional[str] = None
    """Identifier of the human or process that resolved the request."""

    resolution_detail: Optional[str] = None
    """Optional notes from the resolver explaining the decision."""


# ---------------------------------------------------------------------------
# 7. ApprovalHistoryEntry
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ApprovalHistoryEntry:
    """
    Immutable historical record of a resolved ApprovalRequest.

    Written once an ApprovalRequest transitions out of PENDING.  Provides a
    permanent, tamper-evident audit trail of all human/system decisions.
    """

    entry_id: str
    """UUID-format unique identifier for this history entry."""

    request_id: str
    """Foreign key back to the originating ApprovalRequest."""

    item_type: ApprovalItemType
    """Category of the approved/rejected item."""

    status: ApprovalStatus
    """Final resolution status (APPROVED, REJECTED, or DEFERRED)."""

    resolved_at: str
    """UTC ISO-8601 timestamp of resolution."""

    resolved_by: str
    """Identifier of the human or process that made the decision."""

    resolution_detail: str = ""
    """Optional notes from the resolver."""


# ---------------------------------------------------------------------------
# 8. BudgetSnapshot
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class BudgetSnapshot:
    """
    Immutable point-in-time record of the system's API spend posture.

    BudgetSnapshots are written periodically (and on every economy-mode
    transition) to the budget_snapshots table.  The ``burn_rate_per_cycle``
    and ``projected_depletion_cycle`` fields are computed estimates and may
    be 0 / None if insufficient history exists.
    """

    snapshot_id: str
    """Unique identifier for this snapshot."""

    cycle_number: int
    """Cycle during which the snapshot was recorded."""

    timestamp: str
    """UTC ISO-8601 timestamp string."""

    total_budget_usd: float
    """Total monthly budget ceiling in USD."""

    spent_usd: float
    """Amount spent so far in the current budget period."""

    remaining_usd: float
    """Remaining budget (total_budget_usd - spent_usd)."""

    burn_rate_per_cycle: float = 0.0
    """Rolling average USD cost per training cycle."""

    projected_depletion_cycle: Optional[int] = None
    """Estimated cycle at which budget will be exhausted (None if unknown)."""

    economy_mode_active: bool = False
    """True if the system is currently operating in economy mode."""


# ---------------------------------------------------------------------------
# 9. LLMCallRecord
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class LLMCallRecord:
    """
    Immutable record of a single LLM API call made during a training cycle.

    Every call to the language model is logged here for cost accounting,
    performance debugging, and budget projection.  The ``template_name``
    field identifies which prompt template was used, enabling per-template
    cost analysis.
    """

    call_id: str
    """UUID-format unique identifier for this API call."""

    cycle_number: int
    """Training cycle that issued the call."""

    timestamp: str
    """UTC ISO-8601 timestamp when the call was initiated."""

    model: str
    """Model identifier string (e.g. 'claude-sonnet-4-20250514', 'claude-haiku-3-20250305')."""

    prompt_tokens: int
    """Number of tokens in the prompt/input."""

    completion_tokens: int
    """Number of tokens in the model's response."""

    total_tokens: int
    """Total token count (prompt_tokens + completion_tokens)."""

    cost_usd: float
    """Estimated USD cost for this call."""

    latency_ms: float
    """Wall-clock latency from request dispatch to response receipt."""

    finish_reason: FinishReason
    """Why generation terminated (STOP, MAX_TOKENS, or ERROR)."""

    template_name: str = ""
    """Name of the prompt template used (empty if ad-hoc)."""

    success: bool = True
    """False if the call returned an error or unusable response."""

    error_detail: Optional[str] = None
    """Error message or traceback when success=False."""


# ---------------------------------------------------------------------------
# 10. SandboxExecution
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SandboxExecution:
    """
    Immutable record of a single sandboxed code execution.

    Every time generated or candidate code is run inside a sandbox (subprocess,
    Docker, or QEMU), a SandboxExecution record is persisted.  These records
    feed safety monitoring, cost accounting, and performance diagnostics.
    """

    execution_id: str
    """UUID-format unique identifier for this sandbox run."""

    cycle_number: int
    """Training cycle that triggered the execution."""

    timestamp: str
    """UTC ISO-8601 timestamp when execution started."""

    sandbox_type: SandboxType
    """Isolation mechanism used (SUBPROCESS, DOCKER, or QEMU)."""

    language: str
    """Programming language of the executed code (e.g. 'python', 'rust')."""

    timeout_seconds: int
    """Maximum allowed execution time enforced by the sandbox."""

    actual_runtime_ms: float
    """Measured wall-clock execution time in milliseconds."""

    memory_used_mb: float = 0.0
    """Peak memory consumption during execution in megabytes."""

    exit_code: int = 0
    """Process exit code (0 = success, non-zero = error/timeout)."""

    success: bool = True
    """False if the execution failed, timed out, or exceeded resource limits."""

    error_detail: Optional[str] = None
    """Error message or relevant stderr excerpt when success=False."""

    stdout_excerpt: str = ""
    """First/last N bytes of stdout (truncated for storage efficiency)."""

    stderr_excerpt: str = ""
    """First/last N bytes of stderr (truncated for storage efficiency)."""


# ---------------------------------------------------------------------------
# 11. ProtectedParam
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ProtectedParam:
    """
    Immutable descriptor for a database table or configuration parameter that
    has restricted write access.

    ProtectedParam entries are loaded from ``protected_params.yaml`` at
    startup and used by the invariant-check layer to gate write operations.
    ``allowed_update_columns`` lists columns that the system may modify
    autonomously; all others require human approval.
    """

    table_name: str
    """Name of the database table this protection applies to."""

    protection_level: ProtectionLevel
    """Access-control level governing how the parameter may be changed."""

    allowed_update_columns: list[str] = field(default_factory=list)
    """Column names the system may update without approval."""

    description: str = ""
    """Human-readable explanation of why this parameter is protected."""


# ---------------------------------------------------------------------------
# 12. InvariantCheck
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class InvariantCheck:
    """
    Immutable definition and last-known state of a system invariant.

    Invariants are loaded from ``invariant_hashes.json`` and re-evaluated
    on the schedule defined by ``check_frequency``.  A failing invariant
    raises an ``InvariantViolation`` exception (defined in result.py).
    """

    invariant_id: str
    """Canonical identifier (e.g. 'INV-001', 'INV-007')."""

    description: str
    """Human-readable statement of what this invariant asserts."""

    check_frequency: CheckFrequency
    """When the invariant is evaluated (EVERY_CYCLE, ON_STARTUP, etc.)."""

    module_source: str
    """Dotted module path where the check is defined."""

    last_checked_cycle: int = 0
    """Cycle number of the most recent evaluation (0 = never checked)."""

    last_result: bool = True
    """Result of the most recent evaluation (True = passed)."""

    failure_count: int = 0
    """Cumulative number of times this invariant has failed."""


# ---------------------------------------------------------------------------
# 13. CompressionRecord
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CompressionRecord:
    """
    Immutable record of a memory-compression event.

    The system compresses old cycle records to reduce database size.  Warm
    records (last 10 cycles) are kept verbatim; cold records (older than
    100 cycles) are compressed to summary form.  Each compression event is
    logged here for auditing and storage accounting.
    """

    record_id: str
    """Unique identifier for this compression event."""

    tier: CompressionTier
    """Whether this was a WARM_10 or COLD_100 compression."""

    original_cycle: int
    """Cycle number of the original data that was compressed."""

    compressed_at: str
    """UTC ISO-8601 timestamp when compression occurred."""

    data_type: str
    """Class name of the compressed data type (e.g. 'CycleRecord')."""

    original_size_bytes: int
    """Byte size of the data before compression."""

    compressed_size_bytes: int
    """Byte size of the data after compression."""


# ---------------------------------------------------------------------------
# 14. GateSet
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class GateSet:
    """
    Immutable specification for a single graduation gate.

    Graduation gates (G1–G5) define the pass-rate thresholds and exam
    parameters that the system must meet to advance to the next tier.
    GateSet instances are stored inside TrackConfig.graduation_gates and
    referenced by the graduation engine in Layer 3.
    """

    gate_name: str
    """Gate identifier, e.g. 'G1', 'G2', … 'G5'."""

    required_pass_rate: float
    """Minimum rolling pass rate required to pass this gate (0.0–1.0)."""

    required_consecutive_sessions: int = 15
    """Number of consecutive passing exam sessions needed for gate completion."""

    exam_size: int = 200
    """Number of task cycles constituting one exam session."""

    min_cycles_at_level: int = 1000
    """Minimum total cycles at the current difficulty level before the gate
    may be attempted."""


# ---------------------------------------------------------------------------
# 15. SelfModel
# ---------------------------------------------------------------------------

@dataclass
class SelfModel:
    """
    Mutable snapshot of the system's introspective model of its own
    capabilities and knowledge state.

    The SelfModel is rebuilt from the ledger every N cycles by the analysis
    layer and injected into prompts to provide the LLM with accurate
    self-awareness.  It captures overall performance statistics, known
    strengths and weaknesses, and — after multi-track expansion — per-track
    performance summaries and cross-track transfer effectiveness.

    Persisted to the ``self_model`` table after each rebuild; old versions
    become SelfModelHistory entries.
    """

    model_id: str
    """UUID-format identifier for this version of the self-model."""

    updated_at_cycle: int
    """Cycle number when this model was last rebuilt."""

    overall_pass_rate: float = 0.0
    """Rolling pass rate across all tracks and all cycles (lifetime)."""

    current_tier: int = 1
    """Current system graduation tier (1–5)."""

    current_f_level: TaskLevel = TaskLevel.F1
    """Modal F-level being attempted in the primary track."""

    strengths: list[str] = field(default_factory=list)
    """Free-text descriptions of consistent strengths observed in patterns."""

    weaknesses: list[str] = field(default_factory=list)
    """Free-text descriptions of recurring failure themes."""

    dominant_failure_category: Optional[FailureCategory] = None
    """Most frequently occurring failure category in recent history."""

    patterns_count: int = 0
    """Total validated patterns in the pattern library."""

    prevention_artifacts_count: int = 0
    """Total active prevention artifacts across all tracks."""

    active_strategies: list[str] = field(default_factory=list)
    """IDs of strategies currently in CONFIRMED or IN_PROBATION status."""

    confidence_assessment: str = ""
    """One-paragraph system self-assessment of confidence and readiness."""

    last_benchmark_score: Optional[float] = None
    """Most recent benchmark pass rate (None if no benchmark run yet)."""

    # --- Multi-track expansion fields (Section 5.6) ---

    per_track_performance: dict[str, dict] = field(default_factory=dict)
    """
    Mapping of EngineeringTrack value → performance summary dict.

    Each value dict contains at minimum:
      {
        "pass_rate_overall": float,
        "pass_rate_rolling_100": float,
        "current_f_level": str,
        "total_cycles": int,
        "trend": str,
        "health_score": float,
      }
    """

    strongest_track: Optional[EngineeringTrack] = None
    """Track with the highest current pass_rate_rolling_100."""

    weakest_track: Optional[EngineeringTrack] = None
    """Track with the lowest current pass_rate_rolling_100 (among active tracks)."""

    cross_track_transfer_rate: float = 0.0
    """Fraction of attempted cross-track pattern transfers that succeeded."""

    track_balance_assessment: str = ""
    """Natural-language assessment of allocation balance across active tracks."""

    pending_track_readiness: dict[str, dict] = field(default_factory=dict)
    """
    Readiness summaries for INACTIVE tracks being evaluated for activation.

    Mapping of EngineeringTrack value → readiness summary dict.  Updated each
    time a TrackReadinessAssessment is run.  Example value dict shape:
      {
        "overall_ready": bool,
        "blocking_reasons": list[str],
        "confidence": float,
        "assessed_at_cycle": int,
      }
    """

    task_generation_capability_score: dict[str, float] = field(default_factory=dict)
    """
    Per-track task-generation capability scores (acceptance rate proxy).

    Mapping of EngineeringTrack value → float in [0.0, 1.0].  A score below
    TaskGenerationConfig.min_acceptance_rate indicates revoked privilege.
    """


# ---------------------------------------------------------------------------
# 16. SelfModelHistory
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SelfModelHistory:
    """
    Immutable historical record of a past SelfModel state.

    Every time the analysis layer rebuilds the SelfModel, the previous version
    is archived as a SelfModelHistory entry.  This enables longitudinal
    capability tracking and regression detection.
    """

    entry_id: str
    """UUID-format identifier for this history entry."""

    model_id: str
    """Foreign key back to the SelfModel version being archived."""

    cycle_number: int
    """Cycle number when this model was active."""

    timestamp: str
    """UTC ISO-8601 timestamp when the model was superseded."""

    snapshot: dict
    """Full serialised representation of the SelfModel at this point in time."""
