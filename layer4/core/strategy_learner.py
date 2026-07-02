"""strategy_learner.py — Checks triggers every cycle, proposes interventions.

Stage 12.  Proposes interventions on cadence (every 50 cycles, controlled by L5).
Consumes confidence as weighting signal.
Interprets Layer 3 measurements; does NOT override them.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Optional

__all__ = ["StrategyLearner", "StrategyProposal"]


@dataclass(frozen=True)
class StrategyProposal:
    """A proposed strategy intervention."""
    proposal_id: str
    track_id: str
    proposal_type: str       # adjust_weights | change_model | increase_candidates | economy | pause
    description: str
    evidence: list[str]
    confidence: float
    is_safe: bool            # True → auto-apply; False → human approval
    params: dict[str, Any] = field(default_factory=dict)


@dataclass
class StrategyLearner:
    """Proposes strategy interventions based on performance trends.

    Checks triggers every cycle (lightweight).
    Full proposal on cadence (every 50 cycles, controlled by Layer 5).

    Authority: Layer 4 INTERPRETS Layer 3 measurements.
    Cannot override Layer 3 outputs — disagreement flows through proposals only.

    Dependencies:
      - performance_tracker (Layer 3): for health scores
      - skill_tracker (Layer 3): for weakness data
    """

    performance_tracker: Any = None
    skill_tracker: Any = None
    config: dict[str, Any] = field(default_factory=dict)

    _last_proposal_cycle: int = 0
    _trigger_history: list[dict[str, Any]] = field(default_factory=list)

    def check_triggers(
        self,
        cycle_context: dict[str, Any],
    ) -> tuple[bool, Any]:
        """Lightweight per-cycle trigger check.

        Returns (True, ModuleResult) or (False, ModuleError).
        """
        from .intent_interpreter import ModuleResult

        track_id = cycle_context.get("domain_track", "")
        signals: list[dict[str, Any]] = []
        warnings: list[dict[str, Any]] = []

        # Check for stagnation.
        if self.performance_tracker:
            stagnant = self.performance_tracker.detect_stagnation(track_id)
            if stagnant:
                signals.append({
                    "signal_type": "READINESS_CHANGE",
                    "track_id": track_id,
                    "detail": "Stagnation detected — consider strategy change.",
                })

            # Check crash threshold.
            crashing = self.performance_tracker.check_crash_threshold(track_id)
            if crashing:
                signals.append({
                    "signal_type": "PAUSE",
                    "track_id": track_id,
                    "detail": "Crash threshold exceeded.",
                    "evidence": "consecutive_crashes >= threshold",
                })

        return True, ModuleResult(
            primary={"triggers_checked": True, "track_id": track_id},
            lifecycle_signals=signals,
            warnings=warnings,
        )

    def propose(
        self,
        cycle_context: dict[str, Any],
    ) -> tuple[bool, Any]:
        """Full strategy proposal (cadence-controlled by Layer 5).

        Returns (True, ModuleResult) or (False, ModuleError).
        """
        from .intent_interpreter import ModuleResult, ModuleError

        try:
            track_id = cycle_context.get("domain_track", "")
            cycle = cycle_context.get("cycle_number", 0)
            economy = cycle_context.get("economy_mode", False)

            proposals: list[StrategyProposal] = []
            signals: list[dict[str, Any]] = []

            if economy:
                # In economy mode, skip OPPORTUNITY-type proposals.
                return True, ModuleResult(
                    primary={"proposals": [], "skipped": "economy_mode"},
                )

            # Analyze performance and generate proposals.
            if self.performance_tracker:
                health = self.performance_tracker.compute_health_score(track_id)
                overall = health.overall

                if overall < 0.3:
                    proposals.append(StrategyProposal(
                        proposal_id=f"strat_{track_id}_{cycle}_pause",
                        track_id=track_id,
                        proposal_type="pause",
                        description=f"Track health critically low ({overall:.2f}). Recommend pause.",
                        evidence=[f"health_score={overall:.2f}", f"data_gaps={health.data_gaps}"],
                        confidence=0.7,
                        is_safe=False,
                    ))
                    signals.append({
                        "signal_type": "PAUSE",
                        "track_id": track_id,
                        "detail": f"Health score {overall:.2f} below critical threshold.",
                    })

                elif overall < 0.5:
                    proposals.append(StrategyProposal(
                        proposal_id=f"strat_{track_id}_{cycle}_economy",
                        track_id=track_id,
                        proposal_type="economy",
                        description=f"Track health low ({overall:.2f}). Recommend per-track economy.",
                        evidence=[f"health_score={overall:.2f}"],
                        confidence=0.6,
                        is_safe=True,
                        params={"reduce_candidates": 1, "use_cheaper_model": True},
                    ))

            # Skill-based proposals.
            if self.skill_tracker:
                weakest = self.skill_tracker.get_weakest(3, track_id)
                if weakest:
                    weak_skills = [str(w) for w in weakest]
                    proposals.append(StrategyProposal(
                        proposal_id=f"strat_{track_id}_{cycle}_focus",
                        track_id=track_id,
                        proposal_type="adjust_weights",
                        description=f"Focus on weak skills: {', '.join(weak_skills[:3])}",
                        evidence=[f"weak_skills={weak_skills}"],
                        confidence=0.5,
                        is_safe=True,
                        params={"target_skills": weak_skills},
                    ))

            self._last_proposal_cycle = cycle

            return True, ModuleResult(
                primary={"proposals": [p for p in proposals]},
                proposals=[
                    {"type": p.proposal_type, "safe": p.is_safe, "detail": p.description}
                    for p in proposals
                ],
                lifecycle_signals=signals,
            )

        except Exception as exc:
            return False, ModuleError(
                error_type="RECOVERABLE",
                message=f"Strategy proposal failed: {exc}",
                is_retryable=False,
            )
