"""
enums.py — Layer 0 Domain Enumerations
=======================================
All 62 StrEnum types for the Self-Improving Engineering AI system.

Error type enums (LLMErrorType, SandboxErrorType, LedgerErrorType,
ValidationErrorType) are in result.py — NOT here.

All values are lowercase strings matching the member name.

Sections:  3.1 Task & Curriculum (10)  |  3.2 Scoring & Optimization (7)
           3.3 Failure Analysis (3)     |  3.4 Strategy & Learning (4)
           3.5 Agents (8)              |  3.6 Approval & Protection (3)
           3.7 Observability & Safety (6) | 3.8 Misc (2) | 3.9 Extended (19)
           Total: 62

★ New vs original 59: EngineeringTrack, Language, RebalanceStrategy,
  AgentDomainRole, TrackPriority, TrackStatus.
▲ Updated: RoutingCase, ApprovalItemType, SystemEventType, SandboxType.

No imports from other layer0 modules.
"""

from __future__ import annotations

from enum import StrEnum

__all__ = [
    # 3.1 Task & Curriculum
    "TaskLevel", "Domain", "EngineeringTrack", "TrackStatus", "Language",
    "TaskSource", "DirectiveSource", "CycleStatus", "SelectionOutcomeType",
    "FinishReason",
    # 3.2 Scoring & Optimization
    "FunctionRole", "ArtifactType", "SuccessTrigger", "Severity",
    "OptimizationDimension", "Trend", "RebalanceStrategy",
    # 3.3 Failure Analysis
    "FailureCategory", "ChainStatus", "SmellType",
    # 3.4 Strategy & Learning
    "InterventionType", "StrategyStatus", "ArtifactStatus", "PatternStatus",
    # 3.5 Agents
    "AgentLifecycle", "AgentGraduation", "MessageType", "RoutingCase",
    "MergeAction", "CollaborationMode", "AgentDomainRole", "TrackPriority",
    # 3.6 Approval & Protection
    "ApprovalItemType", "ApprovalStatus", "ProtectionLevel",
    # 3.7 Observability & Safety
    "AlertSeverity", "RecoveryAction", "SystemEventType", "ViolationType",
    "CheckFrequency", "SandboxType",
    # 3.8 Misc
    "CompressionTier", "ExtensionStatus",
    # 3.9 Extended Domain Enums
    "GateLevel", "PlanOutcome", "ReviewVerdict", "PromotionDecision",
    "ExplorationOutcome", "CurriculumMode", "CompetitionResult",
    "DigestFrequency", "SafetyLevel", "ChangeScope", "ResourceType",
    "TaskDifficulty", "FeedbackType", "ModelTier", "SessionType",
    "ArchiveReason", "TransferType", "HealthStatus", "BudgetAlertLevel",
]

# ---------------------------------------------------------------------------
# Section 3.1 — Task & Curriculum
# ---------------------------------------------------------------------------

class TaskLevel(StrEnum):
    """Curriculum difficulty ladder (F1 = easiest, F8 = hardest)."""
    F1 = "f1"
    F2 = "f2"
    F3 = "f3"
    F4 = "f4"
    F5 = "f5"
    F6 = "f6"
    F7 = "f7"
    F8 = "f8"

class Domain(StrEnum):
    """Algorithmic / problem domain used to classify tasks."""
    ALGORITHMS = "algorithms"
    DATA_STRUCTURES = "data_structures"
    STRINGS = "strings"
    MATH = "math"
    DYNAMIC_PROG = "dynamic_prog"
    GRAPHS = "graphs"
    TREES = "trees"
    CONCURRENCY = "concurrency"
    SYSTEM_DESIGN = "system_design"
    MIXED = "mixed"

