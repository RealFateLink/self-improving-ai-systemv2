"""
curriculum.py — Curriculum Management Types
============================================
Defines data types for the adaptive curriculum subsystem: mutable state
tracking the system's current difficulty level and mode, immutable records
of level transitions and difficulty assessments, and historical progress
records per level.

All classes are pure data definitions (dataclasses).
Frozen dataclasses are immutable value objects; non-frozen ones are
mutable state containers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .enums import TaskLevel, Domain, CurriculumMode

__all__ = [
    "CurriculumState",
    "CurriculumTransition",
    "DifficultyAssessment",
    "LevelProgressRecord",
]


# ---------------------------------------------------------------------------
# Curriculum State
# ---------------------------------------------------------------------------

@dataclass
class CurriculumState:
    """
    Mutable system-level state for the adaptive curriculum scheduler.

    This is the primary state object read and written by the curriculum
    subsystem each cycle.  It determines which tasks are selected and at
    what difficulty, and triggers promotions or demotions based on observed
    pass rates.

    Attributes:
        current_level: The ``TaskLevel`` the system is currently training at.
        current_mode: The ``CurriculumMode`` controlling task selection
            strategy (standard, exam, exploration, or directed).
        cycles_at_current_level: Number of training cycles completed at
            ``current_level`` without a level change.
        pass_rate_at_level: Rolling pass rate observed at the current level
            (0–1).
        promotion_threshold: Pass rate above which a promotion is
            considered (default 0.85).
        demotion_threshold: Pass rate below which a demotion is triggered
            (default 0.40).
        level_history: Ordered list of level-transition records (dicts)
            providing a full audit trail of curriculum changes.
        exploration_budget_remaining: Fraction of the current cycle's task
            budget reserved for exploratory tasks (0–1).
        directed_queue: Ordered list of task IDs explicitly queued for
            directed-mode training; consumed FIFO.
    """

    current_level: TaskLevel = TaskLevel.F1
    current_mode: CurriculumMode = CurriculumMode.STANDARD
    cycles_at_current_level: int = 0
    pass_rate_at_level: float = 0.0
    promotion_threshold: float = 0.85
    demotion_threshold: float = 0.40
    level_history: list[dict] = field(default_factory=list)
    exploration_budget_remaining: float = 0.0
    directed_queue: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Curriculum Transition
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CurriculumTransition:
    """
    Immutable record of a single curriculum level change.

    Created whenever the curriculum scheduler promotes or demotes the system
    to a new ``TaskLevel``.  Stored in ``CurriculumState.level_history``
    and persisted to the ledger for audit purposes.

    Attributes:
        from_level: The ``TaskLevel`` the system was at before the change.
        to_level: The ``TaskLevel`` the system moved to.
        cycle_number: Training cycle when the transition occurred.
        reason: Human-readable explanation of why the transition happened
            (e.g. ``"pass_rate_above_promotion_threshold"``).
        pass_rate_at_transition: Pass rate that triggered the transition.
        cycles_spent: Number of cycles spent at ``from_level`` before
            this transition.
    """

    from_level: TaskLevel
    to_level: TaskLevel
    cycle_number: int
    reason: str
    pass_rate_at_transition: float = 0.0
    cycles_spent: int = 0


# ---------------------------------------------------------------------------
# Difficulty Assessment
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class DifficultyAssessment:
    """
    Immutable LLM-generated difficulty assessment for a specific task.

    The curriculum subsystem generates assessments to calibrate task
    selection.  A task's assessed level may differ from its nominal
    ``TaskLevel`` label; high-confidence assessments can update the task
    record in the ledger.

    Attributes:
        task_id: Identifier of the task being assessed.
        assessed_level: The ``TaskLevel`` assigned by the assessment.
        actual_difficulty: Continuous difficulty score in [0, 1] derived
            from factors such as solution length, edge-case count, and
            required algorithmic complexity.
        confidence: Assessment confidence in [0, 1]; low-confidence
            assessments are flagged for human review.
        factors: List of named factors that contributed to the difficulty
            score (e.g. ``["nested_loops", "pointer_arithmetic"]``).
    """

    task_id: str
    assessed_level: TaskLevel
    actual_difficulty: float = 0.0
    confidence: float = 0.0
    factors: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Level Progress Record
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class LevelProgressRecord:
    """
    Immutable historical summary of performance at a single ``TaskLevel``.

    One record is finalized each time the system leaves a level (via
    promotion or demotion) and stored in the graduation / curriculum audit
    log.  Partial records (``exited_at_cycle`` is ``None``) represent the
    currently active level.

    Attributes:
        level: The ``TaskLevel`` this record describes.
        entered_at_cycle: Training cycle when the system first entered
            this level.
        exited_at_cycle: Training cycle when the system left this level,
            or ``None`` if the level is still active.
        total_cycles: Total number of training cycles spent at this level.
        pass_rate: Overall pass rate observed across all cycles at this
            level (0–1).
        tasks_attempted: Cumulative number of tasks attempted at this level.
        tasks_passed: Cumulative number of tasks that passed at this level.
    """

    level: TaskLevel
    entered_at_cycle: int
    exited_at_cycle: Optional[int] = None
    total_cycles: int = 0
    pass_rate: float = 0.0
    tasks_attempted: int = 0
    tasks_passed: int = 0
