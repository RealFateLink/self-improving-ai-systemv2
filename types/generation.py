"""
generation.py — Layer 0 Code Generation Types
===============================================
Frozen dataclasses representing the outputs and decisions produced by
the LLM-powered code generation subsystem.

Covers:
    - GenerationAttempt   — a single LLM call that produces generated code
    - GenerationCandidate — a scored, ranked candidate solution
    - SelectionResult     — the outcome of the candidate-selection step
    - PromotionRecord     — the promotion/hold/demote decision for a candidate

All types are pure definitions (frozen dataclasses). No executable logic.
Imported by Layers 1–8; never imports from them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .enums import FinishReason, PromotionDecision, SelectionOutcomeType

__all__ = [
    "GenerationAttempt",
    "GenerationCandidate",
    "SelectionResult",
    "PromotionRecord",
]


# ---------------------------------------------------------------------------
# GenerationAttempt
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class GenerationAttempt:
    """
    A single LLM invocation that produces a candidate solution.

    One cycle may produce several GenerationAttempts (e.g., with different
    temperatures or prompt templates). Each attempt is independently stored
    so the analysis subsystem can learn from the full generation history.

    Attributes
    ----------
    attempt_id : str
        Globally unique identifier for this generation attempt.
    task_id : str
        Identifier of the task the code was generated for.
    cycle_number : int
        Training cycle during which the attempt was made.
    plan_id : Optional[str]
        plan_id of the Plan that guided generation, if any.
    generated_code : str
        Raw code string returned by the LLM.
    language : str
        Programming language of the generated code.  Defaults to "python".
    model_used : str
        Name/version of the LLM that produced the code.
    prompt_tokens : int
        Number of prompt tokens sent to the LLM.
    completion_tokens : int
        Number of completion tokens returned by the LLM.
    total_tokens : int
        Sum of prompt_tokens and completion_tokens.
    cost_usd : float
        Estimated USD cost of this LLM call.
    latency_ms : float
        Wall-clock time from request dispatch to full response receipt,
        in milliseconds.
    finish_reason : FinishReason
        Reason the LLM stopped generating (STOP, MAX_TOKENS, or ERROR).
    created_at : str
        ISO-8601 UTC timestamp when the attempt was initiated.
    attempt_number : int
        One-based attempt index within the current cycle. Useful when
        multiple attempts are made per cycle.
    temperature : float
        Sampling temperature used for this attempt.
    prompt_template : str
        Name or identifier of the prompt template used.
    """

    attempt_id: str
    task_id: str
    cycle_number: int
    plan_id: Optional[str] = None
    generated_code: str = ""
    language: str = "python"
    model_used: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cost_usd: float = 0.0
    latency_ms: float = 0.0
    finish_reason: FinishReason = FinishReason.STOP
    created_at: str = ""
    attempt_number: int = 1
    temperature: float = 0.0
    prompt_template: str = ""


# ---------------------------------------------------------------------------
# GenerationCandidate
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class GenerationCandidate:
    """
    A candidate solution derived from a GenerationAttempt, scored and ranked.

    After raw code is generated, it is executed, tested, and reviewed.
    The results are aggregated into this record so that the selection
    subsystem can pick the best candidate from a pool.

    Attributes
    ----------
    candidate_id : str
        Globally unique identifier for this candidate.
    attempt_id : str
        attempt_id of the GenerationAttempt that produced this code.
    task_id : str
        Identifier of the task this candidate addresses.
    cycle_number : int
        Training cycle during which this candidate was produced.
    code : str
        The candidate's source code (may differ from generated_code if
        post-processed or lightly reformatted).
    score : float
        Aggregate quality score in [0.0, 1.0].
    passed_tests : bool
        True if the candidate passed all required test cases.
    execution_time_ms : float
        Observed execution time of the candidate's code in milliseconds.
    memory_used_mb : float
        Peak memory consumption of the candidate's code in megabytes.
    review_scores : dict[str, float]
        Dimension-keyed review scores (e.g., ``{"correctness": 0.9}``).
        Defaults to an empty dict.
    rank : int
        Position of this candidate within the current cycle's pool
        (1 = best). Zero indicates unranked.
    """

    candidate_id: str
    attempt_id: str
    task_id: str
    cycle_number: int
    code: str
    score: float = 0.0
    passed_tests: bool = False
    execution_time_ms: float = 0.0
    memory_used_mb: float = 0.0
    review_scores: dict[str, float] = field(default_factory=dict)
    rank: int = 0


# ---------------------------------------------------------------------------
# SelectionResult
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SelectionResult:
    """
    The outcome of the candidate-selection step within a cycle.

    After all candidates are scored and ranked, the selection subsystem
    picks the winner (or records why no winner could be chosen).

    Attributes
    ----------
    task_id : str
        Identifier of the task for which selection was performed.
    cycle_number : int
        Training cycle during which selection occurred.
    outcome : SelectionOutcomeType
        Whether a candidate was SELECTED, ALL_FAILED, or TIE_BROKEN.
    selected_candidate_id : Optional[str]
        candidate_id of the winning GenerationCandidate, or None if
        all candidates failed.
    candidates_evaluated : int
        Total number of candidates considered during selection.
    selection_rationale : str
        Human-readable explanation of why this candidate was chosen.
    tie_break_method : Optional[str]
        Name of the tie-breaking algorithm used when outcome is
        TIE_BROKEN, or None otherwise.
    """

    task_id: str
    cycle_number: int
    outcome: SelectionOutcomeType
    selected_candidate_id: Optional[str] = None
    candidates_evaluated: int = 0
    selection_rationale: str = ""
    tie_break_method: Optional[str] = None


# ---------------------------------------------------------------------------
# PromotionRecord
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PromotionRecord:
    """
    The promotion, hold, or demote decision for a selected candidate.

    After a candidate is selected, the promotion subsystem decides whether
    it should replace the current best solution, be held for further
    evaluation, or cause a demotion of the current champion.

    Attributes
    ----------
    task_id : str
        Identifier of the task the candidate addresses.
    cycle_number : int
        Training cycle in which the promotion decision was made.
    candidate_id : str
        candidate_id of the GenerationCandidate under evaluation.
    decision : PromotionDecision
        Outcome: PROMOTE, HOLD, or DEMOTE.
    previous_best_score : Optional[float]
        Score of the previously promoted solution, or None if no prior
        solution exists for this task.
    new_score : float
        Score of the candidate being evaluated.
    reason : str
        Explanation of the promotion decision.
    """

    task_id: str
    cycle_number: int
    candidate_id: str
    decision: PromotionDecision
    previous_best_score: Optional[float] = None
    new_score: float = 0.0
    reason: str = ""