class EngineeringTrack(StrEnum):  # ★ NEW — 15 values
    """
    Engineering discipline tracks the system can train on.

    CORE_ALGORITHMS through OS are immediately active or plannable.
    EMBEDDED_SYSTEMS through MOBILE_DEV are DEFERRED placeholders.
    """
    CORE_ALGORITHMS = "core_algorithms"
    AI_ML = "ai_ml"
    WEB_DEV = "web_dev"
    API_MICROSERVICES = "api_microservices"
    DATA_ENGINEERING = "data_engineering"
    SECURITY = "security"
    NETWORKING = "networking"
    GAME_DEV = "game_dev"
    DEVOPS = "devops"
    OS = "os"
    EMBEDDED_SYSTEMS = "embedded_systems"
    COMPILER_DESIGN = "compiler_design"
    DISTRIBUTED_SYSTEMS = "distributed_systems"
    DATABASE_INTERNALS = "database_internals"
    MOBILE_DEV = "mobile_dev"

class TrackStatus(StrEnum):  # ★ NEW
    """Lifecycle state of an engineering track."""
    INACTIVE = "inactive"
    PREPARING = "preparing"
    ACTIVE = "active"
    PAUSED = "paused"
    GRADUATING = "graduating"
    GRADUATED = "graduated"
    DEACTIVATING = "deactivating"

class Language(StrEnum):  # ★ NEW — 13 values
    """Programming languages supported for task generation and evaluation."""
    PYTHON = "python"
    JAVASCRIPT = "javascript"
    TYPESCRIPT = "typescript"
    RUST = "rust"
    GO = "go"
    JAVA = "java"
    C = "c"
    CPP = "cpp"
    KOTLIN = "kotlin"
    SWIFT = "swift"
    BASH = "bash"
    SQL = "sql"
    ASSEMBLY = "assembly"

class TaskSource(StrEnum):
    """Origin of a task entering the training pipeline."""
    GYM = "gym"
    GENERATED = "generated"
    EXPLORATION = "exploration"
    SHADOW = "shadow"
    OPT = "opt"
    BENCHMARK = "benchmark"
    DIRECTED = "directed"

class DirectiveSource(StrEnum):
    """Source that issued a directive to the current cycle."""
    GYM_TASK = "gym_task"
    BENCHMARK_ANONYMOUS = "benchmark_anonymous"
    DIRECTED_USER = "directed_user"
    SHADOW_TASK = "shadow_task"

class CycleStatus(StrEnum):
    """Phase of the current training cycle."""
    STARTED = "started"
    PLANNING = "planning"
    GENERATING = "generating"
    EVALUATING = "evaluating"
    SELECTING = "selecting"
    PROMOTING = "promoting"
    ANALYZING = "analyzing"
    COMPLETE = "complete"
    FAILED = "failed"
    RECOVERING = "recovering"

class SelectionOutcomeType(StrEnum):
    """Result of the candidate-selection step within a cycle."""
    SELECTED = "selected"
    ALL_FAILED = "all_failed"
    TIE_BROKEN = "tie_broken"

class FinishReason(StrEnum):
    """Reason an LLM generation call terminated."""
    STOP = "stop"
    MAX_TOKENS = "max_tokens"
    ERROR = "error"

# ---------------------------------------------------------------------------
# Section 3.2 — Scoring & Optimization
# ---------------------------------------------------------------------------

class FunctionRole(StrEnum):
    """Semantic role of a function, used for scoring heuristics."""
    PURE_FUNCTION = "pure_function"
    STATE_MODIFIER = "state_modifier"
    IO_HANDLER = "io_handler"
    PARSER = "parser"
    VALIDATOR = "validator"
    TRANSFORMER = "transformer"
    GENERATOR = "generator"
    CONTROLLER = "controller"
    ADAPTER = "adapter"
    UNKNOWN = "unknown"

class ArtifactType(StrEnum):
    """Category of a learned artifact (guard clause, test, rule, etc.)."""
    GUARD_CLAUSE = "guard_clause"
    INPUT_CHECK = "input_check"
    EDGE_CASE_TEST = "edge_case_test"
    PATTERN_RULE = "pattern_rule"
    CONSTRAINT = "constraint"
    ASSERTION = "assertion"
    RECOVERY = "recovery"

