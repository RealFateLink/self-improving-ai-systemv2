"""
review.py — Layer 0 Review and Analysis Types
===============================================
Frozen dataclasses representing the outputs produced by the static
analysis, semantic critique, and code-smell review subsystems.

Covers:
    - StaticReviewResult    — output from the automated static reviewer
    - SemanticCriticResult  — output from the LLM semantic critic
    - CodeSmellResult       — aggregated code-smell detections for a candidate
    - SmellDetection        — a single detected code smell with metadata
    - ReasoningAnalysis     — evaluation of the reasoning chain behind a solution
    - CounterfactualResult  — outcome of a "what if" alternative-approach analysis
    - ReviewSummary         — consolidated verdict combining all review signals
    - FunctionAnalysis      — per-function structural metrics from static analysis

All types are pure definitions (frozen dataclasses). No executable logic.
Imported by Layers 1–8; never imports from them.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .enums import FunctionRole, ReviewVerdict, Severity, SmellType

__all__ = [
    "StaticReviewResult",
    "SemanticCriticResult",
    "CodeSmellResult",
    "SmellDetection",
    "ReasoningAnalysis",
    "CounterfactualResult",
    "ReviewSummary",
    "FunctionAnalysis",
]


# ---------------------------------------------------------------------------
# StaticReviewResult
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class StaticReviewResult:
    """
    Output from the automated static code reviewer.

    The static reviewer applies rule-based and lightweight LLM checks
    (style, syntax correctness, obvious logic errors) without executing
    the code. Results inform the overall ReviewSummary.

    Attributes
    ----------
    review_id : str
        Globally unique identifier for this review record.
    task_id : str
        Identifier of the task whose candidate is being reviewed.
    cycle_number : int
        Training cycle in which the review was performed.
    candidate_id : str
        candidate_id of the GenerationCandidate under review.
    verdict : ReviewVerdict
        High-level judgement: PASS, FAIL, PARTIAL_PASS, or ERROR.
    issues : list[str]
        Blocking problems that must be addressed before promotion.
        Defaults to an empty list.
    warnings : list[str]
        Non-blocking notes that may affect score or readability.
        Defaults to an empty list.
    score : float
        Static-review quality score in [0.0, 1.0].
    model_used : str
        Name/version of the LLM used for any LLM-assisted static checks.
        Empty string if no LLM was involved.
    prompt_tokens : int
        Prompt tokens consumed by LLM-assisted checks (0 if none).
    completion_tokens : int
        Completion tokens produced by LLM-assisted checks (0 if none).
    cost_usd : float
        Estimated USD cost of LLM-assisted static checks (0.0 if none).
    """

    review_id: str
    task_id: str
    cycle_number: int
    candidate_id: str
    verdict: ReviewVerdict
    issues: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    score: float = 0.0
    model_used: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: float = 0.0


# ---------------------------------------------------------------------------
# SemanticCriticResult
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SemanticCriticResult:
    """
    Output from the LLM-based semantic code critic.

    The semantic critic evaluates whether the code is correct with respect
    to the task specification, complete in covering all required cases, and
    elegantly written. Scores across these three dimensions are stored
    individually so that fine-grained learning is possible.

    Attributes
    ----------
    review_id : str
        Globally unique identifier for this review record.
    task_id : str
        Identifier of the task whose candidate is being reviewed.
    cycle_number : int
        Training cycle in which the review was performed.
    candidate_id : str
        candidate_id of the GenerationCandidate under review.
    verdict : ReviewVerdict
        High-level judgement: PASS, FAIL, PARTIAL_PASS, or ERROR.
    correctness_score : float
        Score measuring algorithmic and logical correctness, in [0.0, 1.0].
    completeness_score : float
        Score measuring coverage of all required cases, in [0.0, 1.0].
    elegance_score : float
        Score measuring code clarity, idiom usage, and simplicity,
        in [0.0, 1.0].
    issues : list[str]
        Semantic problems that affect correctness or completeness.
        Defaults to an empty list.
    suggestions : list[str]
        Optional improvements that would raise the elegance score.
        Defaults to an empty list.
    model_used : str
        Name/version of the LLM that produced this critique.
    cost_usd : float
        Estimated USD cost of the critic LLM call.
    """

    review_id: str
    task_id: str
    cycle_number: int
    candidate_id: str
    verdict: ReviewVerdict
    correctness_score: float = 0.0
    completeness_score: float = 0.0
    elegance_score: float = 0.0
    issues: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)
    model_used: str = ""
    cost_usd: float = 0.0


# ---------------------------------------------------------------------------
# SmellDetection
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SmellDetection:
    """
    A single code smell detected during smell analysis.

    SmellDetections are collected into a CodeSmellResult. Each detection
    names the smell, rates its severity, and pinpoints where it occurs.

    Attributes
    ----------
    smell_type : SmellType
        Category of the detected code smell.
    severity : Severity
        Impact severity (S1 = most critical … S4 = least critical).
    location : str
        Human-readable location in the source (e.g., function name,
        line number, or file section).  Empty string if unlocated.
    description : str
        Explanation of why this pattern is considered a smell here.
    suggestion : str
        Recommended refactoring or improvement to resolve the smell.
    """

    smell_type: SmellType
    severity: Severity
    location: str = ""
    description: str = ""
    suggestion: str = ""


# ---------------------------------------------------------------------------
# CodeSmellResult
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CodeSmellResult:
    """
    Aggregated code-smell analysis for a single GenerationCandidate.

    The smell analyzer inspects the candidate's code for patterns known
    to reduce maintainability. All detected smells are stored here along
    with a rolled-up severity score for ranking and filtering.

    Attributes
    ----------
    review_id : str
        Globally unique identifier for this smell-analysis record.
    task_id : str
        Identifier of the task whose candidate is being analysed.
    cycle_number : int
        Training cycle in which the analysis was performed.
    candidate_id : str
        candidate_id of the GenerationCandidate under analysis.
    smells_detected : list[SmellDetection]
        All individual smells found in the candidate's code.
        Defaults to an empty list.
    total_severity_score : float
        Aggregated severity across all detections (higher = worse).
        Computed by the analysis layer; stored here for fast lookup.
    model_used : str
        Name/version of the LLM used for LLM-assisted smell detection.
        Empty string if only rule-based detection was used.
    """

    review_id: str
    task_id: str
    cycle_number: int
    candidate_id: str
    smells_detected: list[SmellDetection] = field(default_factory=list)
    total_severity_score: float = 0.0
    model_used: str = ""


# ---------------------------------------------------------------------------
# ReasoningAnalysis
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ReasoningAnalysis:
    """
    Evaluation of the reasoning chain that produced a candidate solution.

    The reasoning analyser reviews the chain-of-thought or scratchpad
    (when available) to detect logical gaps and hidden assumptions that
    may cause the solution to fail on unseen inputs.

    Attributes
    ----------
    analysis_id : str
        Globally unique identifier for this reasoning analysis record.
    task_id : str
        Identifier of the task whose reasoning is being evaluated.
    cycle_number : int
        Training cycle in which the analysis was performed.
    reasoning_quality : float
        Overall reasoning quality score in [0.0, 1.0].
    logical_gaps : list[str]
        Descriptions of steps where the reasoning chain is missing
        intermediate conclusions.  Defaults to an empty list.
    assumptions : list[str]
        Implicit assumptions the solution relies on that were never
        stated explicitly.  Defaults to an empty list.
    alternative_approaches : list[str]
        Other valid approaches that the reasoning did not consider.
        Defaults to an empty list.
    model_used : str
        Name/version of the LLM that performed the reasoning analysis.
    """

    analysis_id: str
    task_id: str
    cycle_number: int
    reasoning_quality: float = 0.0
    logical_gaps: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    alternative_approaches: list[str] = field(default_factory=list)
    model_used: str = ""


# ---------------------------------------------------------------------------
# CounterfactualResult
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CounterfactualResult:
    """
    Outcome of a counterfactual "what if we had done it differently" analysis.

    The counterfactual engine evaluates whether an alternative approach
    to the same task would have produced better results. This drives
    exploration and strategy-diversification decisions.

    Attributes
    ----------
    result_id : str
        Globally unique identifier for this counterfactual result.
    task_id : str
        Identifier of the task that was analysed.
    cycle_number : int
        Training cycle in which the counterfactual was evaluated.
    original_approach : str
        Description of the approach that was actually taken.
    counterfactual_approach : str
        Description of the hypothetical alternative approach.
    expected_outcome : str
        Predicted result had the counterfactual approach been taken.
    confidence : float
        Confidence in the predicted counterfactual outcome, in [0.0, 1.0].
    would_improve : bool
        True if the counterfactual approach is predicted to outperform
        the original.
    model_used : str
        Name/version of the LLM that produced this counterfactual analysis.
    """

    result_id: str
    task_id: str
    cycle_number: int
    original_approach: str
    counterfactual_approach: str
    expected_outcome: str
    confidence: float = 0.0
    would_improve: bool = False
    model_used: str = ""


# ---------------------------------------------------------------------------
# ReviewSummary
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ReviewSummary:
    """
    Consolidated review verdict combining all review signals for a candidate.

    After StaticReviewResult, SemanticCriticResult, and CodeSmellResult
    are all available, a ReviewSummary is produced to give the selection
    subsystem a single, consistent view of the candidate's quality.

    Attributes
    ----------
    task_id : str
        Identifier of the task whose candidate is being summarised.
    cycle_number : int
        Training cycle in which the summary was produced.
    candidate_id : str
        candidate_id of the GenerationCandidate being summarised.
    static_verdict : ReviewVerdict
        Verdict from the StaticReviewResult. Defaults to PASS.
    semantic_verdict : ReviewVerdict
        Verdict from the SemanticCriticResult. Defaults to PASS.
    combined_score : float
        Weighted combination of static and semantic scores, in [0.0, 1.0].
    smell_count : int
        Total number of code smells detected in the candidate.
    smell_severity : float
        Aggregated severity score from CodeSmellResult.total_severity_score.
    pass_recommendation : bool
        True if the review pipeline recommends promoting this candidate.
    notes : str
        Optional free-text summary of key review findings.
    """

    task_id: str
    cycle_number: int
    candidate_id: str
    static_verdict: ReviewVerdict = ReviewVerdict.PASS
    semantic_verdict: ReviewVerdict = ReviewVerdict.PASS
    combined_score: float = 0.0
    smell_count: int = 0
    smell_severity: float = 0.0
    pass_recommendation: bool = True
    notes: str = ""


# ---------------------------------------------------------------------------
# FunctionAnalysis
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class FunctionAnalysis:
    """
    Per-function structural metrics extracted by the static analyser.

    One FunctionAnalysis is produced for each function or method found
    in a candidate's code. Aggregated across all functions, these records
    help the learning system understand recurring complexity patterns.

    Attributes
    ----------
    function_name : str
        Name of the function or method being analysed.
    role : FunctionRole
        Inferred semantic role (pure function, I/O handler, etc.).
    line_count : int
        Number of source lines in the function body (excluding blank lines
        and comments).
    complexity : int
        McCabe cyclomatic complexity of the function.
    parameters : list[str]
        Ordered list of parameter names.  Defaults to an empty list.
    return_type : str
        Inferred or annotated return type string.  Empty if unknown.
    smells : list[SmellType]
        SmellTypes detected specifically within this function.
        Defaults to an empty list.
    """

    function_name: str
    role: FunctionRole
    line_count: int = 0
    complexity: int = 0
    parameters: list[str] = field(default_factory=list)
    return_type: str = ""
    smells: list[SmellType] = field(default_factory=list)
