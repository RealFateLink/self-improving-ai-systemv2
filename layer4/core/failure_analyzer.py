"""failure_analyzer.py — Coordinates the 5-layer failure analysis pipeline.

Stage 11.  Also handles lightweight non-selected analysis for failed losers
in otherwise successful cycles.

Pipeline:
  1. Narrator → failure narratives + canonical lessons
  2. Reasoning Analyzer → reasoning corrections
  3. Root Cause Detector → failure clustering + drift detection
  4. Counterfactual → counterfactual patches
  5. Predictor → prediction rules

Success path (handled separately):
  Success Analyzer → reusable patterns from qualifying successes.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

__all__ = ["FailureAnalyzer", "AnalysisResult"]


@dataclass(frozen=True)
class AnalysisResult:
    """Aggregate failure analysis result."""
    cycle_number: int
    track_id: str
    narratives: list[dict[str, Any]]
    corrections: list[dict[str, Any]]
    root_causes: list[dict[str, Any]]
    counterfactuals: list[dict[str, Any]]
    predictions: list[dict[str, Any]]
    success_patterns: list[dict[str, Any]]
    is_lightweight: bool  # True for non-selected analysis


@dataclass
class FailureAnalyzer:
    """Coordinates the 5 failure analysis submodules.

    Runs full pipeline for all-failed cycles.
    Runs lightweight analysis for non-selected candidates in successful cycles.

    Dependencies (failure_analysis/ submodules):
      - narrator
      - reasoning_analyzer
      - root_cause_detector
      - counterfactual
      - predictor
      - success_analyzer
    """

    narrator: Any = None
    reasoning_analyzer: Any = None
    root_cause_detector: Any = None
    counterfactual: Any = None
    predictor: Any = None
    success_analyzer: Any = None
    config: dict[str, Any] = field(default_factory=dict)

    def analyze_failure(
        self,
        candidates: list[Any],
        verifications: list[Any],
        task: Any,
        cycle_context: dict[str, Any],
    ) -> tuple[bool, Any]:
        """Full 5-layer failure analysis for all-failed cycles.

        Returns (True, ModuleResult) or (False, ModuleError).
        """
        from .intent_interpreter import ModuleResult, ModuleError

        try:
            is_benchmark = cycle_context.get("is_benchmark", False)
            track_id = cycle_context.get("domain_track", "")
            cycle = cycle_context.get("cycle_number", 0)

            # Layer 1: Narratives + lessons.
            narratives = self._run_narrator(candidates, verifications, task, is_benchmark)

            # Layer 2: Reasoning corrections.
            corrections = self._run_reasoning(candidates, verifications, task, is_benchmark)

            # Layer 3: Root cause clustering (cadence-controlled by L5).
            root_causes = self._run_root_cause(candidates, verifications, task)

            # Layer 4: Counterfactual patches.
            counterfactuals = self._run_counterfactual(candidates, task, is_benchmark)

            # Layer 5: Prediction rules.
            predictions = self._run_predictor(candidates, verifications, task)

            result = AnalysisResult(
                cycle_number=cycle,
                track_id=track_id,
                narratives=narratives,
                corrections=corrections,
                root_causes=root_causes,
                counterfactuals=counterfactuals,
                predictions=predictions,
                success_patterns=[],
                is_lightweight=False,
            )

            return True, ModuleResult(primary=result)

        except Exception as exc:
            return False, ModuleError(
                error_type="RECOVERABLE",
                message=f"Failure analysis error: {exc}",
                is_retryable=False,
            )

    def analyze_non_selected(
        self,
        losers: list[Any],
        verifications: list[Any],
        task: Any,
        cycle_context: dict[str, Any],
    ) -> tuple[bool, Any]:
        """Lightweight analysis for non-selected candidates in successful cycles."""
        from .intent_interpreter import ModuleResult

        track_id = cycle_context.get("domain_track", "")
        cycle = cycle_context.get("cycle_number", 0)

        # Only run narrator (lightweight) for non-selected.
        narratives = self._run_narrator(losers, verifications, task, False)

        result = AnalysisResult(
            cycle_number=cycle,
            track_id=track_id,
            narratives=narratives,
            corrections=[],
            root_causes=[],
            counterfactuals=[],
            predictions=[],
            success_patterns=[],
            is_lightweight=True,
        )

        return True, ModuleResult(primary=result)

    def analyze_success(
        self,
        winner: Any,
        task: Any,
        cycle_context: dict[str, Any],
    ) -> tuple[bool, Any]:
        """Analyze a successful cycle for reusable patterns."""
        from .intent_interpreter import ModuleResult

        patterns = []
        if self.success_analyzer:
            try:
                patterns = self.success_analyzer.analyze(winner, task, cycle_context)
            except Exception:
                pass

        result = AnalysisResult(
            cycle_number=cycle_context.get("cycle_number", 0),
            track_id=cycle_context.get("domain_track", ""),
            narratives=[],
            corrections=[],
            root_causes=[],
            counterfactuals=[],
            predictions=[],
            success_patterns=patterns if isinstance(patterns, list) else [],
            is_lightweight=False,
        )

        return True, ModuleResult(primary=result)

    # ── Submodule dispatchers ────────────────────────────────────────────────

    def _run_narrator(
        self,
        candidates: list[Any],
        verifications: list[Any],
        task: Any,
        is_benchmark: bool,
    ) -> list[dict[str, Any]]:
        """Run narrator submodule."""
        if self.narrator is None:
            return []
        try:
            return self.narrator.narrate(candidates, verifications, task, is_benchmark)
        except Exception:
            return []

    def _run_reasoning(
        self,
        candidates: list[Any],
        verifications: list[Any],
        task: Any,
        is_benchmark: bool,
    ) -> list[dict[str, Any]]:
        """Run reasoning analyzer submodule."""
        if self.reasoning_analyzer is None:
            return []
        try:
            return self.reasoning_analyzer.analyze(candidates, verifications, task, is_benchmark)
        except Exception:
            return []

    def _run_root_cause(
        self,
        candidates: list[Any],
        verifications: list[Any],
        task: Any,
    ) -> list[dict[str, Any]]:
        """Run root cause detector submodule."""
        if self.root_cause_detector is None:
            return []
        try:
            return self.root_cause_detector.detect(candidates, verifications, task)
        except Exception:
            return []

    def _run_counterfactual(
        self,
        candidates: list[Any],
        task: Any,
        is_benchmark: bool,
    ) -> list[dict[str, Any]]:
        """Run counterfactual submodule."""
        if self.counterfactual is None:
            return []
        try:
            return self.counterfactual.generate(candidates, task, is_benchmark)
        except Exception:
            return []

    def _run_predictor(
        self,
        candidates: list[Any],
        verifications: list[Any],
        task: Any,
    ) -> list[dict[str, Any]]:
        """Run predictor submodule."""
        if self.predictor is None:
            return []
        try:
            return self.predictor.predict(candidates, verifications, task)
        except Exception:
            return []
