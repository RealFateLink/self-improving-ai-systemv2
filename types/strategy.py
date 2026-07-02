"""
strategy.py — Layer 0 Strategy & Learning Type Definitions
===========================================================
Frozen dataclasses (and mutable where noted) representing solution patterns,
strategy updates, strategy triggers, taxonomy entries, taxonomy extensions,
and self-improvement proposals used throughout the Self-Improving Engineering
AI system.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
from .enums import (
    PatternStatus, InterventionType, StrategyStatus, ExtensionStatus,
    ApprovalStatus, EngineeringTrack,
)

__all__ = [
    "Pattern", "StrategyUpdate", "StrategyTrigger",
    "TaxonomyEntry", "TaxonomyExtension", "SelfImprovementProposal",
]

@dataclass
class Pattern:
    pattern_id: str
    description: str
    category: str
    status: PatternStatus = PatternStatus.CANDIDATE
    effectiveness: float = 0.0
    applications: int = 0
    discovered_at_cycle: int = 0
    last_applied_cycle: Optional[int] = None
    tasks_improved: list[str] = field(default_factory=list)
    confidence: float = 0.0
    source_track: Optional[EngineeringTrack] = None
    applicable_tracks: list[EngineeringTrack] = field(default_factory=list)
    cross_track_effectiveness: dict[str, float] = field(default_factory=dict)
    transfer_assessed: bool = False

@dataclass(frozen=True)
class StrategyUpdate:
    update_id: str
    intervention_type: InterventionType
    description: str
    cycle_number: int
    status: StrategyStatus = StrategyStatus.PROPOSED
    rationale: str = ""
    expected_impact: str = ""
    actual_impact: Optional[str] = None
    metrics_before: dict[str, float] = field(default_factory=dict)
    metrics_after: dict[str, float] = field(default_factory=dict)
    created_at: str = ""
    confirmed_at: Optional[str] = None
    rolled_back_at: Optional[str] = None
    target_track: Optional[EngineeringTrack] = None
    cross_track_impact: dict[str, str] = field(default_factory=dict)

@dataclass(frozen=True)
class StrategyTrigger:
    trigger_id: str
    condition: str
    intervention_type: InterventionType
    threshold: float = 0.0
    cooldown_cycles: int = 100
    last_triggered_cycle: Optional[int] = None
    times_triggered: int = 0
    active: bool = True
    source_track: Optional[EngineeringTrack] = None

@dataclass(frozen=True)
class TaxonomyEntry:
    entry_id: str
    category: str
    parent_id: Optional[str] = None
    description: str = ""
    depth: int = 0
    children: list[str] = field(default_factory=list)

@dataclass(frozen=True)
class TaxonomyExtension:
    extension_id: str
    parent_entry_id: str
    new_category: str
    description: str
    status: ExtensionStatus = ExtensionStatus.PROVISIONAL
    proposed_at_cycle: int = 0
    evidence: list[str] = field(default_factory=list)
    source_track: Optional[EngineeringTrack] = None

@dataclass(frozen=True)
class SelfImprovementProposal:
    proposal_id: str
    title: str
    description: str
    target_module: str
    expected_benefit: str
    risk_assessment: str = ""
    implementation_plan: str = ""
    status: ApprovalStatus = ApprovalStatus.PENDING
    proposed_at_cycle: int = 0
    model_used: str = ""