class SuccessTrigger(StrEnum):
    """Factor that triggered a successful outcome in a cycle."""
    NEW_STRATEGY = "new_strategy"
    OPTIMIZATION = "optimization"
    PATTERN_APPLIED = "pattern_applied"
    DIFFICULTY_INCREASE = "difficulty_increase"
    LANGUAGE_TRANSFER = "language_transfer"
    AGENT_COLLABORATION = "agent_collaboration"

class Severity(StrEnum):
    """Issue severity level (S1 = most critical, S4 = least critical)."""
    S1 = "s1"
    S2 = "s2"
    S3 = "s3"
    S4 = "s4"

class OptimizationDimension(StrEnum):
    """Axis along which a solution or artifact is being optimized."""
    SIZE = "size"
    RUNTIME = "runtime"
    READABILITY = "readability"
    MAINTAINABILITY = "maintainability"

class Trend(StrEnum):
    """Direction of a measured metric over recent cycles."""
    IMPROVING = "improving"
    STABLE = "stable"
    DECLINING = "declining"

class RebalanceStrategy(StrEnum):  # ★ NEW
    """Algorithm used to redistribute cycle allocations across active tracks."""
    PROPORTIONAL = "proportional"
    PRIORITY_WEIGHTED = "priority_weighted"
    PERFORMANCE_WEIGHTED = "performance_weighted"

# ---------------------------------------------------------------------------
# Section 3.3 — Failure Analysis
# ---------------------------------------------------------------------------

class FailureCategory(StrEnum):
    """High-level category for a recorded test or runtime failure."""
    BOUNDARY = "boundary"
    LOGIC = "logic"
    DATA_STRUCTURE = "data_structure"
    ALGORITHM = "algorithm"
    CONCURRENCY = "concurrency"
    IO = "io"
    TYPE = "type"
    PERFORMANCE = "performance"
    SECURITY = "security"
    DESIGN = "design"
    INTEGRATION = "integration"
    UNKNOWN = "unknown"

class ChainStatus(StrEnum):
    """State of a failure chain (a sequence of causally related failures)."""
    GROWING = "growing"
    STABLE = "stable"
    DECLINING = "declining"
    RESOLVED = "resolved"
    RETIRED = "retired"

class SmellType(StrEnum):
    """Code smell categories detected during static analysis."""
    LONG_PARAM_LIST = "long_param_list"
    FEATURE_ENVY = "feature_envy"
    DATA_CLUMPS = "data_clumps"
    MAGIC_NUMBERS = "magic_numbers"
    PRIMITIVE_OBSESSION = "primitive_obsession"
    LONG_METHOD = "long_method"
    DUPLICATED_LOGIC = "duplicated_logic"
    DEAD_CODE = "dead_code"
    GOD_FUNCTION = "god_function"
    TIGHT_COUPLING = "tight_coupling"

# ---------------------------------------------------------------------------
# Section 3.4 — Strategy & Learning
# ---------------------------------------------------------------------------

class InterventionType(StrEnum):
    """Type of corrective intervention applied to a struggling agent or track."""
    PROMPT_ADJUSTMENT = "prompt_adjustment"
    WEIGHT_SHIFT = "weight_shift"
    PATTERN_INJECTION = "pattern_injection"
    CHECKLIST_ADDITION = "checklist_addition"
    EXPLORATION_BOOST = "exploration_boost"
    CURRICULUM_SHIFT = "curriculum_shift"
    AGENT_PROPOSAL = "agent_proposal"
    SELF_IMPROVEMENT = "self_improvement"
    ECONOMY_MODE = "economy_mode"

class StrategyStatus(StrEnum):
    """Lifecycle state of a proposed or active strategy."""
    PROPOSED = "proposed"
    IN_PROBATION = "in_probation"
    CONFIRMED = "confirmed"
    ROLLED_BACK = "rolled_back"

