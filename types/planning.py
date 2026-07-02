"""
planning.py — Layer 0 Plan Types
=================================
Frozen dataclasses representing how the Self-Improving Engineering AI
plans its approach to a task within a training cycle.

Covers:
    - PlanStep            — a single ordered step in an execution plan
    - Plan                — a full plan composed of ordered steps
    - PlanAdaptation      — a mid-cycle adaptation of an existing plan
    - PlanOutcomeRecord   — the post-execution outcome of a plan
    - IntentInterpretation — the system's parsed understanding of task intent

All types are pure definitions (frozen dataclasses). No executable logic.
Imported by Layers 1–8; never imports from them.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .enums import PlanOutcome

__all__ = [
    "PlanStep",
    "Plan",
    "PlanAdaptation",
    "PlanOutcomeRecord",
    "IntentInterpretation",
]


# ---------------------------------------------------------------------------
# PlanStep
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PlanStep:
    """
    A single ordered step within a Plan.

    Each step encodes what needs to happen (description), how to do it
    (strategy), and what success looks like (expected_outcome).
    Dependencies reference other step_ids that must complete first.

    Attributes
    ----------
    step_id : str
        Unique identifier for this step within its parent plan.
    description : str
        Human-readable summary of what this step accomplishes.
    strategy : str
        Approach or method to be used when executing this step.
    expected_outcome : str
        Description of the observable result when this step succeeds.
    order : int
        Zero-based execution order within the parent plan. Steps with
        equal order values may be executed in parallel by the runner.
    dependencies : list[str]
        step_ids that must complete before this step may begin.
        Defaults to an empty list (no dependencies).
    """

    step_id: str
    description: str
    strategy: str
    expected_outcome: str
    order: int
    dependencies: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Plan
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Plan:
    """
    A complete execution plan produced by the planning subsystem.

    A Plan is created at the start of a cycle and contains an ordered
    sequence of PlanSteps. Token-usage and cost fields capture the
    expense of the LLM call that generated this plan.

    Attributes
    ----------
    plan_id : str
        Globally unique plan identifier (UUID recommended).
    task_id : str
        Identifier of the task this plan targets.
    cycle_number : int
        Training cycle during which this plan was created.
    steps : list[PlanStep]
        Ordered list of steps that make up the plan.
        Defaults to an empty list.
    rationale : str
        Free-text explanation of why this particular approach was chosen.
    created_at : str
        ISO-8601 UTC timestamp when the plan was created.
    model_used : str
        Name/version of the LLM that produced this plan.
    prompt_tokens : int
        Number of prompt tokens consumed during plan generation.
    completion_tokens : int
        Number of completion tokens produced during plan generation.
    total_tokens : int
        Sum of prompt_tokens and completion_tokens.
    cost_usd : float
        Estimated USD cost of the planning LLM call.
    """

    plan_id: str
    task_id: str
    cycle_number: int
    steps: list[PlanStep] = field(default_factory=list)
    rationale: str = ""
    created_at: str = ""
    model_used: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cost_usd: float = 0.0


# ---------------------------------------------------------------------------
# PlanAdaptation
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PlanAdaptation:
    """
    A mid-cycle revision of an existing Plan.

    When the system detects that the current plan is unlikely to succeed
    (e.g., after early test failures), it may adapt the plan rather than
    abandoning the cycle. This record captures both what changed and why.

    Attributes
    ----------
    adaptation_id : str
        Unique identifier for this adaptation record.
    original_plan_id : str
        plan_id of the Plan that was modified.
    task_id : str
        Identifier of the task being worked on.
    cycle_number : int
        Training cycle in which the adaptation occurred.
    reason : str
        Explanation of what triggered the adaptation.
    changes : list[str]
        Human-readable descriptions of each change made to the plan.
        Defaults to an empty list.
    adapted_steps : list[PlanStep]
        The revised set of PlanSteps after adaptation.
        Defaults to an empty list.
    created_at : str
        ISO-8601 UTC timestamp when this adaptation was recorded.
    """

    adaptation_id: str
    original_plan_id: str
    task_id: str
    cycle_number: int
    reason: str
    changes: list[str] = field(default_factory=list)
    adapted_steps: list[PlanStep] = field(default_factory=list)
    created_at: str = ""


# ---------------------------------------------------------------------------
# PlanOutcomeRecord
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PlanOutcomeRecord:
    """
    Post-execution record capturing whether a Plan succeeded or failed.

    Stored after the cycle resolves so that the strategy-learning system
    can correlate plan characteristics with outcomes over many cycles.

    Attributes
    ----------
    plan_id : str
        Identifier of the Plan whose outcome is recorded.
    task_id : str
        Identifier of the task the plan addressed.
    cycle_number : int
        Training cycle in which the plan was executed.
    outcome : PlanOutcome
        High-level result: SUCCESS, PARTIAL, FAILED, or SKIPPED.
    steps_completed : int
        Number of steps that completed before the cycle resolved.
    steps_total : int
        Total number of steps in the plan.
    notes : str
        Optional free-text commentary on the outcome (e.g., failure cause).
    """

    plan_id: str
    task_id: str
    cycle_number: int
    outcome: PlanOutcome
    steps_completed: int = 0
    steps_total: int = 0
    notes: str = ""


# ---------------------------------------------------------------------------
# IntentInterpretation
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class IntentInterpretation:
    """
    The system's parsed understanding of a task's underlying intent.

    Before planning begins, the system interprets what the task is really
    asking for. This record captures the primary interpretation along with
    alternatives and an associated confidence level.

    Attributes
    ----------
    task_id : str
        Identifier of the task being interpreted.
    cycle_number : int
        Training cycle in which this interpretation was produced.
    interpreted_intent : str
        The system's primary interpretation of the task's goal.
    confidence : float
        Confidence in the primary interpretation, in [0.0, 1.0].
    alternative_interpretations : list[str]
        Other plausible interpretations considered but not selected.
        Defaults to an empty list.
    model_used : str
        Name/version of the LLM that produced this interpretation.
    """

    task_id: str
    cycle_number: int
    interpreted_intent: str
    confidence: float = 0.0
    alternative_interpretations: list[str] = field(default_factory=list)
    model_used: str = ""
