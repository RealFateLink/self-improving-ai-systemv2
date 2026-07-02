"""optimization_specialist.py — Builds optimization briefs on cadence.

Stage 9 (parallel).  Injects briefs through context assembly.
MUST avoid double-counting evidence already in semantic quality scoring.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Optional

__all__ = ["OptimizationSpecialist", "OptimizationBrief"]


@dataclass(frozen=True)
class OptimizationBrief:
    """A structured optimization brief for context injection."""
    brief_id: str
    track_id: str
    focus_areas: list[str]
    recommendations: list[str]
    evidence_sources: list[str]
    generated_at: float
    valid_until_cycle: int
    confidence: float

    @property
    def is_expired(self) -> bool:
        return False  # Expiry checked by caller via valid_until_cycle.


@dataclass
class OptimizationSpecialist:
    """Builds optimization briefs analyzing system performance trends.

    Runs on cadence (every 100 cycles, controlled by Layer 5).

    Dependencies:
      - performance_tracker (Layer 3): for metrics
      - llm_client (Layer 2): for brief generation
    """

    performance_tracker: Any = None
    llm_client: Any = None
    config: dict[str, Any] = field(default_factory=dict)

    _active_briefs: dict[str, OptimizationBrief] = field(default_factory=dict)

    def build_brief(
        self,
        track_id: str,
        cycle_context: dict[str, Any],
    ) -> tuple[bool, Any]:
        """Build an optimization brief for a track.

        Returns (True, ModuleResult) or (False, ModuleError).
        """
        from .intent_interpreter import ModuleResult, ModuleError

        try:
            cycle = cycle_context.get("cycle_number", 0)

            # Gather evidence (avoiding semantic scoring overlap).
            evidence = self._gather_evidence(track_id)
            focus_areas = self._identify_focus_areas(evidence)
            recommendations = self._generate_recommendations(focus_areas, evidence)

            brief = OptimizationBrief(
                brief_id=f"opt_{track_id}_{cycle}",
                track_id=track_id,
                focus_areas=focus_areas,
                recommendations=recommendations,
                evidence_sources=[e.get("source", "") for e in evidence],
                generated_at=time.time(),
                valid_until_cycle=cycle + 100,
                confidence=self._compute_confidence(evidence),
            )

            self._active_briefs[track_id] = brief
            return True, ModuleResult(primary=brief)

        except Exception as exc:
            return False, ModuleError(
                error_type="RECOVERABLE",
                message=f"Brief generation failed: {exc}",
                is_retryable=False,
            )

    def get_active_brief(self, track_id: str, current_cycle: int) -> OptimizationBrief | None:
        """Get the current active brief for a track, if not expired."""
        brief = self._active_briefs.get(track_id)
        if brief and brief.valid_until_cycle > current_cycle:
            return brief
        return None

    def _gather_evidence(self, track_id: str) -> list[dict[str, Any]]:
        """Gather performance evidence without overlapping semantic scoring."""
        evidence = []

        if self.performance_tracker:
            perf = self.performance_tracker.get_performance(track_id)
            if perf:
                evidence.append({
                    "source": "pass_rate_trend",
                    "data": perf.pass_rates[-50:] if perf.pass_rates else [],
                })
                evidence.append({
                    "source": "cost_trend",
                    "data": perf.costs[-50:] if perf.costs else [],
                })
                # Explicitly exclude semantic scores to avoid double-counting.
                evidence.append({
                    "source": "gate_progress",
                    "data": perf.gate_progress[-10:] if perf.gate_progress else [],
                })

        return evidence

    def _identify_focus_areas(self, evidence: list[dict[str, Any]]) -> list[str]:
        """Identify top optimization focus areas from evidence."""
        areas = []
        for e in evidence:
            data = e.get("data", [])
            if not data:
                continue
            source = e.get("source", "")

            if source == "pass_rate_trend" and data:
                recent_avg = sum(data[-10:]) / max(len(data[-10:]), 1)
                if recent_avg < 0.5:
                    areas.append("low_pass_rate")
                if len(data) >= 20:
                    early_avg = sum(data[:10]) / 10
                    if recent_avg < early_avg:
                        areas.append("declining_performance")

            if source == "cost_trend" and data:
                recent_cost = sum(data[-10:]) / max(len(data[-10:]), 1)
                if recent_cost > 50:
                    areas.append("high_cost")

        return areas if areas else ["general_improvement"]

    def _generate_recommendations(
        self,
        focus_areas: list[str],
        evidence: list[dict[str, Any]],
    ) -> list[str]:
        """Generate actionable recommendations."""
        recs: dict[str, str] = {
            "low_pass_rate": "Focus on fundamental skill gaps before attempting harder tasks.",
            "declining_performance": "Investigate recent strategy changes that may have regressed performance.",
            "high_cost": "Consider simpler approaches or reduce candidate count to lower cost.",
            "general_improvement": "Continue current approach; monitor for stagnation signals.",
        }

        recommendations = [recs.get(area, f"Address: {area}") for area in focus_areas]

        if self.llm_client and focus_areas:
            try:
                prompt = (
                    f"Given these optimization focus areas: {focus_areas}, "
                    f"suggest 2–3 specific actionable improvements."
                )
                response = self.llm_client.generate(prompt=prompt, max_tokens=200)
                text = getattr(response, "text", str(response))
                if text:
                    for line in text.strip().split("\n"):
                        if line.strip():
                            recommendations.append(line.strip())
            except Exception:
                pass

        return recommendations[:5]

    def _compute_confidence(self, evidence: list[dict[str, Any]]) -> float:
        """Confidence based on evidence quality."""
        if not evidence:
            return 0.2
        data_points = sum(len(e.get("data", [])) for e in evidence)
        return min(1.0, 0.3 + data_points * 0.01)