class ArtifactStatus(StrEnum):
    """Operational status of a learned artifact in the artifact library."""
    ACTIVE = "active"
    DORMANT = "dormant"
    RETIRED = "retired"
    COUNTERPRODUCTIVE = "counterproductive"

class PatternStatus(StrEnum):
    """Lifecycle state of a recognized solution pattern."""
    CANDIDATE = "candidate"
    VALIDATED = "validated"
    SHARED = "shared"
    RETIRED = "retired"
    MERGED = "merged"

# ---------------------------------------------------------------------------
# Section 3.5 — Agents
# ---------------------------------------------------------------------------

class AgentLifecycle(StrEnum):
    """Lifecycle phase of an AI agent within the multi-agent system."""
    PROPOSED = "proposed"
    CONSTRUCTING = "constructing"
    TRAINING = "training"
    PROBATION = "probation"
    ACTIVE = "active"
    PAUSED = "paused"
    MERGING = "merging"
    DISSOLVING = "dissolving"

class AgentGraduation(StrEnum):
    """Graduation tier an agent has achieved (NONE = not yet graduated)."""
    NONE = "none"
    AG1 = "ag1"
    AG2 = "ag2"
    AG3 = "ag3"

class MessageType(StrEnum):
    """Type of inter-agent message on the collaboration bus."""
    HELP_REQUEST = "help_request"
    HELP_RESPONSE = "help_response"
    PATTERN_SHARE = "pattern_share"
    FAILURE_ALERT = "failure_alert"
    REVIEW_REQUEST = "review_request"
    REVIEW_RESPONSE = "review_response"
    MERGE_PROPOSAL = "merge_proposal"
    STATUS_UPDATE = "status_update"
    LEARNING_SHARE = "learning_share"

class RoutingCase(StrEnum):  # ▲ UPDATED
    """Routing decision that determines which agent(s) handle an incoming task."""
    SINGLE_SKILL_AGENT = "single_skill_agent"
    SINGLE_SKILL_GENERALIST = "single_skill_generalist"
    MULTI_SKILL_PRIMARY_AGENT = "multi_skill_primary_agent"
    MULTI_SKILL_COMPETITION = "multi_skill_competition"
    COMPETITION_MODE = "competition_mode"
    AGENT_PAUSED = "agent_paused"
    AGENT_TRAINING = "agent_training"
    DOMAIN_SPECIALIST_MATCH = "domain_specialist_match"

class MergeAction(StrEnum):
    """Decision taken when a merge proposal is evaluated."""
    MERGE = "merge"
    CONSUME = "consume"
    ABORT = "abort"

class CollaborationMode(StrEnum):
    """Level of inter-agent collaboration required for the current task."""
    SOLO = "solo"
    GUIDED = "guided"
    REVIEWED = "reviewed"
    FULL_COLLAB = "full_collab"

class AgentDomainRole(StrEnum):  # ★ NEW
    """Specialization role of an agent with respect to engineering tracks."""
    GENERALIST = "generalist"
    DOMAIN_SPECIALIST = "domain_specialist"
    CROSS_DOMAIN_BRIDGE = "cross_domain_bridge"

class TrackPriority(StrEnum):  # ★ NEW
    """Scheduling priority assigned to an engineering track."""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    DEFERRED = "deferred"

# ---------------------------------------------------------------------------
# Section 3.6 — Approval & Protection
# ---------------------------------------------------------------------------

class ApprovalItemType(StrEnum):  # ▲ UPDATED
    """Category of item requiring human or system approval before execution."""
    EXPLORATION_CANDIDATE = "exploration_candidate"
    STAGE_TRANSITION = "stage_transition"
    AGENT_PROPOSAL = "agent_proposal"
    SELF_IMPROVEMENT_PROPOSAL = "self_improvement_proposal"
    STRATEGY_UPDATE = "strategy_update"
    TRACK_ACTIVATION = "track_activation"
    TRACK_PAUSE = "track_pause"
    TRACK_DEACTIVATION = "track_deactivation"
    GRADUATION_OVERRIDE = "graduation_override"
    TASK_GENERATION_REINSTATEMENT = "task_generation_reinstatement"

