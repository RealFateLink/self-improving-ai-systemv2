"""
observability.py — Layer 0 Observability Type Definitions
==========================================================
Five frozen dataclasses covering the observability and cost-tracking layer of
the Self-Improving Engineering AI system:

* ``DiagnosticTrace``      — Low-level operation span (like an OpenTelemetry span).
* ``FeedbackDigest``       — Aggregated pass/fail summary across a cycle range.
* ``MetaLearnerReview``    — Periodic meta-learner strategy-review record.
* ``CostEvent``            — Single API or compute cost observation.
* ``SystemHealthSnapshot`` — Point-in-time aggregate health reading.

All classes are frozen (immutable) records; they carry no business logic.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .enums import Trend, HealthStatus, BudgetAlertLevel

__all__ = [
    "DiagnosticTrace",
    "FeedbackDigest",
    "MetaLearnerReview",
    "CostEvent",
    "SystemHealthSnapshot",
]


@dataclass(frozen=True)
class DiagnosticTrace:
    """Structured trace span for a single instrumented operation.

    Analogous to an OpenTelemetry span. Spans may be nested via
    ``parent_trace_id`` to form a call tree. The ``metadata`` dict carries
    arbitrary key-value annotations (e.g. agent IDs, task IDs).
    """

    trace_id: str
    cycle_number: int
    timestamp: str
    module: str
    operation: str
    duration_ms: float = 0.0
    success: bool = True
    detail: str = ""
    parent_trace_id: Optional[str] = None
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class FeedbackDigest:
    """Aggregated analytics digest covering a contiguous range of cycles.

    The ``cycle_range`` tuple is ``(start_cycle, end_cycle)`` inclusive.
    Lists of strings capture human-readable summaries for improvements,
    regressions, notable patterns, and actionable recommendations.
    """

    digest_id: str
    cycle_range: tuple[int, int]
    created_at: str
    total_cycles: int = 0
    pass_rate: float = 0.0
    key_improvements: list[str] = field(default_factory=list)
    key_regressions: list[str] = field(default_factory=list)
    notable_patterns: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    model_used: str = ""


@dataclass(frozen=True)
class MetaLearnerReview:
    """Outcome record from a periodic meta-learner strategy-evaluation pass.

    Covers a window ``[period_start, period_end]`` and tallies how many
    strategies were confirmed, rolled back, and how many patterns changed
    status. The ``overall_trend`` reflects the system-wide performance
    direction observed during the reviewed window.
    """

    review_id: str
    cycle_number: int
    period_start: int
    period_end: int
    strategies_evaluated: int = 0
    strategies_confirmed: int = 0
    strategies_rolled_back: int = 0
    patterns_discovered: int = 0
    patterns_retired: int = 0
    overall_trend: Trend = Trend.STABLE
    recommendations: list[str] = field(default_factory=list)
    model_used: str = ""


@dataclass(frozen=True)
class CostEvent:
    """Atomic cost observation for a single billable API or compute event.

    ``category`` is a free-form string (e.g. ``"llm_inference"``,
    ``"sandbox_cpu"``). ``tokens`` is meaningful only for LLM calls;
    leave at 0 for non-token costs.
    """

    event_id: str
    cycle_number: int
    timestamp: str
    category: str
    amount_usd: float
    model: str = ""
    tokens: int = 0
    description: str = ""


@dataclass(frozen=True)
class SystemHealthSnapshot:
    """Point-in-time aggregate health reading for the running system.

    Taken at configurable intervals (e.g. every cycle, every 10 cycles) and
    persisted to the observability store. ``stagnation_risk`` is set by the
    meta-learner when pass-rate improvement has flattened for too long.
    """

    snapshot_id: str
    cycle_number: int
    timestamp: str
    health_status: HealthStatus
    pass_rate_trend: Trend
    active_agents: int = 0
    active_alerts: int = 0
    budget_health: BudgetAlertLevel = BudgetAlertLevel.NORMAL
    stagnation_risk: bool = False
    notes: str = ""
