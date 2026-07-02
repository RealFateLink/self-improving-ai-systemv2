"""
agents.py — Layer 0 Agent System Type Definitions
==================================================
Seven dataclasses describing agents, their construction plans, performance
records, inter-agent messages, merge records, routing decisions, and resource
allocations within the Self-Improving Engineering AI multi-agent system.

All classes are pure data containers (no logic). Frozen dataclasses are
immutable records suitable for storage and hashing; the mutable
``AgentRegistryEntry`` represents live registry state.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .enums import (
    AgentLifecycle,
    AgentGraduation,
    CollaborationMode,
    Trend,
    MessageType,
    MergeAction,
    RoutingCase,
    AgentDomainRole,
    EngineeringTrack,
)

__all__ = [
    "AgentRegistryEntry",
    "AgentConstructionPlan",
    "AgentPerformanceRecord",
    "AgentMessage",
    "AgentMergeRecord",
    "AgentRoutingDecision",
    "AgentResourceAllocation",
]


@dataclass
class AgentRegistryEntry:
    """Live registry record for a single agent.

    Mutable so the scheduler can update lifecycle, performance metrics, and
    resource assignments in-place without replacing the entire record.
    """

    agent_id: str
    name: str
    specialty: str
    lifecycle: AgentLifecycle = AgentLifecycle.PROPOSED
    graduation: AgentGraduation = AgentGraduation.NONE
    created_at_cycle: int = 0
    activated_at_cycle: Optional[int] = None
    pass_rate: float = 0.0
    tasks_completed: int = 0
    collaboration_mode: CollaborationMode = CollaborationMode.SOLO
    skill_domains: list[str] = field(default_factory=list)
    assigned_task_types: list[str] = field(default_factory=list)
    performance_trend: Trend = Trend.STABLE
    paused_at_cycle: Optional[int] = None
    pause_reason: Optional[str] = None
    domain_role: AgentDomainRole = AgentDomainRole.GENERALIST
    primary_track: Optional[EngineeringTrack] = None
    secondary_tracks: list[EngineeringTrack] = field(default_factory=list)
    cross_domain_score: float = 0.0


@dataclass(frozen=True)
class AgentConstructionPlan:
    """Immutable proposal for constructing a new agent.

    Created by the meta-learner and queued for human or system approval before
    the agent enters the ``CONSTRUCTING`` lifecycle phase.
    """

    plan_id: str
    agent_name: str
    specialty: str
    rationale: str
    initial_skills: list[str] = field(default_factory=list)
    training_tasks: list[str] = field(default_factory=list)
    success_criteria: str = ""
    estimated_training_cycles: int = 50
    collaboration_mode: CollaborationMode = CollaborationMode.SOLO
    proposed_at_cycle: int = 0
    model_used: str = ""
    domain_role: AgentDomainRole = AgentDomainRole.GENERALIST
    primary_track: Optional[EngineeringTrack] = None
    secondary_tracks: list[EngineeringTrack] = field(default_factory=list)
    cross_domain_score: float = 0.0


@dataclass(frozen=True)
class AgentPerformanceRecord:
    """Single task-level performance observation for an agent.

    One record is written per task evaluation; aggregates are derived
    downstream by the analytics layer.
    """

    record_id: str
    agent_id: str
    cycle_number: int
    task_id: str
    passed: bool
    score: float = 0.0
    execution_time_ms: float = 0.0
    notes: str = ""


@dataclass(frozen=True)
class AgentMessage:
    """A single message exchanged on the inter-agent collaboration bus.

    All fields except ``metadata`` are required at construction time to ensure
    traceability. The ``metadata`` dict carries optional structured context
    (e.g. attached pattern IDs or task references).
    """

    message_id: str
    sender_id: str
    receiver_id: str
    message_type: MessageType
    content: str
    cycle_number: int
    timestamp: str = ""
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class AgentMergeRecord:
    """Immutable record of a completed or aborted agent merge event.

    Captures both the decision (``action``) and the material outcome
    (``patterns_transferred``, ``artifacts_transferred``, ``outcome``).
    """

    merge_id: str
    source_agent_id: str
    target_agent_id: str
    action: MergeAction
    rationale: str
    cycle_number: int
    patterns_transferred: int = 0
    artifacts_transferred: int = 0
    outcome: str = ""


@dataclass(frozen=True)
class AgentRoutingDecision:
    """Result of the task-routing step for a single task.

    Records which agent was selected, any fallback, the routing case that
    matched, and the confidence score assigned by the router.
    """

    task_id: str
    cycle_number: int
    routing_case: RoutingCase
    selected_agent_id: Optional[str] = None
    fallback_agent_id: Optional[str] = None
    confidence: float = 0.0
    rationale: str = ""


@dataclass(frozen=True)
class AgentResourceAllocation:
    """Snapshot of resource limits assigned to an agent for a cycle.

    Written once per cycle per agent by the resource manager and used by the
    sandbox runner to enforce CPU, memory, API-spend, and task-quota caps.
    """

    agent_id: str
    cycle_number: int
    cpu_percent: float = 0.0
    memory_mb: int = 0
    api_budget_usd: float = 0.0
    task_quota: int = 0