class ApprovalStatus(StrEnum):
    """Current disposition of an approval request."""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    DEFERRED = "deferred"

class ProtectionLevel(StrEnum):
    """Access-control level governing how a protected parameter may be changed."""
    HUMAN_ONLY = "human_only"
    CAN_RAISE_NOT_LOWER = "can_raise_not_lower"
    TIED_TO_GRADUATION = "tied_to_graduation"
    ADD_ONLY_WITHOUT_APPROVAL = "add_only_without_approval"

# ---------------------------------------------------------------------------
# Section 3.7 — Observability & Safety
# ---------------------------------------------------------------------------

class AlertSeverity(StrEnum):
    """Urgency level of an operational alert emitted by the observability layer."""
    INFO = "info"
    WARN = "warn"
    CRITICAL = "critical"

class RecoveryAction(StrEnum):
    """Action taken during a recovery cycle after a detected failure."""
    COMPLETE = "complete"
    ABORT = "abort"
    RETRY = "retry"

class SystemEventType(StrEnum):  # ▲ UPDATED
    """Category of a structured system event logged to the event bus."""
    STARTUP = "startup"
    SHUTDOWN = "shutdown"
    CIRCUIT_BREAKER = "circuit_breaker"
    INVARIANT_VIOLATION = "invariant_violation"
    MANUAL_PAUSE = "manual_pause"
    GRADUATION = "graduation"
    TRACK_ACTIVATED = "track_activated"
    TRACK_PAUSED = "track_paused"
    TRACK_DEACTIVATED = "track_deactivated"

class ViolationType(StrEnum):
    """Type of sandbox policy violation detected during code execution."""
    FILESYSTEM_ACCESS = "filesystem_access"
    NETWORK_ACCESS = "network_access"
    ENV_ACCESS = "env_access"
    RESOURCE_EXCEEDED = "resource_exceeded"
    IMPORT_BLOCKED = "import_blocked"
    SCHEMA_MODIFICATION = "schema_modification"

class CheckFrequency(StrEnum):
    """Trigger frequency for invariant or safety checks."""
    ON_STARTUP = "on_startup"
    EVERY_CYCLE = "every_cycle"
    EVERY_LLM_CALL = "every_llm_call"
    EVERY_WRITE = "every_write"
    PERIODIC_100 = "periodic_100"
    PERIODIC_1000 = "periodic_1000"
    ON_BENCHMARK_RUN = "on_benchmark_run"
    ON_GATE_EVALUATION = "on_gate_evaluation"
    ON_STRATEGY_UPDATE = "on_strategy_update"

class SandboxType(StrEnum):  # ▲ UPDATED
    """Execution isolation mechanism used by the sandbox runner."""
    SUBPROCESS = "subprocess"
    DOCKER = "docker"
    QEMU = "qemu"

# ---------------------------------------------------------------------------
# Section 3.8 — Misc
# ---------------------------------------------------------------------------

class CompressionTier(StrEnum):
    """Memory compression tier controlling record compaction aggressiveness."""
    WARM_10 = "warm_10"
    COLD_100 = "cold_100"

class ExtensionStatus(StrEnum):
    """Operational status of a registered system extension or plugin."""
    PROVISIONAL = "provisional"
    ESTABLISHED = "established"

# ---------------------------------------------------------------------------
# Section 3.9 — Extended Domain Enums
# (implied by track.py, graduation.py, common.py, and the broader type system)
# ---------------------------------------------------------------------------

class GateLevel(StrEnum):
    """Graduation gate checkpoints G1–G5, ordered by required proficiency."""
    G1 = "g1"
    G2 = "g2"
    G3 = "g3"
    G4 = "g4"
    G5 = "g5"

