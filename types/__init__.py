"""Layer 0 types package — re-exports all type definitions."""
from __future__ import annotations

# Core enumerations — all other modules depend on these.
from .enums import *  # noqa: F401,F403

# Shared / primitive types used across the whole system.
from .common import *  # noqa: F401,F403

# Task representation (TaskSpec, TaskMetadata, SamplerRequest, …)
from .task import *  # noqa: F401,F403

# Planning types (Plan, PlanStep, PlanAdaptation, …)
from .planning import *  # noqa: F401,F403

# Generation types (GenerationRequest, GenerationResult, …)
from .generation import *  # noqa: F401,F403

# Review types (StaticReview, SemanticCritique, CodeSmellReport, …)
from .review import *  # noqa: F401,F403

# Scoring types (ScoreBreakdown, SelectionOutcome, …)
from .scoring import *  # noqa: F401,F403

# Failure analysis types (FailureNarrative, RootCauseChain, …)
from .failure import *  # noqa: F401,F403

# Strategy & learning types (StrategyUpdate, Pattern, PreventionArtifact, …)
from .strategy import *  # noqa: F401,F403

# Agent types (AgentRegistryEntry, AgentConstructionPlan, AgentMessage, …)
from .agents import *  # noqa: F401,F403

# Observability types (Alert, DigestEntry, TraceSpan, OvernightSession, …)
from .observability import *  # noqa: F401,F403

# Graduation types (GraduationState, GateSet, BenchmarkVersionInfo, …)
from .graduation import *  # noqa: F401,F403

# Optimization types (OptimizationBrief, OptimizationCandidate, …)
from .optimization import *  # noqa: F401,F403

# Curriculum types (CurriculumState, ExplorationCandidate, …)
from .curriculum import *  # noqa: F401,F403

# Multi-track domain types (TrackDefinition, TrackPerformance,
# TrackGraduationState, GraduationCeilingFlag, CrossTrackInsight,
# GeneratedTaskCandidate, TaskVerificationResult, TaskGenerationCapability, …)
from .track import *  # noqa: F401,F403

# Analytics types (TaskPerformanceRecord, AnalyticsSummary, …)
from .analytics import *  # noqa: F401,F403

# Configuration dataclasses (~44 classes: TracksConfig, TaskGenerationConfig,
# QEMUSandboxConfig, TrackSchedulingConfig, TrackGraduationConfig, …)
from .config import *  # noqa: F401,F403

# Protocol definitions (23 protocols: TrackSchedulerProtocol,
# CrossTrackAnalyzerProtocol, TrackPerformanceTrackerProtocol, …)
from .protocols import *  # noqa: F401,F403
