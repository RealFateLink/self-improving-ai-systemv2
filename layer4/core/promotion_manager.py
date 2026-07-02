"""promotion_manager.py — Promotes winners or handles all-failed cycles.

Stage 10.  INVARIANT-CORE module.
Emits prevention artifacts.
Coordinates with success/failure downstream consumers.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Optional

__all__ = ["PromotionManager", "PromotionResult"]


@dataclass(frozen=True)
class PromotionResult:
    """Result of promotion decision."""
    promoted: bool
    candidate_id: str | None
    promotion_type: str        # winner | improvement | all_failed
    artifacts: list[dict[str, Any]]  # Prevention artifacts, lessons, etc.
    lineage: dict[str, Any] = field(default_factory=dict)
    signals: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class PromotionManager:
    """Promotes winning candidates or handles all-failed cycles.

    INVARIANT-CORE: promotion decisions follow strict rules.

    When a winner exists:
      - Promote code to the solution store
      - Emit success artifacts for downstream learning
      - Record lineage

    When all candidates fail:
      - Emit prevention artifacts
      - Trigger failure analysis pipeline
      - Record failure lineage
    """

    ledger: Any = None       # Layer 2
    config: dict[str, Any] = field(default_factory=dict)

    def promote(
        self,
        selection: Any,
        candidates: list[Any],
        task: Any,
        cycle_context: dict[str, Any],
    ) -> tuple[bool, Any]:
        """Promote winner or handle all-failed.

        Returns (True, ModuleResult) or (False, ModuleError).
        """
        from .intent_interpreter import ModuleResult, ModuleError

        try:
            all_failed = getattr(selection, "all_failed", True)
            winner_id = getattr(selection, "winner_id", None)
            cycle_number = cycle_context.get("cycle_number", 0)
            track_id = cycle_context.get("domain_track", "")
            is_benchmark = cycle_context.get("is_benchmark", False)

            signals: list[dict[str, Any]] = []

            if all_failed:
                result = self._handle_all_failed(
                    candidates, task, cycle_context, is_benchmark,
                )
            else:
                result = self._handle_winner(
                    winner_id, selection, candidates, task, cycle_context, is_benchmark,
                )

            # Check for graduation trigger based on sustained performance.
            if not all_failed and not is_benchmark:
                signals.extend(self._check_lifecycle_signals(track_id, cycle_number))

            return True, ModuleResult(
                primary=result,
                lifecycle_signals=signals,
            )

        except Exception as exc:
            return False, ModuleError(
                error_type="RECOVERABLE",
                message=f"Promotion failed: {exc}",
                is_retryable=False,
            )

    def _handle_winner(
        self,
        winner_id: str | None,
        selection: Any,
        candidates: list[Any],
        task: Any,
        cycle_context: dict[str, Any],
        is_benchmark: bool,
    ) -> PromotionResult:
        """Promote the winning candidate."""
        winner = None
        for c in candidates:
            if getattr(c, "candidate_id", "") == winner_id:
                winner = c
                break

        artifacts = []

        # Store solution (not in benchmark mode).
        if winner and self.ledger and not is_benchmark:
            self._store_solution(winner, task, cycle_context)

        # Emit success artifacts.
        if winner:
            artifacts.append({
                "type": "success_solution",
                "candidate_id": winner_id,
                "task_id": getattr(task, "task_id", ""),
                "track_id": cycle_context.get("domain_track", ""),
                "retention_class": "PERMANENT",
            })

        # Handle non-selected candidates (lightweight analysis).
        losers = [c for c in candidates if getattr(c, "candidate_id", "") != winner_id]
        for loser in losers:
            artifacts.append({
                "type": "non_selected_analysis",
                "candidate_id": getattr(loser, "candidate_id", ""),
                "retention_class": "SHORT_TERM",
            })

        lineage = self._build_lineage(winner_id, task, cycle_context)

        return PromotionResult(
            promoted=True,
            candidate_id=winner_id,
            promotion_type="winner",
            artifacts=artifacts,
            lineage=lineage,
        )

    def _handle_all_failed(
        self,
        candidates: list[Any],
        task: Any,
        cycle_context: dict[str, Any],
        is_benchmark: bool,
    ) -> PromotionResult:
        """Handle all-failed cycle."""
        artifacts = []

        # Emit prevention artifacts.
        for c in candidates:
            cid = getattr(c, "candidate_id", "")
            artifacts.append({
                "type": "prevention_artifact",
                "candidate_id": cid,
                "task_id": getattr(task, "task_id", ""),
                "track_id": cycle_context.get("domain_track", ""),
                "status": "CANDIDATE",
                "retention_class": "MEDIUM_TERM",
                "is_benchmark": is_benchmark,
            })

        lineage = self._build_lineage(None, task, cycle_context)

        return PromotionResult(
            promoted=False,
            candidate_id=None,
            promotion_type="all_failed",
            artifacts=artifacts,
            lineage=lineage,
        )

    def _store_solution(
        self,
        winner: Any,
        task: Any,
        cycle_context: dict[str, Any],
    ) -> None:
        """Persist winning solution via Ledger."""
        if self.ledger is None:
            return
        # In production, calls ledger.insert with full lineage.
        pass

    def _build_lineage(
        self,
        candidate_id: str | None,
        task: Any,
        cycle_context: dict[str, Any],
    ) -> dict[str, Any]:
        """Build lineage metadata."""
        return {
            "artifact_id": str(uuid.uuid4()),
            "parent_id": getattr(task, "task_id", ""),
            "cycle_id": cycle_context.get("cycle_number", 0),
            "entity_id": cycle_context.get("entity_id", "MAIN"),
            "domain_track": cycle_context.get("domain_track", ""),
            "language": cycle_context.get("language", ""),
        }

    def _check_lifecycle_signals(
        self,
        track_id: str,
        cycle_number: int,
    ) -> list[dict[str, Any]]:
        """Check for lifecycle signals to emit."""
        # Signals are accumulated per-cycle and routed by Layer 5.
        return []
