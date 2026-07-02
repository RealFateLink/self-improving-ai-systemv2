"""
failure.py — Layer 0 Failure Analysis Type Definitions
=======================================================
Frozen dataclasses (and mutable where noted) representing failure narratives,
failure chains, root-cause analyses, prevention artifacts, failure patterns,
and success analyses used throughout the Self-Improving Engineering AI system.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
from .enums import (
    FailureCategory, ChainStatus, Severity, ArtifactType, ArtifactStatus,
    SuccessTrigger, EngineeringTrack,
)

__all__ = [
    "FailureNarrative", "FailureChain", "RootCauseAnalysis",
    "RootCauseChain", "PreventionArtifact", "FailurePattern", "SuccessAnalysis",
]

@dataclass(frozen=True)
class FailureNarrative:
    narrative_id: str
    task_id: str
    cycle_number: int
    category: FailureCategory
    summary: str
    root_cause: str = ""
    contributing_factors: list[str] = field(default_factory=list)
    severity: Severity = Severity.S2
    test_failures: list[str] = field(default_factory=list)
    error_output: str = ""
    model_used: str = ""
    cost_usd: float = 0.0
    created_at: str = ""
    domain_track: Optional[EngineeringTrack] = None

@dataclass
class FailureChain:
    chain_id: str
    root_category: FailureCategory
    occurrences: list[str] = field(default_factory=list)
    first_seen_cycle: int = 0
    last_seen_cycle: int = 0
    status: ChainStatus = ChainStatus.GROWING
    frequency: float = 0.0
    severity: Severity = Severity.S2
    related_tasks: list[str] = field(default_factory=list)
    interventions_tried: list[str] = field(default_factory=list)
    resolution_detail: Optional[str] = None

@dataclass(frozen=True)
class RootCauseAnalysis:
    analysis_id: str
    chain_id: str
    cycle_number: int
    root_cause: str
    confidence: float = 0.0
    evidence: list[str] = field(default_factory=list)
    suggested_interventions: list[str] = field(default_factory=list)
    model_used: str = ""
    cost_usd: float = 0.0

@dataclass(frozen=True)
class RootCauseChain:
    chain_id: str
    causes: list[str] = field(default_factory=list)
    depth: int = 0
    confidence: float = 0.0
    primary_category: FailureCategory = FailureCategory.UNKNOWN
    tracks: list[EngineeringTrack] = field(default_factory=list)

@dataclass
class PreventionArtifact:
    artifact_id: str
    artifact_type: ArtifactType
    description: str
    source_chain_id: Optional[str] = None
    source_failure_id: Optional[str] = None
    content: str = ""
    effectiveness: float = 0.0
    applications: int = 0
    status: ArtifactStatus = ArtifactStatus.ACTIVE
    created_at_cycle: int = 0
    last_applied_cycle: Optional[int] = None
    severity: Severity = Severity.S2
    applicable_tracks: list[EngineeringTrack] = field(default_factory=list)

@dataclass(frozen=True)
class FailurePattern:
    pattern_id: str
    category: FailureCategory
    description: str
    frequency: float = 0.0
    first_seen_cycle: int = 0
    task_ids: list[str] = field(default_factory=list)
    suggested_remedy: str = ""

@dataclass(frozen=True)
class SuccessAnalysis:
    analysis_id: str
    task_id: str
    cycle_number: int
    trigger: SuccessTrigger
    key_factors: list[str] = field(default_factory=list)
    replicable: bool = False
    new_pattern_extracted: bool = False
    model_used: str = ""
