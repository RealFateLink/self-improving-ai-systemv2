"""
analytics.py — Analytics and Performance Summary Types
======================================================
Defines immutable data types for the analytics subsystem: per-task and
per-domain performance snapshots, agent performance tracking, strategy
effectiveness records, and rolling cycle summary types at 10-cycle and
100-cycle granularities.

All classes are pure data definitions (frozen dataclasses).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .enums import Trend, EngineeringTrack

__all__ = [
    "AnalyticsTaskPerformance",
    "AnalyticsDomainPerformance",
    "AnalyticsAgentPerformance",
    "AnalyticsStrategyEffectiveness",
    "CycleSummary10",
    "CycleSummary100",
]


# ---------------------------------------------------------------------------
# Task Performance
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class AnalyticsTaskPerformance:
    """
    Immutable aggregate performance snapshot for a single task.

    Updated at the end of each cycle in which the task was attempted.
    Used by the analytics subsystem to identify consistently difficult
    tasks, regression risks, and candidates for curriculum adjustment.

    Attributes:
        task_id: Unique identifier of the task.
        total_attempts: Cumulative number of times this task was attempted.
        total_passes: Cumulative number of successful attempts.
        pass_rate: ``total_passes / total_attempts`` (0–1).
        avg_score: Average continuous quality score across all attempts.
        avg_execution_time_ms: Average wall-clock execution time (ms).
        last_attempted_cycle: Training cycle of the most recent attempt.
        domain_track: The ``EngineeringTrack`` this task belongs to.
    """

    task_id: str
    total_attempts: int = 0
    total_passes: int = 0
    pass_rate: float = 0.0
    avg_score: float = 0.0
    avg_execution_time_ms: float = 0.0
    last_attempted_cycle: int = 0
    domain_track: EngineeringTrack = EngineeringTrack.CORE_ALGORITHMS


# ---------------------------------------------------------------------------
# Domain Performance
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class AnalyticsDomainPerformance:
    """
    Immutable aggregate performance snapshot for a task domain.

    Aggregates metrics across all tasks within a named domain (e.g. a
    ``Domain`` value or an arbitrary grouping string) and tracks whether
    performance is improving, stable, or declining.

    Attributes:
        domain: Domain identifier (typically a ``Domain`` enum value's
            string representation or a custom grouping label).
        total_tasks: Number of distinct tasks that contributed to this
            snapshot.
        pass_rate: Aggregate pass rate across all tasks in the domain (0–1).
        avg_score: Average quality score across all tasks in the domain.
        trend: Direction of the pass rate over the most recent observation
            window (``Trend.IMPROVING``, ``STABLE``, or ``DECLINING``).
        last_updated_cycle: Training cycle when this snapshot was last
            refreshed.
    """

    domain: str
    total_tasks: int = 0
    pass_rate: float = 0.0
    avg_score: float = 0.0
    trend: Trend = Trend.STABLE
    last_updated_cycle: int = 0


# ---------------------------------------------------------------------------
# Agent Performance
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class AnalyticsAgentPerformance:
    """
    Immutable aggregate performance snapshot for a single agent.

    Tracks both general pass rate and specialty-domain pass rate so that
    the system can identify agents that are strong generalists versus those
    with domain-specific strengths.

    Attributes:
        agent_id: Unique identifier of the agent.
        total_tasks: Cumulative tasks assigned to this agent.
        pass_rate: Overall pass rate across all assigned tasks (0–1).
        avg_score: Average quality score across all tasks.
        specialty_pass_rate: Pass rate restricted to the agent's declared
            specialty domains (0–1); may differ substantially from the
            overall rate for domain-specialist agents.
        trend: Direction of the overall pass rate over the most recent
            observation window.
        last_updated_cycle: Training cycle when this snapshot was last
            refreshed.
    """

    agent_id: str
    total_tasks: int = 0
    pass_rate: float = 0.0
    avg_score: float = 0.0
    specialty_pass_rate: float = 0.0
    trend: Trend = Trend.STABLE
    last_updated_cycle: int = 0


# ---------------------------------------------------------------------------
# Strategy Effectiveness
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class AnalyticsStrategyEffectiveness:
    """
    Immutable record of the measured effectiveness of a learning strategy.

    Aggregates outcomes across all cycles in which the strategy was applied,
    enabling the system to confirm, roll back, or retire strategies based
    on empirical evidence.

    Attributes:
        strategy_id: Unique identifier of the strategy being measured.
        intervention_type: The ``InterventionType`` string value describing
            what kind of strategy this is (stored as a plain string to
            avoid a circular import; must match an ``InterventionType``
            member value).
        applications: Number of times this strategy has been applied.
        success_rate: Fraction of applications that produced a measurable
            improvement (0–1).
        avg_improvement: Mean improvement percentage across all successful
            applications.
        last_applied_cycle: Training cycle when the strategy was most
            recently applied.
    """

    strategy_id: str
    intervention_type: str
    applications: int = 0
    success_rate: float = 0.0
    avg_improvement: float = 0.0
    last_applied_cycle: int = 0


# ---------------------------------------------------------------------------
# Cycle Summary (10-cycle window)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CycleSummary10:
    """
    Immutable performance summary over a 10-cycle rolling window.

    Generated at the end of every 10th training cycle.  Provides a
    medium-resolution view of system health suitable for operational
    dashboards and short-term trend detection.

    Attributes:
        summary_id: Unique identifier for this summary record.
        start_cycle: First cycle included in this window (inclusive).
        end_cycle: Last cycle included in this window (inclusive).
        pass_rate: Aggregate pass rate across all tasks in the window (0–1).
        avg_score: Average quality score across all tasks in the window.
        tasks_attempted: Total tasks attempted within the window.
        patterns_discovered: Number of new solution patterns identified
            during the window.
        cost_usd: Cumulative API cost incurred during the window.
        domain_track: The ``EngineeringTrack`` this summary is scoped to;
            defaults to ``CORE_ALGORITHMS`` for system-wide summaries.
    """

    summary_id: str
    start_cycle: int
    end_cycle: int
    pass_rate: float = 0.0
    avg_score: float = 0.0
    tasks_attempted: int = 0
    patterns_discovered: int = 0
    cost_usd: float = 0.0
    domain_track: EngineeringTrack = EngineeringTrack.CORE_ALGORITHMS


# ---------------------------------------------------------------------------
# Cycle Summary (100-cycle window)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CycleSummary100:
    """
    Immutable performance summary over a 100-cycle rolling window.

    Generated at the end of every 100th training cycle.  Provides a
    coarse-resolution view of long-term trends, strategy effectiveness,
    and multi-agent system health.  Includes additional counters for
    strategy updates and active agents that are not tracked in the
    shorter ``CycleSummary10``.

    Attributes:
        summary_id: Unique identifier for this summary record.
        start_cycle: First cycle included in this window (inclusive).
        end_cycle: Last cycle included in this window (inclusive).
        pass_rate: Aggregate pass rate across all tasks in the window (0–1).
        avg_score: Average quality score across all tasks in the window.
        tasks_attempted: Total tasks attempted within the window.
        patterns_discovered: Number of new solution patterns identified
            during the window.
        strategies_updated: Number of strategies that were confirmed,
            rolled back, or retired during the window.
        agents_active: Peak number of agents active at any point during
            the window.
        cost_usd: Cumulative API cost incurred during the window.
        domain_track: The ``EngineeringTrack`` this summary is scoped to;
            defaults to ``CORE_ALGORITHMS`` for system-wide summaries.
    """

    summary_id: str
    start_cycle: int
    end_cycle: int
    pass_rate: float = 0.0
    avg_score: float = 0.0
    tasks_attempted: int = 0
    patterns_discovered: int = 0
    strategies_updated: int = 0
    agents_active: int = 0
    cost_usd: float = 0.0
    domain_track: EngineeringTrack = EngineeringTrack.CORE_ALGORITHMS
