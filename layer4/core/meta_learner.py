"""meta_learner.py — System-wide learning and self-modeling.

Stage 13.  Runs on cadence (every 100 cycles, controlled by L5).
Builds SelfModel using self_model_builder (Layer 3).
Proposes: track activations, improvements, graduation ceiling arguments.

Uses Layer 3 evidence for ceiling arguments; does NOT replace Layer 3 measurements.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Optional

__all__ = ["MetaLearner", "MetaLearnerResult"]


@dataclass(frozen=True)
class TrackActivationProposal:
    """Proposal to activate a new track."""
    track_id: str
    evidence: list[str]
    readiness_assessment: dict[str, Any]
    confidence: float


@dataclass(frozen=True)
class GraduationCeilingFlag:
    """Flag indicating a track may have hit a graduation ceiling."""
    track_id: str
    gate: str
    evidence: dict[str, Any]
    recommendation: str


@dataclass(frozen=True)
class MetaLearnerResult:
    """Aggregate result of meta-learner review."""
    self_model_summary: dict[str, Any]
    activation_proposals: list[TrackActivationProposal]
    improvement_proposals: list[dict[str, Any]]
    ceiling_flags: list[GraduationCeilingFlag]
    signals: list[dict[str, Any]]


@dataclass
class MetaLearner:
    """System-wide learning and self-reflection module.

    Runs on cadence (every 100 cycles, controlled by Layer 5).

    Dependencies:
      - self_model_builder (Layer 3): for SelfModel construction
      - graduation_monitor (Layer 3): for ceiling evidence
      - readiness_evaluator (Layer 3): for track readiness
      - performance_tracker (Layer 3): for health scores
      - skill_tracker (Layer 3): for weakness analysis
    """

    self_model_builder: Any = None
    graduation_monitor: Any = None
    readiness_evaluator: Any = None
    performance_tracker: Any = None
    skill_tracker: Any = None
    config: dict[str, Any] = field(default_factory=dict)

    _inactive_tracks: list[str] = field(default_factory=list)

    def review(
        self,
        cycle_context: dict[str, Any],
    ) -> tuple[bool, Any]:
        """Full meta-learner review.

        Returns (True, ModuleResult) or (False, ModuleError).
        """
        from .intent_interpreter import ModuleResult, ModuleError

        try:
            cycle = cycle_context.get("cycle_number", 0)
            signals: list[dict[str, Any]] = []

            # Build self-model.
            self_model = self._build_self_model(cycle)

            # Check inactive tracks for activation.
            activation_proposals = self._check_track_activations()

            # Check graduation ceilings.
            ceiling_flags = self._check_graduation_ceilings(cycle_context)

            # Generate improvement proposals.
            improvements = self._generate_improvements(self_model)

            # Emit lifecycle signals.
            for proposal in activation_proposals:
                signals.append({
                    "signal_type": "READINESS_CHANGE",
                    "track_id": proposal.track_id,
                    "detail": f"Track activation proposed: {proposal.track_id}",
                })

            for flag in ceiling_flags:
                signals.append({
                    "signal_type": "ALLOCATION_ADJUST",
                    "track_id": flag.track_id,
                    "detail": f"Graduation ceiling detected at gate {flag.gate}.",
                })

            result = MetaLearnerResult(
                self_model_summary=self_model,
                activation_proposals=activation_proposals,
                improvement_proposals=improvements,
                ceiling_flags=ceiling_flags,
                signals=signals,
            )

            return True, ModuleResult(
                primary=result,
                proposals=[
                    {"type": "track_activation", "track_id": p.track_id, "safe": False}
                    for p in activation_proposals
                ] + [
                    {"type": "graduation_ceiling", "track_id": f.track_id, "safe": False}
                    for f in ceiling_flags
                ],
                lifecycle_signals=signals,
            )

        except Exception as exc:
            return False, ModuleError(
                error_type="RECOVERABLE",
                message=f"Meta-learner review failed: {exc}",
                is_retryable=False,
            )

    def _build_self_model(self, cycle: int) -> dict[str, Any]:
        """Build SelfModel via Layer 3 self_model_builder."""
        if self.self_model_builder is None:
            return {"status": "no_builder", "cycle": cycle}

        try:
            # Build over recent window.
            cycle_range = (max(0, cycle - 500), cycle)
            model = self.self_model_builder.build(cycle_range, entity_id="MAIN")
            if hasattr(model, "__dict__"):
                return model.__dict__
            return {"raw": str(model)}
        except Exception as exc:
            return {"error": str(exc), "cycle": cycle}

    def _check_track_activations(self) -> list[TrackActivationProposal]:
        """Check if any inactive tracks are ready for activation."""
        proposals = []

        for track_id in self._inactive_tracks:
            if self.readiness_evaluator is None:
                continue

            try:
                assessment = self.readiness_evaluator.assess_readiness(track_id)
                if assessment.mode == "FULL":
                    evidence = [
                        f"readiness_mode={assessment.mode}",
                        f"constraints={assessment.recommended_constraints}",
                    ]
                    proposals.append(TrackActivationProposal(
                        track_id=track_id,
                        evidence=evidence,
                        readiness_assessment={
                            "mode": assessment.mode,
                            "constraints": assessment.recommended_constraints,
                        },
                        confidence=0.6,
                    ))
            except Exception:
                continue

        return proposals

    def _check_graduation_ceilings(
        self,
        cycle_context: dict[str, Any],
    ) -> list[GraduationCeilingFlag]:
        """Check for graduation ceilings using Layer 3 evidence."""
        flags = []

        if self.graduation_monitor is None or self.performance_tracker is None:
            return flags

        track_id = cycle_context.get("domain_track", "")
        if not track_id:
            return flags

        try:
            summary = self.graduation_monitor.get_graduation_summary(track_id)

            # Check if pace is very slow and improvement trend is near zero.
            if summary.pace > 2000 and abs(summary.streak_trend) < 0.001:
                # Assemble ceiling evidence from Layer 3.
                gate = self.config.get("current_gate", {}).get(track_id, "G1")
                evidence = self.graduation_monitor.assemble_ceiling_evidence(track_id, gate)

                flags.append(GraduationCeilingFlag(
                    track_id=track_id,
                    gate=gate,
                    evidence=evidence,
                    recommendation=(
                        f"Track {track_id} may have hit ceiling at gate {gate}. "
                        f"Pace={summary.pace:.0f} cycles/advancement, "
                        f"trend={summary.streak_trend:.4f}. "
                        f"Consider strategy change or human review."
                    ),
                ))
        except Exception:
            pass

        return flags

    def _generate_improvements(
        self,
        self_model: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Generate improvement proposals based on self-model."""
        improvements = []

        # Check for weak languages.
        if self.skill_tracker:
            try:
                weak_langs = self.skill_tracker.get_weakest_languages(3)
                if weak_langs:
                    improvements.append({
                        "type": "language_improvement",
                        "description": f"Weak languages: {[str(l) for l in weak_langs]}",
                        "safe": True,
                        "params": {"focus_languages": [str(l) for l in weak_langs]},
                    })
            except Exception:
                pass

        # General health-based improvements.
        if "error" not in self_model:
            improvements.append({
                "type": "model_refresh",
                "description": "Self-model updated successfully.",
                "safe": True,
            })

        return improvements

    def set_inactive_tracks(self, tracks: list[str]) -> None:
        """Update the list of tracks to check for activation."""
        self._inactive_tracks = list(tracks)