class PlanOutcome(StrEnum):
    """Result of executing a planning step within a cycle."""
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"
    SKIPPED = "skipped"

class ReviewVerdict(StrEnum):
    """Verdict returned by a code or solution review step."""
    PASS = "pass"
    FAIL = "fail"
    PARTIAL_PASS = "partial_pass"
    ERROR = "error"

class PromotionDecision(StrEnum):
    """Decision made when evaluating a candidate solution for promotion."""
    PROMOTE = "promote"
    HOLD = "hold"
    DEMOTE = "demote"

class ExplorationOutcome(StrEnum):
    """Return-on-investment assessment of an exploration cycle."""
    VALUABLE = "valuable"
    NEUTRAL = "neutral"
    WASTEFUL = "wasteful"

class CurriculumMode(StrEnum):
    """Operating mode of the curriculum scheduler."""
    STANDARD = "standard"
    EXAM = "exam"
    EXPLORATION = "exploration"
    DIRECTED = "directed"

class CompetitionResult(StrEnum):
    """Outcome for a single agent in a multi-agent competition cycle."""
    WINNER = "winner"
    LOSER = "loser"
    TIE = "tie"
    DISQUALIFIED = "disqualified"

class DigestFrequency(StrEnum):
    """How often analytics digests are generated and persisted."""
    EVERY_CYCLE = "every_cycle"
    EVERY_10 = "every_10"
    EVERY_100 = "every_100"
    ON_DEMAND = "on_demand"

class SafetyLevel(StrEnum):
    """Safety classification of a proposed action or generated artifact."""
    SAFE = "safe"
    CAUTION = "caution"
    DANGEROUS = "dangerous"

class ChangeScope(StrEnum):
    """Breadth of a configuration or schema change."""
    FIELD = "field"
    SECTION = "section"
    GLOBAL = "global"

class ResourceType(StrEnum):
    """Computational or financial resource being tracked or budget-limited."""
    CPU = "cpu"
    MEMORY = "memory"
    DISK = "disk"
    API_CALLS = "api_calls"
    BUDGET = "budget"

class TaskDifficulty(StrEnum):
    """Subjective difficulty rating for a task, orthogonal to TaskLevel."""
    TRIVIAL = "trivial"
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"
    EXTREME = "extreme"

class FeedbackType(StrEnum):
    """Qualitative category of feedback received for a submitted solution."""
    POSITIVE = "positive"
    NEGATIVE = "negative"
    NEUTRAL = "neutral"
    MIXED = "mixed"

class ModelTier(StrEnum):
    """LLM cost/capability tier selected for a given operation."""
    FAST = "fast"
    BALANCED = "balanced"
    POWERFUL = "powerful"

class SessionType(StrEnum):
    """Context in which a training session is being run."""
    INTERACTIVE = "interactive"
    OVERNIGHT = "overnight"
    BENCHMARK = "benchmark"
    CALIBRATION = "calibration"

class ArchiveReason(StrEnum):
    """Reason a track, agent, or artifact was moved to the archive."""
    GRADUATED = "graduated"
    DEACTIVATED = "deactivated"
    MERGED = "merged"
    MANUAL = "manual"

class TransferType(StrEnum):
    """How a learned pattern is applied when transferred to a new context."""
    DIRECT_APPLY = "direct_apply"
    ADAPT_REQUIRED = "adapt_required"
    PRINCIPLE_ONLY = "principle_only"

class HealthStatus(StrEnum):
    """Aggregate health state of a system component or subsystem."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    CRITICAL = "critical"
    UNKNOWN = "unknown"

class BudgetAlertLevel(StrEnum):
    """Alert level emitted when API or compute budget thresholds are crossed."""
    NORMAL = "normal"
    WARNING = "warning"
    CRITICAL = "critical"
    EXHAUSTED = "exhausted"
