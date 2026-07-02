"""
protocols.py — Structural interface contracts for all Layer 0 subsystems.

Each Protocol class defines the public API that a concrete implementation must
satisfy.  Methods use ``...`` as their body; no implementation lives here.
All methods return a :class:`~..result.Result` so callers always deal with
explicit success / failure values rather than exceptions.

Python 3.11+  |  ``from __future__ import annotations`` enabled throughout.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from ..result import Result

__all__ = [
    "LedgerProtocol",
    "SandboxProtocol",
    "BudgetProtocol",
    "LLMClientProtocol",
    "ScoringProtocol",
    "CurriculumProtocol",
    "FailureAnalyzerProtocol",
    "StrategyManagerProtocol",
    "PatternLibraryProtocol",
    "AgentManagerProtocol",
    "BenchmarkRunnerProtocol",
    "GraduationProtocol",
    "ApprovalProtocol",
    "ObservabilityProtocol",
    "CompressionProtocol",
    "SafetyProtocol",
    "RecoveryProtocol",
    "TaskSamplerProtocol",
    "PreventionProtocol",
    "OptimizationProtocol",
    "TrackSchedulerProtocol",
    "CrossTrackAnalyzerProtocol",
    "TrackPerformanceTrackerProtocol",
]

# ---------------------------------------------------------------------------
# NOTE: Method parameters that reference domain dataclasses (e.g. CycleRecord,
# TaskResult, AgentPlan …) are typed as ``Any`` here to avoid circular imports.
# Layer 1+ resolves these to their concrete types when it wires the dependency
# graph together.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


@runtime_checkable
class LedgerProtocol(Protocol):
    """Append-only store for cycle records and per-task results."""

    def write_cycle(self, record: Any) -> Result[None, Any]: ...
    def read_cycle(self, cycle_number: int) -> Result[Any, Any]: ...
    def read_cycles(self, start: int, end: int) -> Result[list[Any], Any]: ...
    def query_cycles(self, **filters: Any) -> Result[list[Any], Any]: ...
    def write_task_result(self, result: Any) -> Result[None, Any]: ...
    def read_task_results(self, task_id: str) -> Result[list[Any], Any]: ...


# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------


@runtime_checkable
class SandboxProtocol(Protocol):
    """Isolated code-execution environment."""

    def execute(
        self,
        code: str,
        language: str,
        timeout: int,
        memory_mb: int,
    ) -> Result[Any, Any]: ...

    def validate_code(self, code: str, language: str) -> Result[bool, Any]: ...

    def get_execution_stats(self) -> Result[dict[str, Any], Any]: ...


# ---------------------------------------------------------------------------
# Budget / Cost control
# ---------------------------------------------------------------------------


@runtime_checkable
class BudgetProtocol(Protocol):
    """Tracks spend and enforces cost limits."""

    def check_budget(self, estimated_cost: float) -> Result[bool, Any]: ...
    def record_expense(self, amount: float, category: str, detail: str) -> Result[None, Any]: ...
    def get_remaining(self) -> Result[float, Any]: ...
    def get_burn_rate(self) -> Result[float, Any]: ...
    def enter_economy_mode(self) -> Result[None, Any]: ...
    def exit_economy_mode(self) -> Result[None, Any]: ...


# ---------------------------------------------------------------------------
# Language-model client
# ---------------------------------------------------------------------------


@runtime_checkable
class LLMClientProtocol(Protocol):
    """Thin wrapper around one or more LLM providers."""

    def complete(
        self,
        prompt: str,
        model: str | None,
        temperature: float,
        max_tokens: int,
    ) -> Result[Any, Any]: ...

    def complete_with_template(
        self,
        template_name: str,
        variables: dict[str, Any],
        model: str | None,
    ) -> Result[Any, Any]: ...

    def get_cost_estimate(self, prompt: str, model: str) -> Result[float, Any]: ...


# ---------------------------------------------------------------------------
# Scoring / ranking
# ---------------------------------------------------------------------------


@runtime_checkable
class ScoringProtocol(Protocol):
    """Evaluates and ranks candidate solutions against a task."""

    def score_candidate(self, candidate: Any, task: Any) -> Result[Any, Any]: ...
    def compare_candidates(self, candidates: list[Any], task: Any) -> Result[Any, Any]: ...
    def get_score_breakdown(self, result_id: str) -> Result[Any, Any]: ...


# ---------------------------------------------------------------------------
# Curriculum
# ---------------------------------------------------------------------------


@runtime_checkable
class CurriculumProtocol(Protocol):
    """Manages progression through difficulty levels."""

    def get_current_state(self) -> Result[Any, Any]: ...
    def advance_level(self) -> Result[Any, Any]: ...
    def check_promotion(self) -> Result[bool, Any]: ...
    def check_demotion(self) -> Result[bool, Any]: ...


# ---------------------------------------------------------------------------
# Failure analysis
# ---------------------------------------------------------------------------


@runtime_checkable
class FailureAnalyzerProtocol(Protocol):
    """Detects, tracks, and surfaces recurring failure chains."""

    def analyze_failure(
        self,
        task_id: str,
        cycle_number: int,
        error: str,
    ) -> Result[Any, Any]: ...

    def get_chain(self, chain_id: str) -> Result[Any, Any]: ...
    def update_chain(self, chain_id: str, occurrence: str) -> Result[None, Any]: ...
    def get_active_chains(self) -> Result[list[Any], Any]: ...


# ---------------------------------------------------------------------------
# Strategy management
# ---------------------------------------------------------------------------


@runtime_checkable
class StrategyManagerProtocol(Protocol):
    """Proposes, confirms, rolls back, and evaluates system-level strategies."""

    def propose_strategy(self, strategy: Any) -> Result[Any, Any]: ...
    def confirm_strategy(self, update_id: str) -> Result[None, Any]: ...
    def rollback_strategy(self, update_id: str, reason: str) -> Result[None, Any]: ...
    def get_active_strategies(self) -> Result[list[Any], Any]: ...
    def evaluate_trigger(self, trigger_id: str) -> Result[bool, Any]: ...


# ---------------------------------------------------------------------------
# Pattern library
# ---------------------------------------------------------------------------


@runtime_checkable
class PatternLibraryProtocol(Protocol):
    """Stores and retrieves reusable solution patterns."""

    def add_pattern(self, pattern: Any) -> Result[None, Any]: ...
    def get_pattern(self, pattern_id: str) -> Result[Any, Any]: ...
    def search_patterns(self, query: str, limit: int) -> Result[list[Any], Any]: ...
    def update_effectiveness(self, pattern_id: str, effectiveness: float) -> Result[None, Any]: ...
    def retire_pattern(self, pattern_id: str, reason: str) -> Result[None, Any]: ...


# ---------------------------------------------------------------------------
# Agent management
# ---------------------------------------------------------------------------


@runtime_checkable
class AgentManagerProtocol(Protocol):
    """Lifecycle management for spawned sub-agents."""

    def register_agent(self, plan: Any) -> Result[Any, Any]: ...
    def get_agent(self, agent_id: str) -> Result[Any, Any]: ...
    def list_agents(self) -> Result[list[Any], Any]: ...
    def update_agent(self, agent_id: str, updates: dict[str, Any]) -> Result[None, Any]: ...
    def dissolve_agent(self, agent_id: str, reason: str) -> Result[None, Any]: ...


# ---------------------------------------------------------------------------
# Benchmarking
# ---------------------------------------------------------------------------


@runtime_checkable
class BenchmarkRunnerProtocol(Protocol):
    """Executes benchmark suites and stores session results."""

    def run_benchmark(self, benchmark_id: str) -> Result[Any, Any]: ...
    def get_results(self, session_id: str) -> Result[list[Any], Any]: ...
    def get_session(self, session_id: str) -> Result[Any, Any]: ...


# ---------------------------------------------------------------------------
# Graduation gating
# ---------------------------------------------------------------------------


@runtime_checkable
class GraduationProtocol(Protocol):
    """Controls passage through capability graduation gates."""

    def evaluate_gate(self, gate: str) -> Result[Any, Any]: ...
    def get_state(self) -> Result[Any, Any]: ...
    def update_state(self, state: Any) -> Result[None, Any]: ...


# ---------------------------------------------------------------------------
# Human-in-the-loop approval
# ---------------------------------------------------------------------------


@runtime_checkable
class ApprovalProtocol(Protocol):
    """Submits requests for human review and records decisions."""

    def submit_request(self, request: Any) -> Result[str, Any]: ...
    def get_pending(self) -> Result[list[Any], Any]: ...
    def approve(self, request_id: str, approved_by: str, detail: str) -> Result[None, Any]: ...
    def reject(self, request_id: str, rejected_by: str, detail: str) -> Result[None, Any]: ...


# ---------------------------------------------------------------------------
# Observability
# ---------------------------------------------------------------------------


@runtime_checkable
class ObservabilityProtocol(Protocol):
    """Collects traces, alerts, and health summaries."""

    def record_trace(self, trace: Any) -> Result[None, Any]: ...
    def record_alert(self, alert: Any) -> Result[None, Any]: ...
    def get_health(self) -> Result[Any, Any]: ...
    def get_digest(self, cycle_range: tuple[int, int]) -> Result[Any, Any]: ...


# ---------------------------------------------------------------------------
# Compression / archival
# ---------------------------------------------------------------------------


@runtime_checkable
class CompressionProtocol(Protocol):
    """Compresses cycle data into warm and cold storage tiers."""

    def compress_warm(self, cycle_number: int) -> Result[None, Any]: ...
    def compress_cold(self, cycle_number: int) -> Result[None, Any]: ...
    def get_compression_stats(self) -> Result[dict[str, Any], Any]: ...


# ---------------------------------------------------------------------------
# Safety
# ---------------------------------------------------------------------------


@runtime_checkable
class SafetyProtocol(Protocol):
    """Checks system invariants and records safety violations."""

    def check_invariant(self, invariant_id: str) -> Result[bool, Any]: ...
    def report_violation(self, violation_type: str, detail: str) -> Result[None, Any]: ...
    def get_violation_history(self) -> Result[list[Any], Any]: ...


# ---------------------------------------------------------------------------
# Recovery
# ---------------------------------------------------------------------------


@runtime_checkable
class RecoveryProtocol(Protocol):
    """Initiates and tracks error-recovery procedures."""

    def initiate_recovery(self, error: str, cycle_number: int) -> Result[Any, Any]: ...
    def check_recovery(self, recovery_id: str) -> Result[Any, Any]: ...
    def complete_recovery(self, recovery_id: str, success: bool) -> Result[None, Any]: ...


# ---------------------------------------------------------------------------
# Task sampling
# ---------------------------------------------------------------------------


@runtime_checkable
class TaskSamplerProtocol(Protocol):
    """Samples tasks from the training pool according to curriculum state."""

    def sample_tasks(self, request: Any) -> Result[Any, Any]: ...
    def get_pool_stats(self) -> Result[dict[str, Any], Any]: ...


# ---------------------------------------------------------------------------
# Prevention (artifact-based)
# ---------------------------------------------------------------------------


@runtime_checkable
class PreventionProtocol(Protocol):
    """Applies prevention artifacts to reduce recurring failure modes."""

    def apply_artifact(self, artifact_id: str, task_id: str) -> Result[bool, Any]: ...
    def get_applicable_artifacts(self, task_id: str) -> Result[list[Any], Any]: ...
    def update_effectiveness(self, artifact_id: str, effectiveness: float) -> Result[None, Any]: ...


# ---------------------------------------------------------------------------
# Optimization
# ---------------------------------------------------------------------------


@runtime_checkable
class OptimizationProtocol(Protocol):
    """Generates and applies prompt / strategy optimization candidates."""

    def create_brief(self, task_id: str, cycle_number: int) -> Result[Any, Any]: ...
    def generate_candidates(self, brief_id: str) -> Result[list[Any], Any]: ...
    def apply_optimization(self, candidate_id: str) -> Result[Any, Any]: ...


# ---------------------------------------------------------------------------
# Multi-Track Protocols  (Section 7)
# ---------------------------------------------------------------------------


@runtime_checkable
class TrackSchedulerProtocol(Protocol):
    """Allocates cycles across parallel training tracks."""

    def select_track(
        self,
        cycle_number: int,
        entity_id: str,
        overnight: bool = False,
    ) -> Result[Any, Any]: ...

    def update_allocation(self, track_id: str, new_percent: float) -> Result[None, Any]: ...
    def get_balance(self) -> Result[Any, Any]: ...
    def rebalance(self) -> Result[dict[str, Any], Any]: ...
    def pause_track(self, track_id: str, reason: str) -> Result[None, Any]: ...
    def activate_track(self, track_id: str) -> Result[None, Any]: ...
    def get_scheduler_state(self) -> Result[Any, Any]: ...


@runtime_checkable
class CrossTrackAnalyzerProtocol(Protocol):
    """Identifies and transfers insights between training tracks."""

    def find_transferable_patterns(self, source_track: str) -> Result[list[Any], Any]: ...
    def attempt_transfer(self, insight: Any) -> Result[bool, Any]: ...
    def get_transfer_history(self, track_pair: tuple[str, str]) -> Result[list[Any], Any]: ...
    def compute_transfer_rate(self) -> Result[float, Any]: ...
    def assess_generalization_quality(self, pattern_id: str) -> Result[float, Any]: ...


@runtime_checkable
class TrackPerformanceTrackerProtocol(Protocol):
    """Records per-track performance metrics and readiness signals."""

    def record_cycle(self, track_id: str, cycle_record: Any) -> Result[None, Any]: ...
    def get_performance(self, track_id: str) -> Result[Any, Any]: ...
    def get_all_performances(self) -> Result[dict[str, Any], Any]: ...
    def detect_stagnation(self, track_id: str) -> Result[bool, Any]: ...
    def get_graduation_state(self, track_id: str) -> Result[Any, Any]: ...
    def assess_readiness(self, track_id: str) -> Result[Any, Any]: ...
    def compute_health_score(self, track_id: str) -> Result[float, Any]: ...
